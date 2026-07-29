#!/usr/bin/env python3
"""Build the 7.474 incumbent with one extra learned-delta SG601 smoother."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "kaggle-push/sp45-ridge030-proj-d2-b050/"
    / "rogii-sp45-ridge030-projection-d2-b050.ipynb"
)
SOURCE_SHA256 = "f3833ba45069fd8056255bd3e6c88c4c1c19d3081df8de62d7d2827ca8930786"
OUTPUT = (
    ROOT
    / "kaggle-push/public-learned-sg601-incumbent/"
    / "rogii-public-learned-sg601-incumbent.ipynb"
)


HELPER = r'''
def _smooth_public_meta_delta(frame, values, window=601, polynomial=2):
    """Target-free per-well smoothing selected by independent artifact OOF."""
    array = np.asarray(values, dtype=float)
    output = array.copy()
    work = frame.reset_index(drop=True)
    for _, indices in work.groupby("well", sort=False).groups.items():
        positions = work.index.get_indexer(indices)
        local_window = min(int(window), len(positions))
        if local_window % 2 == 0:
            local_window -= 1
        if local_window >= polynomial + 2:
            output[positions] = savgol_filter(
                array[positions], local_window, polynomial
            )
    return output

'''


def source_text(cell: dict[str, object]) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return source.replace(old, new, 1)


def main() -> None:
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise RuntimeError(f"source notebook changed: {digest}")
    notebook = json.loads(SOURCE.read_text(encoding="utf-8"))
    cell = next(
        candidate
        for candidate in notebook["cells"]
        if "def _find_models():" in source_text(candidate)
        and "test_pred = make_prediction(test_df, meta_test, None)" in source_text(candidate)
    )
    source = source_text(cell)
    source = replace_once(
        source,
        "def _find_models():",
        HELPER + "def _find_models():",
        "insert learned-delta smoother",
    )
    source = replace_once(
        source,
        "make_prediction(train_df, meta_oof, None)",
        "make_prediction(train_df, _smooth_public_meta_delta(train_df, meta_oof), None)",
        "cross-validation smoother",
    )
    source = replace_once(
        source,
        "test_pred = make_prediction(test_df, meta_test, None)",
        "test_pred = make_prediction(test_df, _smooth_public_meta_delta(test_df, meta_test), None)",
        "test smoother",
    )
    cell["source"] = source.splitlines(keepends=True)
    for candidate in notebook["cells"]:
        if candidate.get("cell_type") == "code":
            candidate["execution_count"] = None
            candidate["outputs"] = []
            compile(source_text(candidate), str(OUTPUT), "exec")
    notebook["cells"][0]["source"] = [
        "# ROGII 7.474 incumbent + public learned SG601\n",
        "\n",
        "One change: smooth the public positive-Ridge model delta with per-well "
        "Savgol window 601/poly2 before the unchanged learned postprocess.\n",
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(notebook, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "source_sha256": digest,
                "output_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
                "cells": len(notebook["cells"]),
                "one_change": "public learned model delta SG601/poly2/alpha1.0",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
