"""Extract and reproduce the public New Strategy Ridge-stack OOF.

The five public trainer pickles contain legal group-OOF predictions.  This
script aligns them to the model-package train_gt IDs, verifies their stored
scores, and rebuilds the positive Ridge meta-OOF with GroupKFold.
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import types
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold


ARTIFACTS = [
    "lgbmregressor_trainer_20260526182612.pkl",
    "lgbmregressor_trainer_20260526190415.pkl",
    "lgbmregressor_trainer_20260526192806.pkl",
    "catboostregressor_trainer_20260526193740.pkl",
    "catboostregressor_trainer_20260526194838.pkl",
]

RIDGE_PARAMS = {
    "random_state": 42,
    "alpha": 1.6602834637650032,
    "tol": 0.0005030247295617308,
    "positive": True,
    "fit_intercept": True,
}


def install_koolbox_pickle_shim() -> None:
    """Expose the class path used by the public koolbox Trainer pickle."""

    class Trainer:
        pass

    Trainer.__module__ = "koolbox.trainer.trainer"
    Trainer.__qualname__ = "Trainer"
    package = types.ModuleType("koolbox")
    package.__path__ = []
    trainer_package = types.ModuleType("koolbox.trainer")
    trainer_package.__path__ = []
    trainer_module = types.ModuleType("koolbox.trainer.trainer")
    trainer_module.Trainer = Trainer
    package.Trainer = Trainer
    package.trainer = trainer_package
    trainer_package.Trainer = Trainer
    trainer_package.trainer = trainer_module
    for module in (package, trainer_package, trainer_module):
        sys.modules[module.__name__] = module


def rmse(target: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.sqrt(np.mean((prediction - target) ** 2)))


def run(args: argparse.Namespace) -> dict[str, object]:
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    truth = pd.read_parquet(
        args.train_gt,
        columns=["id", "well_id", "target_delta_from_last_known"],
    )
    if truth["id"].duplicated().any():
        raise RuntimeError("train_gt contains duplicate IDs")
    target = truth["target_delta_from_last_known"].to_numpy(float)
    install_koolbox_pickle_shim()

    artifact_records: list[dict[str, object]] = []
    arrays: list[np.ndarray] = []
    for name in ARTIFACTS:
        path = args.artifact_dir / name
        if not path.exists():
            raise FileNotFoundError(path)
        array_path = args.cache_dir / f"{name}.oof.npy"
        trainer = joblib.load(path)
        values = np.asarray(trainer.oof_preds, dtype=np.float64).reshape(-1)
        if len(values) != len(truth) or not np.isfinite(values).all():
            raise RuntimeError(f"invalid OOF array in {path}")
        np.save(array_path, values)
        record = {
            "artifact": name,
            "rows": int(len(values)),
            "stored_rmse": float(trainer.overall_score),
            "aligned_rmse": rmse(target, values),
            "score_abs_difference": abs(
                float(trainer.overall_score) - rmse(target, values)
            ),
            "array_path": str(array_path),
        }
        artifact_records.append(record)
        arrays.append(values)
        print(json.dumps(record), flush=True)
        del trainer
        gc.collect()

    matrix = np.column_stack(arrays)
    groups = truth["well_id"].astype(str).to_numpy()
    meta_oof = np.full(len(truth), np.nan, dtype=np.float64)
    fold_records: list[dict[str, object]] = []
    splitter = GroupKFold(n_splits=args.folds)
    for fold, (train_index, valid_index) in enumerate(
        splitter.split(matrix, target, groups=groups), 1
    ):
        model = Ridge(**RIDGE_PARAMS)
        model.fit(matrix[train_index], target[train_index])
        meta_oof[valid_index] = model.predict(matrix[valid_index])
        record = {
            "fold": fold,
            "train_wells": int(np.unique(groups[train_index]).size),
            "valid_wells": int(np.unique(groups[valid_index]).size),
            "valid_rmse": rmse(target[valid_index], meta_oof[valid_index]),
            "coef": [float(value) for value in model.coef_],
            "intercept": float(model.intercept_),
        }
        fold_records.append(record)
        print(json.dumps(record), flush=True)
    if not np.isfinite(meta_oof).all():
        raise RuntimeError("Ridge meta-OOF is incomplete")

    np.save(args.output, meta_oof)
    summary = {
        "method": "public_new_strategy_positive_ridge_group_oof",
        "rows": int(len(truth)),
        "wells": int(truth["well_id"].nunique()),
        "artifact_order": ARTIFACTS,
        "artifact_records": artifact_records,
        "ridge_params": RIDGE_PARAMS,
        "fold_records": fold_records,
        "ridge_meta_oof_rmse": rmse(target, meta_oof),
        "public_notebook_reported_rmse": 10.4197,
        "target_precision_note": (
            "train_gt target deltas are rounded to 0.01 ft; tiny score differences "
            "from the public feature CSV are expected"
        ),
        "output": str(args.output),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
