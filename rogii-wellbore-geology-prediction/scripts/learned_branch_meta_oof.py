"""Build a leakage-safe learned trajectory branch from legal base OOF arrays.

The public Ridge artifacts and the model-package postprocessed prediction are
already out-of-fold at the well level.  This script adds one more GroupKFold
layer, so the meta model for a validation well never sees that well's target.
It produces a delta-from-last-known OOF vector for downstream generic-core
blend evaluation.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold


PUBLIC_ARTIFACTS = (
    "lgbmregressor_trainer_20260526182612.pkl.oof.npy",
    "lgbmregressor_trainer_20260526190415.pkl.oof.npy",
    "lgbmregressor_trainer_20260526192806.pkl.oof.npy",
    "catboostregressor_trainer_20260526193740.pkl.oof.npy",
    "catboostregressor_trainer_20260526194838.pkl.oof.npy",
)

VARIANTS = {
    "public5": tuple(f"public_{index}" for index in range(5)),
    "public5_pkg_post": tuple(f"public_{index}" for index in range(5))
    + ("package_postprocessed",),
    "public5_pkg_post_local": tuple(f"public_{index}" for index in range(5))
    + ("package_postprocessed", "local_hgb"),
    "public5_pkg_raw": tuple(f"public_{index}" for index in range(5))
    + (
        "package_lgb",
        "package_xgb",
        "package_catboost",
        "package_hgb",
        "package_sequence_tcn",
    ),
    "all12_dynamic": tuple(f"public_{index}" for index in range(5))
    + (
        "package_lgb",
        "package_xgb",
        "package_catboost",
        "package_hgb",
        "package_sequence_tcn",
        "package_blend",
        "package_postprocessed",
    ),
    "all13": tuple(f"public_{index}" for index in range(5))
    + (
        "package_lgb",
        "package_xgb",
        "package_catboost",
        "package_hgb",
        "package_sequence_tcn",
        "package_blend",
        "package_postprocessed",
        "local_hgb",
    ),
}

PACKAGE_FILES = {
    "package_lgb": "lgb_oof.npy",
    "package_xgb": "xgb_oof.npy",
    "package_catboost": "catboost_oof.npy",
    "package_hgb": "hgb_oof.npy",
    "package_sequence_tcn": "sequence_tcn_oof.npy",
    "package_blend": "blend_oof.npy",
    "package_postprocessed": "blend_oof_postprocessed.npy",
}

RIDGE_PARAMS = {
    "alpha": 1.6602834637650032,
    "positive": True,
    "fit_intercept": True,
    "tol": 0.0005030247295617308,
    "solver": "lbfgs",
    "max_iter": 500,
}


def rmse(target: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.sqrt(np.mean((prediction - target) ** 2)))


def load_array(path: Path, rows: int) -> np.ndarray:
    values = np.asarray(np.load(path, mmap_mode="r"), dtype=np.float32)
    if values.shape != (rows,) or not np.isfinite(values).all():
        raise RuntimeError(f"invalid OOF array: {path}")
    return values


def metrics_by_well(
    truth: pd.DataFrame,
    target: np.ndarray,
    prediction: np.ndarray,
) -> dict[str, float]:
    work = pd.DataFrame(
        {
            "well": truth["well_id"].astype(str),
            "square_error": (prediction - target) ** 2,
        }
    )
    well_rmse = np.sqrt(work.groupby("well")["square_error"].mean())
    return {
        "rmse": rmse(target, prediction),
        "well_rmse_p50": float(well_rmse.quantile(0.50)),
        "well_rmse_p90": float(well_rmse.quantile(0.90)),
    }


def crossfit(
    matrix: np.ndarray,
    target: np.ndarray,
    groups: np.ndarray,
    splits: list[tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, list[dict[str, object]]]:
    prediction = np.full(len(target), np.nan, dtype=np.float32)
    fold_records: list[dict[str, object]] = []
    for fold, (train_index, valid_index) in enumerate(splits, 1):
        model = Ridge(**RIDGE_PARAMS)
        model.fit(matrix[train_index], target[train_index])
        prediction[valid_index] = model.predict(matrix[valid_index])
        fold_records.append(
            {
                "fold": fold,
                "train_wells": int(np.unique(groups[train_index]).size),
                "valid_wells": int(np.unique(groups[valid_index]).size),
                "valid_rmse": rmse(
                    target[valid_index], prediction[valid_index]
                ),
                "coef": [float(value) for value in model.coef_],
                "intercept": float(model.intercept_),
            }
        )
    if not np.isfinite(prediction).all():
        raise RuntimeError("meta OOF is incomplete")
    return prediction, fold_records


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    truth = pd.read_parquet(
        args.train_gt,
        columns=[
            "id",
            "well_id",
            "last_known_TVT",
            "target_delta_from_last_known",
        ],
    )
    if truth["id"].duplicated().any():
        raise RuntimeError("train_gt contains duplicate IDs")
    rows = len(truth)
    target = truth["target_delta_from_last_known"].to_numpy(np.float32)
    groups = truth["well_id"].astype(str).to_numpy()

    arrays: dict[str, np.ndarray] = {}
    for index, name in enumerate(PUBLIC_ARTIFACTS):
        arrays[f"public_{index}"] = load_array(
            args.public_oof_dir / name, rows
        )
    for feature, name in PACKAGE_FILES.items():
        arrays[feature] = load_array(args.package_oof_dir / name, rows)

    local = pd.read_csv(
        args.local_oof, usecols=["_oof_id", "hgb_oof_tvt"]
    )
    if len(local) != rows or not np.array_equal(
        local["_oof_id"].astype(str).to_numpy(),
        truth["id"].astype(str).to_numpy(),
    ):
        raise RuntimeError("local HGB OOF IDs do not align with train_gt")
    arrays["local_hgb"] = (
        local["hgb_oof_tvt"].to_numpy(np.float32)
        - truth["last_known_TVT"].to_numpy(np.float32)
    )

    splitter = GroupKFold(n_splits=args.folds)
    splits = list(splitter.split(np.zeros(rows), target, groups=groups))
    variant_records: dict[str, object] = {}
    selected_prediction: np.ndarray | None = None
    for variant, features in VARIANTS.items():
        matrix = np.column_stack([arrays[name] for name in features])
        prediction, fold_records = crossfit(
            matrix, target, groups, splits
        )
        record = {
            "features": list(features),
            "metrics": metrics_by_well(truth, target, prediction),
            "folds": fold_records,
        }
        variant_records[variant] = record
        print(json.dumps({"variant": variant, **record["metrics"]}), flush=True)
        if variant == args.selected_variant:
            selected_prediction = prediction.copy()
        del matrix, prediction

    if selected_prediction is None:
        raise RuntimeError(f"selected variant not evaluated: {args.selected_variant}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, selected_prediction)
    selected_features = VARIANTS[args.selected_variant]
    fit_all_matrix = np.column_stack(
        [arrays[name] for name in selected_features]
    )
    fit_all_model = Ridge(**RIDGE_PARAMS)
    fit_all_model.fit(fit_all_matrix, target)

    baseline = variant_records["public5"]["metrics"]["rmse"]
    selected = variant_records[args.selected_variant]["metrics"]["rmse"]
    summary = {
        "method": "legal_base_oof_positive_ridge_learned_branch",
        "rows": int(rows),
        "wells": int(truth["well_id"].nunique()),
        "folds": int(args.folds),
        "ridge_params": RIDGE_PARAMS,
        "variants": variant_records,
        "selected_variant": args.selected_variant,
        "selected_features": list(selected_features),
        "selected_improvement_vs_public5": float(baseline - selected),
        "fit_all": {
            "coef": [float(value) for value in fit_all_model.coef_],
            "intercept": float(fit_all_model.intercept_),
            "train_rmse": rmse(
                target, fit_all_model.predict(fit_all_matrix)
            ),
        },
        "output": str(args.output),
        "leakage_controls": {
            "all_inputs_are_well_group_oof": True,
            "meta_model_is_groupkfold": True,
            "suffix_target_used_only_for_outer_fold_training_and_evaluation": True,
            "same_well_contact_used": False,
            "public_well_ids_used": False,
        },
        "elapsed_sec": float(time.perf_counter() - started),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--public-oof-dir", type=Path, required=True)
    parser.add_argument("--package-oof-dir", type=Path, required=True)
    parser.add_argument("--local-oof", type=Path, required=True)
    parser.add_argument(
        "--selected-variant",
        choices=tuple(VARIANTS),
        default="public5_pkg_post",
    )
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
