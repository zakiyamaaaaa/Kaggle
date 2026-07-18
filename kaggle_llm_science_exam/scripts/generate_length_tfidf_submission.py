#!/usr/bin/env python3
"""Generate a length + TF-IDF similarity ensemble submission."""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import Counter
from pathlib import Path


OPTIONS = ("A", "B", "C", "D", "E")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?")
STOPWORDS = {
    "the",
    "of",
    "and",
    "to",
    "in",
    "a",
    "is",
    "are",
    "which",
    "following",
    "statement",
    "statements",
    "accurately",
    "describes",
    "describe",
    "what",
    "how",
    "by",
    "for",
    "with",
    "as",
    "an",
    "on",
    "from",
    "that",
    "it",
    "this",
    "its",
    "be",
    "was",
    "were",
    "can",
    "into",
    "or",
    "not",
    "due",
    "between",
    "among",
    "about",
    "refers",
    "system",
    "systems",
    "object",
    "objects",
    "law",
    "theory",
    "mass",
    "data",
    "time",
    "answer",
    "option",
}


def tokens(text: str) -> list[str]:
    return [word.lower() for word in WORD_RE.findall(text or "")]


def content_tokens(text: str) -> list[str]:
    return [word for word in tokens(text) if len(word) >= 3 and word not in STOPWORDS]


def word_count(text: str) -> int:
    return len(tokens(text))


def zscores(values: list[float]) -> list[float]:
    mean = sum(values) / len(values)
    var = sum((value - mean) ** 2 for value in values) / len(values)
    scale = math.sqrt(var) or 1.0
    return [(value - mean) / scale for value in values]


def build_idf(rows: list[dict[str, str]]) -> dict[str, float]:
    docs: list[set[str]] = []
    for row in rows:
        docs.append(set(content_tokens(row["prompt"])))
        docs.extend(set(content_tokens(row[option])) for option in OPTIONS)

    df: Counter[str] = Counter()
    for doc in docs:
        df.update(doc)

    n_docs = len(docs)
    return {term: math.log((n_docs + 1) / (count + 1)) + 1 for term, count in df.items()}


def tfidf_vector(words: list[str], idf: dict[str, float]) -> dict[str, float]:
    counts = Counter(words)
    return {word: count * idf.get(word, 1.0) for word, count in counts.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    numerator = sum(value * b.get(key, 0.0) for key, value in a.items())
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    if not norm_a or not norm_b:
        return 0.0
    return numerator / (norm_a * norm_b)


def rank_row(row: dict[str, str], idf: dict[str, float], tfidf_weight: float) -> list[str]:
    prompt_vec = tfidf_vector(content_tokens(row["prompt"]), idf)
    length_values = [word_count(row[option]) for option in OPTIONS]
    tfidf_values = [
        cosine(prompt_vec, tfidf_vector(content_tokens(row[option]), idf)) for option in OPTIONS
    ]
    scores = [
        length_z + tfidf_weight * tfidf_z
        for length_z, tfidf_z in zip(zscores(length_values), zscores(tfidf_values))
    ]
    return [
        option
        for _, option in sorted(zip(scores, OPTIONS), key=lambda item: (-item[0], item[1]))
    ]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as src:
        return list(csv.DictReader(src))


def generate_submission(
    train_csv: Path, test_csv: Path, output_csv: Path, tfidf_weight: float
) -> None:
    train_rows = read_rows(train_csv) if train_csv.exists() else []
    test_rows = read_rows(test_csv)
    idf = build_idf(train_rows + test_rows)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as dst:
        writer = csv.DictWriter(dst, fieldnames=["id", "prediction"])
        writer.writeheader()
        for row in test_rows:
            writer.writerow(
                {"id": row["id"], "prediction": " ".join(rank_row(row, idf, tfidf_weight)[:3])}
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train-csv",
        type=Path,
        default=Path("kaggle_llm_science_exam/data/raw/train.csv"),
        help="Path to train.csv for IDF fitting.",
    )
    parser.add_argument(
        "--test-csv",
        type=Path,
        default=Path("kaggle_llm_science_exam/data/raw/test.csv"),
        help="Path to Kaggle test.csv.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("kaggle_llm_science_exam/submissions/length_tfidf_ensemble.csv"),
        help="Path to write the submission CSV.",
    )
    parser.add_argument(
        "--tfidf-weight",
        type=float,
        default=0.25,
        help="Weight for row-normalized TF-IDF prompt/option cosine similarity.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate_submission(args.train_csv, args.test_csv, args.output_csv, args.tfidf_weight)
    print(f"Wrote {args.output_csv}")


if __name__ == "__main__":
    main()
