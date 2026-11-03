#!/usr/bin/env python3
"""Evaluate an extracted public main.py against a registered local reference."""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path

from kaggriculture_agent import registry
from kaggriculture_agent.local_arena import GameSpec, play_game


def load_agent(path: Path, label: str):
    spec = importlib.util.spec_from_file_location(f"public_{label}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not callable(getattr(module, "agent", None)):
        raise RuntimeError(f"{path} does not expose callable agent")
    return module.agent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--opponent", default="public_salem")
    parser.add_argument("--opponent-source", type=Path)
    parser.add_argument("--seed", type=int, default=962100)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    alias = f"_public_{args.label}"
    registry.AGENTS[alias] = load_agent(args.source, args.label)
    opponent = args.opponent
    if args.opponent_source:
        opponent = f"_public_{args.opponent}"
        registry.AGENTS[opponent] = load_agent(args.opponent_source, args.opponent)
    rows = []
    for seed in range(args.seed, args.seed + args.seeds):
        for seat in (0, 1):
            players = (alias, opponent) if seat == 0 else (opponent, alias)
            result = play_game(GameSpec(f"{args.label}-{seed}-{seat}", seed, *players, alias, opponent))
            telemetry = getattr(registry.AGENTS[alias], "telemetry", None)
            own, other = (
                (result.reward_0, result.reward_1) if seat == 0 else (result.reward_1, result.reward_0)
            )
            rows.append(
                {
                    "seed": seed,
                    "seat": seat,
                    "status": result.status,
                    "reward": own,
                    "opponent_reward": other,
                    "margin": None if own is None or other is None else own - other,
                    "win": None if own is None or other is None else own > other,
                    "error": result.error,
                    "telemetry": copy.deepcopy(telemetry) if isinstance(telemetry, dict) else None,
                }
            )
    valid = [row for row in rows if row["status"] == "completed"]
    summary = {
        "agent": args.label,
        "opponent": args.opponent,
        "games": len(rows),
        "completed": len(valid),
        "wins": sum(bool(row["win"]) for row in valid),
        "win_rate": sum(bool(row["win"]) for row in valid) / len(valid) if valid else None,
        "mean_reward": sum(row["reward"] for row in valid) / len(valid) if valid else None,
        "mean_margin": sum(row["margin"] for row in valid) / len(valid) if valid else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"summary": summary, "games": rows}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
