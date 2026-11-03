#!/usr/bin/env python3
"""Benchmark deterministic local Kaggriculture games."""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

from kaggriculture_agent.local_arena import (
    GameSpec,
    dump_json,
    percentile,
    recommended_workers,
    run_games,
    system_info,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--agents", default="baseline,candidate")
    parser.add_argument("--output", type=Path, default=Path("benchmark.json"))
    parser.add_argument("--legacy-runner", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.legacy_runner:
        os.environ["KAGGRICULTURE_LEGACY_RUNNER"] = "1"
    if args.games < 1:
        raise SystemExit("--games must be positive")
    agents = [part.strip() for part in args.agents.split(",")]
    if len(agents) != 2:
        raise SystemExit("--agents must contain exactly two names")
    workers = recommended_workers(args.workers)
    specs = [
        GameSpec(
            game_id=f"benchmark-{index:06d}",
            seed=args.seed + index,
            player_0=agents[0],
            player_1=agents[1],
            agent_a=agents[0],
            agent_b=agents[1],
        )
        for index in range(args.games)
    ]
    usage_before = resource.getrusage(resource.RUSAGE_SELF)
    children_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.perf_counter()
    results = list(run_games(specs, workers))
    total_seconds = time.perf_counter() - started
    usage_after = resource.getrusage(resource.RUSAGE_SELF)
    children_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    completed = [result for result in results if result.status == "completed"]
    elapsed = [result.elapsed_seconds for result in completed]
    decisions = sum(result.decisions for result in results)
    agent_seconds = sum(result.agent_seconds for result in results)
    game_seconds = sum(result.engine_seconds for result in results)
    setup_seconds = sum(result.environment_setup_seconds for result in results)
    framework_seconds = max(0.0, game_seconds - setup_seconds)
    scheduling_estimate = max(0.0, total_seconds - sum(elapsed) / workers)
    cpu_seconds = (
        usage_after.ru_utime
        + usage_after.ru_stime
        - usage_before.ru_utime
        - usage_before.ru_stime
        + children_after.ru_utime
        + children_after.ru_stime
        - children_before.ru_utime
        - children_before.ru_stime
    )
    rss_unit = 1 if sys.platform == "darwin" else 1024
    errors = [r.error for r in results if r.error]
    payload = {
        "games": args.games,
        "completed_games": len(completed),
        "failed_games": args.games - len(completed),
        "total_seconds": total_seconds,
        "games_per_second": len(completed) / total_seconds,
        "decisions_per_second": decisions / total_seconds,
        "mean_game_seconds": sum(elapsed) / len(elapsed) if elapsed else 0.0,
        "p50_game_seconds": percentile(elapsed, 0.50),
        "p95_game_seconds": percentile(elapsed, 0.95),
        "worker_count": workers,
        "runner": "legacy" if args.legacy_runner else "fast",
        "seed_start": args.seed,
        "seed_end": args.seed + args.games - 1,
        "decisions": decisions,
        "agent_seconds": agent_seconds,
        "environment_setup_seconds": setup_seconds,
        "engine_and_framework_seconds": framework_seconds,
        "process_startup_and_scheduling_seconds_estimate": scheduling_estimate,
        "disabled_external_log_io_seconds": 0.0,
        "agent_time_fraction": agent_seconds / (agent_seconds + game_seconds),
        "environment_setup_time_fraction": setup_seconds / (agent_seconds + game_seconds),
        "engine_and_framework_time_fraction": framework_seconds
        / (agent_seconds + game_seconds),
        "cpu_seconds": cpu_seconds,
        "cpu_utilization_percent": 100.0 * cpu_seconds / total_seconds,
        "max_rss_bytes": max(usage_after.ru_maxrss, children_after.ru_maxrss) * rss_unit,
        "error_count": sum("ERROR" in error for error in errors),
        "timeout_count": sum("TIMEOUT" in error for error in errors),
        "invalid_action_count": sum("INVALID" in error for error in errors),
        "errors": errors,
        **system_info(),
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    dump_json(output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"benchmark_json={output}")


if __name__ == "__main__":
    main()
