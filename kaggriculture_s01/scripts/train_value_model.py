#!/usr/bin/env python3
"""Train the first leakage-aware Kaggriculture state-value model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kaggriculture_agent.value_model import load_tables, train_value_model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", default="candidate")
    parser.add_argument("--sample-every", type=int, default=12)
    parser.add_argument("--max-iter", type=int, default=120)
    args = parser.parse_args()
    metrics = train_value_model(
        load_tables(args.data),
        args.output,
        policy=args.policy,
        sample_every=args.sample_every,
        max_iter=args.max_iter,
    )
    print(json.dumps(metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
