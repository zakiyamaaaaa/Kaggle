"""Evaluate a learned OOF branch on wells excluded from meta-model selection.

Feature-set selection and Ridge fitting use only non-evaluation wells.  The
selected branch is then connected to cached target-free SP45 predictions for
the excluded wells, preserving the submitted 60/40 blend structure.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold

from learned_branch_meta_oof import (
    PACKAGE_FILES,
    PUBLIC_ARTIFACTS,
    RIDGE_PARAMS,
    VARIANTS,
    load_array,
    rmse,
)


def load_wells(paths: list[Path]) -> set[str]:
    wells: set[str] = set()
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        current = set(map(str, record["sampled_wells"]))
        if wells & current:
            raise RuntimeError(f"evaluation well summaries overlap: {path}")
        wells |= current
    return wells


def load_inputs(
    args: argparse.Namespace,
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    truth = pd.read_parquet(
        args.train_gt,
        columns=[
            "id",
            "well_id",
            "row_index",
            "last_known_TVT",
            "target_tvt",
            "target_delta_from_last_known",
        ],
    )
    rows = len(truth)
    arrays: dict[str, np.ndarray] = {}
    for index, name in enumerate(PUBLIC_ARTIFACTS):
        arrays[f"public_{index}"] = load_array(
            args.public_oof_dir / name, rows
        )
    for feature, name in PACKAGE_FILES.items():
        arrays[feature] = load_array(args.package_oof_dir / name, rows)
    local = pd.read_csv(
        args.local_oof, usecols=["_oof_id", "hgb_oof_tvt"]
    )
    if len(local) != rows or not np.array_equal(
        local["_oof_id"].astype(str).to_numpy(),
        truth["id"].astype(str).to_numpy(),
    ):
        raise RuntimeError("local HGB OOF IDs do not align with train_gt")
    arrays["local_hgb"] = (
        local["hgb_oof_tvt"].to_numpy(np.float32)
        - truth["last_known_TVT"].to_numpy(np.float32)
    )
    return truth, arrays


def inner_score(
    matrix: np.ndarray,
    target: np.ndarray,
    groups: np.ndarray,
    folds: int,
) -> tuple[float, list[float]]:
    prediction = np.full(len(target), np.nan, dtype=np.float32)
    records = []
    splitter = GroupKFold(n_splits=folds)
    for train_index, valid_index in splitter.split(
        matrix, target, groups=groups
    ):
        model = Ridge(**RIDGE_PARAMS)
        model.fit(matrix[train_index], target[train_index])
        prediction[valid_index] = model.predict(matrix[valid_index])
        records.append(rmse(target[valid_index], prediction[valid_index]))
    if not np.isfinite(prediction).all():
        raise RuntimeError("inner OOF is incomplete")
    return rmse(target, prediction), records


def smooth_by_well(
    frame: pd.DataFrame,
    values: np.ndarray,
    window: int,
    polynomial: int = 3,
) -> np.ndarray:
    output = values.copy()
    for _, part in frame.groupby("well", sort=False):
        positions = part.index.to_numpy(int)
        local_window = min(window, len(positions))
        if local_window % 2 == 0:
            local_window -= 1
        if local_window >= polynomial + 2:
            output[positions] = savgol_filter(
                values[positions], local_window, polynomial
            )
    return output


def metric(
    target: np.ndarray,
    prediction: np.ndarray,
    wells: np.ndarray,
) -> dict[str, float]:
    work = pd.DataFrame(
        {
            "well": wells,
            "square_error": (prediction - target) ** 2,
        }
    )
    per_well = np.sqrt(work.groupby("well")["square_error"].mean())
    return {
        "rmse": rmse(target, prediction),
        "well_rmse_p50": float(per_well.quantile(0.50)),
        "well_rmse_p90": float(per_well.quantile(0.90)),
    }


def bootstrap_improvement(
    frame: pd.DataFrame,
    baseline: str,
    candidate: str,
    samples: int,
    seed: int,
) -> dict[str, float]:
    rows = []
    for _, part in frame.groupby("well", sort=True):
        target = part["target_tvt"].to_numpy(float)
        rows.append(
            (
                len(part),
                float(np.sum((part[baseline].to_numpy(float) - target) ** 2)),
                float(np.sum((part[candidate].to_numpy(float) - target) ** 2)),
            )
        )
    values = np.asarray(rows, dtype=float)
    rng = np.random.default_rng(seed)
    improvements = np.empty(samples, dtype=float)
    for index in range(samples):
        sampled = values[rng.integers(0, len(values), len(values))]
        baseline_rmse = np.sqrt(sampled[:, 1].sum() / sampled[:, 0].sum())
        candidate_rmse = np.sqrt(sampled[:, 2].sum() / sampled[:, 0].sum())
        improvements[index] = baseline_rmse - candidate_rmse
    quantiles = np.quantile(improvements, [0.05, 0.50, 0.95])
    return {
        "probability_improve": float(np.mean(improvements > 0)),
        "q05": float(quantiles[0]),
        "median": float(quantiles[1]),
        "q95": float(quantiles[2]),
    }


def well_win_count(
    frame: pd.DataFrame,
    baseline: str,
    candidate: str,
) -> dict[str, int]:
    wins = 0
    losses = 0
    ties = 0
    for _, part in frame.groupby("well", sort=True):
        target = part["target_tvt"].to_numpy(float)
        baseline_rmse = rmse(target, part[baseline].to_numpy(float))
        candidate_rmse = rmse(target, part[candidate].to_numpy(float))
        if candidate_rmse < baseline_rmse:
            wins += 1
        elif candidate_rmse > baseline_rmse:
            losses += 1
        else:
            ties += 1
    return {"wins": wins, "losses": losses, "ties": ties}


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    evaluation_wells = load_wells(args.evaluation_summary)
    truth, arrays = load_inputs(args)
    is_evaluation = truth["well_id"].astype(str).isin(evaluation_wells)
    if int(is_evaluation.sum()) == 0:
        raise RuntimeError("no evaluation rows selected")
    train = truth.loc[~is_evaluation].reset_index(drop=True)
    evaluation = truth.loc[is_evaluation].reset_index(drop=True)
    train_positions = np.flatnonzero(~is_evaluation.to_numpy())
    evaluation_positions = np.flatnonzero(is_evaluation.to_numpy())
    train_target = train["target_delta_from_last_known"].to_numpy(np.float32)
    train_groups = train["well_id"].astype(str).to_numpy()

    selection_records: dict[str, object] = {}
    for variant, features in VARIANTS.items():
        matrix = np.column_stack(
            [arrays[name][train_positions] for name in features]
        )
        score, fold_scores = inner_score(
            matrix, train_target, train_groups, args.inner_folds
        )
        selection_records[variant] = {
            "features": list(features),
            "inner_oof_rmse": score,
            "fold_rmse": fold_scores,
        }
        print(
            json.dumps({"variant": variant, "inner_oof_rmse": score}),
            flush=True,
        )
        del matrix
    selected_variant = min(
        selection_records,
        key=lambda name: selection_records[name]["inner_oof_rmse"],
    )
    selected_features = VARIANTS[selected_variant]
    train_matrix = np.column_stack(
        [arrays[name][train_positions] for name in selected_features]
    )
    evaluation_matrix = np.column_stack(
        [arrays[name][evaluation_positions] for name in selected_features]
    )
    model = Ridge(**RIDGE_PARAMS)
    model.fit(train_matrix, train_target)
    evaluation_delta = model.predict(evaluation_matrix)
    evaluation["learned_meta_tvt"] = (
        evaluation["last_known_TVT"].to_numpy(float) + evaluation_delta
    )

    caches = [pd.read_parquet(path) for path in args.sp45_cache]
    sp45 = (
        pd.concat(caches, ignore_index=True)
        .drop_duplicates("id", keep="first")
        .reset_index(drop=True)
    )
    sp45["well"] = sp45["well"].astype(str)
    sp45 = sp45[sp45["well"].isin(evaluation_wells)].copy()
    required = {
        "id",
        "well",
        "target_tvt",
        "sp45_sgridge_d2_b050",
        "ridge_pp_savgol17",
    }
    if not required.issubset(sp45.columns):
        raise RuntimeError(f"SP45 cache missing {sorted(required - set(sp45))}")
    package_post = arrays["package_postprocessed"][evaluation_positions]
    learned = evaluation[["id", "learned_meta_tvt"]].copy()
    learned["artifact_tvt"] = (
        evaluation["last_known_TVT"].to_numpy(float) + package_post
    )
    frame = sp45.merge(learned, on="id", how="inner", validate="one_to_one")
    if len(frame) != len(sp45) or len(frame) != len(evaluation):
        raise RuntimeError(
            "SP45 and learned evaluation IDs do not match exactly"
        )
    frame = frame.sort_values(["well", "row_idx"]).reset_index(drop=True)
    frame["learned_meta_smooth"] = smooth_by_well(
        frame,
        frame["learned_meta_tvt"].to_numpy(float),
        args.smooth_window,
    )
    sp45_values = frame["sp45_sgridge_d2_b050"].to_numpy(float)
    frame["artifact_proxy_full"] = (
        args.sp45_weight * sp45_values
        + (1.0 - args.sp45_weight) * frame["artifact_tvt"].to_numpy(float)
    )
    frame["ridge_proxy_full"] = (
        args.sp45_weight * sp45_values
        + (1.0 - args.sp45_weight)
        * frame["ridge_pp_savgol17"].to_numpy(float)
    )
    frame["learned_meta_full_raw"] = (
        args.sp45_weight * sp45_values
        + (1.0 - args.sp45_weight)
        * frame["learned_meta_tvt"].to_numpy(float)
    )
    frame["learned_meta_full_smooth"] = (
        args.sp45_weight * sp45_values
        + (1.0 - args.sp45_weight)
        * frame["learned_meta_smooth"].to_numpy(float)
    )

    prediction_columns = [
        "artifact_proxy_full",
        "ridge_proxy_full",
        "learned_meta_full_raw",
        "learned_meta_full_smooth",
    ]
    target = frame["target_tvt"].to_numpy(float)
    wells = frame["well"].to_numpy()
    metrics: dict[str, object] = {
        "all": {
            name: metric(target, frame[name].to_numpy(float), wells)
            for name in prediction_columns
        }
    }
    branch_metrics: dict[str, object] = {
        "all": {
            name: metric(target, frame[name].to_numpy(float), wells)
            for name in [
                "artifact_tvt",
                "learned_meta_tvt",
                "learned_meta_smooth",
            ]
        }
    }
    split_map = {}
    for path in args.evaluation_summary:
        record = json.loads(path.read_text(encoding="utf-8"))
        label = path.stem
        for well in record["sampled_wells"]:
            split_map[str(well)] = label
    frame["evaluation_split"] = frame["well"].map(split_map)
    for split, part in frame.groupby("evaluation_split", sort=True):
        metrics[str(split)] = {
            name: metric(
                part["target_tvt"].to_numpy(float),
                part[name].to_numpy(float),
                part["well"].to_numpy(),
            )
            for name in prediction_columns
        }
        branch_metrics[str(split)] = {
            name: metric(
                part["target_tvt"].to_numpy(float),
                part[name].to_numpy(float),
                part["well"].to_numpy(),
            )
            for name in [
                "artifact_tvt",
                "learned_meta_tvt",
                "learned_meta_smooth",
            ]
        }
    bootstrap = bootstrap_improvement(
        frame,
        "artifact_proxy_full",
        "learned_meta_full_smooth",
        args.bootstrap_samples,
        args.seed,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.output, index=False)
    summary = {
        "method": "independent_well_learned_branch_meta_selection",
        "train_wells": int(train["well_id"].nunique()),
        "evaluation_wells": int(frame["well"].nunique()),
        "evaluation_rows": int(len(frame)),
        "inner_folds": int(args.inner_folds),
        "selection_records": selection_records,
        "selected_variant": selected_variant,
        "selected_features": list(selected_features),
        "fit_all_coef": [float(value) for value in model.coef_],
        "fit_all_intercept": float(model.intercept_),
        "sp45_weight": float(args.sp45_weight),
        "smooth_window": int(args.smooth_window),
        "metrics": metrics,
        "branch_metrics": branch_metrics,
        "full_blend_improvement_vs_artifact": float(
            metrics["all"]["artifact_proxy_full"]["rmse"]
            - metrics["all"]["learned_meta_full_smooth"]["rmse"]
        ),
        "well_wins_vs_artifact": well_win_count(
            frame,
            "artifact_proxy_full",
            "learned_meta_full_smooth",
        ),
        "bootstrap_vs_artifact_proxy": bootstrap,
        "leakage_controls": {
            "evaluation_wells_excluded_from_feature_selection": True,
            "evaluation_wells_excluded_from_meta_fit": True,
            "all_base_predictions_are_well_group_oof": True,
            "same_well_contact_used": False,
            "public_well_ids_used": False,
        },
        "output": str(args.output),
        "elapsed_sec": float(time.perf_counter() - started),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--public-oof-dir", type=Path, required=True)
    parser.add_argument("--package-oof-dir", type=Path, required=True)
    parser.add_argument("--local-oof", type=Path, required=True)
    parser.add_argument(
        "--evaluation-summary", type=Path, action="append", required=True
    )
    parser.add_argument(
        "--sp45-cache", type=Path, action="append", required=True
    )
    parser.add_argument("--inner-folds", type=int, default=5)
    parser.add_argument("--sp45-weight", type=float, default=0.60)
    parser.add_argument("--smooth-window", type=int, default=61)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
