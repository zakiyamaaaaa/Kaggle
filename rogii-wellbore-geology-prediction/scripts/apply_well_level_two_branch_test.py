"""Apply the whole-well two-branch meta correction to an existing test CSV.

This is an audit generator only.  It consumes the already-produced 7.474
generic-core components and adds a bounded, fit-all target-free well shift.
It does not submit to Kaggle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

from well_level_two_branch_meta import build_well_table, make_models


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_ids(ids: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    values = ids.astype(str).to_numpy()
    wells = np.asarray([value.rsplit("_", 1)[0] for value in values], dtype=str)
    row_idx = np.asarray([int(value.rsplit("_", 1)[1]) for value in values], dtype=int)
    return wells, row_idx


def build_test_frame(
    submission: pd.DataFrame,
    sp45: pd.DataFrame,
    branch: pd.DataFrame,
    hgb: pd.DataFrame,
    data_root: Path,
) -> pd.DataFrame:
    wells, row_idx = parse_ids(submission["id"])
    frame = pd.DataFrame({"id": submission["id"].astype(str), "well": wells, "row_idx": row_idx})
    frame["sp45"] = sp45["tvt"].to_numpy(float)
    frame["branch"] = branch["tvt"].to_numpy(float)
    frame["hgb"] = hgb["tvt"].to_numpy(float)
    last_known = np.empty(len(frame), float)
    md_since = np.empty(len(frame), float)
    for well, positions in frame.groupby("well", sort=False).groups.items():
        horizontal = pd.read_csv(data_root / "test" / f"{well}__horizontal_well.csv")
        tvt_input = pd.to_numeric(horizontal["TVT_input"], errors="coerce").to_numpy(float)
        md = pd.to_numeric(horizontal["MD"], errors="coerce").to_numpy(float)
        known = np.flatnonzero(np.isfinite(tvt_input))
        if len(known) == 0:
            raise RuntimeError(f"{well}: no visible TVT_input prefix")
        last_value = float(tvt_input[known[-1]])
        last_md = float(md[known[-1]])
        local_rows = frame.loc[positions, "row_idx"].to_numpy(int)
        if np.any(local_rows < 0) or np.any(local_rows >= len(horizontal)):
            raise RuntimeError(f"{well}: sample row index is outside horizontal file")
        last_known[positions] = last_value
        md_since[positions] = md[local_rows] - last_md
    frame["last_known"] = last_known
    frame["md_since"] = md_since
    frame["target_tvt"] = np.nan
    frame["split"] = "test"
    return frame


def run(args: argparse.Namespace) -> dict[str, object]:
    gt = pd.read_parquet(args.train_gt, columns=["id", "well_id", "row_index", "last_known_TVT", "target_tvt"])
    train = pd.read_parquet(args.sp45, columns=["id", "well", "row_idx", "target_tvt", "sp45", "ridge_pp_savgol17", "md_since"])
    if len(gt) != len(train) or not gt["id"].astype(str).equals(train["id"].astype(str)):
        raise RuntimeError("training ID order mismatch")
    last = gt["last_known_TVT"].to_numpy(float)
    branch_delta = np.asarray(np.load(args.branch_oof, mmap_mode="r"), dtype=float)
    hgb_delta = np.asarray(np.load(args.hgb_oof, mmap_mode="r"), dtype=float)
    train["last_known"] = last
    train["branch"] = last + branch_delta
    train["hgb"] = last + hgb_delta
    train["well"] = gt["well_id"].astype(str).to_numpy()
    train["row_idx"] = gt["row_index"].to_numpy(int)
    train["split"] = "all"
    train_wells, train_features, feature_names = build_well_table(train, train["branch"].to_numpy(float))
    target = train["target_tvt"].to_numpy(float)
    sp = train["sp45"].to_numpy(float)
    branch = train["branch"].to_numpy(float)
    base = 0.60 * sp + 0.40 * branch
    direction = branch - sp
    codes = pd.Categorical(train["well"], categories=train_wells["well"].astype(str)).codes
    oracle = np.zeros(len(train_wells), float)
    for code in range(len(train_wells)):
        mask = codes == code
        d = direction[mask]
        oracle[code] = np.clip(np.dot(d, target[mask] - base[mask]) / max(np.dot(d, d), 1e-12), -1.0, 1.0)

    test_submission = pd.read_csv(args.base_submission)
    test_sp = pd.read_csv(args.sp45_submission)
    test_branch = pd.read_csv(args.branch_submission)
    test_hgb = pd.read_csv(args.hgb_submission)
    for name, part in {"sp45": test_sp, "branch": test_branch, "hgb": test_hgb}.items():
        if not test_submission["id"].astype(str).equals(part["id"].astype(str)):
            raise RuntimeError(f"{name} test IDs do not match base submission")
    test = build_test_frame(test_submission, test_sp, test_branch, test_hgb, args.data_root)
    test_wells, test_features, _ = build_well_table(test, test["branch"].to_numpy(float))

    predictions = []
    for seed in args.seeds:
        models = make_models(seed)
        for name in ("ridge",):
            model = models[name]
            model.fit(train_features, oracle)
            predictions.append(model.predict(test_features))
    raw_shift = np.mean(predictions, axis=0)
    shift = np.clip(raw_shift, -args.clip, args.clip)
    test_codes = pd.Categorical(test["well"], categories=train_wells["well"].astype(str)).codes
    if np.any(test_codes < 0):
        raise RuntimeError("test well is not represented in training meta feature categories")
    test_base = test_submission["tvt"].to_numpy(float)
    test_direction = test["branch"].to_numpy(float) - test["sp45"].to_numpy(float)
    candidate = test_base + shift[test_codes] * test_direction
    output_submission = pd.DataFrame({"id": test_submission["id"].astype(str), "tvt": candidate})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_submission.to_csv(args.output, index=False)
    report_rows = []
    for well in test_wells["well"].astype(str):
        mask = test["well"].to_numpy() == well
        code = int(pd.Index(train_wells["well"].astype(str)).get_loc(well))
        report_rows.append({
            "well": well,
            "rows": int(mask.sum()),
            "raw_shift": float(raw_shift[code]),
            "bounded_shift": float(shift[code]),
            "direction_mean": float(np.mean(test_direction[mask])),
            "correction_mean": float(np.mean(shift[code] * test_direction[mask])),
            "correction_p95_abs": float(np.quantile(np.abs(shift[code] * test_direction[mask]), 0.95)),
        })
    report = {
        "method": "fit_all_whole_well_ridge_two_branch_meta_test_audit",
        "base_submission": str(args.base_submission),
        "output_submission": str(args.output),
        "base_sha256": sha256(args.base_submission),
        "output_sha256": sha256(args.output),
        "train_wells": int(len(train_wells)),
        "test_wells": int(test["well"].nunique()),
        "clip": float(args.clip),
        "fit_all_target_free_test_features": True,
        "same_well_contact_used": False,
        "public_well_id_used": False,
        "correction_mean": float(np.mean(candidate - test_base)),
        "correction_p95_abs": float(np.quantile(np.abs(candidate - test_base), 0.95)),
        "correction_max_abs": float(np.max(np.abs(candidate - test_base))),
        "wells": report_rows,
        "feature_count": int(len(feature_names)),
        "note": "public test audit only; no Kaggle submission was performed",
    }
    report_path = args.report or args.output.with_suffix(".json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--sp45", type=Path, required=True)
    parser.add_argument("--branch-oof", type=Path, required=True)
    parser.add_argument("--hgb-oof", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--base-submission", type=Path, required=True)
    parser.add_argument("--sp45-submission", type=Path, required=True)
    parser.add_argument("--branch-submission", type=Path, required=True)
    parser.add_argument("--hgb-submission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--clip", type=float, default=0.15)
    parser.add_argument("--seeds", type=int, nargs="+", default=[20260803, 20260804, 20260805, 20260806, 20260807])
    run(parser.parse_args())


if __name__ == "__main__":
    main()
