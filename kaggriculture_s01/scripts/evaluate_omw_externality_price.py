#!/usr/bin/env python3
"""Paired screen of frozen OMW and two forecast4 guard variants."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from kaggriculture_agent import registry
from kaggriculture_agent.local_arena import GameSpec, play_game


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATHS = {
    "control": ROOT / "references/kaggle-scan-2026-09-21/extracted/one-more-wheat/main.py",
    "forecast4": ROOT / "experiments/omw-forecast4/main.py",
    "externality": ROOT / "experiments/omw-externality-gate/main.py",
    "price_guard": ROOT / "experiments/omw-price-guard/main.py",
}
OPPONENT_PATHS = {
    "omw": ROOT / "references/kaggle-scan-2026-09-21/extracted/one-more-wheat/main.py",
    "peak": ROOT / "references/kaggle-scan-2026-09-21/extracted/peak2950/main.py",
    "triad": ROOT / "references/kaggle-scan-2026-09-21/extracted/triad-counter/main.py",
}
OPPONENTS = ("omw", "peak", "triad", "salem", "early_milk", "baseline")


def load(path: Path, label: str):
    spec = importlib.util.spec_from_file_location(label, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module.agent


def init_worker() -> None:
    suffix = str(os.getpid())
    for name, path in POLICY_PATHS.items():
        registry.AGENTS[f"_f4_{name}"] = load(path, f"_f4_{name}_{suffix}")
    for name, path in OPPONENT_PATHS.items():
        registry.AGENTS[f"_f4_opp_{name}"] = load(path, f"_f4_opp_{name}_{suffix}")
    registry.AGENTS["_f4_opp_salem"] = registry.get_agent("public_salem")
    registry.AGENTS["_f4_opp_early_milk"] = registry.get_agent("salem_early_milk")
    registry.AGENTS["_f4_opp_baseline"] = registry.get_agent("baseline")


def run(task: tuple[str, str, int, int]) -> dict:
    policy, opponent, seed, seat = task
    candidate = f"_f4_{policy}"
    rival = f"_f4_opp_{opponent}"
    players = (candidate, rival) if seat == 0 else (rival, candidate)
    result = play_game(
        GameSpec(
            f"omw-guard-comparison-{policy}-{opponent}-{seed}-{seat}",
            seed,
            *players,
            candidate,
            rival,
            f"{policy}-{opponent}-{seed}",
            seat,
        )
    )
    own, other = ((result.reward_0, result.reward_1) if seat == 0
                  else (result.reward_1, result.reward_0))
    margin = None if own is None or other is None else own - other
    return {"policy": policy, "opponent": opponent, "seed": seed, "seat": seat,
            "status": result.status, "reward": own, "opponent_reward": other,
            "margin": margin, "error": result.error}


def stat(rows: list[dict]) -> dict:
    valid = [r for r in rows if r["status"] == "completed" and r["margin"] is not None]
    wins = sum(r["margin"] > 0 for r in valid)
    draws = sum(r["margin"] == 0 for r in valid)
    return {"games": len(rows), "completed": len(valid), "errors": len(rows) - len(valid),
            "wins": wins, "draws": draws, "losses": len(valid) - wins - draws,
            "score": (wins + 0.5 * draws) / len(valid) if valid else None,
            "mean_reward": statistics.fmean(r["reward"] for r in valid) if valid else None,
            "mean_margin": statistics.fmean(r["margin"] for r in valid) if valid else None}


def ci(values: list[float]) -> list[float]:
    rng = random.Random(20260922)
    samples = sorted(statistics.fmean(values[rng.randrange(len(values))]
                                      for _ in values) for _ in range(5000))
    return [samples[125], samples[4874]]


def summarize(rows: list[dict], policies: tuple[str, ...]) -> dict:
    table = {p: {o: stat([r for r in rows if r["policy"] == p and r["opponent"] == o])
                 for o in OPPONENTS} for p in policies}
    aggregate = {}
    lookup = {(r["policy"], r["opponent"], r["seed"], r["seat"]): r for r in rows}
    for policy in policies:
        scores = [table[policy][o]["score"] for o in OPPONENTS]
        margins = [table[policy][o]["mean_margin"] for o in OPPONENTS]
        entry = {"score": statistics.fmean(scores), "mean_opponent_balanced_margin": statistics.fmean(margins),
                 "errors": sum(table[policy][o]["errors"] for o in OPPONENTS)}
        if policy != "control":
            seed_deltas = []
            for seed in sorted({r["seed"] for r in rows}):
                deltas = []
                for opponent in OPPONENTS:
                    for seat in (0, 1):
                        a = lookup[(policy, opponent, seed, seat)]["margin"]
                        b = lookup[("control", opponent, seed, seat)]["margin"]
                        sa = 1.0 if a > 0 else 0.5 if a == 0 else 0.0
                        sb = 1.0 if b > 0 else 0.5 if b == 0 else 0.0
                        deltas.append(sa - sb)
                seed_deltas.append(statistics.fmean(deltas))
            entry["paired_score_delta_vs_control"] = statistics.fmean(seed_deltas)
            entry["paired_score_delta_ci95"] = ci(seed_deltas)
        aggregate[policy] = entry
    return {"metric": "win + 0.5 * draw", "policies": table, "aggregate": aggregate}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=994000)
    parser.add_argument("--seeds", type=int, default=32)
    parser.add_argument("--workers", type=int, default=min(12, os.cpu_count() or 1))
    parser.add_argument("--policies", default=",".join(POLICY_PATHS))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    policies = tuple(part.strip() for part in args.policies.split(",") if part.strip())
    if "control" not in policies or any(policy not in POLICY_PATHS for policy in policies):
        parser.error("--policies must include control and contain only control,forecast4,externality,price_guard")
    tasks = [(p, o, seed, seat) for seed in range(args.seed, args.seed + args.seeds)
             for o in OPPONENTS for p in policies for seat in (0, 1)]
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker) as pool:
        rows = list(pool.map(run, tasks, chunksize=1))
    payload = {"seed_start": args.seed, "seed_count": args.seeds,
               "games": len(rows), "summary": summarize(rows, policies), "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
