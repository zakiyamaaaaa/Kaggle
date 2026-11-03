#!/usr/bin/env python3
"""Validate and display the reproducible Kaggriculture evaluation population."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kaggriculture_agent.population import load_population, population_fingerprint
from kaggriculture_agent.registry import agent_names

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "population.json")
    parser.add_argument("--no-verify-artifacts", action="store_true")
    args = parser.parse_args()
    config = load_population(
        args.config.resolve(),
        available_agents=set(agent_names()),
        verify=not args.no_verify_artifacts,
    )
    payload = config.to_dict()
    payload["fingerprint"] = population_fingerprint(config)
    payload["agent_count"] = len(config.members)
    for name, tier in payload["evaluation_tiers"].items():
        tier["paired_games_per_matchup"] = config.tier(name).games_per_matchup
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
