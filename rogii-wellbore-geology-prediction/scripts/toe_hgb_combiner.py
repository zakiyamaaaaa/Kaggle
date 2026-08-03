"""Group-OOF HGB combiner for the target-free toe disagreement experiment."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor


def rmse(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.sqrt(np.mean((p - y) ** 2)))


def bootstrap(
    wells: np.ndarray,
    y: np.ndarray,
    base: np.ndarray,
    cand: np.ndarray,
    samples: int,
    seed: int,
) -> dict[str, float]:
    rows = []
    for well in np.unique(wells):
        mask = wells == well
        rows.append(
            (
                int(mask.sum()),
                float(np.sum((base[mask] - y[mask]) ** 2)),
                float(np.sum((cand[mask] - y[mask]) ** 2)),
            )
        )
    values = np.asarray(rows, dtype=float)
    rng = np.random.default_rng(seed)
    sample = values[rng.integers(0, len(values), size=(samples, len(values)))]
    base_score = np.sqrt(sample[:, :, 1].sum(axis=1) / sample[:, :, 0].sum(axis=1))
    cand_score = np.sqrt(sample[:, :, 2].sum(axis=1) / sample[:, :, 0].sum(axis=1))
    delta = base_score - cand_score
    q05, q50, q95 = np.quantile(delta, [0.05, 0.50, 0.95])
    return {
        "probability_improve": float(np.mean(delta > 0)),
        "q05": float(q05),
        "median": float(q50),
        "q95": float(q95),
    }


def split_wells(wells: np.ndarray, folds: int, seed: int) -> np.ndarray:
    unique = np.asarray(sorted(set(wells.astype(str))))
    rng = np.random.default_rng(seed)
    unique = unique[rng.permutation(len(unique))]
    fold_map = {}
    for fold, part in enumerate(np.array_split(unique, folds)):
        fold_map.update({well: fold for well in part})
    return np.asarray([fold_map[well] for well in wells], dtype=int)


def make_features(
    sp45: np.ndarray,
    branch: np.ndarray,
    hgb: np.ndarray,
    position: np.ndarray,
    md_since: np.ndarray,
    row_idx: np.ndarray,
) -> np.ndarray:
    gap_branch = branch - sp45
    gap_hgb = hgb - sp45
    md_scale = np.nanpercentile(md_since, 95)
    row_scale = np.nanpercentile(row_idx, 95)
    return np.column_stack(
        [
            gap_branch,
            gap_hgb,
            np.abs(gap_branch),
            np.abs(gap_hgb),
            position,
            position**2,
            gap_branch * position,
            gap_hgb * position,
            md_since / max(md_scale, 1.0),
            row_idx / max(row_scale, 1.0),
        ]
    ).astype(np.float32)


def sample_training_rows(
    wells: np.ndarray,
    train_mask: np.ndarray,
    max_per_well: int,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    selected = []
    for well in np.unique(wells[train_mask]):
        indices = np.flatnonzero(train_mask & (wells == well))
        if len(indices) <= max_per_well:
            selected.append(indices)
        else:
            selected.append(np.sort(rng.choice(indices, max_per_well, replace=False)))
    return np.concatenate(selected)


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    truth = pd.read_parquet(
        args.train_gt,
        columns=["id", "well_id", "last_known_TVT", "target_tvt"],
    )
    sp45 = pd.read_parquet(
        args.sp45,
        columns=["id", "well", "row_idx", "sp45", "md_since"],
    )
    if len(truth) != len(sp45) or not np.array_equal(
        truth["id"].astype(str).to_numpy(), sp45["id"].astype(str).to_numpy()
    ):
        raise RuntimeError("truth and SP45 IDs are not exactly aligned")
    n = len(truth)
    last = truth["last_known_TVT"].to_numpy(float)
    y = truth["target_tvt"].to_numpy(float)
    sp = sp45["sp45"].to_numpy(float)
    branch = last + np.asarray(np.load(args.branch_oof, mmap_mode="r"), dtype=float)
    hgb_oof = last + np.asarray(np.load(args.hgb_oof, mmap_mode="r"), dtype=float)
    wells = truth["well_id"].astype(str).to_numpy()
    md_since = sp45["md_since"].to_numpy(float)
    row_idx = sp45["row_idx"].to_numpy(float)
    suffix_max = sp45.groupby("well", sort=False)["md_since"].transform("max").to_numpy(float)
    position = np.clip(md_since / np.maximum(suffix_max, 1.0), 0.0, 1.0)
    base = 0.60 * sp + 0.40 * branch
    features = make_features(sp, branch, hgb_oof, position, md_since, row_idx)
    folds = split_wells(wells, args.folds, args.seed)
    correction = np.zeros(n, dtype=float)
    fold_records = []
    for fold in range(args.folds):
        train_mask = folds != fold
        valid_mask = folds == fold
        sample = sample_training_rows(wells, train_mask, args.max_rows_per_well, args.seed + fold)
        model = HistGradientBoostingRegressor(
            max_iter=args.max_iter,
            learning_rate=args.learning_rate,
            max_leaf_nodes=args.max_leaf_nodes,
            min_samples_leaf=args.min_samples_leaf,
            l2_regularization=args.l2,
            random_state=args.seed + fold,
        )
        model.fit(features[sample], (y - base)[sample])
        correction[valid_mask] = model.predict(features[valid_mask])
        fold_records.append(
            {
                "fold": fold,
                "train_wells": int(train_mask.sum()),
                "valid_wells": int(valid_mask.sum()),
                "sample_rows": int(len(sample)),
                "valid_rmse_base": rmse(y[valid_mask], base[valid_mask]),
                "valid_rmse_raw": rmse(y[valid_mask], base[valid_mask] + correction[valid_mask]),
            }
        )
        print(json.dumps(fold_records[-1]), flush=True)

    candidate_records = []
    toe_mask = position >= args.toe_report_cutoff
    for cutoff in args.cutoff:
        for clip in args.clip:
            raw = np.clip(correction, -clip, clip)
            pred = base.copy()
            pred[position >= cutoff] += raw[position >= cutoff]
            candidate_records.append(
                {
                    "cutoff": float(cutoff),
                    "clip": float(clip),
                    "base_rmse": rmse(y, base),
                    "candidate_rmse": rmse(y, pred),
                    "improvement": rmse(y, base) - rmse(y, pred),
                    "base_toe_rmse": rmse(y[toe_mask], base[toe_mask]),
                    "candidate_toe_rmse": rmse(y[toe_mask], pred[toe_mask]),
                    "toe_improvement": rmse(y[toe_mask], base[toe_mask]) - rmse(y[toe_mask], pred[toe_mask]),
                    "max_move": float(np.max(np.abs(pred - base))),
                    "p95_move": float(np.quantile(np.abs(pred - base), 0.95)),
                    "bootstrap": bootstrap(wells, y, base, pred, args.bootstrap_samples, args.seed + int(cutoff * 100) + int(clip * 10)),
                }
            )
    candidate_records.sort(key=lambda item: float(item["candidate_rmse"]))
    result = {
        "method": "toe_only_hgb_disagreement_combiner",
        "base": "SP45 0.60 + legal package postprocessed OOF branch 0.40",
        "rows": int(n),
        "wells": int(len(set(wells))),
        "folds": int(args.folds),
        "max_rows_per_well": int(args.max_rows_per_well),
        "candidate_records": candidate_records,
        "fold_records": fold_records,
        "leakage_controls": {
            "outer_split_is_well_grouped": True,
            "target_used_only_in_fold_fit": True,
            "features_use_target": False,
            "same_well_contact_used": False,
            "public_well_ids_used": False,
        },
        "elapsed_sec": float(time.perf_counter() - started),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--sp45", type=Path, required=True)
    parser.add_argument("--branch-oof", type=Path, required=True)
    parser.add_argument("--hgb-oof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument("--max-rows-per-well", type=int, default=500)
    parser.add_argument("--max-iter", type=int, default=250)
    parser.add_argument("--learning-rate", type=float, default=0.04)
    parser.add_argument("--max-leaf-nodes", type=int, default=31)
    parser.add_argument("--min-samples-leaf", type=int, default=100)
    parser.add_argument("--l2", type=float, default=10.0)
    parser.add_argument("--toe-report-cutoff", type=float, default=0.60)
    parser.add_argument("--cutoff", type=float, nargs="+", default=[0.60, 0.70, 0.80])
    parser.add_argument("--clip", type=float, nargs="+", default=[0.50, 1.00, 1.50])
    parser.add_argument("--bootstrap-samples", type=int, default=50000)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
