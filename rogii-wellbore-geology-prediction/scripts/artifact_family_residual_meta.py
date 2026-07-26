"""Nested well-grouped residual meta-model over model-package family OOFs."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold


FAMILIES = ("xgb", "catboost", "hgb", "lgb", "sequence_tcn")


def sample_positions(
    positions: np.ndarray,
    groups: np.ndarray,
    rows_per_well: int,
    seed: int,
) -> np.ndarray:
    if rows_per_well <= 0:
        return positions
    frame = pd.DataFrame({"position": positions, "well": groups[positions]})
    rng = np.random.default_rng(seed)
    frame["random"] = rng.random(len(frame))
    return (
        frame.sort_values(["well", "random"])
        .groupby("well", sort=False)
        .head(rows_per_well)["position"]
        .to_numpy(int)
    )


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


def make_model(args: argparse.Namespace, seed: int) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=args.max_iter,
        learning_rate=args.learning_rate,
        max_leaf_nodes=args.max_leaf_nodes,
        min_samples_leaf=args.min_samples_leaf,
        l2_regularization=args.l2_regularization,
        early_stopping=False,
        random_state=seed,
    )


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    oof_root = args.package_root / "oof"
    train_gt = pd.read_parquet(
        oof_root / "train_gt.parquet",
        columns=[
            "id", "well_id", "row_index", "MD", "last_known_TVT",
            "target_delta_from_last_known",
        ],
    )
    family = np.column_stack(
        [np.load(oof_root / f"{name}_oof.npy").reshape(-1) for name in FAMILIES]
    ).astype(np.float32, copy=False)
    artifact = np.load(oof_root / "blend_oof_postprocessed.npy").reshape(-1).astype(np.float32)
    raw_blend = np.load(oof_root / "blend_oof.npy").reshape(-1).astype(np.float32)
    target = train_gt["target_delta_from_last_known"].to_numpy(np.float32)
    groups, well_names = pd.factorize(train_gt["well_id"].astype(str), sort=False)
    groups = groups.astype(np.int32, copy=False)
    row_index = train_gt["row_index"].to_numpy(np.float32)
    md = train_gt["MD"].to_numpy(np.float32)
    last_known = train_gt["last_known_TVT"].to_numpy(np.float32)
    n_wells = len(well_names)
    row_min = np.full(n_wells, np.inf, dtype=np.float32)
    row_max = np.full(n_wells, -np.inf, dtype=np.float32)
    md_min = np.full(n_wells, np.inf, dtype=np.float32)
    md_max = np.full(n_wells, -np.inf, dtype=np.float32)
    np.minimum.at(row_min, groups, row_index)
    np.maximum.at(row_max, groups, row_index)
    np.minimum.at(md_min, groups, md)
    np.maximum.at(md_max, groups, md)
    row_frac = (row_index - row_min[groups]) / np.maximum(row_max[groups] - row_min[groups], 1.0)
    md_frac = (md - md_min[groups]) / np.maximum(md_max[groups] - md_min[groups], 1.0)
    family_mean = family.mean(axis=1)
    family_median = np.median(family, axis=1)
    disagreement = family.std(axis=1)
    family_range = family.max(axis=1) - family.min(axis=1)
    features = np.column_stack(
        [
            artifact,
            raw_blend,
            family,
            family - artifact[:, None],
            family_mean,
            family_median,
            disagreement,
            family_range,
            row_frac,
            md_frac,
            row_index,
            md,
            last_known,
            np.abs(artifact),
        ]
    ).astype(np.float32, copy=False)
    feature_names = [
        "artifact", "raw_blend",
        *FAMILIES,
        *(f"{name}_minus_artifact" for name in FAMILIES),
        "family_mean", "family_median", "disagreement", "family_range",
        "row_frac", "md_frac", "row_index", "MD", "last_known_TVT",
        "artifact_abs",
    ]
    residual = target - artifact
    alpha_grid = [float(x) for x in args.shrink_grid.split(",") if x.strip()]
    oof = np.full(len(target), np.nan, dtype=np.float32)
    raw_meta_oof = np.full(len(target), np.nan, dtype=np.float32)
    fold_records: list[dict[str, object]] = []
    outer = GroupKFold(n_splits=args.folds)
    for fold, (outer_train, outer_valid) in enumerate(
        outer.split(features, residual, groups=groups), 1
    ):
        inner = GroupKFold(n_splits=args.inner_folds)
        inner_train_rel, inner_valid_rel = next(
            inner.split(
                np.empty(len(outer_train)),
                residual[outer_train],
                groups=groups[outer_train],
            )
        )
        inner_train = outer_train[inner_train_rel]
        inner_valid = outer_train[inner_valid_rel]
        inner_fit = sample_positions(
            inner_train, groups, args.rows_per_well, args.seed + fold * 100
        )
        inner_model = make_model(args, args.seed + fold * 100)
        inner_model.fit(features[inner_fit], residual[inner_fit])
        inner_correction = inner_model.predict(features[inner_valid])
        alpha = min(
            alpha_grid,
            key=lambda value: float(
                np.mean(
                    (
                        artifact[inner_valid]
                        + value * inner_correction
                        - target[inner_valid]
                    )
                    ** 2
                )
            ),
        )

        outer_fit = sample_positions(
            outer_train, groups, args.rows_per_well, args.seed + fold
        )
        model = make_model(args, args.seed + fold)
        model.fit(features[outer_fit], residual[outer_fit])
        correction = model.predict(features[outer_valid])
        raw_meta_oof[outer_valid] = artifact[outer_valid] + correction
        oof[outer_valid] = artifact[outer_valid] + alpha * correction
        fold_rmse = float(np.sqrt(np.mean((oof[outer_valid] - target[outer_valid]) ** 2)))
        record = {
            "fold": fold,
            "train_rows": int(len(outer_fit)),
            "valid_rows": int(len(outer_valid)),
            "selected_alpha": float(alpha),
            "outer_rmse": fold_rmse,
        }
        fold_records.append(record)
        print(json.dumps(record), flush=True)

    valid = np.isfinite(oof)
    summary = {
        "method": "artifact_family_nested_residual_hgb",
        "rows": int(valid.sum()),
        "wells": int(n_wells),
        "feature_names": feature_names,
        "artifact": metrics(target[valid], artifact[valid], groups[valid]),
        "raw_meta": metrics(target[valid], raw_meta_oof[valid], groups[valid]),
        "nested_shrink_meta": metrics(target[valid], oof[valid], groups[valid]),
        "folds": fold_records,
        "rows_per_well": args.rows_per_well,
        "shrink_grid": alpha_grid,
        "elapsed_sec": float(time.perf_counter() - started),
        "validation_note": (
            "Residual model and shrink selection are outer/inner well-grouped. "
            "Stored family inputs are package OOF predictions, not base models "
            "regenerated inside every outer fold."
        ),
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
    parser.add_argument("--inner-folds", type=int, default=4)
    parser.add_argument("--rows-per-well", type=int, default=300)
    parser.add_argument("--max-iter", type=int, default=120)
    parser.add_argument("--learning-rate", type=float, default=0.04)
    parser.add_argument("--max-leaf-nodes", type=int, default=15)
    parser.add_argument("--min-samples-leaf", type=int, default=80)
    parser.add_argument("--l2-regularization", type=float, default=25.0)
    parser.add_argument("--shrink-grid", default="0,0.05,0.1,0.2,0.3,0.5,0.75,1")
    parser.add_argument("--seed", type=int, default=20260726)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
