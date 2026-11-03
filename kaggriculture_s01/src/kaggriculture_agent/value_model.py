"""Leakage-aware value regression for recorded Kaggriculture trajectories.

The trajectory table contains one row per actor and decision step.  A row's
``reward_difference`` is the actor's final reward minus the opponent's final
reward.  This module deliberately keeps that final outcome out of the feature
matrix and splits all rows from a seed/pair together.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

TARGET_COLUMN = "reward_difference"
TABLE_NAMES = ("transitions", "episodes", "pairs")
CATEGORICAL_FEATURES: tuple[str, ...] = ()

# These columns identify a trajectory or are only known after the game.  They
# may be present in an output table, but are never passed to the regressor.
IDENTIFIER_COLUMNS = frozenset(
    {
        "split",
        "evaluation_stage",
        "pair_id",
        "game_id",
        "seed",
        "player",
        "policy",
        "opponent",
        "seat",
        "status",
        "winner",
        "agent_a",
        "agent_b",
        "game_id_seat_0",
        "game_id_seat_1",
    }
)
FUTURE_LEAKAGE_COLUMNS = frozenset(
    {
        "final_reward",
        "opponent_final_reward",
        "reward_difference",
        "win",
        "win_0",
        "win_1",
        "terminal_score",
        "chosen_action_json",
        "steps",
        "elapsed_seconds",
        "reward_a_seat_0",
        "reward_b_seat_0",
        "reward_a_seat_1",
        "reward_b_seat_1",
        "reward_difference_seat_0",
        "reward_difference_seat_1",
        "paired_reward_difference_a",
        "paired_win_rate_a",
        "wins_a",
        "wins_b",
        "draws",
    }
)


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    """The columns used by the value model and the columns intentionally dropped."""

    categorical_columns: tuple[str, ...]
    numeric_columns: tuple[str, ...]
    excluded_columns: tuple[str, ...]

    @property
    def feature_columns(self) -> tuple[str, ...]:
        return self.categorical_columns + self.numeric_columns


@dataclass(frozen=True, slots=True)
class DataSplit:
    """A deterministic seed-grouped split of transition rows."""

    train: pd.DataFrame
    validation: pd.DataFrame
    train_seeds: tuple[int, ...]
    validation_seeds: tuple[int, ...]
    train_pairs: tuple[str, ...]
    validation_pairs: tuple[str, ...]


def load_tables(data_dir: Path) -> dict[str, pd.DataFrame]:
    """Load the three trajectory artifacts from ``data_dir``.

    Keeping all three tables in the loader makes the CLI fail early when a
    partial trajectory export is supplied, while the model itself trains from
    the transition table.
    """

    data_dir = Path(data_dir)
    tables: dict[str, pd.DataFrame] = {}
    for name in TABLE_NAMES:
        path = data_dir / f"{name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"missing {name}.parquet in {data_dir}")
        tables[name] = pd.read_parquet(path)
    return tables


def _require_columns(frame: pd.DataFrame, columns: set[str], table_name: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{table_name} is missing required columns: {', '.join(missing)}")


def validate_transitions(transitions: pd.DataFrame) -> pd.DataFrame:
    """Validate and copy the transition table used for fitting."""

    if not isinstance(transitions, pd.DataFrame):
        raise TypeError("transitions must be a pandas DataFrame")
    _require_columns(
        transitions,
        {TARGET_COLUMN, "seed", "pair_id", "game_id", "policy", "opponent"},
        "transitions",
    )
    if transitions.empty:
        raise ValueError("transitions is empty")
    frame = transitions.copy().reset_index(drop=True)
    for column in ("seed", TARGET_COLUMN):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].isna().any() or not np.isfinite(frame[column].to_numpy()).all():
            raise ValueError(f"transitions.{column} must contain finite values")
    for column in ("pair_id", "game_id", "policy", "opponent"):
        if frame[column].isna().any():
            raise ValueError(f"transitions.{column} must not contain missing values")
    frame["seed"] = frame["seed"].astype(np.int64)
    return frame


def _is_future_leakage_column(column: str) -> bool:
    lowered = column.lower()
    if lowered in FUTURE_LEAKAGE_COLUMNS:
        return True
    return (
        "final_reward" in lowered
        or lowered == TARGET_COLUMN
        or lowered.startswith("reward_difference_")
        or lowered in {"winner", "win"}
        or lowered.endswith("_win")
    )


def build_feature_spec(transitions: pd.DataFrame) -> FeatureSpec:
    """Infer safe categorical and numeric state features from transitions."""

    _require_columns(transitions, set(CATEGORICAL_FEATURES), "transitions")
    categorical = tuple(column for column in CATEGORICAL_FEATURES if column in transitions)
    numeric: list[str] = []
    excluded: list[str] = []
    for column in transitions.columns:
        if column in categorical:
            continue
        if column in IDENTIFIER_COLUMNS or _is_future_leakage_column(column):
            excluded.append(column)
            continue
        if pd.api.types.is_numeric_dtype(transitions[column]):
            if transitions[column].nunique(dropna=True) > 1:
                numeric.append(column)
            else:
                excluded.append(column)
        else:
            # Free-form text/object columns (for example actions) are not
            # state features unless explicitly listed as a safe category.
            excluded.append(column)
    if not numeric:
        raise ValueError("transitions has no numeric state features")
    return FeatureSpec(categorical, tuple(numeric), tuple(excluded))


def make_feature_frame(transitions: pd.DataFrame, feature_spec: FeatureSpec) -> pd.DataFrame:
    """Return a model-ready frame without target, identifiers, or outcomes."""

    columns = list(feature_spec.feature_columns)
    frame = transitions.loc[:, columns].copy()
    for column in feature_spec.categorical_columns:
        # Explicitly turn nulls into a stable category for the imputer and
        # ensure mixed object values cannot surprise OneHotEncoder.
        frame[column] = frame[column].astype(object).where(frame[column].notna(), "__MISSING__")
        frame[column] = frame[column].astype(str)
    for column in feature_spec.numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def split_by_seed(
    transitions: pd.DataFrame,
    train_seed_count: int = 24,
    validation_seed_count: int = 8,
) -> DataSplit:
    """Split sorted unique seeds, keeping every pair entirely in one side.

    The default is the 24/8 split used by the 32-seed development export.  A
    mismatch between the requested counts and observed seeds is an error: it
    prevents silently training on a different split after a data refresh.
    """

    frame = validate_transitions(transitions)
    if train_seed_count < 1 or validation_seed_count < 1:
        raise ValueError("train_seed_count and validation_seed_count must be positive")
    seeds = tuple(sorted(int(value) for value in frame["seed"].unique()))
    expected = train_seed_count + validation_seed_count
    if len(seeds) != expected:
        raise ValueError(
            f"expected exactly {expected} unique seeds ({train_seed_count} train + "
            f"{validation_seed_count} validation), found {len(seeds)}"
        )
    validation_seeds = tuple(seed for index, seed in enumerate(seeds) if index % 4 == 3)
    train_seeds = tuple(seed for seed in seeds if seed not in validation_seeds)
    if len(train_seeds) != train_seed_count or len(validation_seeds) != validation_seed_count:
        raise ValueError("24/8 split requires exactly every fourth seed in validation")

    pair_seed = frame.loc[:, ["pair_id", "seed"]].drop_duplicates()
    if pair_seed["pair_id"].isna().any():
        raise ValueError("pair_id must not be missing")
    pair_seed_counts = pair_seed.groupby("pair_id", sort=False)["seed"].nunique()
    if (pair_seed_counts > 1).any():
        raise ValueError("each pair_id must belong to exactly one seed")

    train_mask = frame["seed"].isin(train_seeds)
    validation_mask = frame["seed"].isin(validation_seeds)
    train = frame.loc[train_mask].copy()
    validation = frame.loc[validation_mask].copy()
    train_pairs = tuple(sorted(str(value) for value in train["pair_id"].unique()))
    validation_pairs = tuple(sorted(str(value) for value in validation["pair_id"].unique()))
    if set(train_pairs) & set(validation_pairs):
        raise AssertionError("pair leakage detected between train and validation")
    if set(train_seeds) & set(validation_seeds):
        raise AssertionError("seed leakage detected between train and validation")
    return DataSplit(train, validation, train_seeds, validation_seeds, train_pairs, validation_pairs)


# Alias kept short for callers writing an experiment notebook.
make_seed_split = split_by_seed


def make_regressor(random_state: int = 20260919, max_iter: int = 120) -> Pipeline:
    """Build the deterministic CPU-only model pipeline."""

    regressor = HistGradientBoostingRegressor(
        learning_rate=0.08,
        max_iter=max_iter,
        max_leaf_nodes=31,
        min_samples_leaf=30,
        l2_regularization=1.0,
        early_stopping=False,
        random_state=random_state,
    )
    return Pipeline([("imputer", SimpleImputer(strategy="median")), ("regressor", regressor)])


def _metrics(y_true: np.ndarray, prediction: np.ndarray) -> dict[str, float | int]:
    y_true = np.asarray(y_true, dtype=np.float64)
    prediction = np.asarray(prediction, dtype=np.float64)
    if y_true.size == 0 or y_true.shape != prediction.shape:
        raise ValueError("metric arrays must be non-empty and have the same shape")
    residual = y_true - prediction
    mse = float(np.mean(residual * residual))
    variance = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 0.0 if variance == 0 else float(1.0 - np.sum(residual * residual) / variance)
    return {
        "n": int(y_true.size),
        "mae": float(np.mean(np.abs(residual))),
        "mse": mse,
        "rmse": float(math.sqrt(mse)),
        "r2": r2,
    }


def _global_mean_prediction(train: pd.DataFrame, frame: pd.DataFrame) -> np.ndarray:
    value = float(train[TARGET_COLUMN].mean())
    return np.full(len(frame), value, dtype=np.float64)


def _time_only_prediction(train: pd.DataFrame, frame: pd.DataFrame) -> np.ndarray:
    global_mean = float(train[TARGET_COLUMN].mean())
    means = train.groupby("day")[TARGET_COLUMN].mean()
    return frame["day"].map(means).fillna(global_mean).to_numpy(dtype=np.float64)


def _feature_summary(frame: pd.DataFrame, feature_spec: FeatureSpec) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for column in feature_spec.feature_columns:
        series = frame[column]
        missing = int(series.isna().sum())
        numeric = column in feature_spec.numeric_columns
        row: dict[str, Any] = {
            "feature": column,
            "kind": "numeric" if numeric else "categorical",
            "dtype": str(series.dtype),
            "n_rows": int(len(series)),
            "n_missing": missing,
            "missing_fraction": float(missing / len(series)),
            "n_unique": int(series.nunique(dropna=True)),
            "mean": "",
            "std": "",
            "min": "",
            "max": "",
            "top_values": "",
        }
        if numeric:
            values = pd.to_numeric(series, errors="coerce")
            if values.notna().any():
                row.update(
                    {
                        "mean": float(values.mean()),
                        "std": float(values.std(ddof=0)),
                        "min": float(values.min()),
                        "max": float(values.max()),
                    }
                )
        else:
            top = series.astype(object).where(series.notna(), "__MISSING__").value_counts().head(5)
            row["top_values"] = json.dumps(
                {str(key): int(value) for key, value in top.items()}, ensure_ascii=False
            )
        rows.append(row)
    return rows


def _write_feature_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "feature",
        "kind",
        "dtype",
        "n_rows",
        "n_missing",
        "missing_fraction",
        "n_unique",
        "mean",
        "std",
        "min",
        "max",
        "top_values",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def train_value_model(
    tables: Mapping[str, pd.DataFrame],
    output_dir: Path,
    *,
    train_seed_count: int = 24,
    validation_seed_count: int = 8,
    random_state: int = 20260919,
    max_iter: int = 120,
    policy: str = "candidate",
    sample_every: int = 12,
) -> dict[str, Any]:
    """Fit baselines and a value model, writing all requested artifacts."""

    if "transitions" not in tables:
        raise ValueError("tables must include transitions")
    all_transitions = validate_transitions(tables["transitions"])
    transitions = all_transitions.loc[all_transitions["policy"] == policy].copy()
    if transitions.empty:
        raise ValueError(f"no transition rows for policy {policy!r}")
    if sample_every < 1:
        raise ValueError("sample_every must be positive")
    transitions = transitions.loc[transitions["step"] % sample_every == 0].reset_index(drop=True)
    split = split_by_seed(transitions, train_seed_count, validation_seed_count)
    feature_spec = build_feature_spec(transitions)
    train_x = make_feature_frame(split.train, feature_spec)
    validation_x = make_feature_frame(split.validation, feature_spec)
    train_y = split.train[TARGET_COLUMN].to_numpy(dtype=np.float64)
    validation_y = split.validation[TARGET_COLUMN].to_numpy(dtype=np.float64)

    model = make_regressor(random_state=random_state, max_iter=max_iter)
    model.fit(train_x, train_y)
    model_train_prediction = model.predict(train_x)
    model_validation_prediction = model.predict(validation_x)

    global_train_prediction = _global_mean_prediction(split.train, split.train)
    global_validation_prediction = _global_mean_prediction(split.train, split.validation)
    time_train_prediction = _time_only_prediction(split.train, split.train)
    time_validation_prediction = _time_only_prediction(split.train, split.validation)

    prediction_by_model = {
        "global_mean": (global_train_prediction, global_validation_prediction),
        "time_only": (time_train_prediction, time_validation_prediction),
        "hist_gradient_boosting": (model_train_prediction, model_validation_prediction),
    }
    model_metrics = {
        name: {"train": _metrics(train_y, train_prediction), "validation": _metrics(validation_y, validation_prediction)}
        for name, (train_prediction, validation_prediction) in prediction_by_model.items()
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "value_model.joblib"
    joblib.dump(
        {
            "model": model,
            "target_column": TARGET_COLUMN,
            "feature_columns": list(feature_spec.feature_columns),
            "categorical_columns": list(feature_spec.categorical_columns),
            "numeric_columns": list(feature_spec.numeric_columns),
            "excluded_columns": list(feature_spec.excluded_columns),
            "random_state": random_state,
        },
        model_path,
    )

    seed_series = transitions["seed"]
    train_mask = seed_series.isin(split.train_seeds).to_numpy()
    validation_mask = ~train_mask
    all_global = np.empty(len(transitions), dtype=np.float64)
    all_time = np.empty(len(transitions), dtype=np.float64)
    all_model = np.empty(len(transitions), dtype=np.float64)
    all_global[train_mask] = global_train_prediction
    all_global[validation_mask] = global_validation_prediction
    all_time[train_mask] = time_train_prediction
    all_time[validation_mask] = time_validation_prediction
    all_model[train_mask] = model_train_prediction
    all_model[validation_mask] = model_validation_prediction

    prediction_columns: dict[str, Any] = {
        "row_index": np.arange(len(transitions), dtype=np.int64),
        "split": np.where(train_mask, "train", "validation"),
        "seed": transitions["seed"].to_numpy(dtype=np.int64),
        "pair_id": transitions["pair_id"].astype(str).to_numpy(),
        "game_id": transitions["game_id"].astype(str).to_numpy(),
        "policy": transitions["policy"].astype(str).to_numpy(),
        "opponent": transitions["opponent"].astype(str).to_numpy(),
        "step": transitions["step"].to_numpy(dtype=np.int64)
        if "step" in transitions
        else np.full(len(transitions), -1, dtype=np.int64),
        "target_reward_difference": transitions[TARGET_COLUMN].to_numpy(dtype=np.float64),
        "target": transitions[TARGET_COLUMN].to_numpy(dtype=np.float64),
        "prediction_global_mean": all_global,
        "prediction_time_only": all_time,
        "prediction_hist_gradient_boosting": all_model,
        "prediction": all_model,
    }
    predictions = pd.DataFrame(prediction_columns)
    predictions.to_parquet(output_dir / "predictions.parquet", index=False)
    _write_feature_summary(output_dir / "feature_summary.csv", _feature_summary(transitions, feature_spec))

    action_counts = (
        transitions["action_type"].fillna("__MISSING__").astype(str).value_counts().to_dict()
        if "action_type" in transitions
        else {}
    )
    eda_payload: dict[str, Any] = {
        "policy": policy,
        "all_transition_rows": int(len(all_transitions)),
        "policy_transition_rows_before_sampling": int(
            (all_transitions["policy"] == policy).sum()
        ),
        "policy_transition_rows_after_sampling": int(len(transitions)),
        "sample_every": sample_every,
        "unique_seeds": int(transitions["seed"].nunique()),
        "unique_games": int(transitions["game_id"].nunique()),
        "target": {
            "mean": float(transitions[TARGET_COLUMN].mean()),
            "std": float(transitions[TARGET_COLUMN].std(ddof=0)),
            "min": float(transitions[TARGET_COLUMN].min()),
            "max": float(transitions[TARGET_COLUMN].max()),
        },
        "action_type_counts": {str(key): int(value) for key, value in action_counts.items()},
        "feature_count": len(feature_spec.feature_columns),
        "excluded_feature_count": len(feature_spec.excluded_columns),
        "limitations": [
            "Only the selected policy is modeled to avoid policy identity leakage.",
            "All development games use one opponent, so this is a pipeline sanity check, not a general value model.",
            "Rows from the same seed and paired seat swap stay in one split.",
        ],
    }
    _write_json(output_dir / "eda_summary.json", eda_payload)

    split_payload: dict[str, Any] = {
        "strategy": "interleaved seed split; every fourth sorted seed is validation",
        "seed_column": "seed",
        "group_columns": ["seed", "pair_id"],
        "train_seed_count": len(split.train_seeds),
        "validation_seed_count": len(split.validation_seeds),
        "train_seeds": list(split.train_seeds),
        "validation_seeds": list(split.validation_seeds),
        "train_pairs": list(split.train_pairs),
        "validation_pairs": list(split.validation_pairs),
        "train": {
            "rows": int(len(split.train)),
            "seeds": list(split.train_seeds),
            "pair_ids": list(split.train_pairs),
        },
        "validation": {
            "rows": int(len(split.validation)),
            "seeds": list(split.validation_seeds),
            "pair_ids": list(split.validation_pairs),
        },
        "disjoint": {
            "seeds": not set(split.train_seeds) & set(split.validation_seeds),
            "pair_ids": not set(split.train_pairs) & set(split.validation_pairs),
        },
    }
    _write_json(output_dir / "data_split.json", split_payload)

    table_rows = {
        name: {"rows": int(len(frame)), "columns": list(frame.columns)}
        for name, frame in tables.items()
    }
    metrics_payload: dict[str, Any] = {
        "target_column": TARGET_COLUMN,
        "target_definition": "actor-centric final reward minus opponent final reward",
        "policy": policy,
        "sample_every": sample_every,
        "input_tables": table_rows,
        "model_artifact": model_path.name,
        "feature_columns": list(feature_spec.feature_columns),
        "excluded_columns": list(feature_spec.excluded_columns),
        "models": model_metrics,
        "validation": {name: values["validation"] for name, values in model_metrics.items()},
        "train": {name: values["train"] for name, values in model_metrics.items()},
        "primary_model": "hist_gradient_boosting",
        "random_state": random_state,
        "max_iter": max_iter,
    }
    _write_json(output_dir / "metrics.json", metrics_payload)
    return metrics_payload


__all__ = [
    "CATEGORICAL_FEATURES",
    "DataSplit",
    "FeatureSpec",
    "TARGET_COLUMN",
    "build_feature_spec",
    "load_tables",
    "make_feature_frame",
    "make_regressor",
    "make_seed_split",
    "split_by_seed",
    "train_value_model",
    "validate_transitions",
]
