"""Hidden-test runtime for the field-aware nested component candidate.

This module is deliberately self-contained so the notebook builder can embed
it verbatim and the same function can be exercised against the local active
test files before a Kaggle kernel is pushed.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.impute import SimpleImputer


def _field_align(
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


def _field_read_well(data_root: Path, split: str, well: str):
    horizontal_path = data_root / split / f"{well}__horizontal_well.csv"
    typewell_path = data_root / split / f"{well}__typewell.csv"
    if not horizontal_path.exists() or not typewell_path.exists():
        raise RuntimeError(f"missing {split} files for {well}")
    return pd.read_csv(horizontal_path), pd.read_csv(typewell_path)


def _field_distribution(values: np.ndarray) -> dict[str, float]:
    values = np.asarray(values, float)
    return {
        "mean": float(np.mean(values)),
        "p50_abs": float(np.quantile(np.abs(values), 0.50)),
        "p95_abs": float(np.quantile(np.abs(values), 0.95)),
        "maximum_abs": float(np.max(np.abs(values))),
    }


def run_field_nested_hidden_candidate(
    *,
    sample: pd.DataFrame,
    base_submission: pd.DataFrame,
    sp45_submission: pd.DataFrame,
    package_submission: pd.DataFrame,
    raw_learned_submission: pd.DataFrame,
    smooth_learned_submission: pd.DataFrame,
    data_root: Path,
    package_root: Path,
    work_dir: Path,
    centroids: list[dict[str, float | int]],
    field_weights: dict[str, dict[str, float]],
    local_reference: dict[str, float],
    build_features_fn,
    coefficients_fn,
    matcher_fn,
    write_submission_on_pass: bool = True,
) -> dict[str, object]:
    """Fit-all and apply the frozen field-aware component policy."""
    sample = sample[["id"]].copy()
    sample["id"] = sample["id"].astype(str)
    if sample["id"].duplicated().any():
        raise RuntimeError("sample contains duplicate IDs")
    work_dir = Path(work_dir)
    data_root = Path(data_root)
    package_root = Path(package_root)
    work_dir.mkdir(parents=True, exist_ok=True)

    base = _field_align(sample, base_submission, "tvt", "base submission")
    sp45 = _field_align(sample, sp45_submission, "tvt", "SP45 submission")
    package_tvt = _field_align(
        sample, package_submission, "tvt", "model-package submission"
    )
    raw_learned = _field_align(
        sample, raw_learned_submission, "tvt", "raw learned submission"
    )
    smooth_learned = _field_align(
        sample, smooth_learned_submission, "tvt", "smooth learned submission"
    )
    sg601 = 0.40 * (smooth_learned - raw_learned)

    gt = pd.read_parquet(package_root / "oof/train_gt.parquet")
    oof_delta = np.asarray(
        np.load(package_root / "oof/blend_oof_postprocessed.npy", mmap_mode="r"),
        float,
    )
    if len(gt) != len(oof_delta) or not np.isfinite(oof_delta).all():
        raise RuntimeError("model-package OOF row contract mismatch")
    gt = gt.copy()
    gt["artifact_tvt"] = (
        pd.to_numeric(gt["last_known_TVT"], errors="coerce").to_numpy(float)
        + oof_delta
    )
    gt = gt.sort_values(["well_id", "row_index"]).reset_index(drop=True)

    train_features = []
    train_labels = []
    train_wells = sorted(gt["well_id"].astype(str).unique())
    for position, well in enumerate(train_wells, 1):
        group = gt.loc[gt["well_id"].astype(str).eq(well)].sort_values("row_index")
        horizontal, typewell = _field_read_well(data_root, "train", well)
        rows = group["row_index"].to_numpy(int)
        expected = np.flatnonzero(horizontal["TVT_input"].isna().to_numpy())
        if not np.array_equal(rows, expected):
            raise RuntimeError(f"{well}: package OOF rows do not match train suffix")
        artifact = group["artifact_tvt"].to_numpy(float)
        train_features.append(
            build_features_fn(horizontal, typewell, rows, artifact, 12)
        )
        residual = group["target_tvt"].to_numpy(float) - artifact
        train_labels.append(coefficients_fn(residual, 5))
        if position % 100 == 0 or position == len(train_wells):
            print(f"field candidate train features {position}/{len(train_wells)}", flush=True)
    train_x = np.vstack(train_features)
    train_y = np.vstack(train_labels)
    if train_x.shape != (773, 207) or train_y.shape != (773, 6):
        raise RuntimeError(f"unexpected train shapes: {train_x.shape}, {train_y.shape}")

    curve_imputer = SimpleImputer(strategy="median")
    train_x_imputed = curve_imputer.fit_transform(train_x)
    curve_model = CatBoostRegressor(
        loss_function="MultiRMSE",
        iterations=700,
        depth=4,
        learning_rate=0.03,
        l2_leaf_reg=30.0,
        verbose=False,
        random_seed=20261731,
        thread_count=6,
        allow_writing_files=False,
    )
    print("fitting field candidate CatBoost curve model", flush=True)
    curve_model.fit(train_x_imputed, train_y)

    ids = sample["id"].astype(str)
    wells = ids.str.rsplit("_", n=1).str[0]
    rows = pd.to_numeric(
        ids.str.rsplit("_", n=1).str[-1], errors="raise"
    ).to_numpy(int)
    matcher = np.zeros(len(sample), float)
    curve = np.zeros(len(sample), float)
    md_since = np.zeros(len(sample), float)
    test_features = []
    test_groups = []
    well_fields: dict[str, int] = {}
    centroid_array = np.asarray(
        [[float(row["x"]), float(row["y"])] for row in centroids], float
    )
    centroid_labels = np.asarray([int(row["field"]) for row in centroids], int)

    for position, well in enumerate(sorted(wells.unique()), 1):
        sample_positions = np.flatnonzero(wells.eq(well).to_numpy())
        local_rows = rows[sample_positions]
        horizontal, typewell = _field_read_well(data_root, "test", str(well))
        expected = np.flatnonzero(horizontal["TVT_input"].isna().to_numpy())
        if not np.array_equal(local_rows, expected):
            raise RuntimeError(f"{well}: sample rows do not match test suffix")
        x = float(pd.to_numeric(horizontal["X"], errors="coerce").median())
        y = float(pd.to_numeric(horizontal["Y"], errors="coerce").median())
        distance = np.sum(np.square(centroid_array - np.asarray([x, y])), axis=1)
        field = int(centroid_labels[int(np.argmin(distance))])
        if str(field) not in field_weights:
            raise RuntimeError(f"{well}: missing weights for field {field}")
        well_fields[str(well)] = field

        artifact = package_tvt[sample_positions]
        test_features.append(
            build_features_fn(horizontal, typewell, local_rows, artifact, 12)
        )
        test_groups.append((sample_positions, str(well), field))
        match_output, diagnostic = matcher_fn(
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
        local_md_since = np.maximum(md[local_rows] - md[known[-1]], 0.0)
        ramp = 1.0 - np.exp(-local_md_since / 300.0)
        matcher[sample_positions] = (
            0.20
            * ramp
            * np.clip(match_output[0.10]["offset_mean"], -4.0, 4.0)
        )
        md_since[sample_positions] = local_md_since
        print(
            f"field candidate test {position}/{wells.nunique()} {well} "
            f"field={field} sigma={float(diagnostic['sigma']):.3f}",
            flush=True,
        )

    test_x = np.vstack(test_features)
    coefficients = np.asarray(
        curve_model.predict(curve_imputer.transform(test_x)), float
    )
    for local, (sample_positions, _, _) in enumerate(test_groups):
        ramp = 1.0 - np.exp(-md_since[sample_positions] / 300.0)
        curve[sample_positions] = (
            0.50 * ramp * np.clip(float(coefficients[local, 0]), -8.0, 8.0)
        )

    weighted_sg = np.zeros(len(sample), float)
    weighted_matcher = np.zeros(len(sample), float)
    weighted_curve = np.zeros(len(sample), float)
    for sample_positions, _, field in test_groups:
        weights = field_weights[str(field)]
        weighted_sg[sample_positions] = float(weights["sg601"]) * sg601[sample_positions]
        weighted_matcher[sample_positions] = (
            float(weights["matcher"]) * matcher[sample_positions]
        )
        weighted_curve[sample_positions] = (
            float(weights["curve"]) * curve[sample_positions]
        )
    total = weighted_sg + weighted_matcher + weighted_curve
    candidate = base + total
    if not np.isfinite(candidate).all():
        raise RuntimeError("field candidate produced non-finite values")

    distribution = _field_distribution(total)
    mean_tolerance = float(local_reference.get("mean_tolerance", 0.15))
    p95_ratio_limit = float(local_reference.get("p95_ratio_limit", 1.50))
    maximum_ratio_limit = float(local_reference.get("maximum_ratio_limit", 1.50))
    guards = {
        "mean_near_local": bool(
            abs(distribution["mean"] - float(local_reference["mean"]))
            <= mean_tolerance
        ),
        "p95_within_local_ratio": bool(
            distribution["p95_abs"]
            <= p95_ratio_limit * float(local_reference["p95_abs"])
        ),
        "maximum_within_local_ratio": bool(
            distribution["maximum_abs"]
            <= maximum_ratio_limit * float(local_reference["maximum_abs"])
        ),
        "all_values_finite": bool(np.isfinite(candidate).all()),
        "all_test_wells_assigned": bool(len(well_fields) == wells.nunique()),
    }
    guard_passed = bool(all(guards.values()))

    candidate_frame = sample.copy()
    candidate_frame["tvt"] = candidate
    candidate_frame.to_csv(work_dir / "field_nested_candidate.csv", index=False)
    pd.DataFrame(
        {
            "id": sample["id"],
            "well": wells,
            "field": wells.map(well_fields).to_numpy(int),
            "base_tvt": base,
            "sg601_raw": sg601,
            "matcher_raw": matcher,
            "curve_raw": curve,
            "sg601_weighted": weighted_sg,
            "matcher_weighted": weighted_matcher,
            "curve_weighted": weighted_curve,
            "total_correction": total,
            "candidate_tvt": candidate,
        }
    ).to_csv(work_dir / "field_nested_candidate_components.csv", index=False)
    base_submission[["id", "tvt"]].to_csv(
        work_dir / "submission_before_field_nested.csv", index=False
    )
    if guard_passed and write_submission_on_pass:
        candidate_frame.to_csv(work_dir / "submission.csv", index=False)

    summary: dict[str, object] = {
        "candidate": "field_nested_component_blend_k6_hidden_dynamic_v1",
        "train_wells": int(len(train_wells)),
        "train_feature_shape": list(train_x.shape),
        "test_wells": int(wells.nunique()),
        "test_rows": int(len(sample)),
        "well_fields": well_fields,
        "field_weights": field_weights,
        "components": {
            "sg601": _field_distribution(weighted_sg),
            "matcher": _field_distribution(weighted_matcher),
            "curve": _field_distribution(weighted_curve),
        },
        "correction_distribution": distribution,
        "local_reference": local_reference,
        "guards": guards,
        "guard_passed": guard_passed,
        "submission_csv_updated": bool(guard_passed and write_submission_on_pass),
        "model_package_used_as_artifact_only": True,
        "model_package_submission_blend_weight": 0.0,
        "global_shift_ft": 0.0,
    }
    (work_dir / "field_nested_candidate_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print("field nested candidate:", summary, flush=True)
    return summary
