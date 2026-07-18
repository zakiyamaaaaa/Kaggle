#!/usr/bin/env python3
"""Evaluate BM25 RAG baselines on labeled train.csv."""

from __future__ import annotations

import argparse
from pathlib import Path

from bm25_rag import RagRanker, RagWeights, ap_at_3, load_wiki_corpus, read_rows
from bm25_rag import BM25Retriever


def map_at_3(rows, ranker: RagRanker) -> float:
    return sum(ap_at_3(ranker.rank_row(row), row["answer"]) for row in rows) / len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train-csv",
        type=Path,
        default=Path("kaggle_llm_science_exam/data/raw/train.csv"),
    )
    parser.add_argument(
        "--corpus-path",
        type=Path,
        default=Path("kaggle_llm_science_exam/data/external/ranchantan"),
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--rag-weight", type=float, default=0.1)
    parser.add_argument("--tfidf-weight", type=float, default=0.25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_rows(args.train_csv)
    corpus_texts, corpus_tokens = load_wiki_corpus(args.corpus_path)
    retriever = BM25Retriever(corpus_tokens)
    ranker = RagRanker(
        retriever,
        corpus_texts,
        rows,
        RagWeights(
            tfidf_weight=args.tfidf_weight,
            rag_weight=args.rag_weight,
            top_k=args.top_k,
        ),
    )
    score = map_at_3(rows, ranker)
    print(f"corpus_docs={len(corpus_texts)}")
    print(f"top_k={args.top_k} tfidf_weight={args.tfidf_weight} rag_weight={args.rag_weight}")
    print(f"train_map@3={score:.4f}")


if __name__ == "__main__":
    main()
