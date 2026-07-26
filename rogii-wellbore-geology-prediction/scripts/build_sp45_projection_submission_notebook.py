"""Build the locally selected SP45 projection as a private Kaggle notebook."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


CANDIDATE_CELL = """# Audit and export the locally selected SP45 branch.
import hashlib as _cand_hashlib
import json as _cand_json
import numpy as _cand_np
import pandas as _cand_pd
from pathlib import Path as _CandPath

_cand_work = _CandPath('/kaggle/working')
_cand_source = _cand_work / 'sp45_projection_submission.csv'
_cand_output = _cand_work / 'submission_sp45_ridge030_d2_b050.csv'
_cand_submission = _cand_work / 'submission.csv'
_cand_sample = _CandPath(COMPETITION_DATA_ROOT) / 'sample_submission.csv'

_cand = _cand_pd.read_csv(_cand_source)
_sample = _cand_pd.read_csv(_cand_sample)
if list(_cand.columns) != ['id', 'tvt']:
    raise RuntimeError(f'candidate columns mismatch: {list(_cand.columns)}')
if len(_cand) != len(_sample):
    raise RuntimeError(f'candidate row count mismatch: {len(_cand)} != {len(_sample)}')
if not _cand['id'].astype(str).equals(_sample['id'].astype(str)):
    raise RuntimeError('candidate ID order does not match sample submission')
_values = _cand['tvt'].to_numpy(dtype=float)
if not _cand_np.isfinite(_values).all():
    raise RuntimeError('candidate contains non-finite TVT values')
_cand.to_csv(_cand_output, index=False)
_cand.to_csv(_cand_submission, index=False)

def _cand_sha256(path):
    digest = _cand_hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()

_cand_audit = {
    'candidate': 'public SP45 Ridge 30% + selector 70% + U projection',
    'projection_degree': int(SP45_PROJECTION_DEGREE),
    'projection_blend_weight': float(SP45_PROJECTION_BLEND_WEIGHT),
    'ridge_weight': float(SP45_RIDGE_MODEL_WEIGHT),
    'selector_weight': float(SP45_SELECTOR_WEIGHT),
    'rows': int(len(_cand)),
    'id_order_matches_sample': True,
    'finite_tvt': True,
    'tvt_min': float(_values.min()),
    'tvt_max': float(_values.max()),
    'tvt_mean': float(_values.mean()),
    'tvt_std': float(_values.std()),
    'sha256': _cand_sha256(_cand_output),
    'sha256_submission_csv': _cand_sha256(_cand_submission),
}
(_cand_work / 'submission_sp45_ridge030_d2_b050_audit.json').write_text(
    _cand_json.dumps(_cand_audit, indent=2) + '\\n',
    encoding='utf-8',
)
print('SP45 submission candidate audit:', _cand_audit, flush=True)
"""

FULL_PIPELINE_AUDIT_CELL = """# Audit the full generic-core candidate without replacing submission.csv.
import hashlib as _full_hashlib
import json as _full_json
import numpy as _full_np
import pandas as _full_pd
from pathlib import Path as _FullPath

_full_work = _FullPath('/kaggle/working')
_full_submission = _full_work / 'submission.csv'
_full_audit_copy = _full_work / 'submission_audit_copy.csv'
_full_latest = _full_work / 'latest_valid_submission.csv'
_full_sp45 = _full_work / 'sp45_projection_submission.csv'
_full_sample = _FullPath(COMPETITION_DATA_ROOT) / 'sample_submission.csv'

def _full_sha256(path):
    digest = _full_hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()

for _required_path in (
    _full_submission,
    _full_audit_copy,
    _full_latest,
    _full_sp45,
    _full_sample,
):
    if not _required_path.exists():
        raise RuntimeError(f'missing required output: {_required_path}')

_full = _full_pd.read_csv(_full_submission)
_audit_copy = _full_pd.read_csv(_full_audit_copy)
_latest = _full_pd.read_csv(_full_latest)
_sp45 = _full_pd.read_csv(_full_sp45)
_sample = _full_pd.read_csv(_full_sample)
if list(_full.columns) != ['id', 'tvt']:
    raise RuntimeError(f'full candidate columns mismatch: {list(_full.columns)}')
if len(_full) != len(_sample):
    raise RuntimeError(f'full candidate row count mismatch: {len(_full)} != {len(_sample)}')
if not _full['id'].astype(str).equals(_sample['id'].astype(str)):
    raise RuntimeError('full candidate ID order does not match sample submission')
_full_values = _full['tvt'].to_numpy(dtype=float)
if not _full_np.isfinite(_full_values).all():
    raise RuntimeError('full candidate contains non-finite TVT values')
for _name, _copy in (
    ('submission_audit_copy.csv', _audit_copy),
    ('latest_valid_submission.csv', _latest),
):
    if not _full['id'].astype(str).equals(_copy['id'].astype(str)):
        raise RuntimeError(f'{_name} ID order differs from submission.csv')
    if not _full_np.array_equal(
        _full_values,
        _copy['tvt'].to_numpy(dtype=float),
        equal_nan=False,
    ):
        raise RuntimeError(f'{_name} values differ from submission.csv')

_sp45_values = _sp45['tvt'].to_numpy(dtype=float)
_sp45_rms_difference = float(
    _full_np.sqrt(_full_np.mean((_full_values - _sp45_values) ** 2))
)
if not _sp45_rms_difference > 0.01:
    raise RuntimeError('full candidate unexpectedly matches the SP45-only branch')

_full_audit = {
    'candidate': 'full generic core: SP45 60% + learned 40% + branch hedge',
    'projection_degree': int(SP45_PROJECTION_DEGREE),
    'projection_blend_weight': float(SP45_PROJECTION_BLEND_WEIGHT),
    'sp45_learned_weight': float(SP45_BLEND_WEIGHT),
    'rows': int(len(_full)),
    'id_order_matches_sample': True,
    'finite_tvt': True,
    'matches_submission_audit_copy': True,
    'matches_latest_valid_submission': True,
    'rms_difference_from_sp45_only': _sp45_rms_difference,
    'tvt_min': float(_full_values.min()),
    'tvt_max': float(_full_values.max()),
    'tvt_mean': float(_full_values.mean()),
    'tvt_std': float(_full_values.std()),
    'sha256_submission_csv': _full_sha256(_full_submission),
}
(_full_work / 'submission_full_d2_b050_audit.json').write_text(
    _full_json.dumps(_full_audit, indent=2) + '\\n',
    encoding='utf-8',
)
print('Full generic-core submission audit:', _full_audit, flush=True)
"""


def source_text(cell: dict) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def set_source(cell: dict, value: str) -> None:
    if isinstance(cell.get("source"), list):
        cell["source"] = value.splitlines(keepends=True)
    else:
        cell["source"] = value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args: argparse.Namespace) -> dict[str, object]:
    notebook = json.loads(args.source_notebook.read_text(encoding="utf-8"))
    metadata = json.loads(args.source_metadata.read_text(encoding="utf-8"))
    control_cell = next(
        (
            cell
            for cell in notebook["cells"]
            if cell.get("cell_type") == "code"
            and "SP45_PROJECTION_DEGREE = " in source_text(cell)
        ),
        None,
    )
    if control_cell is None:
        raise RuntimeError("SP45 projection control cell was not found")
    control = source_text(control_cell)
    replacements = {
        "SP45_PROJECTION_DEGREE = 3": "SP45_PROJECTION_DEGREE = 2",
        "SP45_PROJECTION_BLEND_WEIGHT = 0.75": (
            "SP45_PROJECTION_BLEND_WEIGHT = 0.50"
        ),
    }
    for old, new in replacements.items():
        if control.count(old) != 1:
            raise RuntimeError(f"expected one control assignment: {old}")
        control = control.replace(old, new, 1)
    set_source(control_cell, control)

    audit_cell = (
        FULL_PIPELINE_AUDIT_CELL
        if args.submission_mode == "full-pipeline"
        else CANDIDATE_CELL
    )
    notebook["cells"].append(
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": audit_cell.splitlines(keepends=True),
        }
    )
    for index, cell in enumerate(notebook["cells"]):
        if cell.get("cell_type") == "code":
            compile(source_text(cell), f"cell-{index}", "exec")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    notebook_name = f"{args.slug}.ipynb"
    notebook_path = args.output_dir / notebook_name
    metadata_path = args.output_dir / "kernel-metadata.json"
    metadata.pop("id_no", None)
    metadata.update(
        {
            "id": f"{args.owner}/{args.slug}",
            "title": args.title,
            "code_file": notebook_name,
            "is_private": True,
        }
    )
    notebook_path.write_text(
        json.dumps(notebook, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report = {
        "source_notebook": str(args.source_notebook),
        "source_sha256": sha256(args.source_notebook),
        "notebook": str(notebook_path),
        "notebook_sha256": sha256(notebook_path),
        "metadata": str(metadata_path),
        "kaggle_id": metadata["id"],
        "projection_degree": 2,
        "projection_blend_weight": 0.50,
        "ridge_weight": 0.30,
        "selector_weight": 0.70,
        "submission_mode": args.submission_mode,
        "candidate_output": (
            "submission.csv"
            if args.submission_mode == "full-pipeline"
            else "submission_sp45_ridge030_d2_b050.csv"
        ),
        "code_cells_compiled": sum(
            cell.get("cell_type") == "code" for cell in notebook["cells"]
        ),
    }
    (args.output_dir / "build_report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-notebook", type=Path, required=True)
    parser.add_argument("--source-metadata", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--submission-mode",
        choices=("sp45-only", "full-pipeline"),
        default="sp45-only",
    )
    parser.add_argument("--owner", default="zacky21")
    parser.add_argument(
        "--slug",
        default="rogii-sp45-ridge030-projection-d2-b050",
    )
    parser.add_argument(
        "--title",
        default="ROGII SP45 Ridge030 Projection D2 B050",
    )
    run(parser.parse_args())


if __name__ == "__main__":
    main()
