"""Conservative executor-side waste shield for ``economy_mix50``.

The shield deliberately does not re-plan.  It asks the incumbent planner for
its action and only replaces a unit or market command when the public
observation proves that the command cannot have the requested effect.  In
particular, PASS is preserved as an intentional action and potentially
partial operations (for example PICKUP of more stock than is available) are
left alone.

The small metrics hook is used by the diagnostic runner.  It is process-local
and keyed by the observed player, so it does not affect policy decisions.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from .planning_agent import PLANS, agent_for_plan


_BASE_PLAN = PLANS["economy_mix50"]
_SHIELD_NAME = "economy_mix50_waste_shield"
_SHED_ACCESS = {(4, 4), (5, 4), (4, 5), (5, 5)}
_MOVE_DELTAS = {
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
    "EAST": (1, 0),
    "WEST": (-1, 0),
}
_CROPS = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"}
_ANIMALS = {
    "GOOSE": ("COOP", "EGG"),
    "COW": ("PASTURE", "MILK"),
    "SHEEP": ("PASTURE", "WOOL"),
}
_SEED_PRICES = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}
_ANIMAL_PRICES = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
_METRICS: dict[int, Counter[str]] = {0: Counter(), 1: Counter()}


def _get(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    try:
        return value[key]
    except (KeyError, IndexError, TypeError):
        return getattr(value, key, default)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _positive(value: Any) -> int:
    return max(0, _int(value))


def _position(farm: Any, index: int) -> tuple[int, int] | None:
    value = _get(farm, "farmer", []) if index == 0 else (_get(farm, "hands", []) or [])[index - 1]
    if value is None or len(value) < 2:
        return None
    return (_int(value[0]), _int(value[1]))


def _tile(farm: Any, position: tuple[int, int] | None) -> Any:
    if position is None:
        return "LOCKED"
    tiles = _get(farm, "tiles", []) or []
    x, y = position
    if y < 0 or y >= len(tiles) or x < 0 or x >= len(tiles[y]):
        return "LOCKED"
    return tiles[y][x]


def _inventory(privates: Any, index: int) -> Any:
    inventories = _get(privates, "inventories", []) or []
    return inventories[index] if index < len(inventories) else {}


def _shed_total(shed: Any) -> int:
    return sum(_positive(amount) for amount in (shed or {}).values())


def _metric(player: int, key: str) -> None:
    _METRICS.setdefault(player, Counter())[key] += 1


def reset_metrics() -> None:
    """Reset process-local shield counters before a diagnostic episode."""

    for counter in _METRICS.values():
        counter.clear()


def metrics(player: int | None = None) -> dict[str, int] | dict[int, dict[str, int]]:
    """Return a copy of shield replacements, optionally for one player."""

    if player is not None:
        return dict(_METRICS.get(player, {}))
    return {index: dict(counter) for index, counter in _METRICS.items()}


def _pass(action: Any, player: int, reason: str) -> list[str]:
    if isinstance(action, list) and action:
        _metric(player, f"shielded.{action[0]}.{reason}")
    else:
        _metric(player, f"shielded.MALFORMED.{reason}")
    _metric(player, "shielded_total")
    return ["PASS"]


def _valid_quantity(action: list[Any]) -> bool:
    if len(action) < 3:
        return True
    try:
        return int(action[2]) > 0
    except (TypeError, ValueError):
        return False


def _unit_waste_reason(
    action: Any,
    position: tuple[int, int] | None,
    tile: Any,
    inventory: Any,
    seeds: Any,
    shed: Any,
    day: int,
    board_size: int,
    shed_capacity: int,
) -> str | None:
    """Return a reason only for a command that is certainly ineffective."""

    if not isinstance(action, list) or not action:
        return "malformed"
    op = action[0]
    if op == "PASS":
        return None
    if position is None:
        return "missing_actor"

    if op in _MOVE_DELTAS:
        dx, dy = _MOVE_DELTAS[op]
        x, y = position
        if not (0 <= x + dx < board_size and 0 <= y + dy < board_size):
            return "boundary"
        return None

    in_shed = position in _SHED_ACCESS
    if op == "PICKUP":
        if not in_shed:
            return "not_at_shed"
        if len(action) < 2 or not _valid_quantity(action):
            return "invalid_request"
        if _positive(_get(shed, action[1], 0)) <= 0:
            return "missing_resource"
        # Requests larger than stock are intentionally retained: PICKUP is a
        # valid partial operation in the engine and is not provably wasteful.
        return None

    if op == "DROP":
        if not in_shed:
            return "not_at_shed"
        if not any(_positive(amount) for amount in (inventory or {}).values()):
            return "empty_inventory"
        # The engine discards carried goods when DROP is attempted on a full
        # shed.  PASS preserves the goods for a later route and is safer.
        if _shed_total(shed) >= shed_capacity:
            return "shed_full"
        return None

    if op == "PLACE":
        if len(action) < 2:
            return "invalid_request"
        item = action[1]
        carrying = _positive(_get(inventory, item, 0))
        if item in _ANIMALS:
            structure, _ = _ANIMALS[item]
            if isinstance(tile, dict) and _get(tile, "kind") == structure and "animal" not in tile:
                return None if carrying else "missing_resource"
            # On a shed-access tile an animal can validly be returned to the
            # shed via PLACE, so retain that path when capacity is available.
            if in_shed and carrying and _shed_total(shed) < shed_capacity:
                return None
            return "invalid_target" if carrying else "missing_resource"
        if not in_shed:
            return "not_at_shed"
        if not carrying or not _valid_quantity(action):
            return "missing_resource" if carrying == 0 else "invalid_request"
        if _shed_total(shed) >= shed_capacity:
            return "shed_full"
        return None

    if tile == "LOCKED":
        return "locked_tile"

    if op == "PLANT":
        if len(action) < 2 or action[1] not in _CROPS:
            return "invalid_crop"
        if tile is not None:
            return "occupied_tile"
        if _positive(_get(seeds, action[1], 0)) <= 0:
            return "missing_seed"
        return None

    if op == "WATER":
        if not isinstance(tile, dict) or _get(tile, "kind") != "PLANT":
            return "not_a_plant"
        if bool(_get(tile, "watered_today", False)):
            return "already_watered"
        return None

    if op == "HARVEST":
        if not isinstance(tile, dict) or _positive(_get(tile, "yield_units", 0)) <= 0:
            return "no_yield"
        if _get(tile, "kind") == "PLANT":
            crop = _get(tile, "crop")
            first = {"WHEAT": 2, "CARROT": 2, "TOMATO": 8, "STRAWBERRY": 10, "MELON": 10}
            if crop not in first or day - _int(_get(tile, "planted_day", day)) < first[crop]:
                return "immature"
        return None

    if op == "FERTILIZE":
        if not isinstance(tile, dict) or _get(tile, "kind") != "PLANT":
            return "not_a_plant"
        if _positive(_get(inventory, "FERTILIZER", 0)) <= 0:
            return "missing_resource"
        if _int(_get(tile, "fertilized_until_day", -1)) >= day:
            return "already_fertilized"
        return None

    if op == "DIG":
        if tile is None or (isinstance(tile, dict) and "animal" in tile):
            return "invalid_target"
        return None

    if op in ("BUILD_COOP", "BUILD_PASTURE"):
        return None if tile is None else "occupied_tile"

    if op == "FEED":
        if not isinstance(tile, dict) or "animal" not in tile:
            return "not_animal"
        if bool(_get(tile, "fed_today", False)):
            return "already_fed"
        if _positive(_get(inventory, "WHEAT", 0)) <= 0:
            return "missing_resource"
        return None

    if op == "COLLECT_FERTILIZER":
        if not isinstance(tile, dict) or "animal" not in tile:
            return "not_animal"
        return None if bool(_get(tile, "fertilizer_available", False)) else "unavailable"

    if op == "CARE":
        if not isinstance(tile, dict) or "animal" not in tile:
            return "not_animal"
        return "already_cared" if bool(_get(tile, "cared_today", False)) else None

    # Unknown operations are rejected by the engine's action implementation;
    # replacing them avoids a known malformed/silent command.
    return "unknown_operation"


def _market_waste_reason(
    order: Any,
    farm: Any,
    private: Any,
    prior_orders: list[Any],
    action_units: list[Any],
) -> str | None:
    """Shield only market failures independent of same-turn side effects."""

    if not isinstance(order, list) or not order:
        return "malformed"
    op = order[0]
    if op == "SELL":
        if len(order) < 3:
            return "invalid_request"
        item = order[1]
        try:
            quantity = int(order[2])
        except (TypeError, ValueError):
            return "invalid_request"
        if quantity <= 0:
            return "invalid_request"
        # A previous same-turn unit action can deposit carried goods.  Keep the
        # order if that path exists; otherwise zero current stock is definitive.
        may_deposit = any(
            isinstance(command, list)
            and command
            and command[0] in ("DROP", "PLACE")
            for command in action_units
        )
        if not may_deposit and _positive(_get(_get(private, "shed", {}), item, 0)) <= 0:
            return "missing_resource"
        return None
    if op == "HIRE":
        if any(isinstance(previous, list) and previous and previous[0] == "SELL" for previous in prior_orders):
            return None
        hires = _int(_get(farm, "hires_today", 0))
        a, b = 1, 1
        for _ in range(hires):
            a, b = b, a + b
        return "missing_cash" if _int(_get(farm, "money", 0)) < a else None
    if op == "BUY_LAND":
        if any(isinstance(previous, list) and previous and previous[0] == "SELL" for previous in prior_orders):
            return None
        unlocked = len(_get(farm, "unlocked_quadrants", []) or []) - 1
        if unlocked >= 3:
            return "all_land_owned"
        costs = (1000, 2000, 4000)
        return "missing_cash" if _int(_get(farm, "money", 0)) < costs[unlocked] else None
    if op in ("BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL"):
        if len(order) < 3:
            return "invalid_request"
        try:
            quantity = int(order[2])
        except (TypeError, ValueError):
            return "invalid_request"
        if quantity <= 0:
            return "invalid_request"
        if any(isinstance(previous, list) and previous and previous[0] == "SELL" for previous in prior_orders):
            return None
        item = order[1]
        if op == "BUY_SEED":
            price = _SEED_PRICES.get(item)
            capacity_failure = False
        elif op == "BUY_PRODUCT":
            price = None if item not in ("WHEAT", "FERTILIZER") else 1
            capacity_failure = True
        else:
            price = _ANIMAL_PRICES.get(item)
            capacity_failure = True
        if price is None:
            return "invalid_item"
        # Orders are committed one unit at a time; insufficient cash for the
        # full request still permits a valid partial purchase.  Shield only
        # when even the first unit cannot be bought.
        if op == "BUY_SEED" and _int(_get(farm, "money", 0)) < price:
            return "missing_cash"
        # Dynamic product prices are observable but can change after the
        # opponent's order, so only a full shed is a definitive capacity fail.
        if op != "BUY_SEED" and _int(_get(farm, "money", 0)) <= 0:
            return "missing_cash"
        if capacity_failure and _shed_total(_get(private, "shed", {})) >= 100:
            return "shed_full"
    return None


def shield_action(obs: dict[str, Any], action: dict[str, Any]) -> dict[str, list]:
    """Return the incumbent action with only provably wasteful commands removed."""

    player = _int(_get(obs, "player", 0))
    farms = _get(obs, "farms", []) or []
    if player < 0 or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    private = _get(obs, "private", {}) or {}
    shed = _get(private, "shed", {}) or {}
    seeds = _get(private, "seeds", {}) or {}
    hands = _get(farm, "hands", []) or []
    positions = [_position(farm, index) for index in range(1 + len(hands))]
    inventories = [_inventory(private, index) for index in range(len(positions))]
    tiles = _get(farm, "tiles", []) or []
    board_size = len(tiles) or 10
    day = _int(_get(obs, "day", 0))
    shed_capacity = 100

    raw = action if isinstance(action, dict) else {}
    farmer = raw.get("farmer", ["PASS"])
    raw_hands = raw.get("hands", [])
    if not isinstance(raw_hands, list):
        raw_hands = []
    unit_actions = [farmer, *raw_hands[: len(hands)]]
    unit_actions += [["PASS"]] * (len(positions) - len(unit_actions))

    # The interpreter cancels every PLANT request for a crop when that turn's
    # demand exceeds the shared seed stock.  Replace that whole known-failing
    # group; this never touches a crop request that can be accepted.
    plant_counts: Counter[str] = Counter(
        command[1]
        for command in unit_actions
        if isinstance(command, list) and len(command) >= 2 and command[0] == "PLANT"
    )
    blocked_crops = {
        crop for crop, count in plant_counts.items() if count > _positive(_get(seeds, crop, 0))
    }

    shielded_units: list[list[Any]] = []
    for index, command in enumerate(unit_actions):
        reason = _unit_waste_reason(
            command,
            positions[index],
            _tile(farm, positions[index]),
            inventories[index],
            seeds,
            shed,
            day,
            board_size,
            shed_capacity,
        )
        if (
            reason is None
            and isinstance(command, list)
            and len(command) >= 2
            and command[0] == "PLANT"
            and command[1] in blocked_crops
        ):
            reason = "shared_seed_shortage"
        shielded_units.append(_pass(command, player, reason) if reason else deepcopy(command))

    action_units = shielded_units
    raw_market = raw.get("market", [])
    if not isinstance(raw_market, list):
        raw_market = []
    market: list[list[Any]] = []
    prior_orders: list[Any] = []
    for order in raw_market[:10]:
        reason = _market_waste_reason(order, farm, private, prior_orders, action_units)
        market.append(_pass(order, player, reason) if reason else deepcopy(order))
        prior_orders.append(order)

    return {"farmer": action_units[0], "hands": action_units[1:], "market": market}


def economy_mix50_waste_shield_agent(obs: dict[str, Any]) -> dict[str, list]:
    """Incumbent ``economy_mix50`` with a conservative executor shield."""

    base_action = agent_for_plan(obs, _BASE_PLAN, _SHIELD_NAME)
    return shield_action(obs, base_action)


__all__ = [
    "economy_mix50_waste_shield_agent",
    "metrics",
    "reset_metrics",
    "shield_action",
]
