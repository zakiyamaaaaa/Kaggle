"""Baseline Kaggriculture agent.

The first version intentionally stays small and inspectable.  It provides a
working submission entry point while leaving room for better planning,
market reasoning, and optional LLM-assisted components later.
"""

from __future__ import annotations


def _empty_action() -> dict[str, list]:
    return {"farmer": ["PASS"], "hands": [], "market": []}


def agent(obs: dict) -> dict[str, list]:
    """Return one legal-shaped action for the current observation.

    This starter follows a simple carrot loop: buy one carrot seed, plant it
    on an empty tile, water it, harvest it at maturity, and sell the harvest.
    All unhandled situations safely pass, which makes the first local run
    useful for validating the environment and submission schema.
    """

    farms = obs.get("farms", [])
    player = int(obs.get("player", 0) or 0)
    private = obs.get("private", {}) or {}
    if not farms or player < 0 or player >= len(farms):
        return _empty_action()

    farm = farms[player]
    fx, fy = farm["farmer"]
    tile = farm["tiles"][fy][fx]
    day = int(obs.get("day", 0) or 0)
    seeds = private.get("seeds", {}) or {}
    shed = private.get("shed", {}) or {}

    market: list[list] = []
    if shed.get("CARROT", 0) > 0:
        market.append(["SELL", "CARROT", int(shed["CARROT"])])
    if seeds.get("CARROT", 0) == 0 and farm.get("money", 0) >= 20:
        market.append(["BUY_SEED", "CARROT", 1])

    farmer: list = ["PASS"]
    if tile is None and seeds.get("CARROT", 0) > 0:
        farmer = ["PLANT", "CARROT"]
    elif isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == "CARROT":
        age = day - int(tile.get("planted_day", day))
        if age >= 3:
            farmer = ["HARVEST"]
        elif not tile.get("watered_today", False):
            farmer = ["WATER"]

    return {"farmer": farmer, "hands": [], "market": market}
