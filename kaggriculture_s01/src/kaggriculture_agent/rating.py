"""Bayesian Bradley--Terry ratings for Kaggriculture Arena outcomes.

Only terminal win/draw/loss outcomes enter the fit.  Cash margins are retained
by the Arena for diagnosis but deliberately do not affect these ratings.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

import numpy as np

ELO_SCALE = 400.0 / math.log(10.0)
DEFAULT_PRIOR_SIGMA = 600.0
DEFAULT_PAIR_CAP = 500


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def _record_dict(record: Any) -> dict[str, Any]:
    if isinstance(record, Mapping):
        return dict(record)
    if is_dataclass(record) and not isinstance(record, type):
        return asdict(record)
    raise TypeError("rating records must be mappings or dataclass instances")


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)


def _empty_matchup() -> dict[str, Any]:
    return {
        "games": 0,
        "fit_games": 0,
        "wins": defaultdict(int),
        "draws": 0,
        "excluded": 0,
        "errors": defaultdict(int),
    }


def aggregate_games(
    records: Sequence[Any],
) -> tuple[dict[tuple[str, str], dict[str, Any]], tuple[str, ...]]:
    """Aggregate Arena rows, rejecting duplicate games and excluding engine failures."""

    stats: dict[tuple[str, str], dict[str, Any]] = defaultdict(_empty_matchup)
    agents: set[str] = set()
    seen: set[str] = set()
    for original in records:
        row = _record_dict(original)
        game_id = str(row.get("game_id", ""))
        if not game_id:
            raise ValueError("every rating record requires game_id")
        if game_id in seen:
            raise ValueError(f"duplicate game_id: {game_id}")
        seen.add(game_id)
        player_0 = str(row.get("player_0", ""))
        player_1 = str(row.get("player_1", ""))
        if not player_0 or not player_1 or player_0 == player_1:
            raise ValueError("rating games require two distinct agent names")
        agents.update((player_0, player_1))
        stat = stats[_pair_key(player_0, player_1)]
        stat["games"] += 1

        reward_0 = row.get("reward_0")
        reward_1 = row.get("reward_1")
        completed = str(row.get("status", "")) == "completed"
        if completed and reward_0 is not None and reward_1 is not None:
            reward_0 = float(reward_0)
            reward_1 = float(reward_1)
            if not math.isfinite(reward_0) or not math.isfinite(reward_1):
                raise ValueError(f"non-finite reward in {game_id}")
            if reward_0 > reward_1:
                stat["wins"][player_0] += 1
            elif reward_1 > reward_0:
                stat["wins"][player_1] += 1
            else:
                stat["draws"] += 1
            stat["fit_games"] += 1
            continue

        # A single missing reward identifies the responsible agent.  Unknown,
        # double-sided, and engine failures are excluded instead of inventing a
        # winner that could bias the rating.
        if (reward_0 is None) != (reward_1 is None):
            failed = player_0 if reward_0 is None else player_1
            winner = player_1 if reward_0 is None else player_0
            stat["errors"][failed] += 1
            stat["wins"][winner] += 1
            stat["fit_games"] += 1
        else:
            stat["excluded"] += 1
    return stats, tuple(sorted(agents))


def _ensure_connected(names: Sequence[str], stats: Mapping[tuple[str, str], Mapping[str, Any]]) -> None:
    neighbors = {name: set() for name in names}
    for (left, right), stat in stats.items():
        if int(stat["fit_games"]) > 0:
            neighbors[left].add(right)
            neighbors[right].add(left)
    reached = {names[0]}
    pending = [names[0]]
    while pending:
        current = pending.pop()
        for neighbor in neighbors[current] - reached:
            reached.add(neighbor)
            pending.append(neighbor)
    if reached != set(names):
        missing = ", ".join(sorted(set(names) - reached))
        raise ValueError(f"disconnected comparison pool; unresolved agents: {missing}")


def _fit(
    names: Sequence[str],
    stats: Mapping[tuple[str, str], Mapping[str, Any]],
    prior_sigma: float,
    pair_cap: int,
) -> tuple[np.ndarray, np.ndarray]:
    index = {name: position for position, name in enumerate(names)}
    ratings = np.zeros(len(names), dtype=np.float64)
    prior_precision = 1.0 / (prior_sigma * prior_sigma)
    for _ in range(80):
        gradient = -prior_precision * ratings
        information = np.eye(len(names), dtype=np.float64) * prior_precision
        for (left, right), stat in stats.items():
            games = int(stat["fit_games"])
            if games <= 0:
                continue
            effective_games = float(games if pair_cap <= 0 else min(games, pair_cap))
            scale = effective_games / games
            i, j = index[left], index[right]
            score_left = (int(stat["wins"][left]) + 0.5 * int(stat["draws"])) * scale
            probability = _sigmoid((ratings[i] - ratings[j]) / ELO_SCALE)
            gradient_value = score_left - effective_games * probability
            gradient[i] += gradient_value / ELO_SCALE
            gradient[j] -= gradient_value / ELO_SCALE
            curvature = effective_games * probability * (1.0 - probability) / (ELO_SCALE**2)
            information[i, i] += curvature
            information[j, j] += curvature
            information[i, j] -= curvature
            information[j, i] -= curvature
        step = np.linalg.solve(information, gradient)
        ratings += step
        ratings -= ratings.mean()
        if float(np.max(np.abs(step))) < 1e-5:
            break
    else:
        raise ValueError("Bradley-Terry fit did not converge")

    information = np.eye(len(names), dtype=np.float64) * prior_precision
    for (left, right), stat in stats.items():
        games = int(stat["fit_games"])
        if games <= 0:
            continue
        effective_games = float(games if pair_cap <= 0 else min(games, pair_cap))
        i, j = index[left], index[right]
        probability = _sigmoid((ratings[i] - ratings[j]) / ELO_SCALE)
        curvature = effective_games * probability * (1.0 - probability) / (ELO_SCALE**2)
        information[i, i] += curvature
        information[j, j] += curvature
        information[i, j] -= curvature
        information[j, i] -= curvature
    covariance = np.linalg.inv(information)
    covariance = (
        covariance
        - covariance.mean(axis=0, keepdims=True)
        - covariance.mean(axis=1, keepdims=True)
        + covariance.mean()
    )
    return ratings, covariance


def estimate_ratings(
    records: Sequence[Any],
    *,
    prior_sigma: float = DEFAULT_PRIOR_SIGMA,
    pair_cap: int = DEFAULT_PAIR_CAP,
) -> dict[str, Any]:
    """Estimate centered ratings and posterior uncertainty from Arena games."""

    if not math.isfinite(prior_sigma) or prior_sigma <= 0:
        raise ValueError("prior_sigma must be finite and positive")
    if pair_cap < 0:
        raise ValueError("pair_cap cannot be negative")
    stats, names = aggregate_games(records)
    if len(names) < 2:
        raise ValueError("at least two agents are required")
    _ensure_connected(names, stats)
    centered, covariance = _fit(names, stats, prior_sigma, pair_cap)
    sigma = np.sqrt(np.maximum(0.0, np.diag(covariance)))

    ratings = []
    for position, name in enumerate(names):
        games = sum(int(stat["fit_games"]) for pair, stat in stats.items() if name in pair)
        errors = sum(int(stat["errors"].get(name, 0)) for pair, stat in stats.items() if name in pair)
        mu = 1000.0 + float(centered[position])
        standard_error = float(sigma[position])
        ratings.append(
            {
                "agent": name,
                "mu": mu,
                "sigma": standard_error,
                "lcb": mu - 2.0 * standard_error,
                "interval_low": mu - 1.96 * standard_error,
                "interval_high": mu + 1.96 * standard_error,
                "games": games,
                "errors": errors,
            }
        )

    matchups = []
    name_index = {name: position for position, name in enumerate(names)}
    for (left, right), stat in sorted(stats.items()):
        i, j = name_index[left], name_index[right]
        difference_variance = covariance[i, i] + covariance[j, j] - 2.0 * covariance[i, j]
        games = int(stat["fit_games"])
        matchups.append(
            {
                "agent_a": left,
                "agent_b": right,
                "games": int(stat["games"]),
                "fit_games": games,
                "wins_a": int(stat["wins"][left]),
                "wins_b": int(stat["wins"][right]),
                "draws": int(stat["draws"]),
                "excluded": int(stat["excluded"]),
                "errors_a": int(stat["errors"].get(left, 0)),
                "errors_b": int(stat["errors"].get(right, 0)),
                "score_rate_a": (
                    (int(stat["wins"][left]) + 0.5 * int(stat["draws"])) / games
                    if games
                    else None
                ),
                "model_win_probability_a": _sigmoid(
                    (centered[i] - centered[j]) / ELO_SCALE
                ),
                "difference_sigma": math.sqrt(max(0.0, float(difference_variance))),
            }
        )
    return {
        "format": "kaggriculture-bayesian-bt-v1",
        "scale": "field mean 1000; internal scale, not Kaggle Public rating",
        "prior_sigma": prior_sigma,
        "pair_cap": pair_cap,
        "outcome": "terminal win/draw/loss only; cash margin ignored",
        "ratings": sorted(ratings, key=lambda row: (-row["mu"], row["agent"])),
        "matchups": matchups,
        "covariance_order": list(names),
        "covariance": covariance.tolist(),
    }


__all__ = [
    "DEFAULT_PAIR_CAP",
    "DEFAULT_PRIOR_SIGMA",
    "aggregate_games",
    "estimate_ratings",
]
