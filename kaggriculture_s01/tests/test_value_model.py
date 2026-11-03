import numpy as np
import pandas as pd

from kaggriculture_agent.value_model import build_feature_spec, split_by_seed


def _transitions() -> pd.DataFrame:
    rows = []
    for seed in range(1000, 1032):
        for seat in (0, 1):
            for step in (0, 12, 24):
                rows.append(
                    {
                        "seed": seed,
                        "pair_id": f"pair-{seed}",
                        "game_id": f"game-{seed}-{seat}",
                        "player": seat,
                        "seat": seat,
                        "policy": "candidate",
                        "opponent": "public_salem",
                        "step": step,
                        "day": step // 24,
                        "cash": float(seed + step),
                        "farm_value": float(step * 3 + seat),
                        "opponent_seed_total": 0,
                        "opponent_shed_total": 0,
                        "opponent_inventory_total": 0,
                        "action_type": "PASS",
                        "chosen_action_json": "{}",
                        "final_reward": float(seed),
                        "opponent_final_reward": float(seed + 10),
                        "reward_difference": -10.0,
                        "win": 0,
                    }
                )
    return pd.DataFrame(rows).sample(frac=1, random_state=7).reset_index(drop=True)


def test_value_features_exclude_outcomes_identity_and_constants() -> None:
    spec = build_feature_spec(_transitions())
    forbidden = {
        "policy",
        "opponent",
        "seed",
        "game_id",
        "pair_id",
        "final_reward",
        "opponent_final_reward",
        "reward_difference",
        "win",
        "opponent_seed_total",
        "opponent_shed_total",
        "opponent_inventory_total",
    }
    assert forbidden.isdisjoint(spec.feature_columns)


def test_value_split_is_seed_and_pair_disjoint() -> None:
    transitions = _transitions()
    split = split_by_seed(transitions)
    assert len(split.train_seeds) == 24
    assert len(split.validation_seeds) == 8
    assert not set(split.train_seeds) & set(split.validation_seeds)
    assert not set(split.train_pairs) & set(split.validation_pairs)
    assert set(split.train.index) | set(split.validation.index) == set(transitions.index)
    assert np.isfinite(split.train["reward_difference"]).all()
