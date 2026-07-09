#!/usr/bin/env python3
"""Generate a simple length-based MAP@3 baseline submission.

This baseline ranks answer options by descending word count for each prompt.
It uses only the test features and does not read the train answer labels.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


OPTIONS = ("A", "B", "C", "D", "E")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?")


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def rank_options_by_length(row: dict[str, str]) -> list[str]:
    return sorted(OPTIONS, key=lambda option: (-word_count(row[option]), option))


def generate_submission(test_csv: Path, output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with test_csv.open(newline="", encoding="utf-8") as src, output_csv.open(
        "w", newline="", encoding="utf-8"
    ) as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=["id", "prediction"])
        writer.writeheader()

        for row in reader:
            top3 = rank_options_by_length(row)[:3]
            writer.writerow({"id": row["id"], "prediction": " ".join(top3)})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test-csv",
        type=Path,
        default=Path("kaggle_llm_science_exam/data/raw/test.csv"),
        help="Path to Kaggle test.csv.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("kaggle_llm_science_exam/submissions/length_baseline.csv"),
        help="Path to write the submission CSV.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate_submission(args.test_csv, args.output_csv)
    print(f"Wrote {args.output_csv}")


if __name__ == "__main__":
    main()
