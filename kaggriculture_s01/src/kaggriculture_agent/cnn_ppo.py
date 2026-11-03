"""Dependency-free inference helpers for the CNN + PPO OMW threshold router."""

from __future__ import annotations

from math import exp, tanh
from typing import Any, Callable


THRESHOLDS = (0, 4, 8, 12, 16, 24)
CHANNELS = (
    "own_unlocked",
    "own_crop",
    "own_cow",
    "own_sheep",
    "own_goose",
    "own_fertilized",
    "rival_unlocked",
    "rival_crop",
    "rival_cow",
    "rival_sheep",
    "rival_goose",
    "rival_fertilized",
)
SCALARS = (
    "day",
    "hour",
    "own_cash",
    "rival_cash",
    "cash_margin",
    "wheat_price",
    "milk_price",
    "wool_price",
    "melon_price",
)


def _tile_channels(tile: Any) -> tuple[float, ...]:
    if not isinstance(tile, dict):
        return (0.0,) * 6
    animal = str(tile.get("animal") or "")
    crop = tile.get("crop")
    return (
        1.0,
        float(bool(crop)),
        float(animal == "COW"),
        float(animal == "SHEEP"),
        float(animal == "GOOSE"),
        float(int(tile.get("fertilized_until_day", -1) or -1) >= 0),
    )


def encode_observation(obs: dict[str, Any]) -> tuple[list[list[list[float]]], list[float]]:
    """Encode both farms as a 12-channel 10x10 image plus bounded scalars."""
    player = int(obs.get("player", 0))
    farms = obs.get("farms") or [{}, {}]
    own, rival = farms[player], farms[1 - player]
    own_tiles = own.get("tiles") or []
    rival_tiles = rival.get("tiles") or []
    image = [[[0.0 for _ in CHANNELS] for _ in range(10)] for _ in range(10)]
    for row in range(10):
        for column in range(10):
            own_tile = own_tiles[row][column] if row < len(own_tiles) and column < len(own_tiles[row]) else None
            rival_tile = (
                rival_tiles[row][column]
                if row < len(rival_tiles) and column < len(rival_tiles[row])
                else None
            )
            image[row][column] = list(_tile_channels(own_tile) + _tile_channels(rival_tile))
    prices = ((obs.get("market") or {}).get("prices") or {})
    own_cash = float(own.get("money", 0) or 0)
    rival_cash = float(rival.get("money", 0) or 0)
    scalars = [
        float(obs.get("day", 0) or 0) / 29.0,
        float(obs.get("hour", 0) or 0) / 23.0,
        min(2.5, own_cash / 100_000.0),
        min(2.5, rival_cash / 100_000.0),
        max(-2.5, min(2.5, (own_cash - rival_cash) / 50_000.0)),
        min(3.0, float(prices.get("WHEAT", 0) or 0) / 200.0),
        min(3.0, float(prices.get("MILK", 0) or 0) / 200.0),
        min(3.0, float(prices.get("WOOL", 0) or 0) / 200.0),
        min(3.0, float(prices.get("MELON", 0) or 0) / 200.0),
    ]
    return image, scalars


def policy_value(model: dict[str, Any], image, scalars) -> tuple[list[float], float]:
    """Run a 3x3 CNN, global pooling, and a shared actor-critic MLP."""
    conv = model["conv"]
    pooled = []
    for filter_index, kernel in enumerate(conv["weights"]):
        total = 0.0
        for row in range(8):
            for column in range(8):
                value = float(conv["bias"][filter_index])
                for channel in range(len(CHANNELS)):
                    for dy in range(3):
                        for dx in range(3):
                            value += image[row + dy][column + dx][channel] * kernel[channel][dy][dx]
                total += max(0.0, value)
        pooled.append(total / 64.0)
    shared = pooled + list(scalars)
    hidden = []
    for row, bias in zip(model["hidden"]["weights"], model["hidden"]["bias"]):
        hidden.append(tanh(float(bias) + sum(float(w) * x for w, x in zip(row, shared))))
    logits = [
        float(bias) + sum(float(w) * x for w, x in zip(row, hidden))
        for row, bias in zip(model["policy"]["weights"], model["policy"]["bias"])
    ]
    peak = max(logits)
    scores = [exp(max(-40.0, min(40.0, value - peak))) for value in logits]
    norm = sum(scores)
    probs = [value / norm for value in scores]
    value = float(model["value"]["bias"]) + sum(
        float(w) * x for w, x in zip(model["value"]["weights"], hidden)
    )
    return probs, value


def make_router_agent(
    model: dict[str, Any],
    base_agent: Callable[[dict[str, Any]], dict[str, list]],
    set_threshold: Callable[[int], None],
):
    """Choose a deterministic threshold once per game day, then run OMW."""
    state: dict[int, dict[str, int]] = {}

    def agent(obs: dict[str, Any]) -> dict[str, list]:
        player = int(obs.get("player", 0))
        step = int(obs.get("step", 0))
        day = int(obs.get("day", step // 24))
        current = state.get(player)
        if current is None or step <= current["step"] or day != current["day"]:
            image, scalars = encode_observation(obs)
            probs, _ = policy_value(model, image, scalars)
            action = max(range(len(THRESHOLDS)), key=lambda index: (probs[index], -index))
            current = {"step": step, "day": day, "action": action}
            state[player] = current
        current["step"] = step
        set_threshold(THRESHOLDS[current["action"]])
        return base_agent(obs)

    return agent
