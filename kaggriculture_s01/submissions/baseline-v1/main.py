"""Standalone Kaggriculture submission entry point.

This file intentionally has no project-local imports so it can be copied into
a Kaggle submission package as-is.
"""


def _empty_action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def agent(obs):
    """Small, safe carrot-loop baseline for the Kaggriculture environment."""

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

    market = []
    if shed.get("CARROT", 0) > 0:
        market.append(["SELL", "CARROT", int(shed["CARROT"])])
    if seeds.get("CARROT", 0) == 0 and farm.get("money", 0) >= 20:
        market.append(["BUY_SEED", "CARROT", 1])

    farmer = ["PASS"]
    if tile is None and seeds.get("CARROT", 0) > 0:
        farmer = ["PLANT", "CARROT"]
    elif isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == "CARROT":
        age = day - int(tile.get("planted_day", day))
        if age >= 3:
            farmer = ["HARVEST"]
        elif not tile.get("watered_today", False):
            farmer = ["WATER"]

    return {"farmer": farmer, "hands": [], "market": market}
