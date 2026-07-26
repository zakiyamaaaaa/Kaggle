"""Build a public-notebook variant with OOF-trained artifact well-bias correction."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BIAS_CELL = r'''
# OOF-trained artifact smoothing + per-well bias correction.
# This cell runs after model-package correction and before the final branch hedge.
if bool(globals().get('RUN_ARTIFACT_WELL_BIAS_CORRECTION', False)):
    import json as _wb_json
    from pathlib import Path as _WBPath
    import numpy as _wb_np
    import pandas as _wb_pd
    from scipy.signal import savgol_filter as _wb_savgol
    from sklearn.impute import SimpleImputer as _WBImputer
    from sklearn.linear_model import Ridge as _WBRidge
    from sklearn.pipeline import make_pipeline as _wb_pipeline
    from sklearn.preprocessing import StandardScaler as _WBScaler

    _wb_pkg_root = _mp_find_package_root()
    if _wb_pkg_root is None or _mp_pkg_sub is None:
        print('Artifact well-bias correction skipped: model package unavailable.')
    else:
        _wb_oof = _wb_pkg_root / 'oof'
        _wb_gt = _wb_pd.read_parquet(_wb_oof / 'train_gt.parquet')
        _wb_raw_delta = _wb_np.load(_wb_oof / 'blend_oof_postprocessed.npy').reshape(-1).astype(float)
        _wb_smooth_window = 601
        _wb_smooth_poly = 2
        _wb_smooth_alpha = 1.03
        _wb_bias_scale = 0.10

        def _wb_slope(x, y):
            good = _wb_np.isfinite(x) & _wb_np.isfinite(y)
            if int(good.sum()) < 3 or float(_wb_np.std(x[good])) < 1e-8:
                return 0.0
            return float(_wb_np.polyfit(x[good], y[good], 1)[0])

        def _wb_smooth(values, wells, rows):
            out = _wb_np.asarray(values, dtype=float).copy()
            frame = _wb_pd.DataFrame({'pos': _wb_np.arange(len(out)), 'well': wells, 'row': rows})
            for _, part in frame.groupby('well', sort=False):
                pos = part.sort_values('row')['pos'].to_numpy(dtype=int)
                win = min(_wb_smooth_window, len(pos))
                if win % 2 == 0:
                    win -= 1
                if win < _wb_smooth_poly + 2:
                    continue
                out[pos] = _wb_smooth_alpha * _wb_savgol(
                    out[pos], window_length=win,
                    polyorder=min(_wb_smooth_poly, win - 1), mode='interp'
                )
            return out

        def _wb_prefix(data_root, split, well_ids):
            split_dir = _WBPath(data_root) / split
            rows = []
            for hw_path in sorted(split_dir.glob('*__horizontal_well.csv')):
                wid = hw_path.name.split('__', 1)[0]
                if wid not in well_ids:
                    continue
                tw_path = split_dir / f'{wid}__typewell.csv'
                if not tw_path.exists():
                    continue
                hw = _wb_pd.read_csv(hw_path)
                tw = _wb_pd.read_csv(tw_path)
                known = hw.loc[hw['TVT_input'].notna()].copy()
                if len(known) < 5:
                    continue
                twv = _wb_pd.to_numeric(tw['TVT'], errors='coerce')
                twg = _wb_pd.to_numeric(tw['GR'], errors='coerce')
                twf = _wb_pd.DataFrame({'tvt': twv, 'gr': twg}).dropna().groupby('tvt', as_index=False)['gr'].median().sort_values('tvt')
                tvt = _wb_pd.to_numeric(known['TVT_input'], errors='coerce').to_numpy(float)
                gr = _wb_pd.to_numeric(known['GR'], errors='coerce').to_numpy(float)
                md = _wb_pd.to_numeric(known['MD'], errors='coerce').to_numpy(float)
                z = _wb_pd.to_numeric(known['Z'], errors='coerce').to_numpy(float)
                ref = _wb_np.interp(tvt, twf['tvt'].to_numpy(float), twf['gr'].to_numpy(float)) if len(twf) else _wb_np.full(len(tvt), _wb_np.nan)
                gr_resid = gr - ref
                recent = min(200, len(known))
                rows.append({
                    '_oof_well': wid,
                    'prefix_rows': float(len(known)),
                    'total_rows': float(len(hw)),
                    'suffix_rows': float(hw['TVT_input'].isna().sum()),
                    'last_tvt': float(tvt[-1]),
                    'last_gr': float(gr[-1]) if _wb_np.isfinite(gr[-1]) else _wb_np.nan,
                    'known_tvt_std': float(_wb_np.nanstd(tvt)),
                    'slope_md_recent': _wb_slope(md[-recent:], tvt[-recent:]),
                    'slope_z_recent': _wb_slope(z[-recent:], tvt[-recent:]),
                    'gr_mean': float(_wb_np.nanmean(gr)),
                    'gr_std': float(_wb_np.nanstd(gr)),
                    'gr_residual_mean': float(_wb_np.nanmean(gr_resid)),
                    'gr_residual_std': float(_wb_np.nanstd(gr_resid)),
                })
            return _wb_pd.DataFrame(rows)

        _wb_train_wells = _wb_gt['well_id'].astype(str).drop_duplicates().to_numpy()
        _wb_train_well_arr = _wb_gt['well_id'].astype(str).to_numpy()
        _wb_train_delta = _wb_smooth(
            _wb_raw_delta, _wb_train_well_arr,
            _wb_gt['row_index'].to_numpy(dtype=int)
        )
        _wb_train_abs = _wb_gt['last_known_TVT'].to_numpy(float) + _wb_train_delta
        _wb_train_rows = _wb_pd.DataFrame({
            '_oof_well': _wb_train_well_arr,
            'artifact_delta': _wb_train_delta,
        })
        _wb_train_stats = _wb_train_rows.groupby('_oof_well', sort=False).agg(
            artifact_delta_mean=('artifact_delta', 'mean'),
            artifact_delta_std=('artifact_delta', 'std'),
            artifact_delta_first=('artifact_delta', 'first'),
            artifact_delta_last=('artifact_delta', 'last'),
            artifact_delta_min=('artifact_delta', 'min'),
            artifact_delta_max=('artifact_delta', 'max'),
        ).reset_index()
        _wb_train_prefix = _wb_prefix(_mp_data_dir, 'train', set(_wb_train_wells))
        _wb_train_features = _wb_pd.DataFrame({'_oof_well': _wb_train_wells}).merge(_wb_train_prefix, on='_oof_well', how='left').merge(_wb_train_stats, on='_oof_well', how='left')
        _wb_labels = _wb_pd.DataFrame({'_oof_well': _wb_train_well_arr, 'residual': _wb_gt['target_tvt'].to_numpy(float) - _wb_train_abs}).groupby('_oof_well', sort=False)['residual'].mean().reindex(_wb_train_wells).to_numpy(float)
        _wb_feature_cols = [c for c in _wb_train_features.columns if c != '_oof_well']
        _wb_model = _wb_pipeline(_WBImputer(strategy='median'), _WBScaler(), _WBRidge(alpha=100.0))
        _wb_model.fit(_wb_train_features[_wb_feature_cols].replace([_wb_np.inf, -_wb_np.inf], _wb_np.nan), _wb_labels)

        _wb_base = _mp_pkg_sub[['id', 'tvt']].copy()
        _wb_base['id'] = _wb_base['id'].astype(str)
        _wb_test_well = _wb_base['id'].str.rsplit('_', n=1).str[0]
        _wb_test_row = _wb_base['id'].str.rsplit('_', n=1).str[-1].astype(int)
        _wb_test_prefix = _wb_prefix(_mp_data_dir, 'test', set(_wb_test_well))
        _wb_last = _wb_test_prefix.set_index('_oof_well')['last_tvt']
        _wb_test_delta = _wb_base['tvt'].to_numpy(float) - _wb_test_well.map(_wb_last).to_numpy(float)
        _wb_test_stats_frame = _wb_pd.DataFrame({'_oof_well': _wb_test_well, 'artifact_delta': _wb_test_delta})
        _wb_test_stats = _wb_test_stats_frame.groupby('_oof_well', sort=False).agg(
            artifact_delta_mean=('artifact_delta', 'mean'),
            artifact_delta_std=('artifact_delta', 'std'),
            artifact_delta_first=('artifact_delta', 'first'),
            artifact_delta_last=('artifact_delta', 'last'),
            artifact_delta_min=('artifact_delta', 'min'),
            artifact_delta_max=('artifact_delta', 'max'),
        ).reset_index()
        _wb_test_features = _wb_pd.DataFrame({'_oof_well': _wb_test_well.drop_duplicates().to_numpy()}).merge(_wb_test_prefix, on='_oof_well', how='left').merge(_wb_test_stats, on='_oof_well', how='left')
        _wb_bias_by_well = dict(zip(_wb_test_features['_oof_well'], _wb_model.predict(_wb_test_features[_wb_feature_cols].replace([_wb_np.inf, -_wb_np.inf], _wb_np.nan))))
        _wb_test_delta = _wb_smooth(_wb_test_delta, _wb_test_well.to_numpy(), _wb_test_row.to_numpy())
        _wb_final = _wb_base.copy()
        _wb_final['tvt'] = _wb_test_well.map(_wb_last).to_numpy(float) + _wb_test_delta + _wb_bias_scale * _wb_test_well.map(_wb_bias_by_well).to_numpy(float)
        if not _wb_np.isfinite(_wb_final['tvt'].to_numpy(float)).all():
            raise RuntimeError('Artifact well-bias correction produced non-finite TVT.')
        _wb_final = _mp_validate_submission_ids(_wb_final, _mp_sample, 'artifact_well_bias_submission')
        _wb_final.to_csv(_mp_work / 'submission_artifact_well_bias.csv', index=False)
        _wb_final.to_csv(_mp_final_output, index=False)
        globals()['FINAL_BASE_SOURCE_LABEL'] = 'artifact_smoothing_well_bias_scale_010'
        globals()['FINAL_ARTIFACT_WELL_BIAS_CORRECTION'] = True
        _wb_pd.Series({
            'train_wells': int(len(_wb_train_wells)),
            'test_wells': int(_wb_test_well.nunique()),
            'test_rows': int(len(_wb_final)),
            'smooth_window': _wb_smooth_window,
            'smooth_poly': _wb_smooth_poly,
            'smooth_alpha': _wb_smooth_alpha,
            'bias_scale': _wb_bias_scale,
            'predicted_bias_mean': float(_wb_np.mean(list(_wb_bias_by_well.values()))),
            'predicted_bias_std': float(_wb_np.std(list(_wb_bias_by_well.values()))),
        }).to_csv(_mp_work / 'artifact_well_bias_correction_summary.csv')
        print('wrote artifact_smoothing_well_bias submission', _wb_final.shape, flush=True)
else:
    print('Artifact well-bias correction disabled.')
'''


def source_text(cell: dict) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def set_source(cell: dict, source: str) -> None:
    cell["source"] = source.splitlines(keepends=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(args: argparse.Namespace) -> None:
    notebook = json.loads(args.source_notebook.read_text(encoding="utf-8"))
    metadata = json.loads(args.source_metadata.read_text(encoding="utf-8"))
    control = next(cell for cell in notebook["cells"] if "SUBMISSION_PROFILE = " in source_text(cell))
    set_source(control, source_text(control) + "\nRUN_ARTIFACT_WELL_BIAS_CORRECTION = True\n")
    modelpkg_index = next(i for i, cell in enumerate(notebook["cells"]) if "Optional saved-model correction" in source_text(cell))
    notebook["cells"].insert(modelpkg_index + 1, {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": BIAS_CELL.splitlines(keepends=True),
    })
    metadata["id"] = args.owner + "/" + args.slug
    metadata["title"] = args.title
    metadata["code_file"] = args.code_file
    metadata["is_private"] = True
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_notebook = args.output_dir / args.code_file
    output_notebook.write_text(json.dumps(notebook, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    metadata_path = args.output_dir / "kernel-metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "source_sha256": sha256(args.source_notebook),
        "output_sha256": sha256(output_notebook),
        "source_cells": len(json.loads(args.source_notebook.read_text(encoding="utf-8"))["cells"]),
        "output_cells": len(notebook["cells"]),
        "inserted_after_source_cell": modelpkg_index,
        "bias_cell_markers": ["RUN_ARTIFACT_WELL_BIAS_CORRECTION", "submission_artifact_well_bias.csv", "bias_scale = 0.10"],
    }
    (args.output_dir / "build_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-notebook", type=Path, required=True)
    parser.add_argument("--source-metadata", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--owner", default="zacky21")
    parser.add_argument("--slug", default="rogii-new-strategy-6-213-artifact-bias")
    parser.add_argument("--title", default="ROGII New Strategy 6.213 Artifact Bias")
    parser.add_argument("--code-file", default="rogii-new-strategy-6-213-artifact-bias.ipynb")
    build(parser.parse_args())


if __name__ == "__main__":
    main()
