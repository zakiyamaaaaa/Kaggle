from kaggriculture_agent.macro_rl import ACTIONS, FEATURE_NAMES, features, make_macro_agent, probabilities


def observation(step=0):
    tile = {
        "kind": "PLANT",
        "crop": "WHEAT",
        "fertilized_until_day": -1,
        "planted_day": 0,
        "max_lifespan_step": 120,
        "consecutive_unwatered": 0,
        "watered_today": False,
        "yield_units": 0,
    }
    farm = {
        "money": 1000,
        "hands": [],
        "farmer": [4, 4],
        "tiles": [[tile] + ["LOCKED"] * 9] + [["LOCKED"] * 10 for _ in range(9)],
        "unlocked_quadrants": ["NW"],
    }
    return {
        "step": step,
        "day": step // 24,
        "hour": step % 24,
        "player": 0,
        "farms": [farm, dict(farm)],
        "market": {"prices": {"EGG": 100, "MILK": 100, "WOOL": 100}},
        "private": {"shed": {}, "seeds": {}, "inventories": [{}]},
    }


def test_features_have_stable_schema():
    values = features(observation())
    assert len(values) == len(FEATURE_NAMES)
    assert values[0] == 1.0


def test_probabilities_and_agent_are_deterministic():
    model = {
        "weights": [[0.0] * len(FEATURE_NAMES) for _ in ACTIONS],
        "bias": list(range(len(ACTIONS))),
    }
    probs = probabilities(model, features(observation()))
    assert abs(sum(probs) - 1.0) < 1e-9
    first = make_macro_agent(model)(observation())
    second = make_macro_agent(model)(observation())
    assert first == second
