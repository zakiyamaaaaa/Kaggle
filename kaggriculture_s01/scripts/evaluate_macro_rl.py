#!/usr/bin/env python3
"""Run a small seat-swapped holdout arena for a trained macro policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kaggriculture_agent import registry
from kaggriculture_agent.local_arena import GameSpec, play_game
from kaggriculture_agent.macro_rl import make_macro_agent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=951001)
    parser.add_argument("--seeds", type=int, default=4)
    parser.add_argument("--opponents", default="candidate,economy_mix50")
    args = parser.parse_args()
    model = json.loads(args.model.read_text())
    alias = "_macro_rl_holdout"
    registry.AGENTS[alias] = make_macro_agent(model, "macro-rl-holdout")
    rows = []
    for opponent in args.opponents.split(","):
        for seed in range(args.seed, args.seed + args.seeds):
            for seat in (0, 1):
                players = (alias, opponent) if seat == 0 else (opponent, alias)
                result = play_game(GameSpec(f"{opponent}-{seed}-{seat}", seed, *players, alias, opponent))
                if result.status != "completed":
                    raise RuntimeError(result.error)
                own, other = (
                    (result.reward_0, result.reward_1)
                    if seat == 0
                    else (result.reward_1, result.reward_0)
                )
                rows.append(
                    {
                        "opponent": opponent,
                        "seed": seed,
                        "seat": seat,
                        "reward": own,
                        "opponent_reward": other,
                        "margin": own - other,
                        "win": own > other,
                    }
                )
    summary = {}
    for opponent in args.opponents.split(","):
        selected = [row for row in rows if row["opponent"] == opponent]
        summary[opponent] = {
            "games": len(selected),
            "win_rate": sum(row["win"] for row in selected) / len(selected),
            "mean_reward": sum(row["reward"] for row in selected) / len(selected),
            "mean_margin": sum(row["margin"] for row in selected) / len(selected),
        }
    report = {"model": str(args.model), "summary": summary, "games": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
