"""Observation-driven Kaggriculture policy with no replay-tape dependency."""

from __future__ import annotations

from typing import Any

Action = dict[str, list]

# A compact snake next to the shed.  Ten plots can be serviced by one farmer
# within a 24-turn day without purchasing land or relying on mutable state.
PLOTS: tuple[tuple[int, int], ...] = (
    (4, 4),
    (3, 4),
    (2, 4),
    (1, 4),
    (0, 4),
    (0, 3),
    (1, 3),
    (2, 3),
    (3, 3),
    (4, 3),
)
PLOTS_16: tuple[tuple[int, int], ...] = PLOTS + (
    (4, 2),
    (3, 2),
    (2, 2),
    (1, 2),
    (0, 2),
    (0, 1),
)
PLOTS_8 = PLOTS[:8]
PLOTS_12 = PLOTS + ((4, 2), (3, 2))
PLOTS_25 = tuple((x, y) for y in range(4, -1, -1) for x in range(4, -1, -1))
SHED_ACCESS = frozenset({(4, 4), (5, 4), (4, 5), (5, 5)})
FIRST_YIELD_DAY = {"WHEAT": 2, "TOMATO": 8, "STRAWBERRY": 10, "MELON": 10}
MAX_YIELD_DAY = {"WHEAT": 4, "TOMATO": 8, "STRAWBERRY": 10, "MELON": 12}
SEED_PRICE = {"WHEAT": 10, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}


def _empty_action(hands: int = 0) -> Action:
    return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(hands)], "market": []}


def _distance(left: tuple[int, int], right: tuple[int, int]) -> int:
    return abs(left[0] - right[0]) + abs(left[1] - right[1])


def _move_toward(position: tuple[int, int], target: tuple[int, int]) -> list[str]:
    x, y = position
    tx, ty = target
    if x < tx:
        return ["EAST"]
    if x > tx:
        return ["WEST"]
    if y < ty:
        return ["SOUTH"]
    if y > ty:
        return ["NORTH"]
    return ["PASS"]


def _inventory_total(inventory: Any) -> int:
    return sum(max(0, int(value or 0)) for value in (inventory or {}).values())


def _crop_for_day(day: int) -> str | None:
    if day <= 17:
        return "MELON"
    if day <= 27:
        return "WHEAT"
    return None


def _market_orders(
    obs: dict, farm: dict, crop: str | None, plots: tuple[tuple[int, int], ...]
) -> list[list]:
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    seeds = private.get("seeds", {}) or {}
    orders: list[list] = []
    for item, quantity in sorted(shed.items()):
        amount = max(0, int(quantity or 0))
        if amount:
            orders.append(["SELL", str(item), amount])
    if crop is not None:
        tiles = farm.get("tiles", []) or []
        crop_plots = 0
        for x, y in plots:
            tile = tiles[y][x]
            if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == crop:
                crop_plots += 1
        desired = len(plots) - crop_plots
        missing = max(0, desired - int(seeds.get(crop, 0) or 0))
        price = SEED_PRICE[crop]
        affordable = max(0, int(farm.get("money", 0) or 0) // price)
        quantity = min(missing, affordable)
        if quantity:
            orders.append(["BUY_SEED", crop, quantity])
    return orders[:10]


def _choose_target(
    farm: dict,
    day: int,
    crop: str | None,
    seeds: dict,
    plots: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], list[str]] | None:
    tiles = farm.get("tiles", []) or []
    position = tuple(int(value) for value in farm.get("farmer", (4, 4)))
    candidates: list[tuple[int, int, int, tuple[int, int], list[str]]] = []
    for order, (x, y) in enumerate(plots):
        tile = tiles[y][x]
        action: list[str] | None = None
        priority = 99
        if isinstance(tile, dict) and tile.get("kind") == "PLANT":
            planted_day = int(tile.get("planted_day", day))
            age = day - planted_day
            current_crop = str(tile.get("crop", ""))
            if not bool(tile.get("watered_today", False)):
                # Same-day watering prevents immediate weeds.  Existing plants
                # are also watered daily so the stateless scheduler is robust.
                priority = 0 if age == 0 else 1
                action = ["WATER"]
            elif age >= MAX_YIELD_DAY.get(current_crop, FIRST_YIELD_DAY.get(current_crop, 99)):
                priority = 2
                action = ["HARVEST"]
        elif isinstance(tile, dict) and tile.get("kind") == "WEED":
            priority = 3
            action = ["DIG"]
        elif tile is None and crop is not None and int(seeds.get(crop, 0) or 0) > 0:
            priority = 4
            action = ["PLANT", crop]
        if action is not None:
            candidates.append((priority, _distance(position, (x, y)), order, (x, y), action))
    if not candidates:
        return None
    _, _, _, target, action = min(candidates)
    return target, action


def _agent(obs: dict, plots: tuple[tuple[int, int], ...]) -> Action:
    try:
        farms = obs.get("farms", []) or []
        player = int(obs.get("player", 0) or 0)
        if player < 0 or player >= len(farms):
            return _empty_action()
        farm = farms[player]
        hands = len(farm.get("hands", []) or [])
        day = int(obs.get("day", 0) or 0)
        private = obs.get("private", {}) or {}
        inventories = private.get("inventories", []) or []
        farmer_inventory = inventories[0] if inventories else {}
        position = tuple(int(value) for value in farm.get("farmer", (4, 4)))
        crop = _crop_for_day(day)
        market = _market_orders(obs, farm, crop, plots)

        if _inventory_total(farmer_inventory):
            farmer = ["DROP"] if position in SHED_ACCESS else _move_toward(position, (4, 4))
            return {"farmer": farmer, "hands": [["PASS"] for _ in range(hands)], "market": market}

        target = _choose_target(farm, day, crop, private.get("seeds", {}) or {}, plots)
        if target is None:
            farmer = ["PASS"]
        elif position == target[0]:
            farmer = target[1]
        else:
            farmer = _move_toward(position, target[0])
        return {"farmer": farmer, "hands": [["PASS"] for _ in range(hands)], "market": market}
    except (IndexError, KeyError, TypeError, ValueError):
        return _empty_action()


def agent(obs: dict) -> Action:
    """Ten-plot deterministic policy used as the independent v0 control."""

    return _agent(obs, PLOTS)


def agent_16(obs: dict) -> Action:
    """Sixteen-plot candidate that uses more of the main farmer's capacity."""

    return _agent(obs, PLOTS_16)


def agent_8(obs: dict) -> Action:
    return _agent(obs, PLOTS_8)


def agent_12(obs: dict) -> Action:
    return _agent(obs, PLOTS_12)


def _worker_agent(
    obs: dict, target_hands: int = 8, crop_mode: str = "MELON", *,
    mature_harvest: bool = False, delivery: str = "immediate",
) -> Action:
    """Manage all NW plots with observation-driven multi-worker scheduling."""

    try:
        farms = obs.get("farms", []) or []
        player = int(obs.get("player", 0) or 0)
        if player < 0 or player >= len(farms):
            return _empty_action()
        farm = farms[player]
        day = int(obs.get("day", 0) or 0)
        crop = _crop_for_day(day) if crop_mode == "MELON" else (crop_mode if day <= 27 else None)
        private = obs.get("private", {}) or {}
        seeds = private.get("seeds", {}) or {}
        inventories = list(private.get("inventories", []) or [])
        positions = [farm.get("farmer", [4, 4]), *(farm.get("hands", []) or [])]
        while len(inventories) < len(positions):
            inventories.append({})

        market = _market_orders(obs, farm, crop, PLOTS_25)
        hires_needed = max(0, target_hands - int(farm.get("hires_today", 0) or 0))
        market.extend([["HIRE"] for _ in range(min(hires_needed, 10 - len(market)))])

        tiles = farm.get("tiles", []) or []
        tasks: list[tuple[int, int, tuple[int, int], list[str]]] = []
        for order, (x, y) in enumerate(PLOTS_25):
            tile = tiles[y][x]
            if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                age = day - int(tile.get("planted_day", day))
                tile_crop = str(tile.get("crop", ""))
                if not bool(tile.get("watered_today", False)):
                    tasks.append((0 if age == 0 else 1, order, (x, y), ["WATER"]))
                elif (
                    age >= MAX_YIELD_DAY.get(tile_crop, FIRST_YIELD_DAY.get(tile_crop, 99))
                    or (mature_harvest and tile_crop == "MELON"
                        and age >= FIRST_YIELD_DAY["MELON"]
                        and int(tile.get("yield_units", 0)) >= 6)
                ):
                    tasks.append((2, order, (x, y), ["HARVEST"]))
            elif isinstance(tile, dict) and tile.get("kind") == "WEED":
                tasks.append((3, order, (x, y), ["DIG"]))
            elif tile is None and crop is not None:
                tasks.append((4, order, (x, y), ["PLANT", crop]))

        assigned: set[tuple[int, int]] = set()
        actions: list[list[str]] = []
        for index, raw_position in enumerate(positions):
            position = tuple(int(value) for value in raw_position)
            inventory = inventories[index] if index < len(inventories) else {}
            carried = _inventory_total(inventory)
            total_storage = _inventory_total(private.get("shed", {})) + sum(
                _inventory_total(inv) for inv in inventories
            )
            return_cargo = (
                delivery == "immediate" or day >= 29 or position in SHED_ACCESS
                or total_storage >= 80 or (delivery == "batch" and carried >= 24)
            )
            if carried and return_cargo:
                action = ["DROP"] if position in SHED_ACCESS else _move_toward(position, (4, 4))
                actions.append(action)
                continue
            choices = [task for task in tasks if task[2] not in assigned]
            if not choices:
                actions.append(
                    (["DROP"] if position in SHED_ACCESS else _move_toward(position, (4, 4)))
                    if carried else ["PASS"]
                )
                continue
            priority, _, target, target_action = min(
                choices,
                key=lambda task: (task[0], _distance(position, task[2]), task[1]),
            )
            del priority
            assigned.add(target)
            if position == target:
                if target_action[0] == "PLANT" and int(seeds.get(crop, 0) or 0) <= sum(
                    action[0] == "PLANT" for action in actions
                ):
                    actions.append(["PASS"])
                else:
                    actions.append(target_action)
            else:
                actions.append(_move_toward(position, target))
        if delivery != "immediate":
            # Unit actions precede market processing, so this turn's DROP can
            # be sold now, including on the final actionable step.
            dropping: dict[str, int] = {}
            for inventory, action in zip(inventories, actions):
                if action[0] == "DROP":
                    for item, quantity in inventory.items():
                        dropping[item] = dropping.get(item, 0) + int(quantity)
            for item, quantity in dropping.items():
                existing = next((o for o in market if o[:2] == ["SELL", item]), None)
                if existing is not None:
                    existing[2] += quantity
                else:
                    market.insert(0, ["SELL", item, quantity])
        return {"farmer": actions[0], "hands": actions[1:], "market": market[:10]}
    except (IndexError, KeyError, TypeError, ValueError):
        return _empty_action()


def agent_workers(obs: dict) -> Action:
    return _worker_agent(obs, 8)


def agent_workers_mature(obs: dict) -> Action:
    return _worker_agent(obs, mature_harvest=True)


def agent_workers_batch(obs: dict) -> Action:
    return _worker_agent(obs, mature_harvest=True, delivery="batch")


def agent_workers_daily(obs: dict) -> Action:
    return _worker_agent(obs, mature_harvest=True, delivery="daily")


def agent_workers_4(obs: dict) -> Action:
    return _worker_agent(obs, 4)


def agent_workers_6(obs: dict) -> Action:
    return _worker_agent(obs, 6)


def agent_workers_10(obs: dict) -> Action:
    return _worker_agent(obs, 10)


def agent_workers_7(obs: dict) -> Action:
    return _worker_agent(obs, 7)


def agent_workers_9(obs: dict) -> Action:
    return _worker_agent(obs, 9)


def agent_workers_wheat(obs: dict) -> Action:
    return _worker_agent(obs, 8, "WHEAT")


def agent_workers_strawberry(obs: dict) -> Action:
    return _worker_agent(obs, 8, "STRAWBERRY")


def agent_workers_tomato(obs: dict) -> Action:
    return _worker_agent(obs, 8, "TOMATO")


__all__ = [
    "PLOTS",
    "PLOTS_8",
    "PLOTS_12",
    "PLOTS_16",
    "PLOTS_25",
    "agent",
    "agent_8",
    "agent_12",
    "agent_16",
    "agent_workers",
    "agent_workers_4",
    "agent_workers_6",
    "agent_workers_10",
    "agent_workers_7",
    "agent_workers_9",
    "agent_workers_wheat",
    "agent_workers_strawberry",
    "agent_workers_tomato",
]
