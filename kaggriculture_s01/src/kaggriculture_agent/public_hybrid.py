"""Conservative public-data proposal hybrid.

The incumbent candidate remains the default.  A public behavior model can
select a complete logged action bundle only when the state is in a supported
phase, the predicted action has sufficient probability, the incumbent has no
secondary orders to invalidate, and the proposal passes shape checks.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from kaggriculture_agent.public_rerank import _state_features


ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "outputs" / "public_strategy_pipeline" / "2026-09" / "proposal_index.json"
MODEL_PATH = ROOT / "outputs" / "public_strategy_pipeline" / "2026-09" / "behavior_model" / "model.joblib"
SAFE_FARMER_ACTIONS = {
    "PASS", "NORTH", "SOUTH", "EAST", "WEST", "CARE", "WATER", "FEED", "HARVEST", "DIG",
}
MIN_ACTION_PROBABILITY = 0.20
MAX_PHASE = 1


@lru_cache(maxsize=1)
def _artifacts() -> tuple[dict[str, Any], dict[str, Any]]:
    return json.loads(INDEX_PATH.read_text(encoding="utf-8")), joblib.load(MODEL_PATH)


def _valid_bundle(action: Any, predicted_label: str, incumbent: dict[str, Any]) -> bool:
    if not isinstance(action, dict):
        return False
    farmer = action.get("farmer")
    hands = action.get("hands")
    market = action.get("market")
    if not isinstance(farmer, list) or not farmer or str(farmer[0]) != predicted_label:
        return False
    if predicted_label not in SAFE_FARMER_ACTIONS or len(farmer) != 1:
        return False
    if not isinstance(hands, list) or not isinstance(market, list):
        return False
    # Do not discard an incumbent's coupled secondary plan.  The first policy
    # only considers a complete empty-secondary-order bundle in a matching
    # incumbent state.
    if hands or market or incumbent.get("hands") or incumbent.get("market"):
        return False
    if len(market) > 10:
        return False
    for order in market:
        if not isinstance(order, list) or not order:
            return False
        if len(order) >= 3:
            try:
                if int(order[2]) < 0:
                    return False
            except (TypeError, ValueError):
                return False
    return True


def _nearest_template(index: dict[str, Any], state: dict[str, float], phase: int,
                      label: str) -> dict[str, Any] | None:
    templates = index["groups"].get(f"{phase}|{label}", [])
    if not templates:
        return None
    features = index["state_features"]
    means = np.asarray(index["means"], dtype=float)
    stds = np.maximum(np.asarray(index["stds"], dtype=float), 1e-6)
    vector = np.asarray([float(state[name]) for name in features], dtype=float)
    normalized = (vector - means) / stds
    best = min(
        templates,
        key=lambda template: float(np.mean((
            (np.asarray(template["features"], dtype=float) - means) / stds - normalized
        ) ** 2)),
    )
    return best


def public_hybrid_agent(
    obs: dict[str, Any], incumbent: dict[str, Any] | None = None
) -> dict[str, list]:
    """Return candidate by default and a narrowly gated public proposal rarely."""

    from kaggriculture_agent.registry import candidate_agent

    if incumbent is None:
        incumbent = candidate_agent(obs)
    step = int(obs.get("step", 0) or 0)
    day = int(obs.get("day", 0) or 0)
    if step % 12 != 0 or day >= 20 or incumbent.get("hands") or incumbent.get("market"):
        return incumbent
    try:
        index, artifact = _artifacts()
        state = _state_features(obs)
        columns = list(artifact["feature_columns"])
        probabilities = artifact["model"].predict_proba(pd.DataFrame([state], columns=columns))[0]
        labels = list(artifact["labels"])
        phase = min(MAX_PHASE, day // 10)
        for action_index in probabilities.argsort()[::-1][:3]:
            probability = float(probabilities[action_index])
            if probability < MIN_ACTION_PROBABILITY:
                continue
            label = labels[action_index]
            template = _nearest_template(index, state, phase, label)
            if template is None or not template.get("safe_empty_bundle"):
                continue
            action = template.get("action")
            if _valid_bundle(action, label, incumbent):
                return {
                    "farmer": list(action["farmer"]),
                    "hands": [list(order) for order in action["hands"]],
                    "market": [list(order) for order in action["market"]],
                }
    except (FileNotFoundError, KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        return incumbent
    return incumbent
