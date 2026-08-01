"""Hidden-test runtime for the frozen conservative artifact bag."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def _artifact_align(
    sample: pd.DataFrame,
    frame: pd.DataFrame,
    value_column: str,
    label: str,
) -> np.ndarray:
    work = frame[["id", value_column]].copy()
    work["id"] = work["id"].astype(str)
    if work["id"].duplicated().any():
        raise RuntimeError(f"{label}: duplicate IDs")
    aligned = sample[["id"]].copy()
    aligned["id"] = aligned["id"].astype(str)
    aligned = aligned.merge(work, on="id", how="left", validate="one_to_one")
    values = pd.to_numeric(aligned[value_column], errors="coerce").to_numpy(float)
    if len(values) != len(sample) or not np.isfinite(values).all():
        raise RuntimeError(f"{label}: invalid sample alignment")
    return values


def _artifact_distribution(values: np.ndarray) -> dict[str, float]:
    values = np.asarray(values, float)
    return {
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "p50_abs": float(np.quantile(np.abs(values), 0.50)),
        "p95_abs": float(np.quantile(np.abs(values), 0.95)),
        "maximum_abs": float(np.max(np.abs(values))),
    }


def _artifact_split_dir(data_root: Path, split: str) -> Path:
    candidates = [data_root / split, data_root]
    for candidate in candidates:
        if candidate.exists() and any(candidate.glob(f"*__horizontal_well.csv")):
            return candidate
    raise RuntimeError(f"could not locate {split} wells under {data_root}")


def run_conservative_artifact_hidden_candidate(
    *,
    sample: pd.DataFrame,
    base_submission: pd.DataFrame,
    sp45_submission: pd.DataFrame,
    package_submission: pd.DataFrame,
    raw_learned_submission: pd.DataFrame,
    smooth_learned_submission: pd.DataFrame,
    data_root: Path,
    work_dir: Path,
    local_reference: dict[str, float],
    matcher_fn,
    write_submission_on_pass: bool = True,
) -> dict[str, object]:
    """Apply the predeclared 15% artifact bag, SG601, and bounded matcher."""
    sample = sample[["id"]].copy()
    sample["id"] = sample["id"].astype(str)
    if sample["id"].duplicated().any():
        raise RuntimeError("sample contains duplicate IDs")
    data_root = Path(data_root)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    base = _artifact_align(sample, base_submission, "tvt", "base submission")
    sp45 = _artifact_align(sample, sp45_submission, "tvt", "SP45 submission")
    package = _artifact_align(
        sample, package_submission, "tvt", "model-package submission"
    )
    raw_learned = _artifact_align(
        sample, raw_learned_submission, "tvt", "raw learned submission"
    )
    smooth_learned = _artifact_align(
        sample, smooth_learned_submission, "tvt", "smooth learned submission"
    )

    artifact_base = 0.60 * sp45 + 0.40 * package
    artifact = 0.15 * (artifact_base - base)
    sg601 = 0.40 * (smooth_learned - raw_learned)
    matcher_direct = np.zeros(len(sample), float)

    ids = sample["id"].astype(str)
    wells = ids.str.rsplit("_", n=1).str[0]
    rows = pd.to_numeric(ids.str.rsplit("_", n=1).str[-1], errors="raise").to_numpy(int)
    test_dir = _artifact_split_dir(data_root, "test")
    diagnostics: dict[str, dict[str, float]] = {}
    for position, well in enumerate(sorted(wells.unique()), 1):
        sample_positions = np.flatnonzero(wells.eq(well).to_numpy())
        local_rows = rows[sample_positions]
        horizontal = pd.read_csv(test_dir / f"{well}__horizontal_well.csv")
        typewell = pd.read_csv(test_dir / f"{well}__typewell.csv")
        expected = np.flatnonzero(horizontal["TVT_input"].isna().to_numpy())
        if not np.array_equal(local_rows, expected):
            raise RuntimeError(f"{well}: sample rows do not match test suffix")
        output, diagnostic = matcher_fn(
            horizontal=horizontal,
            typewell=typewell,
            center=sp45[sample_positions],
            radius=60.0,
            offset_step=1.0,
            stride=32,
            half_window=256,
            window_step=4,
            temperatures=(0.10,),
            prior_strength=0.05,
            gr_scale=1.30,
        )
        md = pd.to_numeric(horizontal["MD"], errors="coerce").to_numpy(float)
        known = np.flatnonzero(horizontal["TVT_input"].notna().to_numpy())
        if len(known) == 0:
            raise RuntimeError(f"{well}: no visible prefix")
        md_since = np.maximum(md[local_rows] - md[known[-1]], 0.0)
        ramp = 1.0 - np.exp(-md_since / 300.0)
        matcher_direct[sample_positions] = (
            0.20 * ramp * np.clip(output[0.10]["offset_mean"], -4.0, 4.0)
        )
        diagnostics[str(well)] = {
            "sigma": float(diagnostic["sigma"]),
            "matcher_direct_mean": float(np.mean(matcher_direct[sample_positions])),
            "matcher_direct_max_abs": float(
                np.max(np.abs(matcher_direct[sample_positions]))
            ),
        }
        print(f"artifact bag test {position}/{wells.nunique()} {well}", flush=True)

    matcher = 0.10 * matcher_direct
    raw_total = artifact + sg601 + matcher
    centering_shift = float(np.mean(raw_total))
    total = raw_total - centering_shift
    candidate = base + total
    if not np.isfinite(candidate).all():
        raise RuntimeError("artifact candidate produced non-finite values")
    formula_error = float(
        np.max(
            np.abs(
                candidate
                - (base + artifact + sg601 + matcher - centering_shift)
            )
        )
    )
    distribution = _artifact_distribution(total)
    guards = {
        "formula_exact": bool(formula_error <= 1e-10),
        "mean_near_local": bool(
            abs(distribution["mean"] - float(local_reference["mean"]))
            <= float(local_reference["mean_tolerance"])
        ),
        "p95_within_local_ratio": bool(
            distribution["p95_abs"]
            <= float(local_reference["p95_abs"])
            * float(local_reference["p95_ratio_limit"])
        ),
        "maximum_within_local_ratio": bool(
            distribution["maximum_abs"]
            <= float(local_reference["maximum_abs"])
            * float(local_reference["maximum_ratio_limit"])
        ),
    }
    guard_passed = bool(all(guards.values()))

    before = sample.copy()
    before["tvt"] = base
    final = sample.copy()
    final["tvt"] = candidate
    before.to_csv(work_dir / "submission_before_artifact015.csv", index=False)
    pd.DataFrame(
        {
            "id": sample["id"],
            "base_tvt": base,
            "artifact_base_tvt": artifact_base,
            "artifact_correction": artifact,
            "sg601_correction": sg601,
            "matcher_direct": matcher_direct,
            "matcher_correction": matcher,
            "raw_total_correction": raw_total,
            "centering_shift": centering_shift,
            "total_correction": total,
            "final_tvt": candidate,
        }
    ).to_csv(work_dir / "artifact015_candidate_components.csv", index=False)
    if guard_passed and write_submission_on_pass:
        final.to_csv(work_dir / "submission.csv", index=False)

    summary = {
        "candidate": "artifact015_sg601_matcher010_centered_hidden_dynamic_v1",
        "formula": (
            "base + 0.15*((0.60*SP45+0.40*artifact)-base) "
            "+ 0.40*(SG601 learned-raw learned) + 0.10*matcher_direct "
            "- mean(raw correction)"
        ),
        "rows": int(len(sample)),
        "test_wells": int(wells.nunique()),
        "model_package_direct_weight": 0.0,
        "formula_max_abs_error": formula_error,
        "target_free_centering_shift": centering_shift,
        "component_distribution": {
            "artifact": _artifact_distribution(artifact),
            "sg601": _artifact_distribution(sg601),
            "matcher": _artifact_distribution(matcher),
            "raw_total": _artifact_distribution(raw_total),
            "total": distribution,
        },
        "well_diagnostics": diagnostics,
        "local_reference": local_reference,
        "guards": guards,
        "guard_passed": guard_passed,
        "submission_written": bool(guard_passed and write_submission_on_pass),
    }
    (work_dir / "artifact015_candidate_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary
