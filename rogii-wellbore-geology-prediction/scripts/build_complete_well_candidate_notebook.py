#!/usr/bin/env python3
"""Build the hidden-dynamic notebook for the first 0.08-ft-class candidate."""

from __future__ import annotations

import ast
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
OUTPUT_DIR = ROOT / "kaggle-push/complete-well-008-candidate"
OUTPUT = OUTPUT_DIR / "rogii-complete-well-008-candidate.ipynb"


PUBLIC_SMOOTHER = r'''
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


PRODUCTION_RUNNER = r'''
# Hidden-dynamic complete-well candidate selected on the frozen local contract.
from dataclasses import dataclass as _cw_dataclass
from pathlib import Path as _CWPath
import json as _cw_json

from catboost import CatBoostRegressor as _CWCatBoostRegressor
from sklearn.ensemble import ExtraTreesRegressor as _CWExtraTreesRegressor
from sklearn.impute import SimpleImputer as _CWSimpleImputer
from sklearn.pipeline import make_pipeline as _cw_make_pipeline

_CW_WORK = _CWPath('/kaggle/working') if _CWPath('/kaggle/working').exists() else _CWPath('.')
_CW_SUB = _CW_WORK / 'submission.csv'
_CW_SP45 = _CW_WORK / 'sp45_projection_submission.csv'
_CW_SAMPLE = _mp_sample[['id']].copy()
_CW_DATA = _CWPath(_mp_data_dir)
_CW_PACKAGE = _mp_find_package_root()
if _CW_PACKAGE is None:
    raise RuntimeError('complete-well candidate requires the model package')
if not _CW_SUB.exists() or not _CW_SP45.exists():
    raise RuntimeError('complete-well candidate requires final and SP45 submissions')


def _cw_align(frame, value_column, label):
    work = frame[['id', value_column]].copy()
    work['id'] = work['id'].astype(str)
    aligned = _CW_SAMPLE.assign(id=_CW_SAMPLE['id'].astype(str)).merge(
        work, on='id', how='left', validate='one_to_one'
    )
    values = _mp_pd.to_numeric(aligned[value_column], errors='coerce').to_numpy(float)
    if len(values) != len(_CW_SAMPLE) or not _mp_np.isfinite(values).all():
        raise RuntimeError(f'{label}: invalid sample alignment')
    return values


def _cw_split_dir(split):
    candidates = [
        _CW_DATA / split,
        _CWPath(globals().get('COMPETITION_DATA_ROOT', _CW_DATA)) / split,
    ]
    for candidate in candidates:
        if candidate.exists() and any(candidate.glob('*__horizontal_well.csv')):
            return candidate
    raise RuntimeError(f'could not locate {split} well files under {_CW_DATA}')


def _cw_read_well(split_dir, well):
    horizontal_path = split_dir / f'{well}__horizontal_well.csv'
    typewell_path = split_dir / f'{well}__typewell.csv'
    if not horizontal_path.exists() or not typewell_path.exists():
        raise RuntimeError(f'missing active well files for {well}')
    return _mp_pd.read_csv(horizontal_path), _mp_pd.read_csv(typewell_path)


def _cw_curve_model(kind, seed):
    if kind == 'extra_trees':
        return _cw_make_pipeline(
            _CWSimpleImputer(strategy='median'),
            _CWExtraTreesRegressor(
                n_estimators=500,
                min_samples_leaf=10,
                max_features=0.70,
                n_jobs=-1,
                random_state=seed,
            ),
        )
    if kind == 'catboost':
        return _cw_make_pipeline(
            _CWSimpleImputer(strategy='median'),
            _CWCatBoostRegressor(
                loss_function='MultiRMSE',
                iterations=700,
                depth=4,
                learning_rate=0.03,
                l2_leaf_reg=30.0,
                verbose=False,
                random_seed=seed,
                thread_count=6,
            ),
        )
    raise KeyError(kind)


_cw_train_dir = _cw_split_dir('train')
_cw_test_dir = _cw_split_dir('test')
_cw_gt = _mp_pd.read_parquet(_CW_PACKAGE / 'oof/train_gt.parquet')
_cw_oof_delta = _mp_np.load(
    _CW_PACKAGE / 'oof/blend_oof_postprocessed.npy',
    mmap_mode='r',
)
if len(_cw_gt) != len(_cw_oof_delta):
    raise RuntimeError('model-package OOF row contract mismatch')
_cw_gt = _cw_gt.copy()
_cw_gt['artifact_tvt'] = (
    _mp_pd.to_numeric(_cw_gt['last_known_TVT'], errors='coerce').to_numpy(float)
    + _mp_np.asarray(_cw_oof_delta, float)
)
_cw_gt = _cw_gt.sort_values(['well_id', 'row_index']).reset_index(drop=True)

_cw_train_features = []
_cw_train_labels = []
_cw_train_wells = sorted(_cw_gt['well_id'].astype(str).unique())
for _cw_pos, _cw_well in enumerate(_cw_train_wells, 1):
    _cw_group = _cw_gt.loc[_cw_gt['well_id'].astype(str).eq(_cw_well)].sort_values('row_index')
    _cw_horizontal, _cw_typewell = _cw_read_well(_cw_train_dir, _cw_well)
    _cw_rows = _cw_group['row_index'].to_numpy(int)
    _cw_expected = _mp_np.flatnonzero(_cw_horizontal['TVT_input'].isna().to_numpy())
    if not _mp_np.array_equal(_cw_rows, _cw_expected):
        raise RuntimeError(f'{_cw_well}: package OOF rows do not match active train suffix')
    _cw_artifact = _cw_group['artifact_tvt'].to_numpy(float)
    _cw_train_features.append(
        build_well_features(_cw_horizontal, _cw_typewell, _cw_rows, _cw_artifact, 12)
    )
    _cw_residual = _cw_group['target_tvt'].to_numpy(float) - _cw_artifact
    _cw_train_labels.append(legendre_coefficients(_cw_residual, 5))
    if _cw_pos % 100 == 0 or _cw_pos == len(_cw_train_wells):
        print(f'complete-well train features {_cw_pos}/{len(_cw_train_wells)}', flush=True)
_cw_train_x = _mp_np.vstack(_cw_train_features)
_cw_train_y = _mp_np.vstack(_cw_train_labels)
if _cw_train_x.shape != (773, 207) or _cw_train_y.shape != (773, 6):
    raise RuntimeError(
        f'unexpected complete-well train shapes: {_cw_train_x.shape}, {_cw_train_y.shape}'
    )

_cw_models = {
    'extra_trees': _cw_curve_model('extra_trees', 20261730),
    'catboost': _cw_curve_model('catboost', 20261731),
}
for _cw_name, _cw_model in _cw_models.items():
    print('fitting complete-well', _cw_name, flush=True)
    _cw_model.fit(_cw_train_x, _cw_train_y)

_cw_pkg_tvt = _cw_align(_mp_pkg_sub, 'tvt', 'model-package trajectory')
_cw_sp45_tvt = _cw_align(
    _mp_pd.read_csv(_CW_SP45), 'tvt', 'SP45 center trajectory'
)
_cw_ids = _CW_SAMPLE['id'].astype(str)
_cw_wells = _cw_ids.str.rsplit('_', n=1).str[0]
_cw_rows = _mp_pd.to_numeric(
    _cw_ids.str.rsplit('_', n=1).str[-1], errors='raise'
).to_numpy(int)
_cw_test_features = []
_cw_test_groups = []
_cw_matcher = _mp_np.zeros(len(_CW_SAMPLE), float)
_cw_md_since = _mp_np.zeros(len(_CW_SAMPLE), float)

for _cw_pos, _cw_well in enumerate(sorted(_cw_wells.unique()), 1):
    _cw_positions = _mp_np.flatnonzero(_cw_wells.eq(_cw_well).to_numpy())
    _cw_local_rows = _cw_rows[_cw_positions]
    _cw_horizontal, _cw_typewell = _cw_read_well(_cw_test_dir, _cw_well)
    _cw_expected = _mp_np.flatnonzero(_cw_horizontal['TVT_input'].isna().to_numpy())
    if not _mp_np.array_equal(_cw_local_rows, _cw_expected):
        raise RuntimeError(f'{_cw_well}: sample rows do not match active test suffix')
    _cw_artifact = _cw_pkg_tvt[_cw_positions]
    _cw_test_features.append(
        build_well_features(
            _cw_horizontal, _cw_typewell, _cw_local_rows, _cw_artifact, 12
        )
    )
    _cw_test_groups.append((_cw_positions, _cw_well))
    _cw_match_output, _cw_diag = scan_complete_well(
        horizontal=_cw_horizontal,
        typewell=_cw_typewell,
        center=_cw_sp45_tvt[_cw_positions],
        radius=60.0,
        offset_step=1.0,
        stride=32,
        half_window=256,
        window_step=4,
        temperatures=(0.10,),
        prior_strength=0.05,
        gr_scale=1.30,
    )
    _cw_md = _mp_pd.to_numeric(_cw_horizontal['MD'], errors='coerce').to_numpy(float)
    _cw_known = _mp_np.flatnonzero(_cw_horizontal['TVT_input'].notna().to_numpy())
    if len(_cw_known) == 0:
        raise RuntimeError(f'{_cw_well}: no visible prefix')
    _cw_local_md_since = _mp_np.maximum(
        _cw_md[_cw_local_rows] - _cw_md[_cw_known[-1]], 0.0
    )
    _cw_ramp = 1.0 - _mp_np.exp(-_cw_local_md_since / 300.0)
    _cw_matcher[_cw_positions] = (
        0.20
        * _cw_ramp
        * _mp_np.clip(_cw_match_output[0.10]['offset_mean'], -4.0, 4.0)
    )
    _cw_md_since[_cw_positions] = _cw_local_md_since
    print(
        f'complete-well test {_cw_pos}/{_cw_wells.nunique()} {_cw_well} '
        f'sigma={float(_cw_diag["sigma"]):.3f}',
        flush=True,
    )

_cw_test_x = _mp_np.vstack(_cw_test_features)
_cw_coef = 0.5 * (
    _mp_np.asarray(_cw_models['extra_trees'].predict(_cw_test_x), float)
    + _mp_np.asarray(_cw_models['catboost'].predict(_cw_test_x), float)
)
_cw_curve = _mp_np.zeros(len(_CW_SAMPLE), float)
for _cw_local, (_cw_positions, _cw_well) in enumerate(_cw_test_groups):
    _cw_raw_constant = float(_cw_coef[_cw_local, 0])
    _cw_ramp = 1.0 - _mp_np.exp(-_cw_md_since[_cw_positions] / 300.0)
    # Local selected curve scale 0.50, then submission ensemble weight 1.20.
    _cw_curve[_cw_positions] = (
        1.20 * 0.50 * _cw_ramp * _mp_np.clip(_cw_raw_constant, -4.0, 4.0)
    )

_cw_before = _mp_pd.read_csv(_CW_SUB)
_cw_base = _cw_align(_cw_before, 'tvt', 'pre complete-well submission')
_cw_total = _cw_matcher + _cw_curve + 0.20
_cw_final = _CW_SAMPLE.copy()
_cw_final['tvt'] = _cw_base + _cw_total
if not _mp_np.isfinite(_cw_final['tvt'].to_numpy(float)).all():
    raise RuntimeError('complete-well candidate produced non-finite values')
_cw_before.to_csv(_CW_WORK / 'submission_before_complete_well.csv', index=False)
_cw_final.to_csv(_CW_SUB, index=False)
_mp_pd.DataFrame({
    'id': _CW_SAMPLE['id'].astype(str),
    'base_tvt': _cw_base,
    'matcher_correction': _cw_matcher,
    'curve_correction': _cw_curve,
    'global_shift': 0.20,
    'total_correction': _cw_total,
    'final_tvt': _cw_final['tvt'].to_numpy(float),
}).to_csv(_CW_WORK / 'complete_well_candidate_components.csv', index=False)
_cw_summary = {
    'candidate': 'complete_well_008_hidden_dynamic_v1',
    'train_wells': int(len(_cw_train_wells)),
    'train_feature_shape': list(_cw_train_x.shape),
    'test_wells': int(_cw_wells.nunique()),
    'test_rows': int(len(_CW_SAMPLE)),
    'model_package_used_as_artifact_only': True,
    'model_package_submission_blend_weight': 0.0,
    'matcher': {
        'temperature': 0.10, 'cap': 4.0, 'tau': 300.0, 'scale': 0.20,
    },
    'curve': {
        'models': ['extra_trees', 'catboost'],
        'mean_weight_each': 0.50,
        'degree': 0,
        'cap': 4.0,
        'tau': 300.0,
        'local_scale': 0.50,
        'submission_weight': 1.20,
    },
    'global_shift_ft': 0.20,
    'correction_mean': float(_mp_np.mean(_cw_total)),
    'correction_p95_abs': float(_mp_np.quantile(_mp_np.abs(_cw_total), 0.95)),
    'correction_max_abs': float(_mp_np.max(_mp_np.abs(_cw_total))),
}
(_CW_WORK / 'complete_well_candidate_summary.json').write_text(
    _cw_json.dumps(_cw_summary, indent=2) + '\n', encoding='utf-8'
)
print('complete-well candidate:', _cw_summary, flush=True)
'''


def source_text(cell: dict[str, object]) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return source.replace(old, new, 1)


def extract_nodes(path: Path, names: tuple[str, ...]) -> str:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            start_line = min(
                [node.lineno]
                + [decorator.lineno for decorator in node.decorator_list]
            )
            found[node.name] = "".join(lines[start_line - 1 : node.end_lineno])
    missing = set(names) - set(found)
    if missing:
        raise RuntimeError(f"{path}: missing source nodes {sorted(missing)}")
    return "\n\n".join(found[name] for name in names) + "\n"


def main() -> None:
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise RuntimeError(f"source notebook changed: {digest}")
    notebook = json.loads(SOURCE.read_text(encoding="utf-8"))

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
        PUBLIC_SMOOTHER + "def _find_models():",
        "insert public SG601 smoother",
    )
    learned = replace_once(
        learned,
        "make_prediction(train_df, meta_oof, None)",
        "make_prediction(train_df, _smooth_public_meta_delta(train_df, meta_oof), None)",
        "smooth learned OOF delta",
    )
    learned = replace_once(
        learned,
        "test_pred = make_prediction(test_df, meta_test, None)",
        "test_pred = make_prediction(test_df, _smooth_public_meta_delta(test_df, meta_test), None)",
        "smooth learned test delta",
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

# The package trajectory is required by the target-free whole-well features.
# Its direct blend remains exactly zero; the incumbent is unchanged here.
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
    correction_cell = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": (
            "# Generated target-free complete-well helpers.\n"
            "from dataclasses import dataclass\n"
            + helper_source
            + "\n"
            + PRODUCTION_RUNNER
        ).splitlines(keepends=True),
    }
    audit_index = next(
        index
        for index, cell in enumerate(notebook["cells"])
        if "# Final submission audit:" in source_text(cell)
    )
    notebook["cells"].insert(audit_index, correction_cell)

    notebook["cells"][0]["source"] = [
        "# ROGII complete-well 0.08-ft-class candidate\n",
        "\n",
        "Hidden-dynamic version of the frozen local candidate: public learned "
        "SG601, bounded SP45-centered matcher, whole-well residual model, "
        "and a +0.20 ft global shift.\n",
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
        "id": "zacky21/rogii-complete-well-008-candidate",
        "title": "ROGII Complete Well 008 Candidate",
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
        "model_package_direct_weight": 0.0,
        "local_holdout_improvement_ft": 0.0796429493,
    }
    (OUTPUT_DIR / "build_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
