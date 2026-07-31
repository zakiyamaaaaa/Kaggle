#!/usr/bin/env python3
"""Build the guarded hidden-dynamic field-nested Kaggle notebook."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from build_complete_well_candidate_notebook import (
    SOURCE,
    SOURCE_SHA256,
    extract_nodes,
    replace_once,
    source_text,
)


ROOT = Path(__file__).resolve().parents[1]
LOCAL_SUMMARY = (
    ROOT
    / "outputs/runs/field_nested_component_blend_k6_field4_curve050_200w_summary.json"
)
RUNTIME = ROOT / "scripts/field_nested_hidden_runtime.py"
OUTPUT_DIR = ROOT / "kaggle-push/field-nested-k6-candidate"
OUTPUT = OUTPUT_DIR / "rogii-field-nested-k6-candidate.ipynb"


PUBLIC_CAPTURE = r'''
def _field_smooth_public_meta_delta(frame, values, window=601, polynomial=2):
    """Return the target-free SG601 version without changing the base path."""
    from scipy.signal import savgol_filter as _field_savgol_filter
    array = np.asarray(values, dtype=float)
    output = array.copy()
    work = frame.reset_index(drop=True)
    for _, indices in work.groupby("well", sort=False).groups.items():
        positions = work.index.get_indexer(indices)
        local_window = min(int(window), len(positions))
        if local_window % 2 == 0:
            local_window -= 1
        if local_window >= polynomial + 2:
            output[positions] = _field_savgol_filter(
                array[positions], local_window, polynomial
            )
    return output

'''


PUBLIC_PREDICTION_CAPTURE = r'''_field_raw_test_pred = make_prediction(test_df, meta_test, None)
    _field_smooth_test_pred = make_prediction(
        test_df, _field_smooth_public_meta_delta(test_df, meta_test), None
    )
    _field_raw_sub = sample_template.copy()
    _field_raw_sub["tvt"] = _field_raw_sub["id"].map(
        dict(zip(test_df["id"].astype(str), _field_raw_test_pred))
    ).fillna(fallback)
    _field_smooth_sub = sample_template.copy()
    _field_smooth_sub["tvt"] = _field_smooth_sub["id"].map(
        dict(zip(test_df["id"].astype(str), _field_smooth_test_pred))
    ).fillna(fallback)
    globals()["_FIELD_RAW_LEARNED_SUBMISSION"] = _field_raw_sub[["id", "tvt"]].copy()
    globals()["_FIELD_SMOOTH_LEARNED_SUBMISSION"] = _field_smooth_sub[["id", "tvt"]].copy()
    test_pred = _field_raw_test_pred'''


def code_cell(source: str) -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def deployment_contract() -> tuple[list[dict[str, float | int]], dict[str, dict[str, float]], dict[str, float]]:
    summary = json.loads(LOCAL_SUMMARY.read_text(encoding="utf-8"))
    if not summary["promotion"]["passes_guarded_deployment_gate"]:
        raise RuntimeError("local field candidate no longer passes its guarded gate")
    centroids = summary["field_centroids"]
    weights = {
        field: {
            component: float(stats["mean"])
            for component, stats in components.items()
        }
        for field, components in summary["deployment_weight_summary"].items()
    }
    local = summary["ensemble"]["correction_distribution"]
    reference = {
        "mean": float(local["mean"]),
        "p95_abs": float(local["p95_abs"]),
        "maximum_abs": float(local["maximum_abs"]),
        "mean_tolerance": 0.15,
        "p95_ratio_limit": 1.50,
        "maximum_ratio_limit": 1.50,
    }
    return centroids, weights, reference


def main() -> None:
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise RuntimeError(f"source notebook changed: {digest}")
    notebook = json.loads(SOURCE.read_text(encoding="utf-8"))
    centroids, weights, local_reference = deployment_contract()

    learned_cell = next(
        cell
        for cell in notebook["cells"]
        if "def _find_models():" in source_text(cell)
        and "test_pred = make_prediction(test_df, meta_test, None)" in source_text(cell)
    )
    learned = source_text(learned_cell)
    learned = replace_once(
        learned,
        "def _find_models():",
        PUBLIC_CAPTURE + "def _find_models():",
        "insert public SG601 capture helper",
    )
    learned = replace_once(
        learned,
        "test_pred = make_prediction(test_df, meta_test, None)",
        PUBLIC_PREDICTION_CAPTURE,
        "capture raw and SG601 learned trajectories",
    )
    learned_cell["source"] = learned.splitlines(keepends=True)

    config_cell = next(
        cell
        for cell in notebook["cells"]
        if "MODEL_PACKAGE_GATED_CANDIDATES" in source_text(cell)
        and "SUBMISSION_PROFILE" in source_text(cell)
    )
    config = source_text(config_cell)
    config += r'''

# The package trajectory is an artifact feature only.  Its direct blend is zero.
RUN_MODEL_PACKAGE_CORRECTION = True
MODEL_PACKAGE_REQUIRE = True
MODEL_PACKAGE_GATED_MAX_WEIGHT = 0.0
MODEL_PACKAGE_GATED_CANDIDATES = (0.0,)
MODEL_PACKAGE_DIFF_P95_DISABLE = None
'''
    config_cell["source"] = config.splitlines(keepends=True)

    helper_source = extract_nodes(
        ROOT / "scripts/calibrated_u_viterbi_experiment.py",
        (
            "ViterbiConfig",
            "_rolling_median",
            "_typewell_arrays",
            "_robust_affine_calibration",
        ),
    )
    helper_source += "\n" + extract_nodes(
        ROOT / "scripts/bounded_complete_well_matcher.py",
        ("softmax_posterior", "scan_complete_well"),
    )
    helper_source += "\n" + extract_nodes(
        ROOT / "scripts/complete_well_curve_model.py",
        ("legendre_coefficients", "safe_scale", "build_well_features"),
    )
    runtime_source = RUNTIME.read_text(encoding="utf-8").replace(
        "from __future__ import annotations\n", ""
    )
    call_source = f'''
from pathlib import Path as _FieldPath

_FIELD_WORK = _FieldPath('/kaggle/working') if _FieldPath('/kaggle/working').exists() else _FieldPath('.')
_FIELD_PACKAGE = _mp_find_package_root()
if _FIELD_PACKAGE is None:
    raise RuntimeError('field candidate requires the model package')
if '_FIELD_RAW_LEARNED_SUBMISSION' not in globals() or '_FIELD_SMOOTH_LEARNED_SUBMISSION' not in globals():
    raise RuntimeError('raw/smooth learned trajectory capture is unavailable')
_FIELD_BASE_PATH = _FIELD_WORK / 'submission.csv'
_FIELD_SP45_PATH = _FIELD_WORK / 'sp45_projection_submission.csv'
if not _FIELD_BASE_PATH.exists() or not _FIELD_SP45_PATH.exists():
    raise RuntimeError('field candidate requires base and SP45 submissions')

_FIELD_SUMMARY = run_field_nested_hidden_candidate(
    sample=_mp_sample[['id']].copy(),
    base_submission=_mp_pd.read_csv(_FIELD_BASE_PATH),
    sp45_submission=_mp_pd.read_csv(_FIELD_SP45_PATH),
    package_submission=_mp_pkg_sub,
    raw_learned_submission=globals()['_FIELD_RAW_LEARNED_SUBMISSION'],
    smooth_learned_submission=globals()['_FIELD_SMOOTH_LEARNED_SUBMISSION'],
    data_root=_FieldPath(_mp_data_dir),
    package_root=_FIELD_PACKAGE,
    work_dir=_FIELD_WORK,
    centroids={repr(centroids)},
    field_weights={repr(weights)},
    local_reference={repr(local_reference)},
    build_features_fn=build_well_features,
    coefficients_fn=legendre_coefficients,
    matcher_fn=scan_complete_well,
    write_submission_on_pass=True,
)
if not _FIELD_SUMMARY['guard_passed']:
    print('FIELD CANDIDATE BLOCKED: submission.csv kept at incumbent base', flush=True)
'''
    correction_cell = code_cell(
        "# Generated field-aware complete-well runtime.\n"
        "from dataclasses import dataclass\n"
        + helper_source
        + "\n"
        + runtime_source
        + "\n"
        + call_source
    )
    audit_index = next(
        index
        for index, cell in enumerate(notebook["cells"])
        if "# Final submission audit:" in source_text(cell)
    )
    notebook["cells"].insert(audit_index, correction_cell)

    notebook["cells"][0]["source"] = [
        "# ROGII field-nested K6 guarded candidate\n",
        "\n",
        "Hidden-dynamic fit-all deployment of the locally promoted repeated "
        "nested field blend. Submission output is updated only when correction "
        "distribution guards pass.\n",
    ]
    for cell in notebook["cells"]:
        if cell.get("cell_type") != "code":
            continue
        cell["execution_count"] = None
        cell["outputs"] = []
        compile(source_text(cell), str(OUTPUT), "exec")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(notebook, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    metadata = {
        "id": "zacky21/rogii-field-nested-k6-candidate",
        "title": "ROGII Field Nested K6 Candidate",
        "code_file": OUTPUT.name,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": False,
        "keywords": [],
        "dataset_sources": [
            "phongnguyn23021656/koolbox-offline",
            "nina2025/rogii-03",
            "pilkwang/rogii-model-package",
            "thbdh5765/rogii-v10-fresh-artifacts",
            "fleongg/rogii-claude-models-pub",
            "needless090/rogii-tabicl-mirror",
            "ravaghi/wellbore-geology-prediction-artifacts",
        ],
        "kernel_sources": [],
        "competition_sources": ["rogii-wellbore-geology-prediction"],
        "model_sources": [],
        "docker_image": (
            "gcr.io/kaggle-private-byod/python@sha256:"
            "37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461"
        ),
        "machine_shape": "Gpu",
    }
    (OUTPUT_DIR / "kernel-metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "output": str(OUTPUT),
        "source_sha256": digest,
        "output_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        "cells": len(notebook["cells"]),
        "insertion_index": audit_index,
        "hidden_dynamic": True,
        "field_count": len(centroids),
        "model_package_direct_weight": 0.0,
        "global_shift_ft": 0.0,
        "local_improvement_ft": 0.08115770372225661,
        "local_bootstrap_p01_ft": 0.0013789852871657438,
        "local_bootstrap_p05_ft": 0.022530056192712155,
        "guarded_submission": True,
    }
    (OUTPUT_DIR / "build_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
