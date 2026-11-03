"""Named agents available to the local arena."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
import math

from kaggriculture_agent.agent import agent as baseline_agent
from kaggriculture_agent.independent_agent import agent as independent_v0_agent
from kaggriculture_agent.independent_agent import agent_8 as independent_8_agent
from kaggriculture_agent.independent_agent import agent_12 as independent_12_agent
from kaggriculture_agent.independent_agent import agent_16 as independent_v1_agent
from kaggriculture_agent.independent_agent import agent_workers as independent_workers_agent
from kaggriculture_agent.independent_agent import agent_workers_4 as independent_workers_4_agent
from kaggriculture_agent.independent_agent import agent_workers_6 as independent_workers_6_agent
from kaggriculture_agent.independent_agent import agent_workers_10 as independent_workers_10_agent
from kaggriculture_agent.independent_agent import agent_workers_7
from kaggriculture_agent.independent_agent import agent_workers_9
from kaggriculture_agent.independent_agent import agent_workers_strawberry
from kaggriculture_agent.independent_agent import agent_workers_tomato
from kaggriculture_agent.independent_agent import agent_workers_wheat
from kaggriculture_agent.independent_agent import (
    agent_workers_mature, agent_workers_batch, agent_workers_daily,
)
from kaggriculture_agent.planning_agent import PLANS, make_agent
from kaggriculture_agent.waste_shield import economy_mix50_waste_shield_agent
from kaggriculture_agent.public_rerank import public_rerank_agent
from kaggriculture_agent.public_hybrid import public_hybrid_agent
from kaggriculture_agent.strong_ensemble import strong_ensemble_agent

Agent = Callable[[dict], dict[str, list]]


def candidate_agent(obs: dict) -> dict[str, list]:
    """Current champion: front-running plus selective terminal liquidation.

    Sell MILK from day 28 at hour 12, then all remaining inventory on day 29.
    """

    return _liquidation_variant(obs, 28, start_hour=12, early_items=("MILK",))


def candidate_zero_sell_guard_agent(obs: dict) -> dict[str, list]:
    """Drop SELLs with no available stock when no unit can deposit this turn."""
    action = candidate_agent(obs)
    commands = [action.get("farmer", []), *action.get("hands", [])]
    if any(command and command[0] in ("DROP", "PLACE") for command in commands):
        return action

    shed = dict((obs.get("private", {}) or {}).get("shed", {}) or {})
    orders = []
    for order in action.get("market", []):
        if order and order[0] == "SELL" and len(order) >= 3:
            item = order[1]
            available = max(0, int(shed.get(item, 0)))
            if available <= 0:
                continue
            shed[item] = max(0, available - max(0, int(order[2])))
        elif order and order[0] in ("BUY_PRODUCT", "BUY_ANIMAL") and len(order) >= 3:
            item = order[1]
            shed[item] = max(0, int(shed.get(item, 0))) + max(0, int(order[2]))
        orders.append(order)
    return {**action, "market": orders}


@lru_cache(maxsize=None)
def _salem_module(
    variant: str,
    front_run_items: tuple[str, ...] | None = None,
    weed_replay_steps: int | None = None,
) -> ModuleType:
    """Load an isolated Salem module for one Arena variant and worker."""

    source = Path(__file__).resolve().parents[2] / "submissions" / "public-salem-2900" / "main.py"
    if not source.is_file():
        raise RuntimeError(f"public Salem agent source is missing: {source}")
    spec = spec_from_file_location(f"kaggriculture_public_salem_2900_{variant}", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load public Salem agent: {source}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    if front_run_items is not None:
        module._FR_ITEMS = front_run_items
    if weed_replay_steps is not None:
        module._WEED_REPLAY_STEPS = weed_replay_steps
    return module


def public_salem_agent(obs: dict) -> dict[str, list]:
    """Run the archived public Salem tape agent as a fixed Arena reference."""

    return _salem_module("reference").agent(obs)


_REFERENCE_FRONT_RUN_ITEMS = ("MELON", "MILK", "STRAWBERRY", "WOOL")


def salem_front_wheat_agent(obs: dict) -> dict[str, list]:
    """Reference policy with WHEAT added to one-step market front-running."""

    return _salem_module("front_wheat", _REFERENCE_FRONT_RUN_ITEMS + ("WHEAT",)).agent(obs)


def salem_front_fertilizer_agent(obs: dict) -> dict[str, list]:
    """Reference policy with FERTILIZER added to market front-running."""

    return _salem_module("front_fertilizer", _REFERENCE_FRONT_RUN_ITEMS + ("FERTILIZER",)).agent(
        obs
    )


def salem_front_wheat_fertilizer_agent(obs: dict) -> dict[str, list]:
    """Reference policy with both high-volume products front-run."""

    return _salem_module(
        "front_wheat_fertilizer", _REFERENCE_FRONT_RUN_ITEMS + ("WHEAT", "FERTILIZER")
    ).agent(obs)


def _weed_variant(obs: dict, steps: int) -> dict[str, list]:
    items = _REFERENCE_FRONT_RUN_ITEMS + ("WHEAT", "FERTILIZER")
    return _salem_module(f"weed_replay_{steps}", items, steps).agent(obs)


def salem_weed_replay_4_agent(obs: dict) -> dict[str, list]:
    return _weed_variant(obs, 4)


def salem_weed_replay_12_agent(obs: dict) -> dict[str, list]:
    return _weed_variant(obs, 12)


def salem_weed_replay_16_agent(obs: dict) -> dict[str, list]:
    return _weed_variant(obs, 16)


def _liquidation_variant(
    obs: dict,
    start_day: int,
    weed_replay_steps: int | None = None,
    front_run_items: tuple[str, ...] | None = None,
    start_hour: int = 0,
    early_items: tuple[str, ...] | None = None,
    early_fraction: float = 1.0,
    early_min_price: float | None = None,
) -> dict[str, list]:
    items = front_run_items or (_REFERENCE_FRONT_RUN_ITEMS + ("WHEAT", "FERTILIZER"))
    suffix = f"_weed_{weed_replay_steps}" if weed_replay_steps is not None else ""
    action = _salem_module(f"liquidate_{start_day}{suffix}", items, weed_replay_steps).agent(obs)
    day = int(obs.get("day", 0) or 0)
    hour = int(obs.get("hour", 0) or 0)
    if day < start_day or (day == start_day and hour < start_hour):
        return action

    shed = (obs.get("private", {}) or {}).get("shed", {}) or {}
    non_sell = [list(order) for order in action.get("market", []) if order[0] != "SELL"]
    sell_by_item: dict[str, int] = {}
    for order in action.get("market", []):
        if len(order) >= 3 and order[0] == "SELL":
            sell_by_item[str(order[1])] = max(sell_by_item.get(str(order[1]), 0), int(order[2]))
    force_items = None if day > start_day or early_items is None else set(early_items)
    if force_items is not None and early_min_price is not None:
        prices = (obs.get("market", {}) or {}).get("prices", {}) or {}
        force_items = {
            item for item in force_items if float(prices.get(item, 0) or 0) >= early_min_price
        }
    for item, quantity in shed.items():
        if force_items is not None and str(item) not in force_items:
            continue
        amount = max(0, int(quantity or 0))
        if force_items is not None:
            amount = min(amount, max(1, math.ceil(amount * early_fraction)))
        if amount:
            sell_by_item[str(item)] = max(sell_by_item.get(str(item), 0), amount)
    sells = [["SELL", item, quantity] for item, quantity in sorted(sell_by_item.items())]
    return {**action, "market": (non_sell + sells)[:10]}


def salem_liquidate_26_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 26)


def salem_liquidate_28_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 28)


def salem_liquidate_29_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29)


def salem_liquidate_29_weed_4_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29, 4)


def salem_liquidate_29_weed_10_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29, 10)


def salem_liquidate_29_weed_11_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29, 11)


def salem_liquidate_29_weed_12_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29, 12)


def salem_liquidate_29_weed_13_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29, 13)


def salem_liquidate_29_weed_14_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29, 14)


def salem_liquidate_29_weed_16_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29, 16)


def salem_liquidate_29_weed_20_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29, 20)


def salem_liquidate_29_weed_24_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29, 24)


def salem_liquidate_29_weed_32_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29, 32)


_CURRENT_FRONT_RUN_ITEMS = _REFERENCE_FRONT_RUN_ITEMS + ("WHEAT", "FERTILIZER")


def salem_liquidate_29_front_carrot_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29, front_run_items=_CURRENT_FRONT_RUN_ITEMS + ("CARROT",))


def salem_liquidate_29_front_tomato_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29, front_run_items=_CURRENT_FRONT_RUN_ITEMS + ("TOMATO",))


def salem_liquidate_29_front_egg_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 29, front_run_items=_CURRENT_FRONT_RUN_ITEMS + ("EGG",))


def salem_liquidate_29_front_scarcity_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(
        obs,
        29,
        front_run_items=_CURRENT_FRONT_RUN_ITEMS + ("CARROT", "TOMATO", "EGG"),
    )


def salem_liquidate_28_hour_12_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 28, start_hour=12)


def salem_liquidate_28_hour_18_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 28, start_hour=18)


def salem_liquidate_28_hour_20_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 28, start_hour=20)


def salem_liquidate_28_hour_22_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 28, start_hour=22)


def _selective_early_liquidation(obs: dict, item: str, hour: int = 12) -> dict[str, list]:
    return _liquidation_variant(obs, 28, start_hour=hour, early_items=(item,))


def _selective_early_liquidation_items(
    obs: dict, items: tuple[str, ...], hour: int = 12
) -> dict[str, list]:
    return _liquidation_variant(obs, 28, start_hour=hour, early_items=items)


def salem_early_wheat_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation(obs, "WHEAT")


def salem_early_fertilizer_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation(obs, "FERTILIZER")


def salem_early_melon_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation(obs, "MELON")


def salem_early_milk_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation(obs, "MILK")


def salem_early_milk_6_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation(obs, "MILK", 6)


def salem_early_milk_9_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation(obs, "MILK", 9)


def salem_early_milk_15_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation(obs, "MILK", 15)


def salem_early_milk_18_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation(obs, "MILK", 18)


def salem_early_milk_day_27_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 27, start_hour=12, early_items=("MILK",))


def salem_early_milk_day_26_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 26, start_hour=12, early_items=("MILK",))


def salem_early_milk_fraction_25_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 28, start_hour=12, early_items=("MILK",), early_fraction=0.25)


def salem_early_milk_fraction_50_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 28, start_hour=12, early_items=("MILK",), early_fraction=0.5)


def salem_early_milk_fraction_75_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 28, start_hour=12, early_items=("MILK",), early_fraction=0.75)


def salem_early_milk_price_50_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 28, start_hour=12, early_items=("MILK",), early_min_price=50)


def salem_early_milk_price_100_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 28, start_hour=12, early_items=("MILK",), early_min_price=100)


def salem_early_milk_price_150_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 28, start_hour=12, early_items=("MILK",), early_min_price=150)


def salem_early_milk_price_200_agent(obs: dict) -> dict[str, list]:
    return _liquidation_variant(obs, 28, start_hour=12, early_items=("MILK",), early_min_price=200)


def salem_early_strawberry_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation(obs, "STRAWBERRY")


def salem_early_strawberry_18_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation(obs, "STRAWBERRY", 18)


def salem_early_strawberry_20_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation(obs, "STRAWBERRY", 20)


def salem_early_strawberry_22_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation(obs, "STRAWBERRY", 22)


def salem_early_wool_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation(obs, "WOOL")


def salem_early_milk_strawberry_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation_items(obs, ("MILK", "STRAWBERRY"))


def salem_early_milk_wool_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation_items(obs, ("MILK", "WOOL"))


def salem_early_milk_melon_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation_items(obs, ("MILK", "MELON"))


def salem_early_milk_strawberry_wool_agent(obs: dict) -> dict[str, list]:
    return _selective_early_liquidation_items(obs, ("MILK", "STRAWBERRY", "WOOL"))


AGENTS: dict[str, Agent] = {
    "baseline": baseline_agent,
    "candidate": candidate_agent,
    "candidate_zero_sell_guard": candidate_zero_sell_guard_agent,
    "public_rerank": public_rerank_agent,
    "public_hybrid": public_hybrid_agent,
    "strong_ensemble": strong_ensemble_agent,
    "economy_mix50_waste_shield": economy_mix50_waste_shield_agent,
    "independent_v0": independent_v0_agent,
    "independent_8": independent_8_agent,
    "independent_12": independent_12_agent,
    "independent_v1": independent_v1_agent,
    "independent_crop_v1": independent_8_agent,
    "independent_workers": independent_workers_agent,
    "independent_mature": agent_workers_mature,
    "independent_batch": agent_workers_batch,
    "independent_daily": agent_workers_daily,
    "independent_workers_4": independent_workers_4_agent,
    "independent_workers_6": independent_workers_6_agent,
    "independent_workers_10": independent_workers_10_agent,
    "independent_workers_7": agent_workers_7,
    "independent_workers_9": agent_workers_9,
    "independent_wheat": agent_workers_wheat,
    "independent_strawberry": agent_workers_strawberry,
    "independent_tomato": agent_workers_tomato,
    "public_salem": public_salem_agent,
    "salem_front_fertilizer": salem_front_fertilizer_agent,
    "salem_front_wheat": salem_front_wheat_agent,
    "salem_front_wheat_fertilizer": salem_front_wheat_fertilizer_agent,
    "salem_weed_replay_4": salem_weed_replay_4_agent,
    "salem_weed_replay_12": salem_weed_replay_12_agent,
    "salem_weed_replay_16": salem_weed_replay_16_agent,
    "salem_liquidate_26": salem_liquidate_26_agent,
    "salem_liquidate_28": salem_liquidate_28_agent,
    "salem_liquidate_29": salem_liquidate_29_agent,
    "salem_liquidate_29_weed_4": salem_liquidate_29_weed_4_agent,
    "salem_liquidate_29_weed_10": salem_liquidate_29_weed_10_agent,
    "salem_liquidate_29_weed_11": salem_liquidate_29_weed_11_agent,
    "salem_liquidate_29_weed_12": salem_liquidate_29_weed_12_agent,
    "salem_liquidate_29_weed_13": salem_liquidate_29_weed_13_agent,
    "salem_liquidate_29_weed_14": salem_liquidate_29_weed_14_agent,
    "salem_liquidate_29_weed_16": salem_liquidate_29_weed_16_agent,
    "salem_liquidate_29_weed_20": salem_liquidate_29_weed_20_agent,
    "salem_liquidate_29_weed_24": salem_liquidate_29_weed_24_agent,
    "salem_liquidate_29_weed_32": salem_liquidate_29_weed_32_agent,
    "salem_liquidate_29_front_carrot": salem_liquidate_29_front_carrot_agent,
    "salem_liquidate_29_front_tomato": salem_liquidate_29_front_tomato_agent,
    "salem_liquidate_29_front_egg": salem_liquidate_29_front_egg_agent,
    "salem_liquidate_29_front_scarcity": salem_liquidate_29_front_scarcity_agent,
    "salem_liquidate_28_hour_12": salem_liquidate_28_hour_12_agent,
    "salem_liquidate_28_hour_18": salem_liquidate_28_hour_18_agent,
    "salem_liquidate_28_hour_20": salem_liquidate_28_hour_20_agent,
    "salem_liquidate_28_hour_22": salem_liquidate_28_hour_22_agent,
    "salem_early_wheat": salem_early_wheat_agent,
    "salem_early_fertilizer": salem_early_fertilizer_agent,
    "salem_early_melon": salem_early_melon_agent,
    "salem_early_milk": salem_early_milk_agent,
    "salem_early_milk_6": salem_early_milk_6_agent,
    "salem_early_milk_9": salem_early_milk_9_agent,
    "salem_early_milk_15": salem_early_milk_15_agent,
    "salem_early_milk_18": salem_early_milk_18_agent,
    "salem_early_milk_day_27": salem_early_milk_day_27_agent,
    "salem_early_milk_day_26": salem_early_milk_day_26_agent,
    "salem_early_milk_fraction_25": salem_early_milk_fraction_25_agent,
    "salem_early_milk_fraction_50": salem_early_milk_fraction_50_agent,
    "salem_early_milk_fraction_75": salem_early_milk_fraction_75_agent,
    "salem_early_milk_price_50": salem_early_milk_price_50_agent,
    "salem_early_milk_price_100": salem_early_milk_price_100_agent,
    "salem_early_milk_price_150": salem_early_milk_price_150_agent,
    "salem_early_milk_price_200": salem_early_milk_price_200_agent,
    "salem_early_strawberry": salem_early_strawberry_agent,
    "salem_early_strawberry_18": salem_early_strawberry_18_agent,
    "salem_early_strawberry_20": salem_early_strawberry_20_agent,
    "salem_early_strawberry_22": salem_early_strawberry_22_agent,
    "salem_early_wool": salem_early_wool_agent,
    "salem_early_milk_strawberry": salem_early_milk_strawberry_agent,
    "salem_early_milk_wool": salem_early_milk_wool_agent,
    "salem_early_milk_melon": salem_early_milk_melon_agent,
    "salem_early_milk_strawberry_wool": salem_early_milk_strawberry_wool_agent,
}


AGENTS.update({name: make_agent(name) for name in PLANS})


def get_agent(name: str) -> Agent:
    """Return a registered agent by name."""

    try:
        return AGENTS[name]
    except KeyError as exc:
        choices = ", ".join(sorted(AGENTS))
        raise ValueError(f"unknown agent {name!r}; available: {choices}") from exc


def agent_names() -> tuple[str, ...]:
    return tuple(sorted(AGENTS))
