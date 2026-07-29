#!/usr/bin/env python3
"""Tune one SP45 ridge weight while preserving the 7.474 final pipeline.

The incumbent is reconstructed from the cached d2/b0.50 SP45 branch, the
60/40 learned-proxy blend, and the public PF seed-branch hedge.  Candidate
weights change only the ridge/selector mixture before the unchanged
projection, learned blend, and hedge.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from generic_core_sp45_local import project_sp45


PROXIES = {
    "artifact": "artifact_tvt",
    "hgb": "hgb_oof_tvt",
    "ridge": "ridge_pp_savgol17",
}
SPLITS = ("discovery", "holdout1", "holdout2", "holdout_combined", "all")


def parse_grid(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def pooled_rmse(target: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.sqrt(np.mean((prediction - target) ** 2)))


def build_projection(
    frame: pd.DataFrame,
    data_root: Path,
    ridge_weight: float,
    degree: int,
    blend: float,
) -> np.ndarray:
    raw = (
        ridge_weight * frame["ridge_pp_savgol17"].to_numpy(float)
        + (1.0 - ridge_weight) * frame["selector_raw"].to_numpy(float)
    )
    output = np.full(len(frame), np.nan, dtype=float)
    for well, part in frame.groupby("well", sort=True):
        horizontal = pd.read_csv(
            data_root / "train" / f"{well}__horizontal_well.csv"
        )
        positions = part.index.to_numpy(int)
        output[positions] = project_sp45(
            horizontal,
            part["row_idx"].to_numpy(int),
            raw[positions],
            degree,
            blend,
        )
    if not np.isfinite(output).all():
        raise RuntimeError(f"non-finite projection for ridge weight {ridge_weight}")
    return output


def split_mask(frame: pd.DataFrame, split: str) -> np.ndarray:
    if split == "holdout_combined":
        return frame["validation_split"].isin(["holdout1", "holdout2"]).to_numpy()
    if split == "all":
        return np.ones(len(frame), dtype=bool)
    return frame["validation_split"].eq(split).to_numpy()


def paired_bootstrap(
    frame: pd.DataFrame,
    mask: np.ndarray,
    target: np.ndarray,
    incumbent: np.ndarray,
    challenger: np.ndarray,
    samples: int,
    seed: int,
) -> dict[str, float | int]:
    local = pd.DataFrame(
        {
            "well": frame.loc[mask, "well"].astype(str).to_numpy(),
            "incumbent_se": (incumbent[mask] - target[mask]) ** 2,
            "challenger_se": (challenger[mask] - target[mask]) ** 2,
        }
    )
    by_well = local.groupby("well", sort=True).agg(
        rows=("well", "size"),
        incumbent_sse=("incumbent_se", "sum"),
        challenger_sse=("challenger_se", "sum"),
    )
    rows = by_well["rows"].to_numpy(float)
    incumbent_sse = by_well["incumbent_sse"].to_numpy(float)
    challenger_sse = by_well["challenger_sse"].to_numpy(float)
    rng = np.random.default_rng(seed)
    improvements = np.empty(samples, dtype=float)
    for index in range(samples):
        chosen = rng.integers(0, len(by_well), len(by_well))
        denominator = rows[chosen].sum()
        improvements[index] = (
            np.sqrt(incumbent_sse[chosen].sum() / denominator)
            - np.sqrt(challenger_sse[chosen].sum() / denominator)
        )
    incumbent_well = np.sqrt(incumbent_sse / rows)
    challenger_well = np.sqrt(challenger_sse / rows)
    return {
        "wells": int(len(by_well)),
        "well_wins": int(np.sum(challenger_well < incumbent_well)),
        "samples": int(samples),
        "improvement_probability": float(np.mean(improvements > 0.0)),
        "improvement_p05": float(np.quantile(improvements, 0.05)),
        "improvement_p50": float(np.quantile(improvements, 0.50)),
        "improvement_p95": float(np.quantile(improvements, 0.95)),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    frame = pd.read_parquet(args.input).reset_index(drop=True)
    required = {
        "well",
        "row_idx",
        "validation_split",
        "target_tvt",
        "selector_raw",
        "ridge_pp_savgol17",
        "sp45_sgridge_d2_b050",
        "base_artifact",
        "base_hgb",
        "base_ridge",
        "public_s060_cap200_artifact",
        "public_s060_cap200_hgb",
        "public_s060_cap200_ridge",
        *PROXIES.values(),
    }
    if not required.issubset(frame.columns):
        raise RuntimeError(f"input missing columns: {sorted(required - set(frame))}")

    frame["well"] = frame["well"].astype(str)
    target = frame["target_tvt"].to_numpy(float)
    hedge_shifts = {
        name: (
            frame[f"public_s060_cap200_{name}"].to_numpy(float)
            - frame[f"base_{name}"].to_numpy(float)
        )
        for name in PROXIES
    }
    hedge_shift = hedge_shifts["artifact"]
    for name, values in hedge_shifts.items():
        maximum_difference = float(np.max(np.abs(values - hedge_shift)))
        if maximum_difference > 1e-9:
            raise RuntimeError(
                f"public hedge differs by proxy {name}: {maximum_difference}"
            )

    grid = parse_grid(args.ridge_weight_grid)
    if args.incumbent_ridge_weight not in grid:
        raise RuntimeError("incumbent ridge weight must be present in the grid")
    projections: dict[float, np.ndarray] = {}
    for position, weight in enumerate(grid, 1):
        if np.isclose(weight, args.incumbent_ridge_weight):
            projections[weight] = frame["sp45_sgridge_d2_b050"].to_numpy(float)
        else:
            projections[weight] = build_projection(
                frame,
                args.data_root,
                weight,
                args.projection_degree,
                args.projection_blend,
            )
        print(f"projection {position}/{len(grid)} ridge_weight={weight:.3f}", flush=True)

    predictions: dict[float, dict[str, np.ndarray]] = {}
    for weight, sp45 in projections.items():
        predictions[weight] = {
            name: (
                args.sp45_weight * sp45
                + (1.0 - args.sp45_weight) * frame[column].to_numpy(float)
                + hedge_shift
            )
            for name, column in PROXIES.items()
        }

    split_results: dict[str, object] = {}
    for split in SPLITS:
        mask = split_mask(frame, split)
        records = []
        for weight in grid:
            rmses = {
                name: pooled_rmse(target[mask], values[mask])
                for name, values in predictions[weight].items()
            }
            records.append(
                {
                    "ridge_weight": float(weight),
                    "proxy_rmse": rmses,
                    "mean_proxy_rmse": float(np.mean(list(rmses.values()))),
                    "worst_proxy_rmse": float(np.max(list(rmses.values()))),
                }
            )
        split_results[split] = {
            "rows": int(mask.sum()),
            "wells": int(frame.loc[mask, "well"].nunique()),
            "records": records,
        }

    discovery_records = split_results["discovery"]["records"]
    incumbent_discovery = next(
        record
        for record in discovery_records
        if np.isclose(record["ridge_weight"], args.incumbent_ridge_weight)
    )
    for record in discovery_records:
        improvements = {
            name: (
                incumbent_discovery["proxy_rmse"][name]
                - record["proxy_rmse"][name]
            )
            for name in PROXIES
        }
        record["improvements_vs_incumbent"] = improvements
        record["minimum_improvement"] = float(min(improvements.values()))
        record["mean_improvement"] = float(np.mean(list(improvements.values())))
    selected_record = max(
        discovery_records,
        key=lambda record: (
            record["minimum_improvement"],
            record["mean_improvement"],
            -abs(record["ridge_weight"] - args.incumbent_ridge_weight),
        ),
    )
    selected_weight = float(selected_record["ridge_weight"])

    validation: dict[str, object] = {}
    incumbent_predictions = predictions[args.incumbent_ridge_weight]
    selected_predictions = predictions[selected_weight]
    for split_index, split in enumerate(("holdout1", "holdout2", "holdout_combined")):
        mask = split_mask(frame, split)
        proxy_records = {}
        for proxy_index, name in enumerate(PROXIES):
            incumbent_rmse = pooled_rmse(
                target[mask], incumbent_predictions[name][mask]
            )
            selected_rmse = pooled_rmse(
                target[mask], selected_predictions[name][mask]
            )
            proxy_records[name] = {
                "incumbent_rmse": incumbent_rmse,
                "selected_rmse": selected_rmse,
                "improvement": incumbent_rmse - selected_rmse,
                "paired_bootstrap": paired_bootstrap(
                    frame,
                    mask,
                    target,
                    incumbent_predictions[name],
                    selected_predictions[name],
                    args.bootstrap_samples,
                    args.seed + split_index * 10 + proxy_index,
                ),
            }
        validation[split] = proxy_records

    holdout_records = [
        record
        for split in ("holdout1", "holdout2")
        for record in validation[split].values()
    ]
    combined_records = list(validation["holdout_combined"].values())
    promotion_gate = {
        "selected_differs_from_incumbent": not np.isclose(
            selected_weight, args.incumbent_ridge_weight
        ),
        "discovery_all_proxies_improve": (
            selected_record["minimum_improvement"] > 0.0
        ),
        "each_holdout_all_proxies_improve": all(
            record["improvement"] > 0.0 for record in holdout_records
        ),
        "combined_all_proxies_bootstrap_p05_positive": all(
            record["paired_bootstrap"]["improvement_p05"] > 0.0
            for record in combined_records
        ),
    }
    promotion_gate["passed"] = all(promotion_gate.values())
    result = {
        "method": "exact_incumbent_one_change_sp45_ridge_weight",
        "input": str(args.input),
        "rows": int(len(frame)),
        "wells": int(frame["well"].nunique()),
        "incumbent": {
            "kaggle_score": 7.474,
            "ridge_weight": float(args.incumbent_ridge_weight),
            "projection_degree": int(args.projection_degree),
            "projection_blend": float(args.projection_blend),
            "sp45_weight": float(args.sp45_weight),
            "pf_seed_branch_hedge": "public_s060_cap200",
        },
        "ridge_weight_grid": grid,
        "selection": {
            "source": "discovery only",
            "objective": "maximize minimum improvement across three legal OOF proxies",
            "selected_ridge_weight": selected_weight,
            "selected_discovery_record": selected_record,
        },
        "validation": validation,
        "promotion_gate": promotion_gate,
        "suffix_target_used_for_prediction": False,
        "same_well_contact_used": False,
        "elapsed_sec": float(time.perf_counter() - started),
        "split_results": split_results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--ridge-weight-grid",
        default="0.20,0.25,0.30,0.35,0.40,0.45,0.50,0.55,0.60",
    )
    parser.add_argument("--incumbent-ridge-weight", type=float, default=0.30)
    parser.add_argument("--projection-degree", type=int, default=2)
    parser.add_argument("--projection-blend", type=float, default=0.50)
    parser.add_argument("--sp45-weight", type=float, default=0.60)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260730)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
