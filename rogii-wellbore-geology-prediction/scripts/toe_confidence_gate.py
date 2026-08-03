"""Leakage-safe toe-only confidence gate around the 7.474-style blend.

The gate uses only target-free disagreement between the SP45 trajectory and a
well-group OOF model-package branch, plus normalized suffix position.  It is
fit in outer well-group folds and is applied only to the last part of each
suffix.  This is intentionally a small, auditable experiment rather than a
new broad meta-model.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd


def rmse(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.sqrt(np.mean((p - y) ** 2)))


def make_features(
    sp45: np.ndarray,
    branch: np.ndarray,
    hgb: np.ndarray,
    suffix_pos: np.ndarray,
) -> np.ndarray:
    branch_gap = branch - sp45
    hgb_gap = hgb - sp45
    return np.column_stack(
        [
            branch_gap,
            hgb_gap,
            suffix_pos,
            suffix_pos**2,
            branch_gap * suffix_pos,
            hgb_gap * suffix_pos,
            np.abs(branch_gap),
            np.abs(hgb_gap),
        ]
    ).astype(np.float64)


def fit_ridge(
    x: np.ndarray,
    y: np.ndarray,
    alpha: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale < 1e-8] = 1.0
    z = (x - mean) / scale
    design = np.column_stack([np.ones(len(z)), z])
    gram = design.T @ design
    penalty = np.eye(gram.shape[0], dtype=float) * float(alpha)
    penalty[0, 0] = 0.0
    coef = np.linalg.solve(gram + penalty, design.T @ y)
    return coef, mean, scale


def predict_ridge(
    x: np.ndarray,
    coef: np.ndarray,
    mean: np.ndarray,
    scale: np.ndarray,
) -> np.ndarray:
    z = (x - mean) / scale
    return coef[0] + z @ coef[1:]


def split_wells(wells: np.ndarray, folds: int, seed: int) -> list[np.ndarray]:
    unique = np.asarray(sorted(set(wells.astype(str))))
    rng = np.random.default_rng(seed)
    unique = unique[rng.permutation(len(unique))]
    return [part for part in np.array_split(unique, folds)]


def bootstrap_improvement(
    frame: pd.DataFrame,
    candidate: np.ndarray,
    baseline: np.ndarray,
    samples: int,
    seed: int,
) -> dict[str, float]:
    frame = frame.copy()
    frame["base_sq"] = (baseline - frame["target_tvt"].to_numpy(float)) ** 2
    frame["cand_sq"] = (candidate - frame["target_tvt"].to_numpy(float)) ** 2
    rows: list[tuple[int, float, float]] = []
    for _, part in frame.groupby("well", sort=True):
        rows.append(
            (
                len(part),
                float(part["base_sq"].sum()),
                float(part["cand_sq"].sum()),
            )
        )
    values = np.asarray(rows, dtype=float)
    rng = np.random.default_rng(seed)
    sampled = values[rng.integers(0, len(values), size=(samples, len(values)))]
    base_scores = np.sqrt(sampled[:, :, 1].sum(axis=1) / sampled[:, :, 0].sum(axis=1))
    cand_scores = np.sqrt(sampled[:, :, 2].sum(axis=1) / sampled[:, :, 0].sum(axis=1))
    improvement = base_scores - cand_scores
    q05, q50, q95 = np.quantile(improvement, [0.05, 0.50, 0.95])
    return {
        "probability_improve": float(np.mean(improvement > 0)),
        "q05": float(q05),
        "median": float(q50),
        "q95": float(q95),
    }


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

    last_known = truth["last_known_TVT"].to_numpy(float)
    y = truth["target_tvt"].to_numpy(float)
    sp45_values = sp45["sp45"].to_numpy(float)
    branch_delta = np.asarray(np.load(args.branch_oof, mmap_mode="r"), dtype=float)
    hgb_delta = np.asarray(np.load(args.hgb_oof, mmap_mode="r"), dtype=float)
    if branch_delta.shape != (len(truth),) or hgb_delta.shape != (len(truth),):
        raise RuntimeError("OOF arrays do not match train_gt row count")
    branch = last_known + branch_delta
    hgb = last_known + hgb_delta
    wells = truth["well_id"].astype(str).to_numpy()
    suffix_max = sp45.groupby("well", sort=False)["md_since"].transform("max").to_numpy(float)
    suffix_pos = np.clip(sp45["md_since"].to_numpy(float) / np.maximum(suffix_max, 1.0), 0.0, 1.0)
    base = 0.60 * sp45_values + 0.40 * branch
    features = make_features(sp45_values, branch, hgb, suffix_pos)

    fold_parts = split_wells(wells, args.folds, args.seed)
    valid_fold = np.full(len(truth), -1, dtype=int)
    for fold, valid_wells in enumerate(fold_parts):
        valid_fold[np.isin(wells, valid_wells)] = fold
    if (valid_fold < 0).any():
        raise RuntimeError("some wells were not assigned to a fold")

    candidate_specs = [
        (float(cut), float(shrink))
        for cut in args.cutoff
        for shrink in args.shrink
    ]
    candidate_predictions = {
        (cut, shrink): base.copy() for cut, shrink in candidate_specs
    }
    fold_records: list[dict[str, object]] = []
    for fold in range(args.folds):
        train_mask = valid_fold != fold
        valid_mask = valid_fold == fold
        train_toe = train_mask & (suffix_pos >= args.fit_cutoff)
        if int(train_toe.sum()) < 100:
            raise RuntimeError(f"fold {fold}: too few toe rows")
        coef, feature_mean, feature_scale = fit_ridge(
            features[train_toe],
            (y - base)[train_toe],
            args.alpha,
        )
        correction = predict_ridge(
            features[valid_mask], coef, feature_mean, feature_scale
        )
        correction = np.clip(correction, -args.max_move, args.max_move)
        valid_positions = np.flatnonzero(valid_mask)
        for cut, shrink in candidate_specs:
            apply = suffix_pos[valid_positions] >= cut
            values = candidate_predictions[(cut, shrink)][valid_positions].copy()
            values[apply] += shrink * correction[apply]
            candidate_predictions[(cut, shrink)][valid_positions] = values
        fold_records.append(
            {
                "fold": fold,
                "train_wells": int(train_mask.sum()),
                "valid_wells": int(valid_mask.sum()),
                "train_toe_rows": int(train_toe.sum()),
                "correction_p50": float(np.quantile(correction, 0.50)),
                "correction_p95_abs": float(np.quantile(np.abs(correction), 0.95)),
                "correction_max_abs": float(np.max(np.abs(correction))),
            }
        )

    work = pd.DataFrame(
        {
            "well": wells,
            "target_tvt": y,
            "suffix_pos": suffix_pos,
            "base": base,
        }
    )
    base_rmse = rmse(y, base)
    toe_mask = suffix_pos >= args.report_cutoff
    records: list[dict[str, object]] = []
    for cut, shrink in candidate_specs:
        prediction = candidate_predictions[(cut, shrink)]
        record = {
            "cutoff": cut,
            "shrink": shrink,
            "base_rmse": base_rmse,
            "candidate_rmse": rmse(y, prediction),
            "improvement": base_rmse - rmse(y, prediction),
            "base_toe_rmse": rmse(y[toe_mask], base[toe_mask]),
            "candidate_toe_rmse": rmse(y[toe_mask], prediction[toe_mask]),
            "toe_improvement": rmse(y[toe_mask], base[toe_mask]) - rmse(y[toe_mask], prediction[toe_mask]),
            "max_move": float(np.max(np.abs(prediction - base))),
            "p95_move": float(np.quantile(np.abs(prediction - base), 0.95)),
            "bootstrap": bootstrap_improvement(
                work,
                prediction,
                base,
                args.bootstrap_samples,
                args.seed + int(cut * 1000) + int(shrink * 100),
            ),
        }
        records.append(record)

    records.sort(key=lambda item: float(item["candidate_rmse"]))
    output = {
        "method": "toe_only_continuous_confidence_gate",
        "base": "SP45 0.60 + legal package postprocessed OOF branch 0.40",
        "rows": int(len(truth)),
        "wells": int(len(set(wells))),
        "folds": int(args.folds),
        "alpha": float(args.alpha),
        "fit_cutoff": float(args.fit_cutoff),
        "report_cutoff": float(args.report_cutoff),
        "max_move": float(args.max_move),
        "candidate_records": records,
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
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument("--alpha", type=float, default=3.0)
    parser.add_argument("--fit-cutoff", type=float, default=0.60)
    parser.add_argument("--report-cutoff", type=float, default=0.60)
    parser.add_argument("--cutoff", type=float, nargs="+", default=[0.60, 0.70, 0.80])
    parser.add_argument("--shrink", type=float, nargs="+", default=[0.25, 0.50, 1.00])
    parser.add_argument("--max-move", type=float, default=1.50)
    parser.add_argument("--bootstrap-samples", type=int, default=50000)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
