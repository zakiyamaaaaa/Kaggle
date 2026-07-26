"""Select an additional artifact smoother using only outer-train wells."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from sklearn.model_selection import GroupKFold


def smooth_by_well(
    values: np.ndarray,
    groups: np.ndarray,
    row_index: np.ndarray,
    window: int,
    poly: int,
) -> np.ndarray:
    if window <= 0:
        return values.copy()
    output = values.copy()
    order = np.argsort(groups, kind="stable")
    ordered_groups = groups[order]
    boundaries = np.r_[0, np.flatnonzero(ordered_groups[1:] != ordered_groups[:-1]) + 1, len(order)]
    for start, stop in zip(boundaries[:-1], boundaries[1:]):
        positions = order[start:stop]
        positions = positions[np.argsort(row_index[positions], kind="stable")]
        local_window = min(int(window), len(positions))
        if local_window % 2 == 0:
            local_window -= 1
        if local_window >= poly + 2:
            output[positions] = savgol_filter(values[positions], local_window, poly)
    return output


def metrics(target: np.ndarray, prediction: np.ndarray, groups: np.ndarray) -> dict[str, float]:
    error = prediction - target
    counts = np.bincount(groups)
    sums = np.bincount(groups, weights=error * error)
    by_well = np.sqrt(sums[counts > 0] / counts[counts > 0])
    return {
        "rmse": float(np.sqrt(np.mean(error * error))),
        "well_rmse_p50": float(np.quantile(by_well, 0.50)),
        "well_rmse_p90": float(np.quantile(by_well, 0.90)),
    }


def parse_grid(value: str, cast=int) -> list:
    return [cast(item.strip()) for item in value.split(",") if item.strip()]


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    oof_root = args.package_root / "oof"
    train_gt = pd.read_parquet(
        oof_root / "train_gt.parquet",
        columns=["well_id", "row_index", "target_delta_from_last_known"],
    )
    target = train_gt["target_delta_from_last_known"].to_numpy(np.float32)
    artifact = np.load(oof_root / "blend_oof_postprocessed.npy").reshape(-1).astype(np.float32)
    groups, well_names = pd.factorize(train_gt["well_id"].astype(str), sort=False)
    groups = groups.astype(np.int32, copy=False)
    row_index = train_gt["row_index"].to_numpy(np.int32)
    windows = parse_grid(args.window_grid, int)
    degrees = parse_grid(args.poly_grid, int)
    candidate_predictions: dict[tuple[int, int], np.ndarray] = {(0, 0): artifact.copy()}
    for window in windows:
        if window <= 0:
            continue
        for poly in degrees:
            candidate_predictions[(window, poly)] = smooth_by_well(
                artifact, groups, row_index, window, poly
            ).astype(np.float32, copy=False)

    global_ranking = []
    fitted_global_ranking = []
    for (window, poly), prediction in candidate_predictions.items():
        global_ranking.append(
            {
                "window": window,
                "poly": poly,
                "rmse": float(np.sqrt(np.mean((prediction - target) ** 2))),
            }
        )
        denominator = float(np.dot(prediction, prediction))
        alpha = (
            float(np.dot(prediction, target) / denominator)
            if denominator > 1e-12
            else 1.0
        )
        alpha = float(np.clip(alpha, args.alpha_min, args.alpha_max))
        fitted_global_ranking.append(
            {
                "window": window,
                "poly": poly,
                "alpha": alpha,
                "rmse": float(np.sqrt(np.mean((alpha * prediction - target) ** 2))),
            }
        )
    global_ranking.sort(key=lambda row: row["rmse"])
    fitted_global_ranking.sort(key=lambda row: row["rmse"])

    oof = np.full(len(target), np.nan, dtype=np.float32)
    fold_records: list[dict[str, object]] = []
    outer = GroupKFold(n_splits=args.folds)
    for fold, (train_idx, valid_idx) in enumerate(
        outer.split(artifact, target, groups=groups), 1
    ):
        best = None
        for (window, poly), prediction in candidate_predictions.items():
            denominator = float(np.dot(prediction[train_idx], prediction[train_idx]))
            alpha = (
                float(np.dot(prediction[train_idx], target[train_idx]) / denominator)
                if denominator > 1e-12
                else 1.0
            )
            alpha = float(np.clip(alpha, args.alpha_min, args.alpha_max))
            error = alpha * prediction[train_idx] - target[train_idx]
            score = float(np.sqrt(np.mean(error * error)))
            if best is None or score < best["train_rmse"]:
                best = {
                    "window": int(window),
                    "poly": int(poly),
                    "alpha": alpha,
                    "train_rmse": score,
                }
        assert best is not None
        selected = candidate_predictions[(best["window"], best["poly"])]
        oof[valid_idx] = best["alpha"] * selected[valid_idx]
        best["fold"] = fold
        best["valid_rmse"] = float(
            np.sqrt(np.mean((oof[valid_idx] - target[valid_idx]) ** 2))
        )
        fold_records.append(best)
        print(json.dumps(best), flush=True)

    valid = np.isfinite(oof)
    summary = {
        "method": "artifact_outer_train_selected_savgol",
        "rows": int(valid.sum()),
        "wells": int(len(well_names)),
        "artifact": metrics(target[valid], artifact[valid], groups[valid]),
        "nested_smoothing": metrics(target[valid], oof[valid], groups[valid]),
        "folds": fold_records,
        "global_diagnostic_top10": global_ranking[:10],
        "full_oof_fit_recommendation": fitted_global_ranking[0],
        "full_oof_fitted_top10": fitted_global_ranking[:10],
        "window_grid": windows,
        "poly_grid": degrees,
        "alpha_bounds": [args.alpha_min, args.alpha_max],
        "elapsed_sec": float(time.perf_counter() - started),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, oof)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--window-grid", default="0,61,101,151,301,401,501,601,801")
    parser.add_argument("--poly-grid", default="1,2,3")
    parser.add_argument("--alpha-min", type=float, default=0.97)
    parser.add_argument("--alpha-max", type=float, default=1.03)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
