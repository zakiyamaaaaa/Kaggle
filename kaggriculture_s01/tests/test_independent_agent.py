from kaggriculture_agent.independent_agent import PLOTS, agent
from kaggriculture_agent.independent_agent import (
    agent_workers,
    agent_workers_mature,
    agent_workers_batch,
)


def _observation() -> dict:
    tiles = [["LOCKED" for _ in range(10)] for _ in range(10)]
    for y in range(5):
        for x in range(5):
            tiles[y][x] = None
    return {
        "player": 0,
        "day": 0,
        "hour": 0,
        "farms": [
            {
                "money": 3000,
                "farmer": [4, 4],
                "hands": [],
                "tiles": tiles,
                "unlocked_quadrants": ["NW"],
                "hires_today": 0,
            }
        ],
        "private": {"shed": {}, "seeds": {}, "inventories": [{}]},
        "market": {"inventory": {}, "prices": {}},
        "town": {"unlocked_shops": []},
    }


def test_independent_agent_buys_melon_seeds() -> None:
    action = agent(_observation())
    assert action["market"] == [["BUY_SEED", "MELON", len(PLOTS)]]
    assert action["farmer"] == ["PASS"]


def test_independent_agent_waters_same_day_plant() -> None:
    observation = _observation()
    observation["private"]["seeds"] = {"MELON": 9}
    observation["farms"][0]["tiles"][4][4] = {
        "kind": "PLANT",
        "crop": "MELON",
        "planted_day": 0,
        "watered_today": False,
    }
    assert agent(observation)["farmer"] == ["WATER"]


def test_independent_agent_returns_inventory_to_shed() -> None:
    observation = _observation()
    observation["private"]["inventories"] = [{"MELON": 3}]
    assert agent(observation)["farmer"] == ["DROP"]


def test_mature_melon_harvests_at_ten_days_without_changing_control() -> None:
    obs = _observation()
    obs["day"] = 10
    obs["farms"][0]["tiles"][4][4] = {
        "kind": "PLANT",
        "crop": "MELON",
        "planted_day": 0,
        "watered_today": True,
        "yield_units": 6,
    }
    assert agent_workers(obs)["farmer"] != ["HARVEST"]
    assert agent_workers_mature(obs)["farmer"] == ["HARVEST"]
    obs["day"] = 9
    assert agent_workers_mature(obs)["farmer"] != ["HARVEST"]


def test_batch_cargo_does_not_interrupt_same_day_watering() -> None:
    obs = _observation()
    obs["farms"][0]["farmer"] = [0, 0]
    obs["private"]["inventories"] = [{"MELON": 6}]
    obs["farms"][0]["tiles"][0][0] = {
        "kind": "PLANT",
        "crop": "MELON",
        "planted_day": 0,
        "watered_today": False,
        "yield_units": 1,
    }
    assert agent_workers_batch(obs)["farmer"] == ["WATER"]


def test_batch_sells_same_turn_drop_on_last_day() -> None:
    obs = _observation()
    obs.update(day=29, hour=22, step=718)
    obs["private"]["inventories"] = [{"MELON": 6}]
    action = agent_workers_batch(obs)
    assert action["farmer"] == ["DROP"]
    assert ["SELL", "MELON", 6] in action["market"]
