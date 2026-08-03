"""Whole-well meta model for the legal SP45/package two-branch blend.

The row-level toe combiner was rejected because it learned noisy local moves.
This experiment compresses target-free branch disagreement into one vector per
well, predicts a bounded shift of the SP45/package blend, and evaluates it with
well-grouped outer OOF.  No suffix TVT, same-well contact, or public-well ID is
used as a feature.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def rmse(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(np.asarray(y, float) - np.asarray(p, float)))))


def summary(values: np.ndarray) -> list[float]:
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return [np.nan] * 10
    axis = np.linspace(-1.0, 1.0, len(values))
    degree = min(3, len(values) - 1)
    coeff = np.polynomial.legendre.legfit(axis, values, degree)
    coeff = np.pad(coeff, (0, 4 - len(coeff)), constant_values=np.nan)
    return [
        float(np.mean(values)),
        float(np.std(values)),
        float(np.quantile(values, 0.10)),
        float(np.quantile(values, 0.25)),
        float(np.quantile(values, 0.50)),
        float(np.quantile(values, 0.75)),
        float(np.quantile(values, 0.90)),
        float(values[-1] - values[0]),
        *[float(x) for x in coeff[:2]],
    ]


def build_well_table(frame: pd.DataFrame, branch: np.ndarray) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    frame = frame.copy()
    frame["branch"] = branch
    frame["sp_gap"] = frame["branch"] - frame["sp45"]
    frame["hgb_gap"] = frame["hgb"] - frame["sp45"]
    records: list[dict[str, object]] = []
    vectors: list[list[float]] = []
    names: list[str] | None = None
    for well, part in frame.groupby("well", sort=True):
        part = part.sort_values("row_idx")
        n = len(part)
        pos = part["md_since"].to_numpy(float)
        frac = pos / max(float(np.nanmax(pos)), 1.0)
        channels = {
            "sp_gap": part["sp_gap"].to_numpy(float),
            "hgb_gap": part["hgb_gap"].to_numpy(float),
            "branch_minus_last": part["branch"].to_numpy(float) - part["last_known"].to_numpy(float),
            "sp_minus_last": part["sp45"].to_numpy(float) - part["last_known"].to_numpy(float),
            "frac": frac,
        }
        stats = [float(n), float(np.nanmax(pos)), float(np.nanmean(pos)), float(np.nanstd(pos))]
        channel_names = [
            "mean", "std", "p10", "p25", "p50", "p75", "p90", "end_minus_start", "leg0", "leg1"
        ]
        for channel, values in channels.items():
            if names is None:
                names = [f"{channel}_{stat}" for channel in channels for stat in channel_names]
            stats.extend(summary(values))
        records.append({"well": str(well), "rows": n, "split": str(part["split"].iloc[0])})
        vectors.append(stats)
    return pd.DataFrame(records), np.asarray(vectors, float), ["rows", "md_max", "md_mean", "md_std", *(names or [])]


def make_models(seed: int) -> dict[str, object]:
    return {
        "ridge": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=30.0)),
        "extra_trees": make_pipeline(
            SimpleImputer(strategy="median"),
            ExtraTreesRegressor(
                n_estimators=400,
                min_samples_leaf=12,
                max_features=0.65,
                random_state=seed,
                n_jobs=-1,
            ),
        ),
        "hgb": make_pipeline(
            SimpleImputer(strategy="median"),
            HistGradientBoostingRegressor(
                max_iter=160,
                learning_rate=0.035,
                max_leaf_nodes=9,
                min_samples_leaf=25,
                l2_regularization=20.0,
                random_state=seed,
            ),
        ),
    }


def bootstrap_well_improvement(
    wells: np.ndarray,
    y: np.ndarray,
    base: np.ndarray,
    candidate: np.ndarray,
    draws: int,
    seed: int,
) -> dict[str, float | int]:
    work = pd.DataFrame({"well": wells, "base": (y - base) ** 2, "candidate": (y - candidate) ** 2})
    grouped = work.groupby("well", sort=True).sum()
    rng = np.random.default_rng(seed)
    values = np.empty(draws, float)
    for i in range(draws):
        sample = rng.integers(0, len(grouped), len(grouped))
        values[i] = np.sqrt(grouped.iloc[sample]["base"].sum() / len(y)) - np.sqrt(
            grouped.iloc[sample]["candidate"].sum() / len(y)
        )
    return {
        "draws": int(draws),
        "probability_improve": float(np.mean(values > 0)),
        "q05": float(np.quantile(values, 0.05)),
        "median": float(np.quantile(values, 0.50)),
        "q95": float(np.quantile(values, 0.95)),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    gt = pd.read_parquet(args.train_gt, columns=["id", "well_id", "row_index", "last_known_TVT", "target_tvt"])
    sp = pd.read_parquet(args.sp45, columns=["id", "well", "row_idx", "target_tvt", "sp45", "ridge_pp_savgol17", "md_since"])
    sp = sp.rename(columns={"sp45": "sp45"})
    if len(gt) != len(sp) or not gt["id"].astype(str).equals(sp["id"].astype(str)):
        raise RuntimeError("train_gt and SP45 cache are not in the same ID order")
    branch_delta = np.asarray(np.load(args.branch_oof, mmap_mode="r"), dtype=float)
    hgb_delta = np.asarray(np.load(args.hgb_oof, mmap_mode="r"), dtype=float)
    if len(branch_delta) != len(gt) or len(hgb_delta) != len(gt):
        raise RuntimeError("OOF array lengths do not match train_gt")
    last = gt["last_known_TVT"].to_numpy(float)
    sp["last_known"] = last
    sp["branch"] = last + branch_delta
    sp["hgb"] = last + hgb_delta
    sp["well"] = gt["well_id"].astype(str).to_numpy()
    sp["row_idx"] = gt["row_index"].to_numpy(int)
    sp["split"] = "all"
    frame = sp
    wells, features, feature_names = build_well_table(frame, branch_delta * 0 + frame["branch"].to_numpy(float))
    target = frame["target_tvt"].to_numpy(float)
    sp45 = frame["sp45"].to_numpy(float)
    branch_abs = frame["branch"].to_numpy(float)
    base = 0.60 * sp45 + 0.40 * branch_abs
    direction = branch_abs - sp45
    well_codes = pd.Categorical(frame["well"], categories=wells["well"].astype(str)).codes
    oracle = np.zeros(len(wells), float)
    for code in range(len(wells)):
        mask = well_codes == code
        d = direction[mask]
        r = target[mask] - base[mask]
        oracle[code] = np.clip(np.dot(d, r) / max(np.dot(d, d), 1e-12), -1.0, 1.0)
    codes = well_codes
    model_predictions: dict[str, np.ndarray] = {}
    split = KFold(n_splits=5, shuffle=True, random_state=args.seed)
    for name in make_models(args.seed):
        predictions = np.full(len(wells), np.nan, float)
        for fold, (train_idx, valid_idx) in enumerate(split.split(features), 1):
            model = make_models(args.seed + fold * 100)[name]
            model.fit(features[train_idx], oracle[train_idx])
            predictions[valid_idx] = model.predict(features[valid_idx])
        model_predictions[name] = predictions

    results: dict[str, object] = {}
    for name, raw in model_predictions.items():
        for clip in (0.10, 0.20, 0.35, 0.50, 1.00):
            shift = np.clip(raw, -clip, clip)
            row_shift = shift[codes]
            candidate = base + row_shift * direction
            key = f"{name}_clip{clip:g}"
            results[key] = {
                "base_rmse": rmse(target, base),
                "candidate_rmse": rmse(target, candidate),
                "improvement": rmse(target, base) - rmse(target, candidate),
                "base_toe_rmse": rmse(target[frame["md_since"].to_numpy(float) / frame.groupby("well")["md_since"].transform("max").to_numpy(float) >= 0.60], base[frame["md_since"].to_numpy(float) / frame.groupby("well")["md_since"].transform("max").to_numpy(float) >= 0.60]),
                "candidate_toe_rmse": rmse(target[frame["md_since"].to_numpy(float) / frame.groupby("well")["md_since"].transform("max").to_numpy(float) >= 0.60], candidate[frame["md_since"].to_numpy(float) / frame.groupby("well")["md_since"].transform("max").to_numpy(float) >= 0.60]),
                "shift_mean": float(np.mean(shift)),
                "shift_p95_abs": float(np.quantile(np.abs(shift), 0.95)),
                "bootstrap": bootstrap_well_improvement(frame["well"].to_numpy(), target, base, candidate, args.bootstrap_draws, args.seed + 99),
            }
    best = min(results, key=lambda k: results[k]["candidate_rmse"])
    output = {
        "method": "well_level_two_branch_meta",
        "rows": int(len(frame)),
        "wells": int(len(wells)),
        "features": feature_names,
        "base": "SP45 0.60 + legal package branch 0.40",
        "outer_split": "5-fold shuffled whole-well OOF",
        "oracle_label_only_for_fold_fit": True,
        "same_well_contact_used": False,
        "public_well_ids_used": False,
        "oracle_shift": {"mean": float(np.mean(oracle)), "std": float(np.std(oracle)), "p10": float(np.quantile(oracle, .10)), "p50": float(np.quantile(oracle, .50)), "p90": float(np.quantile(oracle, .90))},
        "results": results,
        "best": best,
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
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument("--bootstrap-draws", type=int, default=10000)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
