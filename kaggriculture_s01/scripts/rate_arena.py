#!/usr/bin/env python3
"""Estimate uncertainty-aware ratings from an Arena games.csv file."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from kaggriculture_agent.rating import DEFAULT_PAIR_CAP, DEFAULT_PRIOR_SIGMA, estimate_ratings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("games_csv", type=Path, help="Arena games.csv to rate")
    parser.add_argument("--output", type=Path, help="write the full result as JSON")
    parser.add_argument("--prior-sigma", type=float, default=DEFAULT_PRIOR_SIGMA)
    parser.add_argument(
        "--pair-cap",
        type=int,
        default=DEFAULT_PAIR_CAP,
        help="maximum effective observations per pair (0 disables the cap)",
    )
    return parser.parse_args()


def load_games(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for field in ("reward_0", "reward_1"):
            value = row.get(field, "")
            row[field] = float(value) if value not in (None, "") else None
    return rows


def main() -> None:
    args = parse_args()
    result = estimate_ratings(
        load_games(args.games_csv),
        prior_sigma=args.prior_sigma,
        pair_cap=args.pair_cap,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(f"{'agent':<32} {'mu':>9} {'sigma':>9} {'LCB':>9} {'games':>7} {'errors':>7}")
    for row in sorted(result["ratings"], key=lambda item: (-item["lcb"], item["agent"])):
        print(
            f"{row['agent']:<32} {row['mu']:>9.2f} {row['sigma']:>9.2f} "
            f"{row['lcb']:>9.2f} {row['games']:>7d} {row['errors']:>7d}"
        )


if __name__ == "__main__":
    main()
