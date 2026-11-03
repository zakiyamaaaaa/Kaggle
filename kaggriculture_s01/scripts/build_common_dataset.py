#!/usr/bin/env python3
"""Combine compatible trajectory Arena outputs into a common Parquet dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kaggriculture_agent.dataset import build_common_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_common_dataset(args.input, args.output.resolve())
    print(json.dumps(result["audit"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
