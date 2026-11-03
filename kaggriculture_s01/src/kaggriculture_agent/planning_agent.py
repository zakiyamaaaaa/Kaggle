"""Deadline-aware farm planning with joint assignment and committed resource routes.

The runtime uses only the standard library and observation-visible information.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Plan:
    hands: int = 8
    assignment: str = "matching"
    delivery: str = "immediate"
    commitment: bool = True
    animals: int = 0
    species: str = "COW"
    land: int = 0
    crop: str = "MELON"
    adaptive_hands: bool = False
    adaptive_crop: bool = False
    feed_batch: int = 1
    diversified: bool = False
    fertilize: bool = False
    milk_hold: int = 0
    land_reserve: int = 1000


@dataclass(frozen=True)
class Task:
    key: tuple
    position: tuple[int, int]
    action: tuple
    priority: float
    resource: str = ""
    reserve: int = 0
    duration: int = 1


SHED = ((4, 4), (5, 4), (4, 5), (5, 5))
SEED_PRICE = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50, "STRAWBERRY": 100, "MELON": 80}
FIRST = {"WHEAT": 2, "CARROT": 2, "TOMATO": 8, "STRAWBERRY": 10, "MELON": 10}
LAST = {"WHEAT": 4, "CARROT": 3, "TOMATO": 11, "STRAWBERRY": 16, "MELON": 12}
MAXIMUM = {"WHEAT": 6, "CARROT": 4, "MELON": 6}
ANIMAL_PRICE = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
ANIMAL_FIRST = {"GOOSE": 4, "COW": 8, "SHEEP": 6}
_STATES: dict[tuple[str, int], dict] = {}


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def nearest_shed(pos):
    return min(SHED, key=lambda target: (distance(pos, target), target))


def move(pos, target):
    if pos[0] < target[0]:
        return ["EAST"]
    if pos[0] > target[0]:
        return ["WEST"]
    if pos[1] < target[1]:
        return ["SOUTH"]
    if pos[1] > target[1]:
        return ["NORTH"]
    return ["PASS"]


def total(inv):
    return sum(max(0, int(n)) for n in inv.values())


def assignment(costs: list[list[float]]) -> list[int]:
    """Rectangular Hungarian algorithm; columns include an idle slot per row."""
    if not costs:
        return []
    n, m = len(costs), len(costs[0])
    if m < n or any(len(row) != m for row in costs):
        raise ValueError("assignment requires rectangular rows <= columns")
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0, best, used = 0, [float("inf")] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], float("inf"), 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = costs[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < best[j]:
                        best[j], way[j] = cur, j0
                    if best[j] < delta:
                        delta, j1 = best[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    best[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    result = [-1] * n
    for j in range(1, m + 1):
        if p[j]:
            result[p[j] - 1] = j - 1
    return result


def crop_for_day(day, plan, obs):
    crop = plan.crop
    if plan.adaptive_crop:
        prices = obs.get("market", {}).get("prices", {})
        # A deliberately small interpretable candidate family; full-season
        # paired evaluation decides whether this adaptation is useful.
        options = ["MELON", "WHEAT", "CARROT", "TOMATO", "STRAWBERRY"]
        options = [c for c in options if day + FIRST[c] <= 27]
        if not options:
            return None
        crop = max(
            options,
            key=lambda c: (
                float(prices.get(c, 0)) * ({"MELON": 6, "WHEAT": 4, "CARROT": 3}.get(c, 4))
                - SEED_PRICE[c]
            )
            / (LAST[c] + 2),
        )
    if crop == "MELON":
        return "MELON" if day <= 17 else "WHEAT" if day <= 25 else None
    return crop if day + LAST[crop] <= 28 else None


def agent_for_plan(obs: dict, plan: Plan, name: str) -> dict[str, list]:
    player = int(obs.get("player", 0))
    farms = obs.get("farms", [])
    if not farms or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    day, hour = int(obs.get("day", 0)), int(obs.get("hour", 0))
    step = int(obs.get("step", day * 24 + hour))
    left = min(24 - hour, 719 - step)
    private = obs.get("private", {})
    shed, seeds = private.get("shed", {}), private.get("seeds", {})
    positions = [tuple(farm["farmer"]), *map(tuple, farm.get("hands", []))]
    inventories = [dict(inv) for inv in private.get("inventories", [])]
    inventories += [{} for _ in range(len(positions) - len(inventories))]
    state_key = name, player
    state = _STATES.get(state_key)
    if state is None or step <= state["step"] or day != state["day"]:
        state = {"step": -1, "day": day, "jobs": {}}
    state["step"] = step
    _STATES[state_key] = state
    tiles = farm["tiles"]
    plots = [(x, y) for y in range(9, -1, -1) for x in range(9, -1, -1) if tiles[y][x] != "LOCKED"]
    animal_order = sorted(
        plots, key=lambda pos: (distance(pos, nearest_shed(pos)), -pos[1], -pos[0])
    )
    if plan.diversified:
        # Keep livestock locations stable when new quadrants are purchased.
        animal_order = sorted(
            [(x, y) for y in range(5) for x in range(5)],
            key=lambda pos: (distance(pos, nearest_shed(pos)), -pos[1], -pos[0]),
        )
    animal_slots = set(animal_order[: plan.animals])
    species_at = {
        pos: ("SHEEP" if plan.diversified and i % 2 else plan.species)
        for i, pos in enumerate(animal_order[: plan.animals])
    }
    animal_tiles = [
        (pos, tiles[pos[1]][pos[0]])
        for pos in plots
        if isinstance(tiles[pos[1]][pos[0]], dict) and "animal" in tiles[pos[1]][pos[0]]
    ]
    animal_count = len(animal_tiles)
    crop = crop_for_day(day, plan, obs)
    prices = obs.get("market", {}).get("prices", {})
    tasks = []

    def crop_at(pos):
        if not plan.diversified:
            return crop
        # Stable spatial mix: wheat supports feed, strawberries diversify revenue.
        c = ("WHEAT", "STRAWBERRY", "MELON")[(pos[0] + 2 * pos[1]) % 3]
        return c if day + LAST[c] <= 28 else "WHEAT" if day <= 25 else None

    def add(pos, op, priority, resource="", reserve=0, duration=1):
        tasks.append(Task((pos, *op), pos, tuple(op), priority, resource, reserve, duration))

    for pos in plots:
        x, y = pos
        tile = tiles[y][x]
        local_crop = crop_at(pos)
        species = species_at.get(pos, plan.species)
        if isinstance(tile, dict) and "animal" in tile:
            if not tile.get("fed_today"):
                add(pos, ["FEED"], 120 if tile.get("consecutive_unfed", 0) else 100, "WHEAT", 1)
            if tile.get("yield_units", 0):
                add(pos, ["HARVEST"], 80 + min(15, tile["yield_units"] * 2))
            if tile.get("fed_today") and not tile.get("cared_today") and day < 28:
                add(pos, ["CARE"], 55)
            if tile.get("fertilizer_available") and prices.get("FERTILIZER", 100) > 3:
                add(pos, ["COLLECT_FERTILIZER"], 60)
        elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
            age, c = day - int(tile["planted_day"]), tile["crop"]
            yield_units = int(tile.get("yield_units", 0))
            ongoing = c in ("TOMATO", "STRAWBERRY")
            ready = (
                age >= FIRST[c]
                and yield_units > 0
                and (ongoing or yield_units >= MAXIMUM[c] or age >= LAST[c] or day >= 28)
            )
            if (
                plan.fertilize
                and ongoing
                and tile.get("watered_today")
                and FIRST[c] - 2 <= age <= FIRST[c] + (3 if c == "TOMATO" else 6) - 1
                and tile.get("fertilized_until_day", -1) < day
                and day < 28
            ):
                add(pos, ["FERTILIZE"], 65, "FERTILIZER", 1)
            if ready and (ongoing or tile.get("watered_today") or yield_units >= MAXIMUM[c]):
                add(pos, ["HARVEST"], 95 if day >= 28 else 85)
            elif not tile.get("watered_today"):
                add(pos, ["WATER"], 115 if age == 0 else 100)
        elif isinstance(tile, dict) and tile.get("kind") == "WEED":
            if local_crop or pos in animal_slots:
                add(pos, ["DIG"], 35)
        elif pos in animal_slots and day + ANIMAL_FIRST[species] <= 25:
            structure = "COOP" if species == "GOOSE" else "PASTURE"
            if tile is None:
                add(pos, ["BUILD_" + structure], 40)
            elif tile.get("kind") == structure:
                add(pos, ["PLACE", species], 50, species, 1)
        elif tile is None and local_crop and seeds.get(local_crop, 0) > 0:
            add(pos, ["PLANT", local_crop], 45, duration=2)

    stock = dict(shed)
    seed_stock = dict(seeds)
    storage = total(shed) + sum(total(inv) for inv in inventories)
    actions: list[list[Any] | None] = [None] * len(positions)
    used = set()
    jobs = {}
    planned_drop = CounterLike()
    task_by_key = {t.key: t for t in tasks}

    def route(i, task):
        pos, inv = positions[i], inventories[i]
        if task.resource and inv.get(task.resource, 0) < task.reserve:
            if stock.get(task.resource, 0) < task.reserve:
                return None, 10000
            access = nearest_shed(pos)
            duration = distance(pos, access) + 1 + distance(access, task.position) + task.duration
            if pos != access:
                return move(pos, access), duration
            quantity = (
                min(plan.feed_batch, stock[task.resource])
                if task.resource == "WHEAT"
                else task.reserve
            )
            return ["PICKUP", task.resource, quantity], duration
        duration = distance(pos, task.position) + task.duration
        if day == 29 and task.action[0] in ("HARVEST", "COLLECT_FERTILIZER"):
            duration += distance(task.position, nearest_shed(task.position)) + 1
        return (list(task.action) if pos == task.position else move(pos, task.position)), duration

    def choose(i, task):
        nonlocal storage
        action, duration = route(i, task)
        if action is None or duration > left:
            return False
        if task.action[0] == "PLANT":
            c = task.action[1]
            if seed_stock.get(c, 0) <= 0:
                return False
            seed_stock[c] -= 1
        if task.resource and inventories[i].get(task.resource, 0) < task.reserve:
            stock[task.resource] -= action[2] if action[0] == "PICKUP" else task.reserve
        if action[0] in ("HARVEST", "COLLECT_FERTILIZER"):
            tile = tiles[task.position[1]][task.position[0]]
            amount = 1 if action[0] == "COLLECT_FERTILIZER" else tile.get("yield_units", 0)
            if storage + amount > 100:
                return False
            storage += amount
        actions[i] = action
        used.add(task.key)
        if positions[i] != task.position or action[0] == "PICKUP":
            jobs[i] = task.key
        return True

    for i, (pos, inv) in enumerate(zip(positions, inventories)):
        goods = (
            total(inv)
            - sum(inv.get(a, 0) for a in ANIMAL_PRICE)
            - (inv.get("WHEAT", 0) if animal_count else 0)
            - (inv.get("FERTILIZER", 0) if plan.fertilize else 0)
        )
        # Keep feed and animal-placement routes intact. Return products in
        # batches; normal-day carry is automatically collected by the engine.
        need_drop = goods > 0 and (
            plan.delivery == "immediate" or pos in SHED or storage >= 80 or day == 29
        )
        if need_drop:
            access = nearest_shed(pos)
            actions[i] = ["DROP"] if pos == access else move(pos, access)
            if pos == access:
                for item, amount in inv.items():
                    planned_drop.add(item, amount)
            continue
        task = task_by_key.get(state["jobs"].get(i))
        if plan.commitment and task and task.key not in used:
            choose(i, task)

    free = [i for i, action in enumerate(actions) if action is None]
    available = [t for t in tasks if t.key not in used]
    costs = []
    for i in free:
        row = []
        for task in available:
            action, duration = route(i, task)
            row.append(
                1000000
                if action is None or duration > left
                else -task.priority * 100 + duration * 10 + distance(positions[i], task.position)
            )
        costs.append(row + [0.0] * len(free))
    if plan.assignment == "matching":
        chosen = assignment(costs)
    else:
        taken = set()
        chosen = []
        for row in costs:
            j = min((j for j in range(len(row)) if j not in taken), key=lambda j: row[j])
            chosen.append(j)
            taken.add(j)
    for row, (i, j) in enumerate(zip(free, chosen)):
        if j < len(available) and costs[row][j] < 0:
            choose(i, available[j])
    for i, action in enumerate(actions):
        if action is None:
            pos, inv = positions[i], inventories[i]
            if total(inv):
                access = nearest_shed(pos)
                actions[i] = ["DROP"] if pos == access else move(pos, access)
                if pos == access:
                    for item, amount in inv.items():
                        planned_drop.add(item, amount)
            else:
                actions[i] = ["PASS"]
    state["jobs"] = jobs

    expected_shed = {item: int(amount) + planned_drop.get(item, 0) for item, amount in shed.items()}
    for item, amount in planned_drop.items():
        expected_shed.setdefault(item, amount)
    # PICKUP precedes the market. Reserve enough feed for unfinished animals;
    # task reservations include workers still travelling to the shed.
    for action in actions:
        if action[0] == "PICKUP":
            expected_shed[action[1]] = max(0, expected_shed.get(action[1], 0) - action[2])
    feed_needed = sum(not tile.get("fed_today") for _, tile in animal_tiles)
    reserve = animal_count if day < 29 else feed_needed
    orders = []
    for item, amount in sorted(expected_shed.items()):
        if item in ANIMAL_PRICE:
            continue
        sell = max(0, amount - (reserve if item == "WHEAT" else 0))
        if item == "FERTILIZER" and plan.fertilize and day < 27:
            sell = max(0, amount - 8)
        if item == "MILK" and plan.milk_hold and day < 28:
            sell = max(0, amount - plan.milk_hold)
        if sell:
            orders.append(["SELL", item, sell])
    money = float(farm.get("money", 0))
    hires = int(farm.get("hires_today", 0))
    target_hands = plan.hands
    if plan.adaptive_hands:
        # Conservative workload estimate with travel allowance; upper bound is
        # the already validated fixed plan, not unlimited Fibonacci hiring.
        work = len(tasks) * 3 + animal_count * 3
        target_hands = min(plan.hands, max(2, (work + 15) // 16 - 1))
    if hour < 8:
        for h in range(hires, target_hands):
            a, b = 1, 1
            for _ in range(h):
                a, b = b, a + b
            if money < a:
                break
            orders.append(["HIRE"])
            money -= a
    if animal_count:
        carried_feed = sum(inv.get("WHEAT", 0) for inv in inventories)
        need = max(0, feed_needed - expected_shed.get("WHEAT", 0) - carried_feed)
        price = max(1, int(prices.get("WHEAT", 25)) + 2)
        quantity = min(need, int(money // price), max(0, 100 - sum(expected_shed.values())))
        if quantity:
            orders.append(["BUY_PRODUCT", "WHEAT", quantity])
            money -= quantity * price
    for species in sorted(set(species_at.values())):
        desired = sum(s == species for s in species_at.values())
        present = sum(tile["animal"] == species for _, tile in animal_tiles)
        unfilled = max(
            0,
            desired
            - present
            - shed.get(species, 0)
            - sum(inv.get(species, 0) for inv in inventories),
        )
        if unfilled and day + ANIMAL_FIRST[species] <= 25:
            reserve_cash = max(100, plan.animals * max(1, int(prices.get("WHEAT", 25))))
            count = min(
                unfilled,
                max(0, int((money - reserve_cash) // ANIMAL_PRICE[species])),
                max(0, 100 - sum(expected_shed.values())),
            )
            if count:
                orders.append(["BUY_ANIMAL", species, count])
                money -= count * ANIMAL_PRICE[species]
    needed_seeds = {}
    for pos in plots:
        c = crop_at(pos)
        if c and tiles[pos[1]][pos[0]] is None and pos not in animal_slots:
            needed_seeds[c] = needed_seeds.get(c, 0) + 1
    for c in sorted(needed_seeds):
        count = min(max(0, needed_seeds[c] - int(seeds.get(c, 0))), int(money // SEED_PRICE[c]))
        if count:
            orders.append(["BUY_SEED", c, count])
            money -= count * SEED_PRICE[c]
    owned = len(farm.get("unlocked_quadrants", ["NW"])) - 1
    if owned < plan.land and day <= 15:
        cost = (1000, 2000, 4000)[owned]
        if money >= cost + max(plan.land_reserve, animal_count * 50):
            orders.append(["BUY_LAND"])
    return {"farmer": actions[0], "hands": actions[1:], "market": orders[:10]}


class CounterLike(dict):
    def add(self, item, amount):
        self[item] = self.get(item, 0) + amount


PLANS = {
    "planner_greedy": Plan(assignment="greedy", commitment=False),
    "planner_committed": Plan(assignment="greedy"),
    "planner_daily": Plan(delivery="daily"),
    "planner_matching": Plan(),
    "planner_cows8": Plan(delivery="daily", animals=8),
    "planner_geese8": Plan(delivery="daily", animals=8, species="GOOSE"),
    "planner_sheep8": Plan(delivery="daily", animals=8, species="SHEEP"),
    "planner_cows16": Plan(delivery="daily", animals=16, hands=10),
    "planner_geese16": Plan(delivery="daily", animals=16, species="GOOSE", hands=10),
    "planner_sheep16": Plan(delivery="daily", animals=16, species="SHEEP", hands=10),
    "planner_crop_land": Plan(land=1, hands=10),
    "planner_cows_land": Plan(delivery="daily", animals=16, land=1, hands=10),
    "planner_adaptive": Plan(
        delivery="daily", animals=16, land=1, hands=10, adaptive_hands=True, adaptive_crop=True
    ),
}

PLANS.update(
    {
        "planner_daily_greedy": Plan(delivery="daily", assignment="greedy"),
        "planner_geese8_greedy": Plan(
            delivery="daily", animals=8, species="GOOSE", assignment="greedy"
        ),
        "planner_cows8_greedy": Plan(delivery="daily", animals=8, assignment="greedy"),
        "planner_geese_tomato": Plan(delivery="daily", animals=8, species="GOOSE", crop="TOMATO"),
        "planner_geese_adaptive": Plan(
            delivery="daily", animals=8, species="GOOSE", adaptive_crop=True
        ),
        "planner_carrot": Plan(delivery="daily", crop="CARROT"),
        "planner_tomato": Plan(delivery="daily", crop="TOMATO"),
        "planner_strawberry": Plan(delivery="daily", crop="STRAWBERRY"),
        "planner_cows_carrot": Plan(delivery="daily", animals=8, crop="CARROT"),
        "planner_geese_carrot": Plan(delivery="daily", animals=8, species="GOOSE", crop="CARROT"),
        "planner_sheep_carrot": Plan(delivery="daily", animals=8, species="SHEEP", crop="CARROT"),
        "planner_cows16_batch": Plan(delivery="daily", animals=16, hands=10, feed_batch=3),
    }
)


PLANS.update(
    {
        "economy_mix25": Plan(delivery="daily", animals=8, diversified=True, feed_batch=3),
        "economy_mix50": Plan(
            delivery="daily", animals=8, diversified=True, feed_batch=3, land=1, hands=12
        ),
        "economy_mix75": Plan(
            delivery="daily", animals=8, diversified=True, feed_batch=3, land=2, hands=12
        ),
        "economy_fert50": Plan(
            delivery="daily",
            animals=8,
            diversified=True,
            feed_batch=3,
            land=1,
            hands=12,
            fertilize=True,
        ),
        "economy_fert75": Plan(
            delivery="daily",
            animals=8,
            diversified=True,
            feed_batch=3,
            land=2,
            hands=12,
            fertilize=True,
        ),
        "economy_fert75_h10": Plan(
            delivery="daily",
            animals=8,
            diversified=True,
            feed_batch=3,
            land=2,
            hands=10,
            fertilize=True,
        ),
        "economy_fert75_a12": Plan(
            delivery="daily",
            animals=12,
            diversified=True,
            feed_batch=3,
            land=2,
            hands=12,
            fertilize=True,
        ),
        "economy_fert75_early": Plan(
            delivery="daily",
            animals=8,
            diversified=True,
            feed_batch=3,
            land=2,
            hands=12,
            fertilize=True,
            land_reserve=100,
        ),
        "economy_cows_hold": Plan(delivery="daily", animals=8, milk_hold=40),
        "economy_cows4": Plan(delivery="daily", animals=4),
    }
)


def make_agent(name):
    plan = PLANS[name]

    def policy(obs):
        return agent_for_plan(obs, plan, name)

    policy.__name__ = name
    return policy
