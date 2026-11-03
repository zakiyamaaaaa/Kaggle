from __future__ import annotations

import pandas as pd

from kaggriculture_agent.outcome_model import add_terminal_score, feature_groups


def _rows() -> pd.DataFrame:
    rows = []
    for seed, rewards in ((1, (2.0, 1.0)), (2, (1.0, 1.0)), (3, (0.0, 1.0))):
        for step in (0, 1):
            rows.append(
                {
                    "seed": seed,
                    "pair_id": f"pair-{seed}",
                    "game_id": f"game-{seed}",
                    "policy": "candidate",
                    "opponent": "other",
                    "step": step,
                    "day": step,
                    "hour": step,
                    "own_money": 10 + seed + step,
                    "opponent_money": 8 + seed,
                    "market_price_wheat": 100 + seed,
                    "own_shed_wheat": seed,
                    "chosen_action_json": "{}",
                    "final_reward": rewards[0],
                    "opponent_final_reward": rewards[1],
                    "reward_difference": rewards[0] - rewards[1],
                    "win": rewards[0] > rewards[1],
                }
            )
    return pd.DataFrame(rows)


def test_terminal_score_preserves_draws() -> None:
    scored = add_terminal_score(_rows())
    assert scored.groupby("seed")["terminal_score"].first().to_dict() == {
        1: 1.0,
        2: 0.5,
        3: 0.0,
    }


def test_feature_groups_include_item_market_features_without_outcomes() -> None:
    groups = feature_groups(add_terminal_score(_rows()))
    assert "market_price_wheat" in groups["terminal_market"]
    assert "own_shed_wheat" in groups["terminal_market"]
    for columns in groups.values():
        assert "terminal_score" not in columns
        assert "final_reward" not in columns
        assert "opponent_final_reward" not in columns
