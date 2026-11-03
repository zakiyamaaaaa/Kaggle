#!/usr/bin/env python3
"""Run deterministic Kaggriculture matchups in parallel."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from kaggriculture_agent.local_arena import (
    EPISODE_FIELDS,
    GameResult,
    MATCHUP_FIELDS,
    PAIR_FIELDS,
    TRANSITION_FIELDS,
    build_schedule,
    dump_json,
    episode_rows,
    matchup_rows,
    pair_rows,
    rating_rows,
    read_parquet,
    read_completed,
    recommended_workers,
    run_games,
    percentile,
    system_info,
    write_csv,
    write_games,
    write_parquet,
)
from kaggriculture_agent.registry import agent_names


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents", default="baseline,candidate")
    parser.add_argument("--games-per-pair", type=int, default=100)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--swap-seats", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--legacy-runner", action="store_true")
    parser.add_argument(
        "--trajectory",
        "--trajectories",
        dest="trajectory",
        action="store_true",
        help="collect compact per-player transitions and Parquet summaries",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.legacy_runner:
        os.environ["KAGGRICULTURE_LEGACY_RUNNER"] = "1"
    agents = [value.strip() for value in args.agents.split(",") if value.strip()]
    unknown = sorted(set(agents) - set(agent_names()))
    if unknown:
        raise SystemExit(f"unknown agents: {', '.join(unknown)}")
    if len(agents) != len(set(agents)):
        raise SystemExit("--agents contains duplicate names")
    workers = recommended_workers(args.workers)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    games_path = output / "games.csv"
    completed = {} if args.no_resume else read_completed(games_path)
    schedule = build_schedule(agents, args.games_per_pair, args.seed, args.swap_seats)
    pending = [spec for spec in schedule if spec.game_id not in completed]

    transition_path = output / "transitions.parquet"
    existing_transition_rows = read_parquet(transition_path) if args.trajectory else []
    if args.trajectory:
        # A previous non-trajectory run may have completed games.csv without
        # producing rows.  Re-run only those games so opting in later still
        # creates a complete collection; normal CSV resume remains unchanged.
        collected_game_ids = {row.get("game_id") for row in existing_transition_rows}
        pending = [
            spec
            for spec in schedule
            if spec.game_id not in completed or spec.game_id not in collected_game_ids
        ]

    started = time.perf_counter()
    new_results = []
    new_transition_rows = []
    checkpoint_rows = {game_id: row for game_id, row in completed.items()}
    checkpoint_every = max(1, workers * 2)
    game_runs = run_games(pending, workers, capture_trajectory=args.trajectory)
    for game_run in game_runs:
        if args.trajectory:
            result, transition_rows = game_run
            new_transition_rows.extend(transition_rows)
        else:
            result = game_run
        new_results.append(result)
        checkpoint_rows[result.game_id] = result.csv_row()
        if len(new_results) % checkpoint_every == 0:
            write_games(
                games_path,
                [checkpoint_rows[spec.game_id] for spec in schedule if spec.game_id in checkpoint_rows],
            )
    total_seconds = time.perf_counter() - started
    result_by_id = {result.game_id: result for result in new_results}
    rows = []
    complete_results = []
    for spec in schedule:
        if spec.game_id in result_by_id:
            result = result_by_id[spec.game_id]
            rows.append(result.csv_row())
            complete_results.append(result)
        elif spec.game_id in completed:
            row = completed[spec.game_id]
            rows.append({key: row.get(key, "") for key in row})
            complete_results.append(
                GameResult(
                    game_id=spec.game_id,
                    seed=spec.seed,
                    player_0=spec.player_0,
                    player_1=spec.player_1,
                    reward_0=float(row["reward_0"]),
                    reward_1=float(row["reward_1"]),
                    winner=row["winner"],
                    steps=int(row["steps"]),
                    elapsed_seconds=float(row["elapsed_seconds"]),
                    status=row["status"],
                    error=row["error"],
                    agent_a=spec.agent_a,
                    agent_b=spec.agent_b,
                )
            )
    write_games(games_path, rows)
    matchups = matchup_rows(complete_results)
    write_csv(output / "matchups.csv", MATCHUP_FIELDS, matchups)
    ratings = rating_rows(complete_results)
    write_csv(output / "ratings.csv", ("agent", "rating", "games"), ratings)

    if args.trajectory:
        # Deduplicate by game/seat/step so a resumed or retried run cannot
        # append duplicate transitions.  The parent is the only writer.
        transition_by_key = {
            (row.get("game_id"), row.get("seat"), row.get("step")): row
            for row in existing_transition_rows
        }
        transition_by_key.update(
            {(row.get("game_id"), row.get("seat"), row.get("step")): row for row in new_transition_rows}
        )
        transition_rows = sorted(
            transition_by_key.values(),
            key=lambda row: (str(row.get("game_id")), int(row.get("seat", 0)), int(row.get("step", 0))),
        )
        write_parquet(transition_path, TRANSITION_FIELDS, transition_rows)
        write_parquet(output / "episodes.parquet", EPISODE_FIELDS, episode_rows(complete_results, schedule))
        write_parquet(output / "pairs.parquet", PAIR_FIELDS, pair_rows(complete_results, schedule))

    failures = [result for result in new_results if result.status != "completed"]
    summary = {
        "agents": agents,
        "scheduled_games": len(schedule),
        "completed_games": sum(r.status == "completed" for r in complete_results),
        "failed_games": len(failures),
        "reused_games": sum(spec.game_id in completed for spec in schedule),
        "executed_games": len(new_results),
        "total_seconds": total_seconds,
        "games_per_second": len(new_results) / total_seconds if total_seconds else 0.0,
        "worker_count": workers,
        "seed_start": min(spec.seed for spec in schedule),
        "seed_end": max(spec.seed for spec in schedule),
        "swap_seats": args.swap_seats,
        "trajectory": args.trajectory,
        "runner": "fast" if args.trajectory or not args.legacy_runner else "legacy",
        "system": system_info(),
    }
    dump_json(output / "summary.json", summary)
    benchmark_path = output / "benchmark.json"
    if new_results or not benchmark_path.exists():
        game_times = [result.elapsed_seconds for result in new_results]
        decisions = sum(result.decisions for result in new_results)
        benchmark = {
            "games": len(new_results),
            "completed_games": sum(r.status == "completed" for r in new_results),
            "failed_games": len(failures),
            "total_seconds": total_seconds,
            "games_per_second": len(new_results) / total_seconds if total_seconds else 0.0,
            "decisions_per_second": decisions / total_seconds if total_seconds else 0.0,
            "mean_game_seconds": sum(game_times) / len(game_times) if game_times else 0.0,
            "p50_game_seconds": percentile(game_times, 0.50),
            "p95_game_seconds": percentile(game_times, 0.95),
            "worker_count": workers,
            "seed_start": summary["seed_start"],
            "seed_end": summary["seed_end"],
            **system_info(),
        }
        dump_json(benchmark_path, benchmark)
    print(
        f"completed={summary['completed_games']} failed={summary['failed_games']} "
        f"reused={summary['reused_games']} seconds={total_seconds:.3f} "
        f"games_per_second={summary['games_per_second']:.3f} output={output}"
    )


if __name__ == "__main__":
    main()
