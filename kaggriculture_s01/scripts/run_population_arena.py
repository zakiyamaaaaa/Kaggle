#!/usr/bin/env python3
"""Run a reproducible candidate evaluation against the configured population."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kaggriculture_agent.population import load_population
from kaggriculture_agent.population_arena import run_population_arena
from kaggriculture_agent.registry import agent_names

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", default="candidate")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "population.json")
    parser.add_argument("--tier", choices=("development", "adoption", "final"), default="development")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--reference")
    parser.add_argument("--min-lcb-margin", type=float, default=0.0)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    available = set(agent_names())
    if args.candidate not in available:
        raise SystemExit(f"unknown candidate: {args.candidate}")
    config = load_population(args.config.resolve(), available_agents=available)
    summary = run_population_arena(
        args.candidate,
        config,
        args.tier,
        args.output.resolve(),
        workers=args.workers,
        resume=not args.no_resume,
        reference=args.reference,
        min_lcb_margin=args.min_lcb_margin,
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
