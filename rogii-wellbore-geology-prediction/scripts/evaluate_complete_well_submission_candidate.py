"""Evaluate the first 0.08-ft-class candidate on the exact 7.474 proxy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


SPLITS = ("discovery", "holdout1", "holdout2", "holdout_combined", "all")


def rmse(target: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(target - prediction))))


def split_mask(frame: pd.DataFrame, split: str) -> np.ndarray:
    if split == "holdout_combined":
        return frame["validation_split"].isin(["holdout1", "holdout2"]).to_numpy()
    if split == "all":
        return np.ones(len(frame), dtype=bool)
    return frame["validation_split"].eq(split).to_numpy()


def bootstrap(
    frame: pd.DataFrame,
    baseline: np.ndarray,
    candidate: np.ndarray,
    mask: np.ndarray,
    seed: int,
    draws: int,
) -> dict[str, float | int]:
    subset = frame.loc[mask, ["well", "target_tvt"]].copy()
    target = subset["target_tvt"].to_numpy(float)
    subset["baseline_se"] = np.square(target - baseline[mask])
    subset["candidate_se"] = np.square(target - candidate[mask])
    by_well = subset.groupby("well", sort=False).agg(
        rows=("well", "size"),
        baseline_sse=("baseline_se", "sum"),
        candidate_sse=("candidate_se", "sum"),
    )
    rng = np.random.default_rng(seed)
    rows = by_well["rows"].to_numpy(float)
    baseline_sse = by_well["baseline_sse"].to_numpy(float)
    candidate_sse = by_well["candidate_sse"].to_numpy(float)
    values = np.empty(draws, float)
    for draw in range(draws):
        sampled = rng.integers(0, len(by_well), len(by_well))
        count = rows[sampled].sum()
        values[draw] = np.sqrt(baseline_sse[sampled].sum() / count) - np.sqrt(
            candidate_sse[sampled].sum() / count
        )
    return {
        "wells": int(len(by_well)),
        "well_wins": int(
            np.sum(
                candidate_sse / rows
                < baseline_sse / rows
            )
        ),
        "draws": int(draws),
        "probability_positive": float(np.mean(values > 0.0)),
        "p01": float(np.quantile(values, 0.01)),
        "p05": float(np.quantile(values, 0.05)),
        "p50": float(np.quantile(values, 0.50)),
        "p95": float(np.quantile(values, 0.95)),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    curve = pd.read_parquet(args.curve_cache).sort_values(
        ["well", "row_idx"]
    ).reset_index(drop=True)
    matcher = pd.read_parquet(
        args.matcher_cache,
        columns=["id", "matcher_direct_correction"],
    )
    frame = curve.merge(matcher, on="id", validate="one_to_one")

    oof_ids = pd.read_csv(args.oof_ids, usecols=["_oof_id"])
    raw_public = np.asarray(np.load(args.raw_public_oof, mmap_mode="r"), float)
    smooth_public = np.asarray(
        np.load(args.smooth_public_oof, mmap_mode="r"), float
    )
    if not (
        len(oof_ids) == len(raw_public) == len(smooth_public)
        and np.isfinite(raw_public).all()
        and np.isfinite(smooth_public).all()
    ):
        raise RuntimeError("public learned arrays do not share one finite ID contract")
    position_map = dict(
        zip(oof_ids["_oof_id"].astype(str), np.arange(len(oof_ids)))
    )
    positions = frame["id"].astype(str).map(position_map)
    if positions.isna().any():
        raise RuntimeError("fixed 200-well cache is not covered by public OOF IDs")
    positions = positions.to_numpy(int)

    last_known = frame["last_known_tvt"].to_numpy(float)
    public_absolute = last_known + raw_public[positions]
    hedge_shift = (
        frame["public_s060_cap200_artifact"].to_numpy(float)
        - frame["base_artifact"].to_numpy(float)
    )
    exact_incumbent = (
        args.sp45_weight
        * frame["sp45_sgridge_d2_b050"].to_numpy(float)
        + (1.0 - args.sp45_weight) * public_absolute
        + hedge_shift
    )
    smoother_correction = (
        (1.0 - args.sp45_weight)
        * (smooth_public[positions] - raw_public[positions])
    )
    matcher_correction = frame["matcher_direct_correction"].to_numpy(float)
    curve_correction = frame["complete_well_curve_correction"].to_numpy(float)
    total_correction = (
        args.matcher_weight * matcher_correction
        + args.curve_weight * curve_correction
        + args.smoother_weight * smoother_correction
        + args.global_shift
    )
    candidate = exact_incumbent + total_correction
    target = frame["target_tvt"].to_numpy(float)

    frame["exact_7474_proxy"] = exact_incumbent
    frame["candidate_tvt"] = candidate
    frame["candidate_total_correction"] = total_correction
    frame["candidate_matcher_correction"] = (
        args.matcher_weight * matcher_correction
    )
    frame["candidate_curve_correction"] = args.curve_weight * curve_correction
    frame["candidate_smoother_correction"] = (
        args.smoother_weight * smoother_correction
    )
    frame["candidate_global_shift"] = args.global_shift

    summary: dict[str, object] = {
        "method": "exact_7474_complete_well_submission_candidate",
        "weights": {
            "sp45": float(args.sp45_weight),
            "bounded_matcher": float(args.matcher_weight),
            "whole_well_curve": float(args.curve_weight),
            "public_learned_sg601": float(args.smoother_weight),
            "global_shift_ft": float(args.global_shift),
        },
        "contracts": {
            "fixed_validation_wells_excluded_from_curve_model_fit": True,
            "curve_model_train_wells": 573,
            "fixed_validation_wells": 200,
            "same_well_contact_used": False,
            "formation_surfaces_used": False,
            "suffix_tvt_used_as_features": False,
            "full_hidden_gr_lookahead_used": True,
            "global_shift_selected_on_discovery_only": True,
        },
        "splits": {},
    }
    for split_index, split in enumerate(SPLITS):
        mask = split_mask(frame, split)
        baseline_score = rmse(target[mask], exact_incumbent[mask])
        candidate_score = rmse(target[mask], candidate[mask])
        summary["splits"][split] = {
            "rows": int(mask.sum()),
            "wells": int(frame.loc[mask, "well"].nunique()),
            "baseline_rmse": baseline_score,
            "candidate_rmse": candidate_score,
            "improvement": baseline_score - candidate_score,
            "bootstrap": bootstrap(
                frame,
                exact_incumbent,
                candidate,
                mask,
                args.seed + split_index,
                args.bootstrap_draws,
            ),
        }
    holdout = summary["splits"]["holdout_combined"]
    holdout1 = summary["splits"]["holdout1"]
    holdout2 = summary["splits"]["holdout2"]
    improvement = float(holdout["improvement"])
    summary["promotion"] = {
        "both_holdouts_improve": bool(
            holdout1["improvement"] > 0.0 and holdout2["improvement"] > 0.0
        ),
        "holdout_improvement": improvement,
        "strict_effect_gate_ft": float(args.strict_effect_gate),
        "passes_strict_effect_gate": bool(
            improvement >= args.strict_effect_gate
        ),
        "near_effect_gate_tolerance_ft": float(args.near_gate_tolerance),
        "is_008_class_candidate": bool(
            improvement
            >= args.strict_effect_gate - args.near_gate_tolerance
        ),
        "bootstrap_probability_positive": float(
            holdout["bootstrap"]["probability_positive"]
        ),
        "bootstrap_p05_positive": bool(holdout["bootstrap"]["p05"] > 0.0),
        "recommendation": (
            "build_hidden-dynamic Kaggle notebook; one controlled submission"
            if (
                holdout1["improvement"] > 0.0
                and holdout2["improvement"] > 0.0
                and improvement
                >= args.strict_effect_gate - args.near_gate_tolerance
            )
            else "continue local experiments"
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.output, index=False)
    args.summary.write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--curve-cache", type=Path, required=True)
    parser.add_argument("--matcher-cache", type=Path, required=True)
    parser.add_argument("--oof-ids", type=Path, required=True)
    parser.add_argument("--raw-public-oof", type=Path, required=True)
    parser.add_argument("--smooth-public-oof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--sp45-weight", type=float, default=0.60)
    parser.add_argument("--matcher-weight", type=float, default=1.00)
    parser.add_argument("--curve-weight", type=float, default=1.20)
    parser.add_argument("--smoother-weight", type=float, default=1.00)
    parser.add_argument("--global-shift", type=float, default=0.20)
    parser.add_argument("--strict-effect-gate", type=float, default=0.08)
    parser.add_argument("--near-gate-tolerance", type=float, default=0.005)
    parser.add_argument("--bootstrap-draws", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=20260730)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
