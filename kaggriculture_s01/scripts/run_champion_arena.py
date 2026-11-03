#!/usr/bin/env python3
"""Evaluate registered candidates and persist champion promotions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kaggriculture_agent.champion_arena import load_config, run_champion_arena

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "champion_arena.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, help="override the config output directory")
    parser.add_argument(
        "--games-per-matchup",
        "--games-per-pair",
        dest="games_per_matchup",
        type=int,
        help="override the number of paired games per candidate/champion matchup",
    )
    parser.add_argument("--workers", type=int, help="override worker count")
    parser.add_argument("--seed", type=int, help="override the first schedule seed")
    seats = parser.add_mutually_exclusive_group()
    seats.add_argument("--swap-seats", dest="swap_seats", action="store_true")
    seats.add_argument("--no-swap-seats", dest="swap_seats", action="store_false")
    parser.set_defaults(swap_seats=None)
    parser.add_argument("--no-resume", action="store_true", help="do not reuse completed games")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate config and print the schedule size without playing games",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="run one game per matchup (and one worker) for a quick end-to-end check",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config.resolve())
    config = config.with_overrides(
        games_per_matchup=args.games_per_matchup,
        seed=args.seed,
        swap_seats=args.swap_seats,
        workers=args.workers,
        output=args.output.resolve() if args.output else None,
    )
    summary = run_champion_arena(
        config,
        resume=not args.no_resume,
        dry_run=args.dry_run,
        smoke=args.smoke,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
