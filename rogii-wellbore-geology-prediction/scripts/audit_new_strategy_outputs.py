"""Audit reproduced and ablated outputs from the public ROGII 6.213 notebook.

The visible three test wells share identifiers and input rows with train wells.
Their train TVT is useful only as a public-placeholder diagnostic; it is not an
honest hidden-test estimate.  This script labels that metric explicitly and
also compares every candidate with a reference output by prediction RMS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_submission(path: Path) -> pd.DataFrame | None:
    try:
        frame = pd.read_csv(path)
    except Exception:
        return None
    if list(frame.columns) != ["id", "tvt"] or not frame["id"].is_unique:
        return None
    frame["id"] = frame["id"].astype(str)
    frame["tvt"] = pd.to_numeric(frame["tvt"], errors="coerce")
    if not np.isfinite(frame["tvt"].to_numpy(float)).all():
        return None
    return frame


def train_truth_for_ids(data_root: Path, ids: pd.Series) -> np.ndarray:
    parsed = ids.str.rsplit("_", n=1, expand=True)
    wells = parsed[0].astype(str)
    rows = pd.to_numeric(parsed[1], errors="raise").astype(int)
    truth = np.full(len(ids), np.nan, dtype=float)
    for well in wells.drop_duplicates():
        path = data_root / "train" / f"{well}__horizontal_well.csv"
        if not path.exists():
            continue
        horizontal = pd.read_csv(path, usecols=["TVT"])
        mask = wells.eq(well).to_numpy()
        row_index = rows[mask].to_numpy(int)
        if (row_index < 0).any() or (row_index >= len(horizontal)).any():
            continue
        truth[mask] = horizontal["TVT"].to_numpy(float)[row_index]
    return truth


def audit_directory(
    output_dir: Path,
    data_root: Path,
    reference: pd.DataFrame | None,
) -> list[dict]:
    records = []
    for path in sorted(output_dir.glob("*.csv")):
        frame = read_submission(path)
        if frame is None:
            continue
        truth = train_truth_for_ids(data_root, frame["id"])
        valid_truth = np.isfinite(truth)
        record = {
            "file": path.name,
            "rows": int(len(frame)),
            "sha256": file_sha256(path),
            "public_placeholder_truth_rows": int(valid_truth.sum()),
            "public_placeholder_rmse": (
                float(
                    np.sqrt(
                        np.mean(
                            np.square(
                                frame.loc[valid_truth, "tvt"].to_numpy(float)
                                - truth[valid_truth]
                            )
                        )
                    )
                )
                if valid_truth.any()
                else None
            ),
        }
        if reference is not None and frame["id"].equals(reference["id"]):
            delta = frame["tvt"].to_numpy(float) - reference["tvt"].to_numpy(float)
            record["rms_vs_reference"] = float(np.sqrt(np.mean(np.square(delta))))
            record["max_abs_vs_reference"] = float(np.max(np.abs(delta)))
        records.append(record)
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--reference-submission", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    reference = (
        read_submission(args.reference_submission)
        if args.reference_submission is not None
        else None
    )
    result = {
        "metric_warning": (
            "public_placeholder_rmse uses train TVT for matching visible well IDs; "
            "it is not an honest hidden-test or private-LB estimate"
        ),
        "output_dir": str(args.output_dir),
        "records": audit_directory(args.output_dir, args.data_root, reference),
    }
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
