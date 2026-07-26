"""Leakage-safe well-level gate between the artifact and a Viterbi candidate."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold


def row_metrics(y: np.ndarray, pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((pred - y) ** 2)))


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    viterbi = pd.read_csv(args.viterbi_oof)
    train_gt = pd.read_parquet(args.train_gt, columns=["id", "last_known_TVT"])
    artifact_delta = np.load(args.artifact_predictions).reshape(-1).astype(float)
    if len(viterbi) != len(train_gt) or len(artifact_delta) != len(train_gt):
        raise ValueError("row count mismatch between viterbi OOF, train_gt and artifact")
    if not viterbi["_oof_id"].astype(str).equals(train_gt["id"].astype(str)):
        raise ValueError("viterbi OOF IDs do not exactly match train_gt order")

    y = viterbi["target_tvt"].to_numpy(float)
    artifact = train_gt["last_known_TVT"].to_numpy(float) + artifact_delta
    base = viterbi["base_tvt"].to_numpy(float)
    raw_viterbi = viterbi["viterbi_tvt"].to_numpy(float)
    safe = base + 0.2 * np.clip(raw_viterbi - base, -10.0, 10.0)
    well_codes, well_names = pd.factorize(viterbi["_oof_well"].astype(str), sort=False)
    n_wells = len(well_names)
    row_index = viterbi["_oof_row_idx"].to_numpy(float)
    max_row = np.zeros(n_wells, dtype=float)
    np.maximum.at(max_row, well_codes, row_index)
    viterbi["artifact"] = artifact
    viterbi["safe"] = safe
    viterbi["artifact_se"] = (artifact - y) ** 2
    viterbi["safe_se"] = (safe - y) ** 2
    viterbi["artifact_delta"] = artifact - train_gt["last_known_TVT"].to_numpy(float)
    viterbi["safe_offset"] = safe - artifact
    viterbi["row_frac"] = row_index / np.maximum(max_row[well_codes], 1.0)

    grouped = viterbi.groupby("_oof_well", sort=False)
    well = grouped.agg(
        artifact_se=("artifact_se", "mean"),
        safe_se=("safe_se", "mean"),
        artifact_delta_mean=("artifact_delta", "mean"),
        artifact_delta_std=("artifact_delta", "std"),
        safe_offset_mean=("safe_offset", "mean"),
        safe_offset_std=("safe_offset", "std"),
        safe_offset_absmax=("safe_offset", lambda x: float(np.max(np.abs(x)))),
        row_count=("safe", "size"),
        row_frac_mean=("row_frac", "mean"),
        calibration_sigma=("calibration_sigma", "mean"),
        calibration_alpha=("calibration_alpha", "mean"),
        offset_std=("offset_std", "mean"),
        last_known_TVT=("artifact", "first"),
    ).reset_index()
    # The target-dependent label is created only for the training wells of each
    # outer fold. It represents the best fixed gate weight for that well.
    grid = np.asarray([float(x) for x in args.weight_grid.split(",") if x.strip()])
    artifact_group = well["artifact_se"].to_numpy(float)
    safe_group = well["safe_se"].to_numpy(float)
    # Reconstruct the per-well cross term to score arbitrary weights exactly.
    viterbi["cross"] = (viterbi["safe"] - viterbi["artifact"]) * (viterbi["artifact"] - y)
    viterbi["move_sq"] = (viterbi["safe"] - viterbi["artifact"]) ** 2
    cross_group = viterbi.groupby("_oof_well", sort=False)["cross"].mean().to_numpy(float)
    move_group = viterbi.groupby("_oof_well", sort=False)["move_sq"].mean().to_numpy(float)
    best_alpha = np.zeros(n_wells, dtype=float)
    for i in range(n_wells):
        scores = artifact_group[i] + 2.0 * grid * cross_group[i] + grid * grid * move_group[i]
        best_alpha[i] = grid[int(np.argmin(scores))]

    feature_cols = [
        "artifact_delta_mean", "artifact_delta_std", "safe_offset_mean",
        "safe_offset_std", "safe_offset_absmax", "row_count", "row_frac_mean",
        "calibration_sigma", "calibration_alpha", "offset_std", "last_known_TVT",
    ]
    X = well[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(np.float32)
    groups = np.arange(n_wells)
    continuous = np.full(n_wells, np.nan, dtype=float)
    nearest = np.full(n_wells, np.nan, dtype=float)
    global_alpha = np.full(n_wells, np.nan, dtype=float)
    outer = GroupKFold(n_splits=args.folds)
    for fold, (train_idx, valid_idx) in enumerate(outer.split(X, best_alpha, groups=groups), 1):
        model = HistGradientBoostingRegressor(
            max_iter=args.max_iter,
            learning_rate=args.learning_rate,
            max_leaf_nodes=args.max_leaf_nodes,
            l2_regularization=args.l2_regularization,
            early_stopping=False,
            random_state=args.seed + fold,
        )
        model.fit(X[train_idx], best_alpha[train_idx])
        predicted = np.clip(model.predict(X[valid_idx]), 0.0, 1.0)
        continuous[valid_idx] = predicted
        nearest[valid_idx] = grid[np.abs(grid[:, None] - predicted[None, :]).argmin(axis=0)]
        train_scores = []
        for alpha in grid:
            train_scores.append(float(np.sum(artifact_group[train_idx] + 2 * alpha * cross_group[train_idx] + alpha * alpha * move_group[train_idx])))
        global_alpha[valid_idx] = grid[int(np.argmin(train_scores))]
        print(f"fold {fold}: train_wells={len(train_idx)} valid_wells={len(valid_idx)} global_alpha={global_alpha[valid_idx][0]:.3f}", flush=True)

    valid = np.isfinite(continuous)
    row_well = well_codes
    pred_cont = artifact + continuous[row_well] * (safe - artifact)
    pred_nearest = artifact + nearest[row_well] * (safe - artifact)
    pred_global = artifact + global_alpha[row_well] * (safe - artifact)
    summary = {
        "method": "well_level_viterbi_gate_outer_group_kfold",
        "rows": int(valid[row_well].sum()),
        "wells": int(valid.sum()),
        "artifact_rmse": row_metrics(y, artifact),
        "safe_viterbi_rmse": row_metrics(y, safe),
        "continuous_gate_rmse": row_metrics(y, pred_cont),
        "nearest_grid_gate_rmse": row_metrics(y, pred_nearest),
        "global_train_selected_gate_rmse": row_metrics(y, pred_global),
        "weight_grid": grid.tolist(),
        "selected_alpha_counts": {str(x): int(np.sum(best_alpha == x)) for x in grid},
        "predicted_alpha_mean": float(np.nanmean(continuous)),
        "predicted_alpha_median": float(np.nanmedian(continuous)),
        "feature_cols": feature_cols,
        "folds": args.folds,
        "elapsed_sec": float(time.perf_counter() - started),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    output = well[["_oof_well"]].copy()
    output["best_alpha_train_only"] = best_alpha
    output["predicted_alpha"] = continuous
    output["nearest_alpha"] = nearest
    output["global_alpha"] = global_alpha
    output.to_csv(args.output, index=False)
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--viterbi-oof", type=Path, required=True)
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--artifact-predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--weight-grid", default="0,0.05,0.1,0.2,0.3,0.5,0.75,1")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--max-iter", type=int, default=100)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--max-leaf-nodes", type=int, default=15)
    parser.add_argument("--l2-regularization", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=20260726)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
