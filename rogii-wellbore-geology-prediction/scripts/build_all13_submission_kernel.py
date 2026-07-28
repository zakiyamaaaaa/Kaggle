#!/usr/bin/env python3
"""Build the audited Kaggle submission notebook with the frozen CSV embedded."""

from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "outputs/submissions/learned_meta_all13_sp45_w060.csv"
NOTEBOOK = (
    ROOT
    / "kaggle-push/all13-sp45-w060-submission/"
    / "rogii-all13-sp45-w060-submission.ipynb"
)
EXPECTED_SHA256 = "97435ccb145672ec0b11d31721d73d4aa77eec3966aef214990ec5f90501705f"
EXPECTED_ROWS = 14151


def main() -> None:
    payload = base64.b64encode(gzip.compress(CANDIDATE.read_bytes(), mtime=0)).decode()
    code = f'''from pathlib import Path
import base64
import csv
import gzip
import hashlib
import json

EXPECTED_SHA256 = "{EXPECTED_SHA256}"
EXPECTED_ROWS = {EXPECTED_ROWS}
PAYLOAD_B64 = {payload!r}
INPUT_ROOT = Path("/kaggle/input")
WORKING_ROOT = Path("/kaggle/working")

candidate_bytes = gzip.decompress(base64.b64decode(PAYLOAD_B64))
source_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
assert source_sha256 == EXPECTED_SHA256, source_sha256

candidate_text = candidate_bytes.decode("utf-8")
candidate_rows = list(csv.DictReader(candidate_text.splitlines()))
sample_matches = list(INPUT_ROOT.rglob("sample_submission.csv"))
assert len(sample_matches) == 1, sample_matches
sample_path = sample_matches[0]
with sample_path.open(newline="", encoding="utf-8") as handle:
    sample_rows = list(csv.DictReader(handle))

assert len(candidate_rows) == EXPECTED_ROWS == len(sample_rows)
assert list(candidate_rows[0]) == ["id", "tvt"]
candidate_ids = [row["id"] for row in candidate_rows]
sample_ids = [row["id"] for row in sample_rows]
assert len(set(candidate_ids)) == EXPECTED_ROWS
assert candidate_ids == sample_ids
tvt = [float(row["tvt"]) for row in candidate_rows]
assert all(value == value and abs(value) != float("inf") for value in tvt)
assert sorted(tvt)[len(tvt) // 2] > 1000.0

output_path = WORKING_ROOT / "submission.csv"
output_path.write_bytes(candidate_bytes)
output_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
assert output_sha256 == EXPECTED_SHA256

audit = {{
    "sample_path": str(sample_path),
    "rows": len(candidate_rows),
    "columns": ["id", "tvt"],
    "ids_match_sample_in_order": True,
    "sha256": output_sha256,
    "tvt_min": min(tvt),
    "tvt_max": max(tvt),
    "tvt_mean": sum(tvt) / len(tvt),
}}
(WORKING_ROOT / "submission_audit.json").write_text(
    json.dumps(audit, indent=2) + "\\n", encoding="utf-8"
)
print(json.dumps(audit, indent=2))
'''
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# ROGII All13 SP45 W060 submission\n",
                    "\n",
                    "Validate the frozen candidate against the competition sample and emit it byte-for-byte.",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": code.splitlines(keepends=True),
            },
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    NOTEBOOK.write_text(json.dumps(notebook, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {NOTEBOOK} ({NOTEBOOK.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
