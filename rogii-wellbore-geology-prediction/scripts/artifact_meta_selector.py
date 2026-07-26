"""Leakage-safe meta-selector for artifact OOF and a local candidate OOF.

Both base predictions must already be out-of-fold.  The meta model is trained
with an outer GroupKFold by well, so it cannot learn a well-specific correction
from the validation well's target values.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold


FEATURES = [
    "artifact_tvt",
    "candidate_tvt",
    "artifact_delta",
    "candidate_delta",
    "candidate_minus_artifact",
    "row_frac",
    "row_index",
    "last_known_TVT",
]


def metrics(y: np.ndarray, pred: np.ndarray, well: np.ndarray, n_wells: int) -> dict[str, float]:
    err = pred - y
    counts = np.bincount(well, minlength=n_wells)
    sums = np.bincount(well, weights=err * err, minlength=n_wells)
    by_well = np.sqrt(sums[counts > 0] / counts[counts > 0])
    return {
        "rmse": float(np.sqrt(np.mean(err * err))),
        "well_rmse_p50": float(np.quantile(by_well, 0.50)),
        "well_rmse_p90": float(np.quantile(by_well, 0.90)),
    }


def sample_train_positions(positions: np.ndarray, wells: np.ndarray, rows_per_well: int, seed: int) -> np.ndarray:
    if rows_per_well <= 0:
        return positions
    frame = pd.DataFrame({"pos": positions, "well": wells[positions]})
    rng = np.random.default_rng(seed)
    frame["random"] = rng.random(len(frame))
    frame = frame.sort_values(["well", "random"])
    return frame.groupby("well", sort=False).head(rows_per_well)["pos"].to_numpy(dtype=int)


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    candidate = pd.read_csv(
        args.candidate_oof,
        usecols=["_oof_id", "_oof_well", "_oof_row_idx", "target_tvt", "hgb_oof_tvt"],
    )
    required = {"_oof_id", "_oof_well", "_oof_row_idx", "target_tvt", "hgb_oof_tvt"}
    missing = required - set(candidate.columns)
    if missing:
        raise ValueError(f"candidate OOF missing columns: {sorted(missing)}")
    train_gt = pd.read_parquet(args.train_gt, columns=["id", "last_known_TVT"])
    artifact_delta = np.load(args.artifact_predictions).reshape(-1).astype(float)
    if len(candidate) != len(train_gt) or len(artifact_delta) != len(train_gt):
        raise ValueError(f"row count mismatch: candidate={len(candidate)}, train_gt={len(train_gt)}, artifact={len(artifact_delta)}")
    if not candidate["_oof_id"].astype(str).equals(train_gt["id"].astype(str)):
        raise ValueError("candidate OOF IDs do not exactly match train_gt order")
    viterbi = None
    if args.viterbi_oof is not None:
        viterbi = pd.read_csv(
            args.viterbi_oof,
            usecols=[
                "_oof_id", "viterbi_tvt", "viterbi_offset", "calibration_sigma",
                "calibration_alpha", "offset_std",
            ],
        )
        if len(viterbi) != len(candidate):
            raise ValueError(f"viterbi OOF row count mismatch: {len(viterbi)} != {len(candidate)}")
        if not viterbi["_oof_id"].astype(str).equals(candidate["_oof_id"].astype(str)):
            raise ValueError("viterbi OOF IDs do not exactly match candidate OOF order")

    ids = candidate["_oof_id"].astype(str).to_numpy()
    wells = candidate["_oof_well"].astype(str).to_numpy()
    well_codes, well_names = pd.factorize(wells, sort=False)
    well_codes = well_codes.astype(np.int32, copy=False)
    n_wells = len(well_names)
    row_index = candidate["_oof_row_idx"].to_numpy(dtype=np.float32)
    y = candidate["target_tvt"].to_numpy(dtype=np.float32)
    candidate_tvt = candidate["hgb_oof_tvt"].to_numpy(dtype=np.float32)
    viterbi_tvt = None if viterbi is None else viterbi["viterbi_tvt"].to_numpy(dtype=np.float32)
    viterbi_offset = None if viterbi is None else viterbi["viterbi_offset"].to_numpy(dtype=np.float32)
    calibration_sigma = None if viterbi is None else viterbi["calibration_sigma"].to_numpy(dtype=np.float32)
    calibration_alpha = None if viterbi is None else viterbi["calibration_alpha"].to_numpy(dtype=np.float32)
    offset_std = None if viterbi is None else viterbi["offset_std"].to_numpy(dtype=np.float32)
    last_known = train_gt["last_known_TVT"].to_numpy(dtype=np.float32)
    artifact_tvt = last_known + artifact_delta.astype(np.float32)
    artifact_delta = artifact_tvt - last_known
    candidate_delta = candidate_tvt - last_known
    candidate_minus_artifact = candidate_tvt - artifact_tvt
    max_index = np.zeros(n_wells, dtype=np.float32)
    np.maximum.at(max_index, well_codes, row_index)
    row_frac = row_index / np.maximum(max_index[well_codes], 1.0)
    feature_arrays = [
        artifact_tvt, candidate_tvt, artifact_delta, candidate_delta,
        candidate_minus_artifact, row_frac, row_index, last_known,
    ]
    if viterbi_tvt is not None:
        feature_arrays.extend([
            viterbi_tvt,
            viterbi_offset,
            viterbi_tvt - artifact_tvt,
            viterbi_tvt - candidate_tvt,
            calibration_sigma,
            calibration_alpha,
            offset_std,
        ])
    X = np.column_stack(feature_arrays).astype(np.float32, copy=False)
    meta_oof = np.full(len(y), np.nan, dtype=np.float32)
    outer_fold = np.full(len(y), -1, dtype=np.int8)
    del candidate, train_gt, wells, viterbi
    outer = GroupKFold(n_splits=args.folds)
    shrink_grid = [float(x) for x in args.shrink_grid.split(",")]
    selected_alphas = []
    for fold, (train_idx, valid_idx) in enumerate(outer.split(X, y, groups=well_codes), 1):
        alpha = 1.0
        if args.nested_shrink:
            inner = GroupKFold(n_splits=args.inner_folds)
            inner_train_rel, inner_valid_rel = next(
                inner.split(train_idx, y[train_idx], groups=well_codes[train_idx])
            )
            inner_train_idx = train_idx[inner_train_rel]
            inner_valid_idx = train_idx[inner_valid_rel]
            inner_fit_idx = sample_train_positions(
                inner_train_idx, well_codes, args.rows_per_well, args.seed + fold * 100
            )
            inner_model = HistGradientBoostingRegressor(
                max_iter=args.max_iter,
                learning_rate=args.learning_rate,
                max_leaf_nodes=args.max_leaf_nodes,
                l2_regularization=args.l2_regularization,
                early_stopping=False,
                random_state=args.seed + fold * 100,
            )
            inner_model.fit(X[inner_fit_idx], y[inner_fit_idx] - artifact_tvt[inner_fit_idx])
            inner_raw = artifact_tvt[inner_valid_idx] + inner_model.predict(X[inner_valid_idx])
            alpha = min(
                shrink_grid,
                key=lambda a: float(
                    np.mean((artifact_tvt[inner_valid_idx] + a * (inner_raw - artifact_tvt[inner_valid_idx]) - y[inner_valid_idx]) ** 2)
                ),
            )
        selected_alphas.append(alpha)
        fit_idx = sample_train_positions(train_idx, well_codes, args.rows_per_well, args.seed + fold)
        residual = y[fit_idx] - artifact_tvt[fit_idx]
        model = HistGradientBoostingRegressor(
            max_iter=args.max_iter,
            learning_rate=args.learning_rate,
            max_leaf_nodes=args.max_leaf_nodes,
            l2_regularization=args.l2_regularization,
            early_stopping=False,
            random_state=args.seed + fold,
        )
        model.fit(X[fit_idx], residual)
        raw_pred = artifact_tvt[valid_idx] + model.predict(X[valid_idx])
        pred = artifact_tvt[valid_idx] + alpha * (raw_pred - artifact_tvt[valid_idx])
        meta_oof[valid_idx] = pred
        outer_fold[valid_idx] = fold
        print(f"fold {fold}: train_rows={len(fit_idx)} valid_rows={len(valid_idx)} alpha={alpha:.3f} meta_rmse={metrics(y[valid_idx], pred, well_codes[valid_idx], n_wells)['rmse']:.6f}", flush=True)

    valid = np.isfinite(meta_oof)
    summary = {
        "method": "artifact_oof_outer_group_meta_selector_nested_shrink" if args.nested_shrink else "artifact_oof_outer_group_meta_selector",
        "rows": int(valid.sum()),
        "wells": int(np.unique(well_codes[valid]).size),
        "artifact": metrics(y[valid], artifact_tvt[valid], well_codes[valid], n_wells),
        "candidate": metrics(y[valid], candidate_tvt[valid], well_codes[valid], n_wells),
        "meta_selector": metrics(y[valid], meta_oof[valid], well_codes[valid], n_wells),
        "rows_per_well_fit": args.rows_per_well,
        "folds": args.folds,
        "nested_shrink": args.nested_shrink,
        "shrink_grid": shrink_grid,
        "selected_alphas": selected_alphas,
        "elapsed_sec": float(time.perf_counter() - started),
    }
    if viterbi_tvt is not None:
        summary["viterbi"] = metrics(y[valid], viterbi_tvt[valid], well_codes[valid], n_wells)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.unlink(missing_ok=True)
    for start in range(0, len(y), 250_000):
        stop = min(start + 250_000, len(y))
        pd.DataFrame({
            "id": ids[start:stop],
            "well": well_names[well_codes[start:stop]],
            "row_index": row_index[start:stop],
            "target_tvt": y[start:stop],
            "artifact_tvt": artifact_tvt[start:stop],
            "candidate_tvt": candidate_tvt[start:stop],
            "meta_oof_tvt": meta_oof[start:stop],
            "outer_fold": outer_fold[start:stop],
        }).to_csv(args.output, mode="a", header=start == 0, index=False)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-oof", type=Path, required=True)
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--artifact-predictions", type=Path, required=True)
    parser.add_argument("--viterbi-oof", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--rows-per-well", type=int, default=300)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--max-iter", type=int, default=120)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--max-leaf-nodes", type=int, default=31)
    parser.add_argument("--l2-regularization", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=20260726)
    parser.add_argument("--nested-shrink", action="store_true")
    parser.add_argument("--inner-folds", type=int, default=5)
    parser.add_argument("--shrink-grid", default="0,0.05,0.1,0.2,0.3,0.5,0.75,1.0")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
