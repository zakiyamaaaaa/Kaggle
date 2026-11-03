"""Conservative offline-value reranker for the September public-data experiment.

The reranker keeps the current candidate's market policy and only replaces a
parameter-free farmer action when the learned action-value model predicts a
clear uplift.  Any loading or schema error falls back to the incumbent, so the
experimental policy is safe to run in the local Arena.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd



ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "outputs" / "public_strategy_pipeline" / "2026-09" / "action_value_model" / "model.joblib"
ACTION_ARTIFACT = ROOT / "outputs" / "public_strategy_pipeline" / "2026-09" / "behavior_model" / "model.joblib"
SIMPLE_ACTIONS = {
    "PASS", "NORTH", "SOUTH", "EAST", "WEST", "HARVEST", "WATER", "CARE", "FEED", "DIG",
}


@lru_cache(maxsize=1)
def _models() -> tuple[dict[str, Any], dict[str, Any]]:
    return joblib.load(ARTIFACT), joblib.load(ACTION_ARTIFACT)


def _state_features(obs: dict[str, Any]) -> dict[str, float]:
    from kaggriculture_agent.local_arena import _trajectory_features

    seat = int(obs.get("player", 0) or 0)
    features = {key: float(value) for key, value in _trajectory_features(obs, seat).items()}
    day = int(obs.get("day", 0) or 0)
    step = int(obs.get("step", 0) or 0)
    features["phase"] = float(day // 10)
    features["hours_remaining"] = float(max(0, 720 - step))
    features["market_price_spread"] = features["market_max_price"] - features["market_min_price"]
    features["own_inventory_share"] = features["own_inventory_total"] / (
        features["own_inventory_total"] + features["market_inventory_total"] + 1.0
    )
    features["own_cash_share"] = features["own_money"] / (
        features["own_money"] + features["opponent_money"] + 1.0
    )
    features["inventory_advantage"] = features["own_inventory_total"] - features["opponent_inventory_total"]
    return features


def _action_name(action: dict[str, Any]) -> str:
    farmer = action.get("farmer") if isinstance(action, dict) else None
    return str(farmer[0]) if isinstance(farmer, list) and farmer else "PASS"


def _score_action(model: dict[str, Any], state: dict[str, float], label: str) -> float:
    labels = list(model["labels"])
    row = dict(state)
    for index in range(len(labels)):
        row[f"action_{index:03d}"] = float(labels[index] == label)
    columns = list(model["feature_columns"])
    return float(model["model"].predict(pd.DataFrame([row], columns=columns))[0])


def public_rerank_agent(obs: dict[str, Any]) -> dict[str, list]:
    """Run the incumbent and conservatively rerank simple farmer actions."""

    from kaggriculture_agent.registry import candidate_agent

    incumbent = candidate_agent(obs)
    if int(obs.get("step", 0) or 0) % 12 != 0:
        return incumbent
    try:
        action_value, action_model = _models()
        state = _state_features(obs)
        columns = list(action_model["feature_columns"])
        probabilities = action_model["model"].predict_proba(pd.DataFrame([state], columns=columns))[0]
        labels = list(action_model["labels"])
        top_indices = probabilities.argsort()[::-1][:3]
        base_name = _action_name(incumbent)
        candidates = [labels[index] for index in top_indices if labels[index] in SIMPLE_ACTIONS]
        if base_name not in candidates:
            candidates.append(base_name)
        score_rows = []
        for label in candidates:
            row = dict(state)
            for index, known_label in enumerate(action_value["labels"]):
                row[f"action_{index:03d}"] = float(known_label == label)
            score_rows.append(row)
        score_frame = pd.DataFrame(score_rows, columns=list(action_value["feature_columns"]))
        score_values = action_value["model"].predict(score_frame)
        scores = dict(zip(candidates, (float(value) for value in score_values)))
        selected = max(scores, key=scores.get)
        if selected in SIMPLE_ACTIONS and scores[selected] >= scores.get(base_name, 0.0) + 0.02:
            return {**incumbent, "farmer": [selected]}
    except (FileNotFoundError, KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        pass
    return incumbent
