#!/usr/bin/env python3
"""Build a hidden-test-compatible dynamic all12 submission notebook."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_NOTEBOOK = (
    ROOT
    / "kaggle-push/sp45-ridge030-proj-d2-b050/"
    / "rogii-sp45-ridge030-projection-d2-b050.ipynb"
)
BASE_SHA256 = "f3833ba45069fd8056255bd3e6c88c4c1c19d3081df8de62d7d2827ca8930786"
MODEL_SUMMARY = ROOT / "outputs/runs/learned_branch_meta_all12_dynamic_oof_summary.json"
NOTEBOOK = (
    ROOT
    / "kaggle-push/all13-sp45-w060-submission/"
    / "rogii-all13-sp45-w060-submission.ipynb"
)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return source.replace(old, new, 1)


def code_cell(source: str) -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def main() -> None:
    digest = hashlib.sha256(BASE_NOTEBOOK.read_bytes()).hexdigest()
    if digest != BASE_SHA256:
        raise RuntimeError(f"base notebook hash changed: {digest}")

    notebook = json.loads(BASE_NOTEBOOK.read_text(encoding="utf-8"))
    model = json.loads(MODEL_SUMMARY.read_text(encoding="utf-8"))
    if model["selected_variant"] != "all12_dynamic":
        raise RuntimeError("production summary is not all12_dynamic")
    features = list(model["selected_features"])
    coefficients = list(model["fit_all"]["coef"])
    intercept = float(model["fit_all"]["intercept"])
    if len(features) != 12 or len(coefficients) != 12:
        raise RuntimeError("all12 feature/coefficient count mismatch")

    profile_index = next(
        index
        for index, cell in enumerate(notebook["cells"])
        if "SUBMISSION_PROFILE =" in "".join(cell.get("source", []))
    )
    profile = "".join(notebook["cells"][profile_index]["source"])
    profile = replace_once(
        profile,
        "RIDGE_ARTIFACT_ROOT = '/kaggle/input/datasets/ravaghi/wellbore-geology-prediction-artifacts'",
        "RIDGE_ARTIFACT_ROOT = '/kaggle/input/wellbore-geology-prediction-artifacts'",
        "use current Kaggle artifact mount",
    )
    profile = replace_once(
        profile,
        "RUN_MODEL_PACKAGE_CORRECTION = bool(_profile.get('run_model_package_correction', False))",
        "RUN_MODEL_PACKAGE_CORRECTION = True  # required by dynamic all12 meta",
        "enable model package",
    )
    profile = replace_once(
        profile,
        "MODEL_PACKAGE_REQUIRE = False",
        "MODEL_PACKAGE_REQUIRE = True",
        "require model package",
    )
    notebook["cells"][profile_index]["source"] = profile.splitlines(keepends=True)

    package_index = next(
        index
        for index, cell in enumerate(notebook["cells"])
        if "# Optional saved-model correction" in "".join(cell.get("source", []))
    )
    package = "".join(notebook["cells"][package_index]["source"])
    package = replace_once(
        package,
        """        for col, weight in weights.items():
            pred_value += float(weight) * predictions[col].to_numpy(dtype=float)
        target_space =""",
        """        for col, weight in weights.items():
            pred_value += float(weight) * predictions[col].to_numpy(dtype=float)
        _all12_raw_blend_delta = pred_value.copy()
        target_space =""",
        "capture raw model-package blend",
    )
    package = replace_once(
        package,
        """        submission = _mp_validate_submission_ids(_mp_pd.DataFrame({'id': feature_frame['id'].to_numpy(), 'tvt': tvt}), _mp_sample, 'model_package_submission')
        info = {""",
        """        submission = _mp_validate_submission_ids(_mp_pd.DataFrame({'id': feature_frame['id'].to_numpy(), 'tvt': tvt}), _mp_sample, 'model_package_submission')
        _all12_post_by_id = submission.assign(id=submission['id'].astype(str)).set_index('id')['tvt']
        _all12_ids = feature_frame['id'].astype(str)
        predictions['all12_package_blend'] = _all12_raw_blend_delta
        predictions['all12_package_postprocessed'] = (
            _all12_ids.map(_all12_post_by_id).to_numpy(dtype=float)
            - feature_frame['last_known_TVT'].to_numpy(dtype=float)
        )
        globals()['ALL12_PACKAGE_PREDICTIONS'] = predictions.copy()
        globals()['ALL12_PACKAGE_FEATURE_FRAME'] = feature_frame.copy()
        globals()['ALL12_PACKAGE_TARGET_SPACE'] = target_space
        info = {""",
        "export dynamic package components",
    )
    notebook["cells"][package_index]["source"] = package.splitlines(keepends=True)

    dynamic_code = f'''# Dynamic hidden-test-compatible all12 learned-meta branch.
import hashlib as _a12_hashlib
import json as _a12_json
from pathlib import Path as _A12Path

import numpy as _a12_np
import pandas as _a12_pd
from scipy.signal import savgol_filter as _a12_savgol

_A12_FEATURES = {features!r}
_A12_COEFFICIENTS = _a12_np.asarray({coefficients!r}, dtype=float)
_A12_INTERCEPT = {intercept!r}
_A12_SP45_WEIGHT = 0.60
_A12_SAVGOL_WINDOW = 61
_A12_SAVGOL_POLY = 3
_A12_WORK = _A12Path('/kaggle/working') if _A12Path('/kaggle/working').exists() else _A12Path('.')
_A12_SAMPLE_PATH = _A12Path(CFG.DATA) / 'sample_submission.csv'
_a12_sample = _a12_pd.read_csv(_A12_SAMPLE_PATH, dtype={{'id': str}})[['id']]

_a12_public_columns = ['lightgbm-1', 'lightgbm-2', 'lightgbm-3', 'catboost-1', 'catboost-2']
if list(test_preds.columns) != _a12_public_columns:
    raise RuntimeError(f'public component order changed: {{list(test_preds.columns)}}')
_a12_public_ids = test_df2['id'].astype(str).reset_index(drop=True)
if len(_a12_public_ids) != len(test_preds):
    raise RuntimeError('public prediction/id row mismatch')
_a12_public = _a12_pd.DataFrame({{'id': _a12_public_ids}})
for _a12_index, _a12_column in enumerate(_a12_public_columns):
    _a12_public[f'public_{{_a12_index}}'] = test_preds[_a12_column].to_numpy(dtype=float)

if globals().get('ALL12_PACKAGE_TARGET_SPACE') != 'delta':
    raise RuntimeError(f"model package target space is not delta: {{globals().get('ALL12_PACKAGE_TARGET_SPACE')}}")
_a12_package = globals()['ALL12_PACKAGE_PREDICTIONS'].copy()
_a12_package['id'] = _a12_package['id'].astype(str)
_a12_feature_frame = globals()['ALL12_PACKAGE_FEATURE_FRAME'].copy()
_a12_feature_frame['id'] = _a12_feature_frame['id'].astype(str)
_a12_last = _a12_feature_frame[['id', 'last_known_TVT']].copy()

_a12_package_map = {{
    'package_lgb': 'pred_delta_drift_ncc_lgb_alltrain',
    'package_xgb': 'pred_delta_drift_ncc_xgb_alltrain',
    'package_catboost': 'pred_delta_drift_ncc_catboost_alltrain',
    'package_hgb': 'pred_delta_drift_ncc_hgb_alltrain',
    'package_sequence_tcn': 'pred_delta_sequence_tcn_tcn_residual',
    'package_blend': 'all12_package_blend',
    'package_postprocessed': 'all12_package_postprocessed',
}}
_a12_missing_package = sorted(set(_a12_package_map.values()) - set(_a12_package.columns))
if _a12_missing_package:
    raise RuntimeError(f'missing model-package components: {{_a12_missing_package}}')
_a12_package = _a12_package[['id', *_a12_package_map.values()]].rename(
    columns={{value: key for key, value in _a12_package_map.items()}}
)

_a12_frame = (
    _a12_sample.merge(_a12_public, on='id', how='left', validate='one_to_one')
    .merge(_a12_package, on='id', how='left', validate='one_to_one')
    .merge(_a12_last, on='id', how='left', validate='one_to_one')
)
if _a12_frame[_A12_FEATURES + ['last_known_TVT']].isna().any().any():
    raise RuntimeError('dynamic all12 component alignment produced missing values')
_a12_matrix = _a12_frame[_A12_FEATURES].to_numpy(dtype=float)
if not _a12_np.isfinite(_a12_matrix).all():
    raise RuntimeError('dynamic all12 component matrix contains non-finite values')

_a12_meta = (
    _a12_frame['last_known_TVT'].to_numpy(dtype=float)
    + _A12_INTERCEPT
    + _a12_matrix @ _A12_COEFFICIENTS
)
_a12_wells = _a12_frame['id'].str.rsplit('_', n=1).str[0]
for _, _a12_positions in _a12_frame.groupby(_a12_wells, sort=False).groups.items():
    _a12_pos = _a12_frame.index.get_indexer(_a12_positions)
    _a12_window = min(_A12_SAVGOL_WINDOW, len(_a12_pos))
    if _a12_window % 2 == 0:
        _a12_window -= 1
    if _a12_window >= _A12_SAVGOL_POLY + 2:
        _a12_meta[_a12_pos] = _a12_savgol(
            _a12_meta[_a12_pos], _a12_window, _A12_SAVGOL_POLY
        )

_a12_sp45 = _a12_pd.read_csv(
    _A12_WORK / 'sp45_projection_submission.csv', dtype={{'id': str}}
)[['id', 'tvt']]
_a12_sp45 = _a12_sample.merge(_a12_sp45, on='id', how='left', validate='one_to_one')
if _a12_sp45['tvt'].isna().any():
    raise RuntimeError('SP45 component does not cover active hidden sample')
_a12_final = _a12_sample.copy()
_a12_final['tvt'] = (
    _A12_SP45_WEIGHT * _a12_sp45['tvt'].to_numpy(dtype=float)
    + (1.0 - _A12_SP45_WEIGHT) * _a12_meta
)
if not _a12_np.isfinite(_a12_final['tvt'].to_numpy(dtype=float)).all():
    raise RuntimeError('dynamic all12 output contains non-finite values')

_a12_existing = _A12_WORK / 'submission.csv'
if _a12_existing.exists():
    _a12_pd.read_csv(_a12_existing).to_csv(
        _A12_WORK / 'submission_before_all12_dynamic.csv', index=False
    )
_a12_final.to_csv(_A12_WORK / 'submission_all12_dynamic_w060.csv', index=False)
_a12_final.to_csv(_a12_existing, index=False)

_a12_digest = _a12_hashlib.sha256(_a12_existing.read_bytes()).hexdigest()
_a12_report = {{
    'method': 'dynamic_hidden_test_all12_meta_savgol61_sp45_w060',
    'rows': int(len(_a12_final)),
    'wells': int(_a12_wells.nunique()),
    'features': _A12_FEATURES,
    'coefficients': _A12_COEFFICIENTS.tolist(),
    'intercept': float(_A12_INTERCEPT),
    'sp45_weight': float(_A12_SP45_WEIGHT),
    'id_order_matches_active_sample': bool(_a12_final['id'].equals(_a12_sample['id'])),
    'finite_tvt': True,
    'sha256_submission_csv': _a12_digest,
    'tvt_min': float(_a12_final['tvt'].min()),
    'tvt_max': float(_a12_final['tvt'].max()),
    'tvt_mean': float(_a12_final['tvt'].mean()),
}}
(_A12_WORK / 'all12_dynamic_audit.json').write_text(
    _a12_json.dumps(_a12_report, indent=2) + '\\n', encoding='utf-8'
)
print('Dynamic all12 submission audit:', _a12_report, flush=True)
'''

    hedge_index = next(
        index
        for index, cell in enumerate(notebook["cells"])
        if "# Guarded PF seed-branch midpoint hedge" in "".join(cell.get("source", []))
    )
    notebook["cells"].insert(hedge_index + 1, code_cell(dynamic_code))

    for cell in notebook["cells"]:
        if cell.get("cell_type") == "code":
            cell["execution_count"] = None
            cell["outputs"] = []

    notebook["cells"][0]["source"] = [
        "# ROGII dynamic all12 SP45 W060 submission\n",
        "\n",
        "Hidden-test-compatible inference: five public boosters, seven model-package components, and SP45.\n",
    ]
    NOTEBOOK.write_text(json.dumps(notebook, indent=1) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "notebook": str(NOTEBOOK),
                "cells": len(notebook["cells"]),
                "base_sha256": digest,
                "selected_variant": model["selected_variant"],
                "features": features,
                "coefficients": coefficients,
                "intercept": intercept,
                "bytes": NOTEBOOK.stat().st_size,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
