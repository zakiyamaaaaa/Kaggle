#!/usr/bin/env python3
"""Evaluate nested artifact smoothing inside the exact 7.474 proxy pipeline."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from generic_core_exact_incumbent_ridge_weight import (
    paired_bootstrap,
    pooled_rmse,
    split_mask,
)


SPLITS = ("discovery", "holdout1", "holdout2", "holdout_combined", "all")


def last_known_by_well(data_root: Path, wells: pd.Series) -> dict[str, float]:
    output: dict[str, float] = {}
    for well in pd.unique(wells.astype(str)):
        horizontal = pd.read_csv(
            data_root / "train" / f"{well}__horizontal_well.csv",
            usecols=["TVT_input"],
        )
        known = pd.to_numeric(horizontal["TVT_input"], errors="coerce").dropna()
        if known.empty:
            raise RuntimeError(f"well has no visible TVT_input rows: {well}")
        output[str(well)] = float(known.iloc[-1])
    return output


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    frame = pd.read_parquet(args.incumbent_cache).reset_index(drop=True)
    required = {
        "id",
        "well",
        "target_tvt",
        "validation_split",
        "sp45_sgridge_d2_b050",
        "artifact_tvt",
        "base_artifact",
        "public_s060_cap200_artifact",
    }
    if not required.issubset(frame.columns):
        raise RuntimeError(f"incumbent cache missing: {sorted(required - set(frame))}")
    frame["id"] = frame["id"].astype(str)
    frame["well"] = frame["well"].astype(str)

    oof_ids = pd.read_csv(
        args.oof_ids,
        usecols=["_oof_id", "_oof_well"],
        dtype={"_oof_id": str, "_oof_well": str},
    )
    candidate_delta = np.asarray(
        np.load(args.candidate_delta_oof, mmap_mode="r"), dtype=float
    )
    if len(oof_ids) != len(candidate_delta) or not np.isfinite(candidate_delta).all():
        raise RuntimeError("candidate OOF rows do not align with OOF ID file")
    last_known = last_known_by_well(args.data_root, oof_ids["_oof_well"])
    candidate_absolute = (
        oof_ids["_oof_well"].map(last_known).to_numpy(float) + candidate_delta
    )
    candidate = pd.DataFrame(
        {
            "id": oof_ids["_oof_id"],
            "candidate_artifact_tvt": candidate_absolute,
        }
    )
    if args.incumbent_delta_oof is not None:
        incumbent_delta = np.asarray(
            np.load(args.incumbent_delta_oof, mmap_mode="r"), dtype=float
        )
        if (
            len(incumbent_delta) != len(oof_ids)
            or not np.isfinite(incumbent_delta).all()
        ):
            raise RuntimeError("incumbent OOF rows do not align with OOF ID file")
        candidate["incumbent_learned_tvt"] = (
            oof_ids["_oof_well"].map(last_known).to_numpy(float)
            + incumbent_delta
        )
    frame = frame.merge(candidate, on="id", how="left", validate="one_to_one")
    if frame["candidate_artifact_tvt"].isna().any():
        raise RuntimeError("candidate artifact OOF does not cover incumbent cache")

    target = frame["target_tvt"].to_numpy(float)
    sp45 = frame["sp45_sgridge_d2_b050"].to_numpy(float)
    hedge_shift = (
        frame["public_s060_cap200_artifact"].to_numpy(float)
        - frame["base_artifact"].to_numpy(float)
    )
    incumbent_learned = (
        frame["artifact_tvt"].to_numpy(float)
        if args.incumbent_delta_oof is None
        else frame["incumbent_learned_tvt"].to_numpy(float)
    )
    incumbent = (
        args.sp45_weight * sp45
        + (1.0 - args.sp45_weight) * incumbent_learned
        + hedge_shift
    )
    challenger = (
        args.sp45_weight * sp45
        + (1.0 - args.sp45_weight)
        * frame["candidate_artifact_tvt"].to_numpy(float)
        + hedge_shift
    )

    splits: dict[str, object] = {}
    for split_index, split in enumerate(SPLITS):
        mask = split_mask(frame, split)
        incumbent_rmse = pooled_rmse(target[mask], incumbent[mask])
        challenger_rmse = pooled_rmse(target[mask], challenger[mask])
        splits[split] = {
            "rows": int(mask.sum()),
            "wells": int(frame.loc[mask, "well"].nunique()),
            "incumbent_rmse": incumbent_rmse,
            "challenger_rmse": challenger_rmse,
            "improvement": incumbent_rmse - challenger_rmse,
            "paired_bootstrap": paired_bootstrap(
                frame,
                mask,
                target,
                incumbent,
                challenger,
                args.bootstrap_samples,
                args.seed + split_index,
            ),
        }

    artifact_summary = json.loads(
        args.artifact_summary.read_text(encoding="utf-8")
    )
    raw_metrics = artifact_summary.get("artifact", artifact_summary.get("raw"))
    if raw_metrics is None:
        raise RuntimeError("smoothing summary has no raw/artifact metrics")
    fit_all_recommendation = artifact_summary.get(
        "full_oof_fit_recommendation",
        artifact_summary.get("fit_all_recommendation"),
    )
    if fit_all_recommendation is None:
        raise RuntimeError("smoothing summary has no fit-all recommendation")
    holdout_signs = [
        splits[name]["improvement"] > 0.0
        for name in ("holdout1", "holdout2")
    ]
    promotion_gate = {
        "nested_oof_improves_all_773_wells": (
            artifact_summary["nested_smoothing"]["rmse"]
            < raw_metrics["rmse"]
        ),
        "discovery_improves": splits["discovery"]["improvement"] > 0.0,
        "each_holdout_improves": all(holdout_signs),
        "combined_holdout_bootstrap_p05_positive": (
            splits["holdout_combined"]["paired_bootstrap"]["improvement_p05"]
            > 0.0
        ),
    }
    promotion_gate["passed"] = all(promotion_gate.values())
    result = {
        "method": "exact_incumbent_learned_nested_smoothing",
        "incumbent": {
            "kaggle_score": 7.474,
            "sp45_ridge_weight": 0.30,
            "projection_degree": 2,
            "projection_blend": 0.50,
            "sp45_weight": float(args.sp45_weight),
            "pf_seed_branch_hedge": "public_s060_cap200",
            "learned_proxy": args.proxy_name,
        },
        "one_change": (
            f"replace raw {args.proxy_name} delta with leakage-safe "
            "outer-train-selected Savgol OOF delta"
        ),
        "artifact_all_well_oof": {
            "raw_rmse": raw_metrics["rmse"],
            "nested_smoothing_rmse": artifact_summary["nested_smoothing"]["rmse"],
            "improvement": (
                raw_metrics["rmse"]
                - artifact_summary["nested_smoothing"]["rmse"]
            ),
            "fit_all_recommendation": fit_all_recommendation,
        },
        "splits": splits,
        "promotion_gate": promotion_gate,
        "leakage_controls": {
            "artifact_candidate_is_outer_group_oof": True,
            "suffix_target_used_only_for_evaluation": True,
            "same_well_contact_used": False,
            "public_well_ids_used": False,
            "incumbent_projection_blend_and_hedge_unchanged": True,
        },
        "elapsed_sec": float(time.perf_counter() - started),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--incumbent-cache", type=Path, required=True)
    parser.add_argument("--oof-ids", type=Path, required=True)
    parser.add_argument("--candidate-delta-oof", type=Path, required=True)
    parser.add_argument("--incumbent-delta-oof", type=Path)
    parser.add_argument("--proxy-name", default="model_package_artifact_oof")
    parser.add_argument("--artifact-summary", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--sp45-weight", type=float, default=0.60)
    parser.add_argument("--bootstrap-samples", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
