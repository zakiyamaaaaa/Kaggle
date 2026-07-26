"""Coordinated nested evaluation of artifact smoothing and well-bias correction."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from artifact_nested_smoothing import smooth_by_well
from artifact_well_bias_correction import build_prefix_features


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


def aggregate_well(values: np.ndarray, groups: np.ndarray, n_wells: int) -> dict[str, np.ndarray]:
    counts = np.bincount(groups, minlength=n_wells).astype(float)
    sums = np.bincount(groups, weights=values, minlength=n_wells)
    square_sums = np.bincount(groups, weights=values * values, minlength=n_wells)
    mean = sums / counts
    variance = np.maximum(square_sums / counts - mean * mean, 0.0)
    minimum = np.full(n_wells, np.inf, dtype=float)
    maximum = np.full(n_wells, -np.inf, dtype=float)
    np.minimum.at(minimum, groups, values)
    np.maximum.at(maximum, groups, values)
    first_position = np.full(n_wells, len(values), dtype=int)
    last_position = np.full(n_wells, -1, dtype=int)
    positions = np.arange(len(values))
    np.minimum.at(first_position, groups, positions)
    np.maximum.at(last_position, groups, positions)
    return {
        "mean": mean,
        "std": np.sqrt(variance),
        "first": values[first_position],
        "last": values[last_position],
        "min": minimum,
        "max": maximum,
    }


def make_ridge(alpha: float):
    return make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        Ridge(alpha=alpha),
    )


def parse_grid(value: str, cast=int) -> list:
    return [cast(item.strip()) for item in value.split(",") if item.strip()]


def select_bias_gate(
    X: np.ndarray,
    labels: np.ndarray,
    well_indices: np.ndarray,
    row_counts: np.ndarray,
    scale_grid: np.ndarray,
    threshold_grid: np.ndarray,
    folds: int,
    ridge_alpha: float,
) -> tuple[float, float, float]:
    gate_sse = np.zeros((len(scale_grid), len(threshold_grid)), dtype=float)
    gate_rows = np.zeros((len(scale_grid), len(threshold_grid)), dtype=float)
    inner = GroupKFold(n_splits=folds)
    for train_rel, valid_rel in inner.split(
        well_indices, labels[well_indices], groups=well_indices
    ):
        train_wells = well_indices[train_rel]
        valid_wells = well_indices[valid_rel]
        model = make_ridge(ridge_alpha)
        model.fit(X[train_wells], labels[train_wells])
        predicted_bias = model.predict(X[valid_wells])
        for scale_position, scale in enumerate(scale_grid):
            for threshold_position, threshold in enumerate(threshold_grid):
                gated_bias = predicted_bias * (np.abs(predicted_bias) >= threshold)
                gate_sse[scale_position, threshold_position] += float(
                    np.sum(
                        row_counts[valid_wells]
                        * (labels[valid_wells] - scale * gated_bias) ** 2
                    )
                )
                gate_rows[scale_position, threshold_position] += float(
                    np.sum(row_counts[valid_wells])
                )
    scores = gate_sse / np.maximum(gate_rows, 1.0)
    best = np.unravel_index(int(np.argmin(scores)), scores.shape)
    return (
        float(scale_grid[best[0]]),
        float(threshold_grid[best[1]]),
        float(np.sqrt(scores[best])),
    )


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    oof_root = args.package_root / "oof"
    gt = pd.read_parquet(
        oof_root / "train_gt.parquet",
        columns=[
            "id", "well_id", "row_index", "last_known_TVT",
            "target_delta_from_last_known",
        ],
    )
    artifact = np.load(oof_root / "blend_oof_postprocessed.npy").reshape(-1).astype(np.float32)
    target = gt["target_delta_from_last_known"].to_numpy(np.float32)
    groups, well_names = pd.factorize(gt["well_id"].astype(str), sort=False)
    groups = groups.astype(np.int32, copy=False)
    row_index = gt["row_index"].to_numpy(np.int32)
    n_wells = len(well_names)
    row_counts = np.bincount(groups, minlength=n_wells).astype(float)
    windows = parse_grid(args.window_grid, int)
    degrees = parse_grid(args.poly_grid, int)
    scale_grid = np.asarray(parse_grid(args.scale_grid, float))
    threshold_grid = np.asarray(parse_grid(args.bias_threshold_grid, float))

    candidates: dict[tuple[int, int], np.ndarray] = {(0, 0): artifact.copy()}
    for window in windows:
        if window <= 0:
            continue
        for poly in degrees:
            candidates[(window, poly)] = smooth_by_well(
                artifact, groups, row_index, window, poly
            ).astype(np.float32, copy=False)

    prefix = build_prefix_features(args.data_root, set(map(str, well_names)))
    prefix = pd.DataFrame({"_oof_well": well_names.astype(str)}).merge(
        prefix, on="_oof_well", how="left"
    )
    prefix_cols = [column for column in prefix.columns if column != "_oof_well"]
    prefix_values = prefix[prefix_cols].replace([np.inf, -np.inf], np.nan).to_numpy(float)

    smoothing_oof = np.full(len(target), np.nan, dtype=np.float32)
    combined_oof = np.full(len(target), np.nan, dtype=np.float32)
    fold_records: list[dict[str, object]] = []
    outer = GroupKFold(n_splits=args.folds)
    for fold, (train_wells, valid_wells) in enumerate(
        outer.split(prefix_values, groups=np.arange(n_wells)), 1
    ):
        train_rows = np.flatnonzero(np.isin(groups, train_wells))
        valid_rows = np.flatnonzero(np.isin(groups, valid_wells))
        best = None
        for (window, poly), prediction in candidates.items():
            denominator = float(np.dot(prediction[train_rows], prediction[train_rows]))
            alpha = (
                float(np.dot(prediction[train_rows], target[train_rows]) / denominator)
                if denominator > 1e-12
                else 1.0
            )
            alpha = float(np.clip(alpha, args.alpha_min, args.alpha_max))
            error = alpha * prediction[train_rows] - target[train_rows]
            score = float(np.sqrt(np.mean(error * error)))
            if best is None or score < best["train_rmse"]:
                best = {
                    "window": int(window),
                    "poly": int(poly),
                    "alpha": alpha,
                    "train_rmse": score,
                }
        assert best is not None
        selected_delta = best["alpha"] * candidates[(best["window"], best["poly"])]
        smoothing_oof[valid_rows] = selected_delta[valid_rows]
        residual = target - selected_delta
        labels = np.bincount(groups, weights=residual, minlength=n_wells) / row_counts
        stats = aggregate_well(selected_delta.astype(float), groups, n_wells)
        stats_matrix = np.column_stack(
            [
                stats["mean"], stats["std"], stats["first"], stats["last"],
                stats["min"], stats["max"],
            ]
        )
        X = np.column_stack([prefix_values, stats_matrix])

        selected_scale, selected_threshold, inner_bias_rmse = select_bias_gate(
            X,
            labels,
            train_wells,
            row_counts,
            scale_grid,
            threshold_grid,
            args.inner_folds,
            args.ridge_alpha,
        )
        model = make_ridge(args.ridge_alpha)
        model.fit(X[train_wells], labels[train_wells])
        valid_bias = model.predict(X[valid_wells])
        valid_bias = valid_bias * (np.abs(valid_bias) >= selected_threshold)
        bias_by_well = np.zeros(n_wells, dtype=float)
        bias_by_well[valid_wells] = valid_bias
        combined_oof[valid_rows] = (
            selected_delta[valid_rows]
            + selected_scale * bias_by_well[groups[valid_rows]]
        )
        record = {
            **best,
            "fold": fold,
            "train_wells": int(len(train_wells)),
            "valid_wells": int(len(valid_wells)),
            "bias_scale": selected_scale,
            "bias_threshold": selected_threshold,
            "inner_bias_rmse": inner_bias_rmse,
            "smoothing_valid_rmse": float(
                np.sqrt(np.mean((smoothing_oof[valid_rows] - target[valid_rows]) ** 2))
            ),
            "combined_valid_rmse": float(
                np.sqrt(np.mean((combined_oof[valid_rows] - target[valid_rows]) ** 2))
            ),
        }
        fold_records.append(record)
        print(json.dumps(record), flush=True)

    valid = np.isfinite(combined_oof)
    fit_all_best = None
    for (window, poly), prediction in candidates.items():
        denominator = float(np.dot(prediction, prediction))
        alpha = (
            float(np.dot(prediction, target) / denominator)
            if denominator > 1e-12
            else 1.0
        )
        alpha = float(np.clip(alpha, args.alpha_min, args.alpha_max))
        score = float(np.sqrt(np.mean((alpha * prediction - target) ** 2)))
        if fit_all_best is None or score < fit_all_best["train_rmse"]:
            fit_all_best = {
                "window": int(window),
                "poly": int(poly),
                "alpha": alpha,
                "train_rmse": score,
            }
    assert fit_all_best is not None
    fit_all_delta = (
        fit_all_best["alpha"]
        * candidates[(fit_all_best["window"], fit_all_best["poly"])]
    )
    fit_all_residual = target - fit_all_delta
    fit_all_labels = (
        np.bincount(groups, weights=fit_all_residual, minlength=n_wells)
        / row_counts
    )
    fit_all_stats = aggregate_well(fit_all_delta.astype(float), groups, n_wells)
    fit_all_X = np.column_stack(
        [
            prefix_values,
            fit_all_stats["mean"],
            fit_all_stats["std"],
            fit_all_stats["first"],
            fit_all_stats["last"],
            fit_all_stats["min"],
            fit_all_stats["max"],
        ]
    )
    fit_all_scale, fit_all_threshold, fit_all_bias_rmse = select_bias_gate(
        fit_all_X,
        fit_all_labels,
        np.arange(n_wells),
        row_counts,
        scale_grid,
        threshold_grid,
        args.inner_folds,
        args.ridge_alpha,
    )
    fit_all_recommendation = {
        **fit_all_best,
        "bias_scale": fit_all_scale,
        "bias_threshold": fit_all_threshold,
        "crossfit_bias_rmse": fit_all_bias_rmse,
    }
    summary = {
        "method": "artifact_coordinated_nested_smoothing_well_bias",
        "rows": int(valid.sum()),
        "wells": int(n_wells),
        "artifact": metrics(target[valid], artifact[valid], groups[valid]),
        "nested_smoothing": metrics(target[valid], smoothing_oof[valid], groups[valid]),
        "nested_smoothing_bias": metrics(target[valid], combined_oof[valid], groups[valid]),
        "folds": fold_records,
        "prefix_features": prefix_cols,
        "artifact_stat_features": [
            "smoothed_delta_mean", "smoothed_delta_std", "smoothed_delta_first",
            "smoothed_delta_last", "smoothed_delta_min", "smoothed_delta_max",
        ],
        "ridge_alpha": args.ridge_alpha,
        "scale_grid": scale_grid.tolist(),
        "bias_threshold_grid": threshold_grid.tolist(),
        "fit_all_recommendation": fit_all_recommendation,
        "elapsed_sec": float(time.perf_counter() - started),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, combined_oof)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--inner-folds", type=int, default=5)
    parser.add_argument("--window-grid", default="0,61,101,151,301,401,501,601,801")
    parser.add_argument("--poly-grid", default="1,2,3")
    parser.add_argument("--alpha-min", type=float, default=0.97)
    parser.add_argument("--alpha-max", type=float, default=1.03)
    parser.add_argument("--ridge-alpha", type=float, default=100.0)
    parser.add_argument("--scale-grid", default="0.1,0.25,0.5,0.75,1.0")
    parser.add_argument("--bias-threshold-grid", default="0.0")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
