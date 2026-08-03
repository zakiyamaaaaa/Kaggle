"""Repeated whole-well cross-fit ensemble for the two-branch meta experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

from well_level_two_branch_meta import (
    bootstrap_well_improvement,
    build_well_table,
    make_models,
    rmse,
)


def parse_ints(value: str) -> tuple[int, ...]:
    return tuple(int(item) for item in value.split(",") if item.strip())


def run(args: argparse.Namespace) -> dict[str, object]:
    gt = pd.read_parquet(args.train_gt, columns=["id", "well_id", "row_index", "last_known_TVT", "target_tvt"])
    sp = pd.read_parquet(args.sp45, columns=["id", "well", "row_idx", "target_tvt", "sp45", "ridge_pp_savgol17", "md_since"])
    if len(gt) != len(sp) or not gt["id"].astype(str).equals(sp["id"].astype(str)):
        raise RuntimeError("train_gt and SP45 cache are not in the same ID order")
    last = gt["last_known_TVT"].to_numpy(float)
    branch = last + np.asarray(np.load(args.branch_oof, mmap_mode="r"), dtype=float)
    hgb = last + np.asarray(np.load(args.hgb_oof, mmap_mode="r"), dtype=float)
    sp["last_known"] = last
    sp["branch"] = branch
    sp["hgb"] = hgb
    sp["well"] = gt["well_id"].astype(str).to_numpy()
    sp["row_idx"] = gt["row_index"].to_numpy(int)
    sp["split"] = "all"
    wells, features, feature_names = build_well_table(sp, branch)
    target = sp["target_tvt"].to_numpy(float)
    sp45 = sp["sp45"].to_numpy(float)
    base = 0.60 * sp45 + 0.40 * branch
    direction = branch - sp45
    codes = pd.Categorical(sp["well"], categories=wells["well"].astype(str)).codes

    oracle = np.zeros(len(wells), float)
    for code in range(len(wells)):
        mask = codes == code
        d = direction[mask]
        oracle[code] = np.clip(np.dot(d, target[mask] - base[mask]) / max(np.dot(d, d), 1e-12), -1.0, 1.0)

    seeds = parse_ints(args.seeds)
    sums = {name: np.zeros(len(wells), float) for name in make_models(args.seed)}
    counts = np.zeros(len(wells), int)
    fold_records: list[dict[str, int]] = []
    for seed in seeds:
        splitter = KFold(n_splits=args.folds, shuffle=True, random_state=seed)
        for fold, (train_idx, valid_idx) in enumerate(splitter.split(features), 1):
            models = make_models(seed + fold * 1000)
            for name, model in models.items():
                model.fit(features[train_idx], oracle[train_idx])
                sums[name][valid_idx] += model.predict(features[valid_idx])
            counts[valid_idx] += 1
            fold_records.append({"seed": seed, "fold": fold, "train_wells": int(len(train_idx)), "valid_wells": int(len(valid_idx))})
    if not np.all(counts == len(seeds)):
        raise RuntimeError("cross-fit predictions are incomplete")

    results: dict[str, object] = {}
    for name, values in sums.items():
        raw = values / counts
        for clip in (0.05, 0.075, 0.10, 0.125, 0.15, 0.20, 0.35):
            shift = np.clip(raw, -clip, clip)
            candidate = base + shift[codes] * direction
            key = f"{name}_clip{clip:g}"
            results[key] = {
                "base_rmse": rmse(target, base),
                "candidate_rmse": rmse(target, candidate),
                "improvement": rmse(target, base) - rmse(target, candidate),
                "shift_mean": float(np.mean(shift)),
                "shift_p95_abs": float(np.quantile(np.abs(shift), 0.95)),
                "bootstrap": bootstrap_well_improvement(sp["well"].to_numpy(), target, base, candidate, args.bootstrap_draws, args.seed + 77),
            }
    best = min(results, key=lambda key: results[key]["candidate_rmse"])
    conservative = [key for key, value in results.items() if value["bootstrap"]["q05"] > 0 and value["shift_p95_abs"] <= 0.15]
    output = {
        "method": "repeated_whole_well_crossfit_two_branch_meta",
        "rows": int(len(sp)),
        "wells": int(len(wells)),
        "features": feature_names,
        "base": "SP45 0.60 + legal package branch 0.40",
        "seeds": list(seeds),
        "folds": int(args.folds),
        "each_validation_well_excluded_from_fit": True,
        "same_well_contact_used": False,
        "public_well_ids_used": False,
        "results": results,
        "best": best,
        "conservative_candidates": conservative,
        "fold_records": fold_records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--sp45", type=Path, required=True)
    parser.add_argument("--branch-oof", type=Path, required=True)
    parser.add_argument("--hgb-oof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", default="20260803,20260804,20260805,20260806,20260807")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument("--bootstrap-draws", type=int, default=10000)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
