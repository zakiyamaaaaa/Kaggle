#!/usr/bin/env python3
"""Build the guarded hidden-dynamic artifact015 Kaggle notebook."""

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
    / "outputs/runs/full773_artifact015_sg601_matcher010_centered_exact_summary.json"
)
RUNTIME = ROOT / "scripts/conservative_artifact_hidden_runtime.py"
OUTPUT_DIR = ROOT / "kaggle-push/artifact015-sg601-matcher010-centered"
OUTPUT = OUTPUT_DIR / "rogii-artifact015-sg601-matcher010-centered.ipynb"


PUBLIC_CAPTURE = r'''
def _artifact_smooth_public_meta_delta(frame, values, window=601, polynomial=2):
    """Return target-free SG601 values while preserving the incumbent path."""
    from scipy.signal import savgol_filter as _artifact_savgol_filter
    array = np.asarray(values, dtype=float)
    output = array.copy()
    work = frame.reset_index(drop=True)
    for _, indices in work.groupby("well", sort=False).groups.items():
        positions = work.index.get_indexer(indices)
        local_window = min(int(window), len(positions))
        if local_window % 2 == 0:
            local_window -= 1
        if local_window >= polynomial + 2:
            output[positions] = _artifact_savgol_filter(
                array[positions], local_window, polynomial
            )
    return output

'''


PREDICTION_CAPTURE = r'''_artifact_raw_test_pred = make_prediction(test_df, meta_test, None)
    _artifact_smooth_test_pred = make_prediction(
        test_df, _artifact_smooth_public_meta_delta(test_df, meta_test), None
    )
    _artifact_raw_sub = sample_template.copy()
    _artifact_raw_sub["tvt"] = _artifact_raw_sub["id"].map(
        dict(zip(test_df["id"].astype(str), _artifact_raw_test_pred))
    ).fillna(fallback)
    _artifact_smooth_sub = sample_template.copy()
    _artifact_smooth_sub["tvt"] = _artifact_smooth_sub["id"].map(
        dict(zip(test_df["id"].astype(str), _artifact_smooth_test_pred))
    ).fillna(fallback)
    globals()["_ARTIFACT_RAW_LEARNED_SUBMISSION"] = _artifact_raw_sub[["id", "tvt"]].copy()
    globals()["_ARTIFACT_SMOOTH_LEARNED_SUBMISSION"] = _artifact_smooth_sub[["id", "tvt"]].copy()
    test_pred = _artifact_raw_test_pred'''


def code_cell(source: str) -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def deployment_contract() -> dict[str, float]:
    summary = json.loads(LOCAL_SUMMARY.read_text(encoding="utf-8"))
    if not summary["promotion"]["passes_local_submission_gate"]:
        raise RuntimeError("local candidate no longer passes its submission gate")
    correction = summary["primary_correction_distribution"]
    return {
        "mean": float(correction["mean"]),
        "p95_abs": float(correction["p95_abs"]),
        "maximum_abs": float(correction["maximum_abs"]),
        "mean_tolerance": 0.35,
        "p95_ratio_limit": 2.00,
        "maximum_ratio_limit": 1.50,
    }


def main() -> None:
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise RuntimeError(f"source notebook changed: {digest}")
    notebook = json.loads(SOURCE.read_text(encoding="utf-8"))
    local_reference = deployment_contract()

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
        "insert SG601 capture helper",
    )
    learned = replace_once(
        learned,
        "test_pred = make_prediction(test_df, meta_test, None)",
        PREDICTION_CAPTURE,
        "capture raw and smooth learned trajectories",
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

# The model package is an artifact trajectory only; direct incumbent blend is zero.
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
    runtime_source = RUNTIME.read_text(encoding="utf-8").replace(
        "from __future__ import annotations\n", ""
    )
    call_source = f'''
from pathlib import Path as _ArtifactPath

_ARTIFACT_WORK = _ArtifactPath('/kaggle/working') if _ArtifactPath('/kaggle/working').exists() else _ArtifactPath('.')
_ARTIFACT_BASE = _ARTIFACT_WORK / 'submission.csv'
_ARTIFACT_SP45 = _ARTIFACT_WORK / 'sp45_projection_submission.csv'
if not _ARTIFACT_BASE.exists() or not _ARTIFACT_SP45.exists():
    raise RuntimeError('artifact candidate requires base and SP45 submissions')
if '_ARTIFACT_RAW_LEARNED_SUBMISSION' not in globals() or '_ARTIFACT_SMOOTH_LEARNED_SUBMISSION' not in globals():
    raise RuntimeError('raw/smooth learned trajectory capture is unavailable')

_ARTIFACT_SUMMARY = run_conservative_artifact_hidden_candidate(
    sample=_mp_sample[['id']].copy(),
    base_submission=_mp_pd.read_csv(_ARTIFACT_BASE),
    sp45_submission=_mp_pd.read_csv(_ARTIFACT_SP45),
    package_submission=_mp_pkg_sub,
    raw_learned_submission=globals()['_ARTIFACT_RAW_LEARNED_SUBMISSION'],
    smooth_learned_submission=globals()['_ARTIFACT_SMOOTH_LEARNED_SUBMISSION'],
    data_root=_ArtifactPath(_mp_data_dir),
    work_dir=_ARTIFACT_WORK,
    local_reference={repr(local_reference)},
    matcher_fn=scan_complete_well,
    write_submission_on_pass=True,
)
if not _ARTIFACT_SUMMARY['guard_passed']:
    print('ARTIFACT015 CANDIDATE BLOCKED: incumbent submission.csv retained', flush=True)
'''
    correction_cell = code_cell(
        "# Generated frozen conservative artifact runtime.\n"
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
        "# ROGII artifact015 + SG601 + matcher010 centered candidate\n",
        "\n",
        "Hidden-dynamic deployment of the frozen full-773 candidate. The final "
        "file is replaced only when target-free distribution guards pass.\n",
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
        "id": "zacky21/rogii-artifact015-sg601-matcher010-centered",
        "title": "ROGII Artifact015 SG601 Matcher010 Centered",
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
        "full773_primary": "artifact015_sg601_matcher010_centered",
        "full773_rmse": 9.490477863947113,
        "unseen573_improvement_ft": 0.08084379720631674,
        "guarded_submission": True,
    }
    (OUTPUT_DIR / "build_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
