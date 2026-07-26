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

    notebook["cells"].append(
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": CANDIDATE_CELL.splitlines(keepends=True),
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
        "candidate_output": "submission_sp45_ridge030_d2_b050.csv",
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
