#!/usr/bin/env python3
"""Train leakage-safe terminal-score model ablations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kaggriculture_agent.outcome_model import train_from_directory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", default="candidate")
    parser.add_argument("--sample-every", type=int, default=12)
    args = parser.parse_args()
    result = train_from_directory(
        args.data.resolve(),
        args.output.resolve(),
        policy=args.policy,
        sample_every=args.sample_every,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
