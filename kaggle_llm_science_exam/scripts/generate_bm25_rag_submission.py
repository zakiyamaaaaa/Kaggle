#!/usr/bin/env python3
"""Generate a BM25 RAG submission CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from bm25_rag import BM25Retriever, RagRanker, RagWeights, load_wiki_corpus, read_rows


def generate_submission(
    train_csv: Path,
    test_csv: Path,
    corpus_path: Path,
    output_csv: Path,
    weights: RagWeights,
) -> None:
    train_rows = read_rows(train_csv) if train_csv.exists() else []
    test_rows = read_rows(test_csv)
    corpus_texts, corpus_tokens = load_wiki_corpus(corpus_path)
    retriever = BM25Retriever(corpus_tokens)
    ranker = RagRanker(retriever, corpus_texts, train_rows + test_rows, weights)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as dst:
        writer = csv.DictWriter(dst, fieldnames=["id", "prediction"])
        writer.writeheader()
        for row in test_rows:
            writer.writerow({"id": row["id"], "prediction": " ".join(ranker.rank_row(row)[:3])})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train-csv",
        type=Path,
        default=Path("kaggle_llm_science_exam/data/raw/train.csv"),
    )
    parser.add_argument(
        "--test-csv",
        type=Path,
        default=Path("kaggle_llm_science_exam/data/raw/test.csv"),
    )
    parser.add_argument(
        "--corpus-path",
        type=Path,
        default=Path("kaggle_llm_science_exam/data/external/ranchantan"),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("kaggle_llm_science_exam/submissions/bm25_rag.csv"),
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--rag-weight", type=float, default=0.1)
    parser.add_argument("--tfidf-weight", type=float, default=0.25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    weights = RagWeights(
        tfidf_weight=args.tfidf_weight,
        rag_weight=args.rag_weight,
        top_k=args.top_k,
    )
    generate_submission(
        args.train_csv,
        args.test_csv,
        args.corpus_path,
        args.output_csv,
        weights,
    )
    print(f"Wrote {args.output_csv}")


if __name__ == "__main__":
    main()
