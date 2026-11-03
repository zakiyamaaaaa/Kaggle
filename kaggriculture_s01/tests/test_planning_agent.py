import copy
import itertools
import random

from kaggriculture_agent.planning_agent import Plan, agent_for_plan, assignment


def obs():
    tiles = [[None if x < 5 and y < 5 else "LOCKED" for x in range(10)] for y in range(10)]
    return {
        "player": 0,
        "step": 0,
        "day": 0,
        "hour": 0,
        "farms": [
            {
                "farmer": [4, 4],
                "hands": [],
                "tiles": tiles,
                "money": 3000,
                "unlocked_quadrants": ["NW"],
                "hires_today": 0,
            }
        ],
        "private": {"shed": {}, "seeds": {}, "inventories": [{}]},
        "market": {"prices": {}, "inventory": {}},
        "town": {"unlocked_shops": []},
    }


def test_assignment_matches_exhaustive_optimum():
    rng = random.Random(9)
    for _ in range(30):
        costs = [[rng.randrange(-50, 100) for _ in range(5)] for _ in range(3)]
        selected = assignment(costs)
        assert len(set(selected)) == 3
        actual = sum(costs[i][j] for i, j in enumerate(selected))
        expected = min(
            sum(costs[i][j] for i, j in enumerate(js)) for js in itertools.permutations(range(5), 3)
        )
        assert actual == expected


def test_joint_plant_requests_do_not_exceed_shared_seed_stock():
    o = obs()
    o["farms"][0]["hands"] = [[3, 4], [2, 4]]
    o["private"]["inventories"] = [{}, {}, {}]
    o["private"]["seeds"] = {"MELON": 1}
    before = copy.deepcopy(o)
    a = agent_for_plan(o, Plan(), "seeds-test")
    assert sum(x[0] == "PLANT" for x in [a["farmer"], *a["hands"]]) == 1
    assert o == before


def test_feed_resource_route_finishes_after_pickup():
    o = obs()
    o["farms"][0]["tiles"][4][4] = {
        "kind": "PASTURE",
        "animal": "COW",
        "fed_today": False,
        "cared_today": False,
        "yield_units": 0,
        "fertilizer_available": False,
    }
    o["private"]["shed"] = {"WHEAT": 1}
    plan = Plan(animals=1)
    assert agent_for_plan(o, plan, "feed-test")["farmer"] == ["PICKUP", "WHEAT", 1]
    o.update(step=1, hour=1)
    o["private"]["shed"] = {"WHEAT": 0}
    o["private"]["inventories"] = [{"WHEAT": 1}]
    assert agent_for_plan(o, plan, "feed-test")["farmer"] == ["FEED"]


def test_carried_animal_is_placed_instead_of_dropped_back_into_shed():
    o = obs()
    o["farms"][0]["tiles"][4][4] = {"kind": "PASTURE"}
    o["private"]["inventories"] = [{"COW": 1}]
    assert agent_for_plan(o, Plan(animals=1), "place-test")["farmer"] == ["PLACE", "COW"]


def test_final_step_drop_is_sold_in_the_same_step():
    o = obs()
    o.update(day=29, hour=22, step=718)
    o["private"]["inventories"] = [{"MELON": 6}]
    a = agent_for_plan(o, Plan(), "last-test")
    assert a["farmer"] == ["DROP"]
    assert ["SELL", "MELON", 6] in a["market"]


def test_no_plant_when_same_day_watering_cannot_finish():
    o = obs()
    o.update(step=23, hour=23)
    o["private"]["seeds"] = {"MELON": 25}
    a = agent_for_plan(o, Plan(), "deadline-test")
    assert a["farmer"] == ["PASS"]


def test_diversified_animals_do_not_move_slots_after_land_purchase():
    o = obs()
    o["farms"][0]["tiles"] = [[None for _ in range(10)] for _ in range(10)]
    o["farms"][0]["farmer"] = [5, 4]
    o["farms"][0]["unlocked_quadrants"] = ["NW", "NE", "SW", "SE"]
    a = agent_for_plan(o, Plan(diversified=True, animals=8), "stable-slots")
    assert a["farmer"] != ["BUILD_PASTURE"]
    assert a["farmer"] != ["BUILD_COOP"]


def test_diversified_plan_buys_multiple_crops_within_budget():
    o = obs()
    a = agent_for_plan(o, Plan(diversified=True, hands=0), "crop-mix")
    orders = [x for x in a["market"] if x[0] == "BUY_SEED"]
    assert {x[1] for x in orders} == {"WHEAT", "MELON", "STRAWBERRY"}
    costs = {"WHEAT": 10, "MELON": 80, "STRAWBERRY": 100}
    assert sum(costs[x[1]] * x[2] for x in orders) <= 3000


def test_milk_buffer_is_liquidated_in_terminal_days():
    o = obs()
    o["private"]["shed"] = {"MILK": 50}
    plan = Plan(milk_hold=40)
    assert ["SELL", "MILK", 10] in agent_for_plan(o, plan, "hold-test")["market"]
    o.update(step=672, day=28, hour=0)
    assert ["SELL", "MILK", 50] in agent_for_plan(o, plan, "hold-test")["market"]


def test_fertilizer_route_only_uses_available_resource():
    o = obs()
    o.update(step=240, day=10, hour=0)
    o["farms"][0]["tiles"][4][4] = {
        "kind": "PLANT",
        "crop": "STRAWBERRY",
        "planted_day": 0,
        "watered_today": True,
        "yield_units": 0,
        "fertilized_until_day": -1,
    }
    plan = Plan(fertilize=True, animals=0, hands=0)
    assert agent_for_plan(o, plan, "fert-test")["farmer"] == ["PASS"]
    o["private"]["shed"] = {"FERTILIZER": 1}
    assert agent_for_plan(o, plan, "fert-test")["farmer"] == ["PICKUP", "FERTILIZER", 1]
    o.update(step=241, hour=1)
    o["private"]["shed"] = {}
    o["private"]["inventories"] = [{"FERTILIZER": 1}]
    assert agent_for_plan(o, plan, "fert-test")["farmer"] == ["FERTILIZE"]
