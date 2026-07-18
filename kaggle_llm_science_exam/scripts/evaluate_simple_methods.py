#!/usr/bin/env python3
"""Evaluate simple MAP@3 baselines on the labeled train split."""

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


def ap_at_3(order: list[str], answer: str) -> float:
    top3 = order[:3]
    if answer not in top3:
        return 0.0
    return 1.0 / (top3.index(answer) + 1)


def map_at_3(rows: list[dict[str, str]], predictions: list[list[str]]) -> float:
    return sum(ap_at_3(pred, row["answer"]) for row, pred in zip(rows, predictions)) / len(rows)


def rank_scores(scores: dict[str, float]) -> list[str]:
    return sorted(OPTIONS, key=lambda option: (-scores[option], option))


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


def predictions_for_methods(rows: list[dict[str, str]]) -> dict[str, list[list[str]]]:
    answer_counts = Counter(row["answer"] for row in rows)
    frequency_order = [option for option, _ in answer_counts.most_common()]
    idf = build_idf(rows)

    predictions: dict[str, list[list[str]]] = {
        "sample_ABC": [list(OPTIONS) for _ in rows],
        "label_frequency": [frequency_order for _ in rows],
        "length": [],
        "tfidf": [],
        "overlap": [],
        "length_tfidf_ensemble": [],
    }

    for row in rows:
        prompt_set = set(content_tokens(row["prompt"]))
        prompt_vec = tfidf_vector(content_tokens(row["prompt"]), idf)

        length_values = [word_count(row[option]) for option in OPTIONS]
        tfidf_values = [
            cosine(prompt_vec, tfidf_vector(content_tokens(row[option]), idf)) for option in OPTIONS
        ]
        overlap_values = []
        for option in OPTIONS:
            option_set = set(content_tokens(row[option]))
            overlap_values.append(len(prompt_set & option_set) / (len(prompt_set | option_set) or 1))

        length_scores = dict(zip(OPTIONS, length_values))
        tfidf_scores = dict(zip(OPTIONS, tfidf_values))
        overlap_scores = dict(zip(OPTIONS, overlap_values))

        ensemble_values = [
            length_z + 0.25 * tfidf_z
            for length_z, tfidf_z in zip(zscores(length_values), zscores(tfidf_values))
        ]
        ensemble_scores = dict(zip(OPTIONS, ensemble_values))

        predictions["length"].append(rank_scores(length_scores))
        predictions["tfidf"].append(rank_scores(tfidf_scores))
        predictions["overlap"].append(rank_scores(overlap_scores))
        predictions["length_tfidf_ensemble"].append(rank_scores(ensemble_scores))

    return predictions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train-csv",
        type=Path,
        default=Path("kaggle_llm_science_exam/data/raw/train.csv"),
        help="Path to labeled train.csv.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with args.train_csv.open(newline="", encoding="utf-8") as src:
        rows = list(csv.DictReader(src))

    predictions = predictions_for_methods(rows)
    print("method,map@3")
    for method, preds in sorted(
        predictions.items(), key=lambda item: map_at_3(rows, item[1]), reverse=True
    ):
        print(f"{method},{map_at_3(rows, preds):.4f}")


if __name__ == "__main__":
    main()
