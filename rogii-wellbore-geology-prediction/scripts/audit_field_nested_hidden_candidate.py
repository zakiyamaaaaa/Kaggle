#!/usr/bin/env python3
"""Run the hidden field candidate against the cached active three-well test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from bounded_complete_well_matcher import scan_complete_well
from complete_well_curve_model import build_well_features, legendre_coefficients
from field_nested_hidden_runtime import run_field_nested_hidden_candidate


def align(sample: pd.DataFrame, frame: pd.DataFrame, label: str) -> np.ndarray:
    work = frame[["id", "tvt"]].copy()
    work["id"] = work["id"].astype(str)
    aligned = sample[["id"]].copy()
    aligned["id"] = aligned["id"].astype(str)
    aligned = aligned.merge(work, on="id", how="left", validate="one_to_one")
    values = pd.to_numeric(aligned["tvt"], errors="coerce").to_numpy(float)
    if not np.isfinite(values).all():
        raise RuntimeError(f"{label}: invalid alignment")
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--complete-well-output", type=Path, required=True)
    parser.add_argument("--raw-learned-output", type=Path, required=True)
    parser.add_argument("--local-summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    local = json.loads(args.local_summary.read_text(encoding="utf-8"))
    if not local["promotion"]["passes_guarded_deployment_gate"]:
        raise RuntimeError("field candidate does not pass the frozen guarded gate")
    centroids = local["field_centroids"]
    field_weights = {
        field: {
            component: float(stats["mean"])
            for component, stats in components.items()
        }
        for field, components in local["deployment_weight_summary"].items()
    }
    correction = local["ensemble"]["correction_distribution"]
    local_reference = {
        "mean": float(correction["mean"]),
        "p95_abs": float(correction["p95_abs"]),
        "maximum_abs": float(correction["maximum_abs"]),
        "mean_tolerance": 0.15,
        "p95_ratio_limit": 1.50,
        "maximum_ratio_limit": 1.50,
    }

    sample = pd.read_csv(args.data_root / "sample_submission.csv", usecols=["id"])
    complete = args.complete_well_output
    raw_root = args.raw_learned_output
    smooth_learned_frame = pd.read_csv(complete / "learned_trajectory_submission.csv")
    raw_learned_frame = pd.read_csv(raw_root / "learned_trajectory_submission.csv")
    sp45_frame = pd.read_csv(complete / "sp45_projection_submission.csv")
    package_frame = pd.read_csv(complete / "submission_model_package_only.csv")
    smoothed_base_frame = pd.read_csv(
        complete / "submission_before_complete_well.csv"
    )

    smooth_learned = align(sample, smooth_learned_frame, "smooth learned")
    raw_learned = align(sample, raw_learned_frame, "raw learned")
    sp45 = align(sample, sp45_frame, "SP45")
    smoothed_base = align(sample, smoothed_base_frame, "smoothed base")
    hedge = smoothed_base - (0.60 * sp45 + 0.40 * smooth_learned)
    raw_base = 0.60 * sp45 + 0.40 * raw_learned + hedge
    base_frame = sample.copy()
    base_frame["tvt"] = raw_base

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = run_field_nested_hidden_candidate(
        sample=sample,
        base_submission=base_frame,
        sp45_submission=sp45_frame,
        package_submission=package_frame,
        raw_learned_submission=raw_learned_frame,
        smooth_learned_submission=smooth_learned_frame,
        data_root=args.data_root,
        package_root=args.package_root,
        work_dir=args.output_dir,
        centroids=centroids,
        field_weights=field_weights,
        local_reference=local_reference,
        build_features_fn=build_well_features,
        coefficients_fn=legendre_coefficients,
        matcher_fn=scan_complete_well,
        write_submission_on_pass=True,
    )
    audit = {
        "method": "active_three_well_hidden_runtime_audit",
        "rows": int(len(sample)),
        "raw_base_reconstruction": {
            "hedge_mean": float(np.mean(hedge)),
            "hedge_p95_abs": float(np.quantile(np.abs(hedge), 0.95)),
            "sg601_component_mean": float(
                np.mean(0.40 * (smooth_learned - raw_learned))
            ),
            "sg601_component_p95_abs": float(
                np.quantile(np.abs(0.40 * (smooth_learned - raw_learned)), 0.95)
            ),
        },
        "runtime_summary": summary,
    }
    (args.output_dir / "field_nested_hidden_local_audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
