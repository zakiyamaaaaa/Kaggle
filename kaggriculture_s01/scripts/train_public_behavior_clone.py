#!/usr/bin/env python3
"""Train a leakage-safe first-stage behavior-cloning model.

The full action JSON is highly combinatorial.  This pilot predicts the
farmer's primary action from the observation-visible scalar state.  It is
intended as a measurable baseline and a component for a future planner, not a
submission policy by itself.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import balanced_accuracy_score, classification_report, top_k_accuracy_score


def farmer_action(action_json: str) -> str:
    try:
        action = json.loads(action_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return "INVALID"
    value = action.get("farmer") if isinstance(action, dict) else None
    if isinstance(value, list) and value:
        return str(value[0])
    return "NONE"


def market_ops(action_json: str) -> list[str]:
    try:
        action = json.loads(action_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    value = action.get("market") if isinstance(action, dict) else None
    if not isinstance(value, list):
        return []
    return [str(item[0]) for item in value if isinstance(item, list) and item]


def train(data_path: Path, output: Path, max_iter: int = 120) -> dict[str, Any]:
    frame = pd.read_parquet(data_path)
    required = {"episode_id", "chosen_action_json", "day", "hour"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing columns: {', '.join(missing)}")
    frame["farmer_action"] = frame["chosen_action_json"].map(farmer_action)
    frame["market_ops"] = frame["chosen_action_json"].map(market_ops)
    excluded = {
        "source_date", "episode_id", "seed", "seat", "step", "agent", "opponent_agent",
        "chosen_action_json", "final_reward", "opponent_final_reward", "reward_difference",
        "win", "status", "farmer_action", "market_ops",
    }
    feature_columns = [
        column for column in frame.columns
        if column not in excluded and pd.api.types.is_numeric_dtype(frame[column])
    ]
    if not feature_columns:
        raise ValueError("no numeric state features")
    # Group by episode, not by row. Both seats and all time steps stay together.
    episode_ids = np.array(sorted(frame["episode_id"].unique()))
    validation_ids = set(episode_ids[episode_ids % 5 == 0].tolist())
    if not validation_ids:
        validation_ids = set(episode_ids[-max(1, len(episode_ids) // 5):].tolist())
    validation_mask = frame["episode_id"].isin(validation_ids).to_numpy()
    train_mask = ~validation_mask
    X_train = frame.loc[train_mask, feature_columns].astype(float)
    X_valid = frame.loc[validation_mask, feature_columns].astype(float)
    y_train = frame.loc[train_mask, "farmer_action"]
    y_valid = frame.loc[validation_mask, "farmer_action"]
    model = HistGradientBoostingClassifier(
        learning_rate=0.08,
        max_iter=max_iter,
        max_leaf_nodes=31,
        min_samples_leaf=32,
        l2_regularization=1.0,
        random_state=20260923,
    )
    model.fit(X_train, y_train)
    predicted = model.predict(X_valid)
    probabilities = model.predict_proba(X_valid)
    labels = list(model.classes_)
    report = classification_report(y_valid, predicted, output_dict=True, zero_division=0)
    valid_with_pred = frame.loc[validation_mask, ["episode_id", "day", "agent", "farmer_action"]].copy()
    valid_with_pred["predicted"] = predicted
    day_accuracy = (
        valid_with_pred.assign(correct=valid_with_pred["farmer_action"] == valid_with_pred["predicted"])
        .groupby("day", as_index=True)["correct"]
        .mean()
        .round(6)
        .to_dict()
    )
    market_counts: dict[str, int] = {}
    for ops in frame.loc[validation_mask, "market_ops"]:
        for op in set(ops):
            market_counts[op] = market_counts.get(op, 0) + 1
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": model, "feature_columns": feature_columns, "target": "farmer_action", "labels": labels},
        output / "farmer_action_model.joblib",
    )
    metrics = {
        "format": "kaggriculture-public-behavior-clone-v1",
        "data": str(data_path),
        "rows": int(len(frame)),
        "episodes": int(frame["episode_id"].nunique()),
        "train_rows": int(train_mask.sum()),
        "validation_rows": int(validation_mask.sum()),
        "train_episodes": int(frame.loc[train_mask, "episode_id"].nunique()),
        "validation_episode_ids": sorted(int(x) for x in validation_ids),
        "feature_columns": feature_columns,
        "labels": labels,
        "accuracy": float((predicted == y_valid.to_numpy()).mean()),
        "balanced_accuracy": float(balanced_accuracy_score(y_valid, predicted)),
        "top3_accuracy": float(top_k_accuracy_score(y_valid, probabilities, k=3, labels=labels)),
        "classification_report": report,
        "accuracy_by_day": day_accuracy,
        "validation_market_operation_episode_rows": market_counts,
        "outcome_features_excluded": ["final_reward", "opponent_final_reward", "reward_difference", "win"],
        "opponent_private_state_excluded": True,
        "status": "baseline_component_only",
    }
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-iter", type=int, default=120)
    args = parser.parse_args()
    print(json.dumps(train(args.data, args.output, args.max_iter), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
