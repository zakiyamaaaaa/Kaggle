#!/usr/bin/env python3
"""Summarize paired validation/holdout results for OMW net-stock v2."""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments/omw-net-stock-sellnow-v2"
OPPONENTS = ("omw", "peak", "triad", "salem", "early_milk", "baseline")


def score(game: dict) -> float:
    margin = game["margin"]
    return 1.0 if margin > 0 else 0.5 if margin == 0 else 0.0


def summarize_file(path: Path) -> tuple[dict, dict[tuple[int, int], float]]:
    payload = json.loads(path.read_text())
    games = payload["games"]
    values = [score(game) for game in games]
    wins = sum(value == 1.0 for value in values)
    draws = sum(value == 0.5 for value in values)
    completed = sum(game["status"] == "completed" for game in games)
    return (
        {
            "games": len(games),
            "completed": completed,
            "errors": len(games) - completed,
            "wins": wins,
            "draws": draws,
            "losses": len(games) - wins - draws,
            "score": sum(values) / len(values),
            "mean_reward": payload["summary"]["mean_reward"],
            "mean_margin": payload["summary"]["mean_margin"],
        },
        {(game["seed"], game["seat"]): value for game, value in zip(games, values)},
    )


def bootstrap(seed_diffs: dict[int, float], samples: int = 20_000) -> list[float]:
    rng = random.Random(20260921)
    seeds = sorted(seed_diffs)
    estimates = []
    for _ in range(samples):
        estimates.append(sum(seed_diffs[rng.choice(seeds)] for _ in seeds) / len(seeds))
    estimates.sort()
    return [estimates[int(samples * 0.025)], estimates[int(samples * 0.975)]]


def summarize_stage(stage: str) -> dict:
    directory = EXPERIMENT / stage
    rows = []
    by_seed: dict[int, list[float]] = {}
    for opponent in OPPONENTS:
        candidate, candidate_games = summarize_file(directory / f"candidate-{opponent}.json")
        control, control_games = summarize_file(directory / f"control-{opponent}.json")
        keys = sorted(candidate_games)
        if keys != sorted(control_games):
            raise RuntimeError(f"unpaired games for {stage}/{opponent}")
        for seed, seat in keys:
            by_seed.setdefault(seed, []).append(candidate_games[(seed, seat)] - control_games[(seed, seat)])
        rows.append(
            {
                "opponent": opponent,
                "candidate": candidate,
                "control": control,
                "score_delta": candidate["score"] - control["score"],
            }
        )
    candidate_score = sum(row["candidate"]["score"] for row in rows) / len(rows)
    control_score = sum(row["control"]["score"] for row in rows) / len(rows)
    seed_diffs = {seed: sum(values) / len(values) for seed, values in by_seed.items()}
    return {
        "stage": stage,
        "seed_count": len(seed_diffs),
        "opponents": rows,
        "aggregate": {
            "candidate_score": candidate_score,
            "control_score": control_score,
            "paired_score_delta": candidate_score - control_score,
            "bootstrap_95_ci": bootstrap(seed_diffs),
            "games_per_policy": sum(row["candidate"]["games"] for row in rows),
            "errors_per_policy": sum(row["candidate"]["errors"] for row in rows),
        },
    }


def main() -> None:
    result = {
        "policy": "omw_net_stock_sellnow_v2",
        "selection_metric": "win + 0.5 * draw",
        "stages": [summarize_stage("validation"), summarize_stage("holdout")],
    }
    output = EXPERIMENT / "results-summary.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
