#!/usr/bin/env python3
"""BM25 retrieval and RAG scoring helpers for LLM Science Exam."""

from __future__ import annotations

import csv
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from datasets import load_from_disk


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


def ap_at_3(order: list[str], answer: str) -> float:
    top3 = order[:3]
    if answer not in top3:
        return 0.0
    return 1.0 / (top3.index(answer) + 1)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as src:
        return list(csv.DictReader(src))


def load_wiki_corpus(corpus_path: Path) -> tuple[list[str], list[list[str]]]:
    dataset = load_from_disk(str(corpus_path))
    texts: list[str] = []
    tokenized: list[list[str]] = []
    for row in dataset:
        title = row.get("title") or ""
        section = row.get("section") or ""
        body = row.get("text") or ""
        text = " ".join(part for part in (title, section, body) if part).strip()
        if not text:
            continue
        texts.append(text)
        tokenized.append(content_tokens(text))
    return texts, tokenized


class BM25Retriever:
    def __init__(
        self,
        documents: list[list[str]],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.n_docs = len(documents)
        self.doc_lens = [len(doc) for doc in documents]
        self.avgdl = sum(self.doc_lens) / self.n_docs if self.n_docs else 1.0
        self.term_freqs = [Counter(doc) for doc in documents]
        self.inverted_index: dict[str, list[tuple[int, int]]] = {}

        df: Counter[str] = Counter()
        for idx, tf_counter in enumerate(self.term_freqs):
            for term, tf in tf_counter.items():
                df[term] += 1
                self.inverted_index.setdefault(term, []).append((idx, tf))

        self.idf = {
            term: math.log(1 + (self.n_docs - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def score(self, query_tokens: list[str]) -> dict[int, float]:
        scores: dict[int, float] = {}
        for term in set(query_tokens):
            if term not in self.idf:
                continue
            idf = self.idf[term]
            for idx, tf in self.inverted_index.get(term, []):
                dl = self.doc_lens[idx]
                denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                scores[idx] = scores.get(idx, 0.0) + idf * (tf * (self.k1 + 1)) / denom
        return scores

    def retrieve(self, query_tokens: list[str], top_k: int) -> list[int]:
        scores = self.score(query_tokens)
        if not scores:
            return list(range(min(top_k, self.n_docs)))
        ranked = sorted(scores, key=lambda idx: (-scores[idx], idx))
        return ranked[:top_k]


@dataclass
class RagWeights:
    tfidf_weight: float = 0.25
    rag_weight: float = 0.1
    top_k: int = 10


class RagRanker:
    def __init__(
        self,
        retriever: BM25Retriever,
        corpus_texts: list[str],
        exam_rows: list[dict[str, str]],
        weights: RagWeights | None = None,
    ) -> None:
        self.retriever = retriever
        self.corpus_texts = corpus_texts
        self.exam_idf = build_idf(exam_rows)
        self.weights = weights or RagWeights()
        self._context_cache: dict[str, str] = {}

    def build_query(self, row: dict[str, str]) -> list[str]:
        return content_tokens(row["prompt"])

    def retrieve_context(self, row: dict[str, str]) -> str:
        cache_key = row.get("id", row["prompt"])
        if cache_key in self._context_cache:
            return self._context_cache[cache_key]

        query = self.build_query(row)
        top_indices = self.retriever.retrieve(query, self.weights.top_k)
        chunks = [self.corpus_texts[idx] for idx in top_indices if self.corpus_texts[idx]]
        context = "\n".join(chunks)
        self._context_cache[cache_key] = context
        return context

    def rank_row(self, row: dict[str, str]) -> list[str]:
        prompt_vec = tfidf_vector(content_tokens(row["prompt"]), self.exam_idf)
        context = self.retrieve_context(row)
        context_vec = tfidf_vector(content_tokens(context), self.exam_idf)

        length_values = [word_count(row[option]) for option in OPTIONS]
        prompt_tfidf_values = [
            cosine(prompt_vec, tfidf_vector(content_tokens(row[option]), self.exam_idf))
            for option in OPTIONS
        ]
        rag_values = [
            cosine(context_vec, tfidf_vector(content_tokens(row[option]), self.exam_idf))
            for option in OPTIONS
        ]

        scores = [
            length_z + self.weights.tfidf_weight * prompt_tfidf_z + self.weights.rag_weight * rag_z
            for length_z, prompt_tfidf_z, rag_z in zip(
                zscores(length_values), zscores(prompt_tfidf_values), zscores(rag_values)
            )
        ]
        return [
            option
            for _, option in sorted(zip(scores, OPTIONS), key=lambda item: (-item[0], item[1]))
        ]
