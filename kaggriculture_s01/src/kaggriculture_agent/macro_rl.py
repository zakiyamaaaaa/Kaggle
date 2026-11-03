"""Small standard-library macro policy layered over the planning executor."""

from __future__ import annotations

from math import exp
from typing import Any

from .planning_agent import PLANS, agent_for_plan


ACTIONS = (
    "economy_mix25",
    "economy_mix50",
    "economy_mix75",
    "economy_fert50",
    "planner_cows8",
    "planner_sheep8",
)
FEATURE_NAMES = (
    "constant",
    "day",
    "hour",
    "own_cash",
    "other_cash",
    "cash_margin",
    "own_hands",
    "other_hands",
    "own_land",
    "other_land",
    "own_cows",
    "own_sheep",
    "own_geese",
    "own_crops",
    "shed_products",
    "animal_price_signal",
)


def _farm_counts(farm: dict[str, Any]) -> dict[str, int]:
    counts = {"COW": 0, "SHEEP": 0, "GOOSE": 0, "CROP": 0, "FERTILIZED": 0}
    for row in farm.get("tiles", []):
        for tile in row:
            if not isinstance(tile, dict):
                continue
            animal = tile.get("animal")
            if animal in counts:
                counts[animal] += 1
            if tile.get("crop"):
                counts["CROP"] += 1
            if int(tile.get("fertilized_until_day", -1)) >= 0:
                counts["FERTILIZED"] += 1
    return counts


def features(obs: dict[str, Any]) -> list[float]:
    """Return bounded, observation-only features shared by training and runtime."""
    player = int(obs.get("player", 0))
    farms = obs.get("farms", [{}, {}])
    own, other = farms[player], farms[1 - player]
    own_counts = _farm_counts(own)
    prices = obs.get("market", {}).get("prices", {})
    shed = obs.get("private", {}).get("shed", {})
    own_cash = float(own.get("money", 0))
    other_cash = float(other.get("money", 0))
    product_prices = [float(prices.get(item, 0)) for item in ("EGG", "MILK", "WOOL")]
    return [
        1.0,
        float(obs.get("day", 0)) / 29.0,
        float(obs.get("hour", 0)) / 23.0,
        min(2.0, own_cash / 50_000.0),
        min(2.0, other_cash / 50_000.0),
        max(-2.0, min(2.0, (own_cash - other_cash) / 50_000.0)),
        min(1.5, len(own.get("hands", [])) / 12.0),
        min(1.5, len(other.get("hands", [])) / 12.0),
        len(own.get("unlocked_quadrants", [])) / 4.0,
        len(other.get("unlocked_quadrants", [])) / 4.0,
        own_counts["COW"] / 12.0,
        own_counts["SHEEP"] / 12.0,
        own_counts["GOOSE"] / 12.0,
        own_counts["CROP"] / 50.0,
        sum(float(shed.get(item, 0)) for item in ("EGG", "MILK", "WOOL")) / 100.0,
        min(2.0, sum(product_prices) / 600.0),
    ]


def probabilities(model: dict[str, Any], values: list[float]) -> list[float]:
    logits = [
        float(bias) + sum(float(weight) * value for weight, value in zip(row, values))
        for row, bias in zip(model["weights"], model["bias"])
    ]
    peak = max(logits)
    scores = [exp(max(-40.0, min(40.0, logit - peak))) for logit in logits]
    total = sum(scores)
    return [score / total for score in scores]


def make_macro_agent(model: dict[str, Any], name: str = "macro-rl"):
    """Create a deterministic policy that reconsiders its plan every three days."""
    state: dict[int, dict[str, Any]] = {}

    def agent(obs: dict[str, Any]) -> dict[str, list]:
        player = int(obs.get("player", 0))
        step = int(obs.get("step", 0))
        current = state.get(player)
        phase = step // 72
        if current is None or step <= current["step"] or phase != current["phase"]:
            probs = probabilities(model, features(obs))
            action = max(range(len(ACTIONS)), key=lambda index: (probs[index], -index))
            current = {"step": step, "phase": phase, "action": action}
            state[player] = current
        current["step"] = step
        plan_name = ACTIONS[current["action"]]
        return agent_for_plan(obs, PLANS[plan_name], name)

    return agent
