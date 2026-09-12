from kaggriculture_agent import agent
from main import agent as standalone_agent


def test_agent_returns_kaggriculture_action_shape() -> None:
    observation = {
        "player": 0,
        "day": 0,
        "hour": 0,
        "farms": [
            {
                "farmer": [0, 0],
                "hands": [],
                "tiles": [[None]],
                "money": 100,
                "unlocked_quadrants": ["NW"],
            }
        ],
        "private": {},
        "market": {},
    }

    action = agent(observation)

    assert set(action) == {"farmer", "hands", "market"}
    assert isinstance(action["farmer"], list)
    assert isinstance(action["hands"], list)
    assert isinstance(action["market"], list)


def test_standalone_submission_has_same_action_shape() -> None:
    action = standalone_agent({})

    assert action == {"farmer": ["PASS"], "hands": [], "market": []}
