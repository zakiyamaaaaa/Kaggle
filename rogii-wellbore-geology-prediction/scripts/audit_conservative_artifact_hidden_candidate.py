#!/usr/bin/env python3
"""Audit the frozen artifact candidate on the cached active three-well test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from bounded_complete_well_matcher import scan_complete_well
from conservative_artifact_hidden_runtime import (
    run_conservative_artifact_hidden_candidate,
)


def align(sample: pd.DataFrame, frame: pd.DataFrame, label: str) -> np.ndarray:
    work = frame[["id", "tvt"]].copy()
    work["id"] = work["id"].astype(str)
    aligned = sample.assign(id=sample["id"].astype(str)).merge(
        work, on="id", how="left", validate="one_to_one"
    )
    values = pd.to_numeric(aligned["tvt"], errors="coerce").to_numpy(float)
    if not np.isfinite(values).all():
        raise RuntimeError(f"{label}: invalid alignment")
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--complete-well-output", type=Path, required=True)
    parser.add_argument("--raw-learned-output", type=Path, required=True)
    parser.add_argument("--local-summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    local = json.loads(args.local_summary.read_text(encoding="utf-8"))
    if not local["promotion"]["passes_local_submission_gate"]:
        raise RuntimeError("full-773 candidate does not pass its promotion gate")
    reference = local["primary_correction_distribution"]
    local_reference = {
        "mean": float(reference["mean"]),
        "p95_abs": float(reference["p95_abs"]),
        "maximum_abs": float(reference["maximum_abs"]),
        "mean_tolerance": 0.35,
        "p95_ratio_limit": 2.00,
        "maximum_ratio_limit": 1.50,
    }

    sample = pd.read_csv(args.data_root / "sample_submission.csv", usecols=["id"])
    complete = args.complete_well_output
    raw_root = args.raw_learned_output
    smooth_frame = pd.read_csv(complete / "learned_trajectory_submission.csv")
    raw_frame = pd.read_csv(raw_root / "learned_trajectory_submission.csv")
    sp45_frame = pd.read_csv(complete / "sp45_projection_submission.csv")
    package_frame = pd.read_csv(complete / "submission_model_package_only.csv")
    smoothed_base_frame = pd.read_csv(complete / "submission_before_complete_well.csv")

    smooth = align(sample, smooth_frame, "smooth learned")
    raw = align(sample, raw_frame, "raw learned")
    sp45 = align(sample, sp45_frame, "SP45")
    smoothed_base = align(sample, smoothed_base_frame, "smoothed base")
    hedge = smoothed_base - (0.60 * sp45 + 0.40 * smooth)
    raw_base = 0.60 * sp45 + 0.40 * raw + hedge
    base_frame = sample.copy()
    base_frame["tvt"] = raw_base

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = run_conservative_artifact_hidden_candidate(
        sample=sample,
        base_submission=base_frame,
        sp45_submission=sp45_frame,
        package_submission=package_frame,
        raw_learned_submission=raw_frame,
        smooth_learned_submission=smooth_frame,
        data_root=args.data_root,
        work_dir=args.output_dir,
        local_reference=local_reference,
        matcher_fn=scan_complete_well,
        write_submission_on_pass=True,
    )
    audit = {
        "method": "active_three_well_artifact015_hidden_runtime_audit",
        "rows": int(len(sample)),
        "raw_base_reconstruction": {
            "hedge_mean": float(np.mean(hedge)),
            "hedge_p95_abs": float(np.quantile(np.abs(hedge), 0.95)),
            "sg601_mean": float(np.mean(0.40 * (smooth - raw))),
            "sg601_p95_abs": float(np.quantile(np.abs(0.40 * (smooth - raw)), 0.95)),
        },
        "runtime_summary": summary,
    }
    (args.output_dir / "artifact015_hidden_local_audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
