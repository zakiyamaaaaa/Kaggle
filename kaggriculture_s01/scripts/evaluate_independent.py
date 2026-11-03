#!/usr/bin/env python3
"""Compare fixed policies against an identical seed/seat/opponent panel."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

from kaggriculture_agent.local_arena import GameSpec, run_games, write_games
from kaggriculture_agent.registry import get_agent

ROOT = Path(__file__).resolve().parents[1]


def fingerprints() -> dict[str, str]:
    paths = [
        *sorted((ROOT / "src/kaggriculture_agent").glob("*.py")),
        ROOT / "submissions/public-salem-2900/main.py",
        Path(__file__).resolve(),
    ]
    from kaggle_environments.envs.kaggriculture import kaggriculture as engine

    paths.append(Path(engine.__file__))
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def bootstrap(values: list[float]) -> list[float]:
    rng = random.Random(20260920)
    n = len(values)
    samples = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(2000))
    return [samples[50], samples[1949]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents", required=True)
    parser.add_argument("--opponents", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--seeds", type=int, default=32)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    agents = args.agents.split(",")
    opponents = args.opponents.split(",")
    if args.reference not in agents or args.seeds < 1:
        parser.error("reference must be in agents; seeds must be positive")
    if len(set(agents)) != len(agents) or len(set(opponents)) != len(opponents):
        parser.error("duplicate policies")
    for name in agents + opponents:
        get_agent(name)
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error("use a new output directory; results are immutable")
    before = fingerprints()
    manifest = {**vars(args), "output": str(args.output), "fingerprints": before}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    specs = []
    for agent in agents:
        for opponent in opponents:
            for seed in range(args.seed, args.seed + args.seeds):
                pair = f"{agent}--{opponent}--{seed}"
                for seat in (0, 1):
                    players = (agent, opponent) if seat == 0 else (opponent, agent)
                    specs.append(
                        GameSpec(f"{pair}--{seat}", seed, *players, agent, opponent, pair, seat)
                    )
    spec_by_id = {s.game_id: s for s in specs}
    observations = defaultdict(list)
    results = []
    start = time.perf_counter()
    for result in run_games(specs, args.workers):
        results.append(result)
        if result.status == "completed":
            spec = spec_by_id[result.game_id]
            own, other = (
                (result.reward_0, result.reward_1)
                if spec.seat == 0
                else (result.reward_1, result.reward_0)
            )
            score = 1.0 if own > other else 0.0 if own < other else 0.5
            observations[spec.agent_a, spec.agent_b, spec.seed].append((score, own, own - other))
        if len(results) % 64 == 0:
            write_games(args.output / "games.csv", [r.csv_row() for r in results])
            print(f"{len(results)}/{len(specs)} games", flush=True)
    write_games(args.output / "games.csv", [r.csv_row() for r in results])
    failed = [r.game_id for r in results if r.status != "completed"]
    if fingerprints() != before:
        raise RuntimeError("source changed during evaluation; reject this run")
    if failed:
        raise RuntimeError(f"failed games: {failed}")
    paired = {
        key: tuple(statistics.fmean(v[i] for v in vals) for i in range(3))
        for key, vals in observations.items()
    }
    summary = {
        "seeds": args.seeds,
        "seed_start": args.seed,
        "games": len(results),
        "failed_games": len(failed),
        "seconds": time.perf_counter() - start,
        "reference": args.reference,
        "policies": {},
    }
    for agent in agents:
        panel = {}
        for opponent in opponents:
            values = [paired[agent, opponent, s] for s in range(args.seed, args.seed + args.seeds)]
            panel[opponent] = dict(
                zip(
                    ("score", "cash", "cash_margin"),
                    (statistics.fmean(v[i] for v in values) for i in range(3)),
                )
            )
        score_deltas, cash_deltas = [], []
        for seed in range(args.seed, args.seed + args.seeds):
            score_deltas.append(
                statistics.fmean(
                    paired[agent, o, seed][0] - paired[args.reference, o, seed][0]
                    for o in opponents
                )
            )
            cash_deltas.append(
                statistics.fmean(
                    paired[agent, o, seed][1] - paired[args.reference, o, seed][1]
                    for o in opponents
                )
            )
        summary["policies"][agent] = {
            "opponents": panel,
            "score_delta": statistics.fmean(score_deltas),
            "score_delta_ci95": bootstrap(score_deltas),
            "cash_delta": statistics.fmean(cash_deltas),
            "cash_delta_ci95": bootstrap(cash_deltas),
        }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
