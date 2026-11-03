from __future__ import annotations

from kaggriculture_agent.registry import agent_names, get_agent
from kaggriculture_agent.waste_shield import shield_action


def _obs(*, farmer=(4, 4), hands=None, seeds=None, shed=None, inventories=None, tiles=None):
    board = tiles or [[None for _ in range(10)] for _ in range(10)]
    hands = list(hands or [])
    inventories = list(inventories or [{} for _ in range(1 + len(hands))])
    return {
        "player": 0,
        "step": 0,
        "day": 0,
        "hour": 0,
        "farms": [
            {
                "farmer": list(farmer),
                "hands": [list(position) for position in hands],
                "tiles": board,
                "money": 3000,
                "unlocked_quadrants": ["NW"],
                "hires_today": 0,
            }
        ],
        "private": {
            "shed": dict(shed or {}),
            "seeds": dict(seeds or {}),
            "inventories": inventories,
        },
        "market": {"prices": {}, "inventory": {}},
        "town": {"unlocked_shops": []},
    }


def test_pass_is_intentional_and_untouched():
    action = {"farmer": ["PASS"], "hands": [], "market": []}
    assert shield_action(_obs(), action) == action


def test_obvious_unit_noops_are_replaced():
    obs = _obs(farmer=(0, 0), hands=[(1, 1)])
    action = {
        "farmer": ["NORTH"],
        "hands": [["DROP"]],
        "market": [],
    }
    assert shield_action(obs, action) == {
        "farmer": ["PASS"],
        "hands": [["PASS"]],
        "market": [],
    }


def test_partial_pickup_and_partial_seed_purchase_are_preserved():
    obs = _obs(shed={"WHEAT": 1})
    action = {
        "farmer": ["PICKUP", "WHEAT", 3],
        "hands": [],
        "market": [["BUY_SEED", "WHEAT", 2]],
    }
    assert shield_action(obs, action) == action


def test_shared_seed_shortage_is_removed_as_a_group():
    obs = _obs(farmer=(0, 0), hands=[(1, 0)], seeds={"WHEAT": 1})
    action = {
        "farmer": ["PLANT", "WHEAT"],
        "hands": [["PLANT", "WHEAT"]],
        "market": [],
    }
    shielded = shield_action(obs, action)
    assert shielded["farmer"] == ["PASS"]
    assert shielded["hands"] == [["PASS"]]


def test_experiment_is_separately_registered():
    assert "economy_mix50" in agent_names()
    assert "economy_mix50_waste_shield" in agent_names()
    action = get_agent("economy_mix50_waste_shield")({})
    assert action == {"farmer": ["PASS"], "hands": [], "market": []}
