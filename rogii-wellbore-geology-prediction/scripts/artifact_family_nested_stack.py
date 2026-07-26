"""Nested well-grouped stack of the public model-package family OOF branches.

The package exposes five already out-of-fold delta predictions.  This script
refits only the small constrained level-2 blend.  Blend weights are fitted on
outer-train wells; disagreement shrinkage and smoothing are selected on an
inner held-out set of wells before evaluating the untouched outer fold.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.signal import savgol_filter
from sklearn.model_selection import GroupKFold


FAMILIES = ("xgb", "catboost", "hgb", "lgb", "sequence_tcn")


def fit_simplex_weights(
    predictions: np.ndarray,
    target: np.ndarray,
    indices: np.ndarray,
    l2: float,
) -> np.ndarray:
    x = predictions[indices].astype(np.float64, copy=False)
    y = target[indices].astype(np.float64, copy=False)
    gram = (x.T @ x) / len(x)
    cross = (x.T @ y) / len(x)

    def objective(weight: np.ndarray) -> float:
        return float(weight @ gram @ weight - 2.0 * weight @ cross + l2 * (weight @ weight))

    def gradient(weight: np.ndarray) -> np.ndarray:
        return 2.0 * gram @ weight - 2.0 * cross + 2.0 * l2 * weight

    initial = np.full(predictions.shape[1], 1.0 / predictions.shape[1])
    result = minimize(
        objective,
        initial,
        jac=gradient,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * predictions.shape[1],
        constraints={"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)},
        options={"maxiter": 500, "ftol": 1e-12},
    )
    if not result.success:
        raise RuntimeError(f"simplex blend optimization failed: {result.message}")
    weight = np.clip(np.asarray(result.x, dtype=float), 0.0, 1.0)
    return weight / weight.sum()


def postprocess(
    raw_delta: np.ndarray,
    disagreement: np.ndarray,
    groups: np.ndarray,
    row_index: np.ndarray,
    alpha: float,
    gamma: float,
    window: int,
    poly: int = 2,
) -> np.ndarray:
    prediction = alpha * raw_delta / (1.0 + gamma * disagreement)
    if window <= 0:
        return prediction
    output = prediction.copy()
    order = np.argsort(groups, kind="stable")
    ordered_groups = groups[order]
    boundaries = np.r_[0, np.flatnonzero(ordered_groups[1:] != ordered_groups[:-1]) + 1, len(order)]
    for start, stop in zip(boundaries[:-1], boundaries[1:]):
        positions = order[start:stop]
        positions = positions[np.argsort(row_index[positions], kind="stable")]
        n = len(positions)
        local_window = min(int(window), n)
        if local_window % 2 == 0:
            local_window -= 1
        if local_window >= poly + 2:
            output[positions] = savgol_filter(prediction[positions], local_window, poly)
    return output


def metrics(target: np.ndarray, prediction: np.ndarray, groups: np.ndarray) -> dict[str, float]:
    error = prediction - target
    codes, _ = pd.factorize(groups, sort=False)
    counts = np.bincount(codes)
    sums = np.bincount(codes, weights=error * error)
    per_well = np.sqrt(sums / counts)
    return {
        "rmse": float(np.sqrt(np.mean(error * error))),
        "well_rmse_p50": float(np.quantile(per_well, 0.50)),
        "well_rmse_p90": float(np.quantile(per_well, 0.90)),
    }


def parse_grid(value: str, cast=float) -> list:
    return [cast(item.strip()) for item in value.split(",") if item.strip()]


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    oof_root = args.package_root / "oof"
    train_gt = pd.read_parquet(
        oof_root / "train_gt.parquet",
        columns=["id", "well_id", "row_index", "target_delta_from_last_known"],
    )
    predictions = np.column_stack(
        [np.load(oof_root / f"{family}_oof.npy").reshape(-1) for family in FAMILIES]
    ).astype(np.float32, copy=False)
    target = train_gt["target_delta_from_last_known"].to_numpy(np.float32)
    groups, well_names = pd.factorize(train_gt["well_id"].astype(str), sort=False)
    groups = groups.astype(np.int32, copy=False)
    row_index = train_gt["row_index"].to_numpy(np.int32)
    disagreement = predictions.std(axis=1, dtype=np.float64).astype(np.float32)
    package_post = np.load(oof_root / "blend_oof_postprocessed.npy").reshape(-1).astype(np.float32)
    if len(target) != len(predictions) or len(package_post) != len(target):
        raise ValueError("OOF row count mismatch")

    alpha_grid = parse_grid(args.alpha_grid, float)
    gamma_grid = parse_grid(args.gamma_grid, float)
    window_grid = parse_grid(args.window_grid, int)
    raw_oof = np.full(len(target), np.nan, dtype=np.float32)
    nested_oof = np.full(len(target), np.nan, dtype=np.float32)
    fold_records: list[dict[str, object]] = []
    outer = GroupKFold(n_splits=args.folds)

    for fold, (outer_train, outer_valid) in enumerate(
        outer.split(predictions, target, groups=groups), 1
    ):
        inner = GroupKFold(n_splits=args.inner_folds)
        inner_train_rel, inner_valid_rel = next(
            inner.split(
                np.empty(len(outer_train)),
                target[outer_train],
                groups=groups[outer_train],
            )
        )
        inner_train = outer_train[inner_train_rel]
        inner_valid = outer_train[inner_valid_rel]
        inner_weight = fit_simplex_weights(predictions, target, inner_train, args.l2)
        inner_raw = predictions[inner_valid] @ inner_weight
        best = None
        for alpha in alpha_grid:
            for gamma in gamma_grid:
                pred = postprocess(
                    inner_raw,
                    disagreement[inner_valid],
                    groups[inner_valid],
                    row_index[inner_valid],
                    alpha,
                    gamma,
                    0,
                )
                score = float(np.sqrt(np.mean((pred - target[inner_valid]) ** 2)))
                if best is None or score < best["rmse"]:
                    best = {"alpha": alpha, "gamma": gamma, "window": 0, "rmse": score}
        assert best is not None
        for window in window_grid:
            pred = postprocess(
                inner_raw,
                disagreement[inner_valid],
                groups[inner_valid],
                row_index[inner_valid],
                best["alpha"],
                best["gamma"],
                window,
            )
            score = float(np.sqrt(np.mean((pred - target[inner_valid]) ** 2)))
            if score < best["rmse"]:
                best = {**best, "window": window, "rmse": score}

        outer_weight = fit_simplex_weights(predictions, target, outer_train, args.l2)
        outer_raw = predictions[outer_valid] @ outer_weight
        raw_oof[outer_valid] = outer_raw
        outer_prediction = postprocess(
            outer_raw,
            disagreement[outer_valid],
            groups[outer_valid],
            row_index[outer_valid],
            float(best["alpha"]),
            float(best["gamma"]),
            int(best["window"]),
        )
        nested_oof[outer_valid] = outer_prediction
        fold_rmse = float(np.sqrt(np.mean((outer_prediction - target[outer_valid]) ** 2)))
        record = {
            "fold": fold,
            "train_wells": int(np.unique(groups[outer_train]).size),
            "valid_wells": int(np.unique(groups[outer_valid]).size),
            "alpha": float(best["alpha"]),
            "gamma": float(best["gamma"]),
            "window": int(best["window"]),
            "inner_rmse": float(best["rmse"]),
            "outer_rmse": fold_rmse,
            "weights": {family: float(value) for family, value in zip(FAMILIES, outer_weight)},
        }
        fold_records.append(record)
        print(json.dumps(record), flush=True)

    valid = np.isfinite(nested_oof)
    summary = {
        "method": "artifact_family_nested_simplex_disagreement_stack",
        "rows": int(valid.sum()),
        "wells": int(len(well_names)),
        "families": list(FAMILIES),
        "package_postprocessed": metrics(target[valid], package_post[valid], groups[valid]),
        "outer_simplex_raw": metrics(target[valid], raw_oof[valid], groups[valid]),
        "outer_nested_postprocessed": metrics(target[valid], nested_oof[valid], groups[valid]),
        "folds": fold_records,
        "alpha_grid": alpha_grid,
        "gamma_grid": gamma_grid,
        "window_grid": window_grid,
        "l2": args.l2,
        "elapsed_sec": float(time.perf_counter() - started),
        "validation_note": (
            "Level-2 weights and postprocess parameters are outer/inner well-grouped. "
            "The stored family predictions are package OOF rather than fully regenerated "
            "inside each outer fold, so any improvement remains a screening result."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, nested_oof)
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
    parser.add_argument("--inner-folds", type=int, default=4)
    parser.add_argument("--l2", type=float, default=1e-5)
    parser.add_argument("--alpha-grid", default="0.95,0.975,1.0,1.025,1.05,1.075,1.1")
    parser.add_argument("--gamma-grid", default="0,0.0025,0.005,0.01,0.02,0.04,0.08")
    parser.add_argument("--window-grid", default="0,11,25,61")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
