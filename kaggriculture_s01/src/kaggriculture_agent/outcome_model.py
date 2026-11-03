"""Seed-grouped terminal-score models for conservative policy improvement."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from kaggriculture_agent.value_model import (
    build_feature_spec,
    make_regressor,
    split_by_seed,
    validate_transitions,
)

OUTCOME_COLUMN = "terminal_score"


def add_terminal_score(transitions: pd.DataFrame) -> pd.DataFrame:
    """Add actor-centric 1/0.5/0 labels without treating draws as losses."""

    frame = validate_transitions(transitions)
    own = frame["final_reward"].to_numpy(dtype=np.float64)
    other = frame["opponent_final_reward"].to_numpy(dtype=np.float64)
    frame[OUTCOME_COLUMN] = np.where(own > other, 1.0, np.where(own < other, 0.0, 0.5))
    return frame


def feature_groups(transitions: pd.DataFrame) -> dict[str, tuple[str, ...]]:
    """Return explicit ablation groups from leakage-safe numeric features."""

    safe = set(build_feature_spec(transitions).numeric_columns)
    basic_wanted = {
        "step",
        "day",
        "hour",
        "own_money",
        "opponent_money",
        "own_planted_tile_count",
        "opponent_planted_tile_count",
        "own_watered_tile_count",
        "opponent_watered_tile_count",
        "own_inventory_total",
        "market_inventory_total",
        "market_mean_price",
        "market_min_price",
        "market_max_price",
    }
    terminal_market_wanted = basic_wanted | {
        column
        for column in safe
        if column.startswith(("own_seed_", "own_shed_", "market_inventory_", "market_price_"))
    }
    return {
        "basic": tuple(sorted(safe & basic_wanted)),
        "terminal_market": tuple(sorted(safe & terminal_market_wanted)),
        "full": tuple(sorted(safe)),
    }


def _metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float | int]:
    target = np.asarray(target, dtype=np.float64)
    prediction = np.clip(np.asarray(prediction, dtype=np.float64), 0.0, 1.0)
    residual = target - prediction
    mse = float(np.mean(residual**2))
    return {
        "n": int(len(target)),
        "mae": float(np.mean(np.abs(residual))),
        "brier": mse,
        "rmse": math.sqrt(mse),
    }


def _last_state_metrics(frame: pd.DataFrame, prediction: np.ndarray) -> dict[str, float | int]:
    values = frame.loc[:, ["game_id", "step", OUTCOME_COLUMN]].copy()
    values["prediction"] = prediction
    last = values.sort_values(["game_id", "step"]).groupby("game_id", sort=False).tail(1)
    return _metrics(last[OUTCOME_COLUMN].to_numpy(), last["prediction"].to_numpy())


def train_outcome_models(
    transitions: pd.DataFrame,
    output: Path,
    *,
    policy: str = "candidate",
    sample_every: int = 12,
    random_state: int = 20260919,
) -> dict[str, Any]:
    """Train feature ablations and select by validation last-state Brier score."""

    if sample_every < 1:
        raise ValueError("sample_every must be positive")
    all_rows = add_terminal_score(transitions)
    rows = all_rows.loc[all_rows["policy"] == policy].copy()
    if rows.empty:
        raise ValueError(f"no transitions for policy {policy!r}")
    rows = rows.loc[rows["step"] % sample_every == 0].reset_index(drop=True)
    split = split_by_seed(rows)
    groups = feature_groups(rows)
    output.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    fitted = {}
    for name, columns in groups.items():
        if not columns:
            raise ValueError(f"feature group {name!r} is empty")
        train_x = split.train.loc[:, columns]
        validation_x = split.validation.loc[:, columns]
        train_y = split.train[OUTCOME_COLUMN].to_numpy(dtype=np.float64)
        validation_y = split.validation[OUTCOME_COLUMN].to_numpy(dtype=np.float64)
        model = make_regressor(random_state=random_state, max_iter=160)
        model.fit(train_x, train_y)
        train_prediction = model.predict(train_x)
        validation_prediction = model.predict(validation_x)
        results[name] = {
            "features": list(columns),
            "train_transition": _metrics(train_y, train_prediction),
            "validation_transition": _metrics(validation_y, validation_prediction),
            "validation_last_state": _last_state_metrics(split.validation, validation_prediction),
        }
        fitted[name] = model

    baseline_value = float(split.train[OUTCOME_COLUMN].mean())
    baseline_prediction = np.full(len(split.validation), baseline_value)
    baseline = {
        "value": baseline_value,
        "validation_transition": _metrics(
            split.validation[OUTCOME_COLUMN].to_numpy(), baseline_prediction
        ),
        "validation_last_state": _last_state_metrics(split.validation, baseline_prediction),
    }
    selected = min(
        results,
        key=lambda name: (results[name]["validation_last_state"]["brier"], name),
    )
    artifact = {
        "model": fitted[selected],
        "model_name": selected,
        "feature_columns": list(groups[selected]),
        "target": OUTCOME_COLUMN,
        "policy": policy,
        "sample_every": sample_every,
        "random_state": random_state,
    }
    joblib.dump(artifact, output / "outcome_model.joblib")
    payload = {
        "format": "kaggriculture-outcome-model-v1",
        "policy": policy,
        "target": "terminal win=1, draw=0.5, loss=0",
        "sample_every": sample_every,
        "effective_sample": {
            "train_seeds": len(split.train_seeds),
            "validation_seeds": len(split.validation_seeds),
            "train_games": int(split.train["game_id"].nunique()),
            "validation_games": int(split.validation["game_id"].nunique()),
            "train_rows": len(split.train),
            "validation_rows": len(split.validation),
        },
        "baseline": baseline,
        "models": results,
        "selected_model": selected,
        "selection_metric": "validation_last_state.brier",
        "limitations": [
            "Transitions from one game share a terminal label; game and seed counts are the effective sample sizes.",
            "This is a state-value model and cannot rank unseen actions until candidate-action features are added.",
            "Opponent identity is excluded; evaluation measures state signal rather than policy-name memorization.",
        ],
    }
    (output / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def train_from_directory(data: Path, output: Path, **kwargs: Any) -> dict[str, Any]:
    transitions = pd.read_parquet(data / "transitions.parquet")
    return train_outcome_models(transitions, output, **kwargs)


__all__ = [
    "OUTCOME_COLUMN",
    "add_terminal_score",
    "feature_groups",
    "train_from_directory",
    "train_outcome_models",
]
