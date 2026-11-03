#!/usr/bin/env python3
"""Train a leakage-safe terminal win-probability model on public episodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor


def metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float | int]:
    target = np.asarray(target, dtype=float)
    prediction = np.clip(np.asarray(prediction, dtype=float), 0.0, 1.0)
    error = target - prediction
    brier = float(np.mean(error * error))
    return {"n": int(len(target)), "brier": brier, "rmse": float(np.sqrt(brier)), "mae": float(np.mean(np.abs(error)))}


def train(data: Path, output: Path, sample_every: int = 12, max_iter: int = 140) -> dict[str, Any]:
    frame = pd.read_parquet(data)
    required = {"episode_id", "seat", "step", "final_reward", "opponent_final_reward"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing columns: {', '.join(missing)}")
    frame["terminal_score"] = np.where(
        frame["final_reward"] > frame["opponent_final_reward"], 1.0,
        np.where(frame["final_reward"] < frame["opponent_final_reward"], 0.0, 0.5),
    )
    rows = frame.loc[frame["step"] % sample_every == 0].copy()
    excluded = {
        "source_date", "episode_id", "seed", "seat", "agent", "opponent_agent",
        "chosen_action_json", "final_reward", "opponent_final_reward", "reward_difference",
        "win", "status", "terminal_score",
    }
    feature_columns = [
        c for c in rows.columns
        if c not in excluded and pd.api.types.is_numeric_dtype(rows[c])
    ]
    episode_ids = np.array(sorted(rows["episode_id"].unique()))
    validation_ids = set(episode_ids[episode_ids % 5 == 0].tolist())
    if not validation_ids:
        validation_ids = set(episode_ids[-max(1, len(episode_ids) // 5):].tolist())
    valid_mask = rows["episode_id"].isin(validation_ids)
    train_mask = ~valid_mask
    groups = {
        "basic": [c for c in feature_columns if c in {
            "step", "day", "hour", "own_money", "opponent_money", "own_planted_tile_count",
            "opponent_planted_tile_count", "own_watered_tile_count", "opponent_watered_tile_count",
            "own_inventory_total", "market_inventory_total", "market_mean_price", "market_min_price",
            "market_max_price",
        }],
        "full": feature_columns,
    }
    results: dict[str, Any] = {}
    fitted: dict[str, Any] = {}
    for name, columns in groups.items():
        model = HistGradientBoostingRegressor(
            learning_rate=0.08,
            max_iter=max_iter,
            max_leaf_nodes=31,
            min_samples_leaf=32,
            l2_regularization=1.0,
            loss="squared_error",
            random_state=20260923,
        )
        model.fit(rows.loc[train_mask, columns], rows.loc[train_mask, "terminal_score"])
        pred = model.predict(rows.loc[valid_mask, columns])
        valid = rows.loc[valid_mask, ["episode_id", "seat", "step", "terminal_score"]].copy()
        valid["prediction"] = np.clip(pred, 0.0, 1.0)
        last = valid.sort_values(["episode_id", "seat", "step"]).groupby(["episode_id", "seat"], sort=False).tail(1)
        results[name] = {
            "features": columns,
            "validation_transition": metrics(valid["terminal_score"], valid["prediction"]),
            "validation_last_state": metrics(last["terminal_score"], last["prediction"]),
        }
        fitted[name] = model
    baseline_value = float(rows.loc[train_mask, "terminal_score"].mean())
    baseline_prediction = np.full(int(valid_mask.sum()), baseline_value)
    baseline_valid = rows.loc[valid_mask, ["episode_id", "seat", "step", "terminal_score"]].copy()
    baseline_valid["prediction"] = baseline_prediction
    baseline_last = baseline_valid.sort_values(["episode_id", "seat", "step"]).groupby(["episode_id", "seat"], sort=False).tail(1)
    baseline = {
        "value": baseline_value,
        "validation_transition": metrics(baseline_valid["terminal_score"], baseline_valid["prediction"]),
        "validation_last_state": metrics(baseline_last["terminal_score"], baseline_last["prediction"]),
    }
    selected = min(results, key=lambda key: (results[key]["validation_last_state"]["brier"], key))
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": fitted[selected], "model_name": selected, "feature_columns": groups[selected], "target": "terminal_score"},
        output / "outcome_model.joblib",
    )
    payload = {
        "format": "kaggriculture-public-outcome-model-v1",
        "data": str(data),
        "sample_every": sample_every,
        "rows": int(len(rows)),
        "episodes": int(frame["episode_id"].nunique()),
        "train_episodes": int(rows.loc[train_mask, "episode_id"].nunique()),
        "validation_episodes": int(rows.loc[valid_mask, "episode_id"].nunique()),
        "baseline": baseline,
        "models": results,
        "selected_model": selected,
        "outcome_features_excluded": ["final_reward", "opponent_final_reward", "reward_difference", "win"],
        "opponent_private_state_excluded": True,
        "limitations": [
            "All rows from one episode share one terminal label; episode count is the effective sample size.",
            "This is a state-value model and does not evaluate unseen actions.",
        ],
    }
    (output / "metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-every", type=int, default=12)
    parser.add_argument("--max-iter", type=int, default=140)
    args = parser.parse_args()
    print(json.dumps(train(args.data, args.output, args.sample_every, args.max_iter), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
