"""Build a leakage-safe OOF notebook for the submitted generic-core pipeline.

The public submission notebook loads pretrained learned-branch models for test
inference.  That is valid for competition inference but cannot be evaluated on
the same 773 train wells without leakage.  This builder enables the notebook's
target-free SP45/Ridge/selector diagnostics and appends a GroupKFold-retrained
learned branch before blending the two predictions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def source_text(cell: dict) -> str:
    value = cell.get("source", "")
    return "".join(value) if isinstance(value, list) else str(value)


def set_source(cell: dict, value: str) -> None:
    if isinstance(cell.get("source"), list):
        cell["source"] = value.splitlines(keepends=True)
    else:
        cell["source"] = value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_control(
    source: str,
    selector_pf_seeds: int,
    selector_particles: int,
    run_cv_report: bool,
    fast: bool,
    n_wells: int,
    run_learned_oof: bool,
) -> str:
    replacements = {
        "RUN_CV_REPORT = False": f"RUN_CV_REPORT = {bool(run_cv_report)}",
        "RUN_FULL_STACK_CV_ABLATION = False": "RUN_FULL_STACK_CV_ABLATION = True",
        "CV_N_WELLS = 250": f"CV_N_WELLS = {int(n_wells)}",
        "CV_ABLATION_N_WELLS = 250": f"CV_ABLATION_N_WELLS = {int(n_wells)}",
        "CV_SELECTOR_PF_SEEDS = 24": f"CV_SELECTOR_PF_SEEDS = {int(selector_pf_seeds)}",
        "SP45_SELECTOR_N_PARTICLES = 500": f"SP45_SELECTOR_N_PARTICLES = {int(selector_particles)}",
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise RuntimeError(f"Expected one control assignment {old!r}")
        source = source.replace(old, new, 1)
    marker = f"CV_SELECTOR_PF_SEEDS = {int(selector_pf_seeds)}\n"
    source = source.replace(
        marker,
        marker
        + "RUN_HEEL_ABLATION_GRID = False\n"
        + f"RUN_GENERIC_CORE_OOF = {bool(run_learned_oof)}\n"
        + "RUN_GENERIC_CORE_SP45_OOF = True\n",
        1,
    )
    if fast:
        source = source.replace("RUN_GENERIC_CORE_OOF = True\n", "RUN_GENERIC_CORE_OOF = True\nimport os as _gc_fast_os\n_gc_fast_os.environ['FAST'] = '1'\n", 1)
    return source


def patch_full_stack_cell(source: str, single_generic_core_grid: bool) -> str:
    if single_generic_core_grid:
        start = source.index("    grid = []\n")
        end = source.index("    rows = []\n", start)
        source = source[:start] + "    grid = [(True, 'off', False, False)]\n\n" + source[end:]
    old = "    rows = []\n    floor_rows = []\n"
    new = "    rows = []\n    prediction_rows = []\n    floor_rows = []\n"
    if source.count(old) != 1:
        raise RuntimeError("Could not add full-stack prediction accumulator")
    source = source.replace(old, new, 1)

    old = "                rmse, n, sse = _fs_rmse_sse(y, final)\n                rows.append({\n"
    new = """                rmse, n, sse = _fs_rmse_sse(y, final)
                if bool(heel_on) and detector_mode == 'off' and not prefix_trust_on and not vp_on:
                    prediction_rows.extend([
                        {
                            'id': f'{wid}_{int(_ri)}',
                            'well': wid,
                            'row_idx': int(_ri),
                            'sp45_oof': float(_pv),
                            'target_tvt': float(_yv),
                        }
                        for _ri, _pv, _yv in zip(row_idx, final, y)
                    ])
                rows.append({
"""
    if source.count(old) != 1:
        raise RuntimeError("Could not save the selected SP45 OOF rows")
    source = source.replace(old, new, 1)

    old = "    well_df.to_csv(_FS_WORK / 'full_stack_bimodal_ablation_by_well.csv', index=False)\n"
    new = old + "    _fs_pd.DataFrame(prediction_rows).to_csv(_FS_WORK / 'generic_core_sp45_oof.csv', index=False)\n"
    if source.count(old) != 1:
        raise RuntimeError("Could not write the selected SP45 OOF file")
    return source.replace(old, new, 1)


SP45_SUMMARY_CELL = r'''# Cached target-free SP45 OOF summary.
if bool(globals().get('RUN_GENERIC_CORE_SP45_OOF', False)):
    import json as _sp_json
    import numpy as _sp_np
    import pandas as _sp_pd
    from pathlib import Path as _SpPath

    _sp_work = _SpPath('/kaggle/working') if _SpPath('/kaggle/working').exists() else _SpPath('.')
    _sp_oof = _sp_pd.read_csv(_sp_work / 'generic_core_sp45_oof.csv')
    _sp_required = {'id', 'well', 'row_idx', 'sp45_oof', 'target_tvt'}
    if not _sp_required.issubset(_sp_oof.columns):
        raise RuntimeError(f'SP45 OOF cache missing columns: {sorted(_sp_required - set(_sp_oof.columns))}')
    if _sp_oof['id'].duplicated().any():
        raise RuntimeError('SP45 OOF cache contains duplicate ids')
    _sp_values = _sp_oof[['sp45_oof', 'target_tvt']].to_numpy(float)
    if not _sp_np.isfinite(_sp_values).all():
        raise RuntimeError('SP45 OOF cache contains non-finite values')
    _sp_oof['square_error'] = (_sp_oof['sp45_oof'] - _sp_oof['target_tvt']) ** 2
    _sp_by_well = _sp_oof.groupby('well', sort=True).agg(
        rows=('id', 'size'),
        mse=('square_error', 'mean'),
    ).reset_index()
    _sp_by_well['sp45_oof_rmse'] = _sp_np.sqrt(_sp_by_well['mse'])
    _sp_by_well.drop(columns=['mse']).to_csv(
        _sp_work / 'generic_core_sp45_oof_by_well.csv', index=False
    )
    _sp_summary = {
        'evaluation': 'target-free generic-core SP45 branch on fixed sampled train wells',
        'sample_seed': int(globals().get('CV_SEED', 0)),
        'requested_wells': int(globals().get('CV_ABLATION_N_WELLS', 0)),
        'wells': int(_sp_by_well['well'].nunique()),
        'rows': int(len(_sp_oof)),
        'sp45_oof_rmse': float(_sp_np.sqrt(_sp_oof['square_error'].mean())),
        'well_rmse_p50': float(_sp_by_well['sp45_oof_rmse'].quantile(0.50)),
        'well_rmse_p90': float(_sp_by_well['sp45_oof_rmse'].quantile(0.90)),
        'selector_pf_seeds': int(globals().get('CV_SELECTOR_PF_SEEDS', 0)),
        'selector_particles': int(globals().get('SP45_SELECTOR_N_PARTICLES', 0)),
        'fast': bool(getattr(CFG, 'FAST', False)),
        'same_well_contact_included': False,
        'visible_prefix_overlay_included': False,
        'model_package_correction_included': False,
    }
    (_sp_work / 'generic_core_sp45_oof_summary.json').write_text(
        _sp_json.dumps(_sp_summary, indent=2) + '\n', encoding='utf-8'
    )
    print('generic-core SP45 OOF summary')
    print(_sp_json.dumps(_sp_summary, indent=2))
'''


OOF_CELL = r'''# Leakage-safe generic-core OOF: retrain only the learned branch by GroupKFold.
if bool(globals().get('RUN_GENERIC_CORE_OOF', False)):
    import json as _gc_json
    import numpy as _gc_np
    import pandas as _gc_pd
    from pathlib import Path as _GcPath

    _gc_work = _GcPath('/kaggle/working') if _GcPath('/kaggle/working').exists() else _GcPath('.')
    _gc_sp45 = _gc_pd.read_csv(_gc_work / 'generic_core_sp45_oof.csv')
    _gc_train_wids = sorted(
        p.stem.replace('__horizontal_well', '')
        for p in (CFG.DATA / 'train').glob('*__horizontal_well.csv')
    )
    _gc_likpf = build_likpf(_gc_train_wids, 'train')
    _gc_train = add_likpf_features(
        build_features(_gc_train_wids, 'train', is_train=True), _gc_likpf
    ).reset_index(drop=True)
    _gc_features = [
        c for c in _gc_train.columns
        if c not in {'well', 'id', 'target'}
        and not (c.startswith('likpf_scale_') or c == 'likpf_mean')
    ]
    # A one-row placeholder is only used to satisfy train_stack's test matrix;
    # all learned predictions evaluated below are the GroupKFold OOF vector.
    _gc_meta_oof, _, _, _ = train_stack(
        _gc_train, _gc_train.iloc[:1].copy(), _gc_features
    )
    _gc_learned_oof = make_prediction(_gc_train, _gc_meta_oof, None)
    _gc_learned = _gc_train[['id']].copy()
    _gc_learned['learned_oof'] = _gc_learned_oof
    _gc_truth = _gc_train[['id', 'well', 'last_known_tvt', 'target']].copy()
    _gc_truth['target_tvt'] = _gc_truth['last_known_tvt'] + _gc_truth['target']
    _gc_out = _gc_sp45.merge(_gc_learned, on='id', how='inner').merge(
        _gc_truth[['id', 'well', 'target_tvt']], on=['id', 'well'], how='inner'
    )
    _gc_out['generic_core_oof'] = (
        float(SP45_BLEND_WEIGHT) * _gc_out['sp45_oof']
        + (1.0 - float(SP45_BLEND_WEIGHT)) * _gc_out['learned_oof']
    )
    _gc_out.to_csv(_gc_work / 'generic_core_oof_predictions.csv', index=False)
    _gc_rows = []
    for _wid, _g in _gc_out.groupby('well', sort=True):
        _err = _g['generic_core_oof'].to_numpy(float) - _g['target_tvt'].to_numpy(float)
        _base_err = _g['sp45_oof'].to_numpy(float) - _g['target_tvt'].to_numpy(float)
        _learned_err = _g['learned_oof'].to_numpy(float) - _g['target_tvt'].to_numpy(float)
        _gc_rows.append({
            'well': str(_wid),
            'rows': int(len(_g)),
            'generic_core_oof_rmse': float(_gc_np.sqrt(_gc_np.mean(_err * _err))),
            'sp45_oof_rmse': float(_gc_np.sqrt(_gc_np.mean(_base_err * _base_err))),
            'learned_oof_rmse': float(_gc_np.sqrt(_gc_np.mean(_learned_err * _learned_err))),
        })
    _gc_by_well = _gc_pd.DataFrame(_gc_rows)
    _gc_by_well.to_csv(_gc_work / 'generic_core_oof_by_well.csv', index=False)
    _gc_e = _gc_out['generic_core_oof'].to_numpy(float) - _gc_out['target_tvt'].to_numpy(float)
    _gc_summary = {
        'evaluation': 'GroupKFold learned branch + target-free SP45/Ridge/selector/projection',
        'wells': int(_gc_by_well['well'].nunique()),
        'rows': int(len(_gc_out)),
        'sp45_blend_weight': float(SP45_BLEND_WEIGHT),
        'generic_core_oof_rmse': float(_gc_np.sqrt(_gc_np.mean(_gc_e * _gc_e))),
        'well_rmse_p50': float(_gc_by_well['generic_core_oof_rmse'].quantile(0.50)),
        'well_rmse_p90': float(_gc_by_well['generic_core_oof_rmse'].quantile(0.90)),
        'sp45_oof_rmse': float(_gc_np.sqrt(_gc_np.mean((_gc_out['sp45_oof'] - _gc_out['target_tvt']) ** 2))),
        'learned_oof_rmse': float(_gc_np.sqrt(_gc_np.mean((_gc_out['learned_oof'] - _gc_out['target_tvt']) ** 2))),
        'branch_hedge_included': False,
        'same_well_contact_included': False,
        'visible_prefix_overlay_included': False,
        'model_package_correction_included': False,
    }
    (_gc_work / 'generic_core_oof_summary.json').write_text(
        _gc_json.dumps(_gc_summary, indent=2) + '\n', encoding='utf-8'
    )
    print('generic-core leakage-safe OOF summary')
    print(_gc_json.dumps(_gc_summary, indent=2))
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-notebook", type=Path, required=True)
    parser.add_argument("--source-metadata", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--owner", default="zacky21")
    parser.add_argument("--selector-pf-seeds", type=int, default=128)
    parser.add_argument("--selector-particles", type=int, default=500)
    parser.add_argument("--run-cv-report", action="store_true")
    parser.add_argument("--single-generic-core-grid", action="store_true")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--n-wells", type=int, default=773)
    parser.add_argument("--sp45-only", action="store_true")
    parser.add_argument("--slug", default="rogii-new-strategy-6-213-generic-core-oof")
    parser.add_argument("--title", default="ROGII New Strategy 6.213 Generic Core Group OOF")
    args = parser.parse_args()

    notebook_bytes = args.source_notebook.read_bytes()
    notebook = json.loads(notebook_bytes)
    control = next(
        c for c in notebook['cells']
        if c.get('cell_type') == 'code' and 'RUN_CV_REPORT' in source_text(c)
    )
    set_source(
        control,
        patch_control(
            source_text(control),
            args.selector_pf_seeds,
            args.selector_particles,
            args.run_cv_report,
            args.fast,
            args.n_wells,
            not args.sp45_only,
        ),
    )
    full_stack = next(
        c for c in notebook['cells']
        if c.get('cell_type') == 'code' and 'Full-stack bimodal CV ablation' in source_text(c)
    )
    set_source(full_stack, patch_full_stack_cell(source_text(full_stack), args.single_generic_core_grid))
    notebook['cells'].append({
        'cell_type': 'code',
        'execution_count': None,
        'metadata': {},
        'outputs': [],
        'source': SP45_SUMMARY_CELL.splitlines(keepends=True),
    })
    if not args.sp45_only:
        notebook['cells'].append({
            'cell_type': 'code',
            'execution_count': None,
            'metadata': {},
            'outputs': [],
            'source': OOF_CELL.splitlines(keepends=True),
        })

    metadata = json.loads(args.source_metadata.read_text(encoding='utf-8'))
    metadata['id'] = f"{args.owner}/{args.slug}"
    metadata['title'] = args.title
    metadata['code_file'] = 'rogii-new-strategy-6-213-generic-core-oof.ipynb'
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_notebook = args.output_dir / metadata['code_file']
    output_notebook.write_text(json.dumps(notebook, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (args.output_dir / 'kernel-metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    manifest = {
        'source_notebook': str(args.source_notebook),
        'source_sha256': sha256(args.source_notebook),
        'notebook': str(output_notebook),
        'notebook_sha256': sha256(output_notebook),
        'kaggle_id': metadata['id'],
        'evaluation': (
            'target-free SP45/Ridge/selector/projection sampled-well OOF'
            if args.sp45_only
            else 'GroupKFold learned branch + target-free SP45/Ridge/selector/projection'
        ) + '; no contact/visible-prefix/model-package overlays',
        'n_wells': int(args.n_wells),
        'sp45_only': bool(args.sp45_only),
        'selector_pf_seeds': int(args.selector_pf_seeds),
        'selector_particles': int(args.selector_particles),
        'fast': bool(args.fast),
    }
    (args.output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
