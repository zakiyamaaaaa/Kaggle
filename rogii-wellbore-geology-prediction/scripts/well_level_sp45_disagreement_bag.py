"""Field-free nested well-level bagging of generic-core trajectories.

Each well receives one target-free feature vector made only from deployable
trajectory candidates and their disagreement.  The training label is the
bounded SP45 blend-weight shift that minimizes aggregate SSE across four legal
OOF proxies.  Ridge regularization, prediction shrinkage, and the maximum
weight move are selected inside each outer training fold.  Outer validation
wells are therefore excluded from both fitting and hyperparameter selection.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


PROXY_COLUMNS = {
    "exact_public": "exact_7474_proxy",
    "artifact": "public_s060_cap200_artifact",
    "hgb": "public_s060_cap200_hgb",
    "ridge": "public_s060_cap200_ridge",
}
SPLITS = ("discovery", "holdout1", "holdout2")


def rmse(target: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(target - prediction))))


def parse_floats(value: str) -> np.ndarray:
    return np.asarray([float(part) for part in value.split(",")], float)


def parse_ints(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(","))


def trajectory_channels(part: pd.DataFrame) -> dict[str, np.ndarray]:
    exact = part["exact_7474_proxy"].to_numpy(float)
    public = part["public_s060_cap200_artifact"].to_numpy(float)
    family = part[
        [
            "reduced_s040_cap100_artifact",
            "reduced_s060_cap100_artifact",
            "public_s060_cap200_artifact",
            "strong_s080_cap200_artifact",
            "extended_s060_cap300_artifact",
        ]
    ].to_numpy(float)
    return {
        "md_since": part["md_since"].to_numpy(float),
        "selector_from_last": part["selector_raw"].to_numpy(float)
        - part["last_known_tvt"].to_numpy(float),
        "ridge_from_last": part["ridge_pp"].to_numpy(float)
        - part["last_known_tvt"].to_numpy(float),
        "pf_from_selector": part["pf_ancc_recomputed"].to_numpy(float)
        - part["selector_raw"].to_numpy(float),
        "sp45_from_last": part["sp45_sgridge_d2_b050"].to_numpy(float)
        - part["last_known_tvt"].to_numpy(float),
        "exact_from_last": exact - part["last_known_tvt"].to_numpy(float),
        "sp45_minus_exact": part["sp45_sgridge_d2_b050"].to_numpy(float)
        - exact,
        "public_minus_exact": public - exact,
        "family_disagreement": np.std(family, axis=1),
        "family_range": np.max(family, axis=1) - np.min(family, axis=1),
        "sp45_projection_delta": part["sp45_sgridge_d2_b050"].to_numpy(float)
        - part["sp45_sgridge_raw"].to_numpy(float),
    }


def summarize_channel(values: np.ndarray) -> list[float]:
    values = np.asarray(values, float)
    finite = np.isfinite(values)
    if finite.sum() < 2:
        return [np.nan] * 11
    values = values[finite]
    axis = np.linspace(-1.0, 1.0, len(values))
    degree = min(3, len(values) - 1)
    coefficients = np.polynomial.legendre.legfit(axis, values, degree)
    coefficients = np.pad(coefficients, (0, 4 - len(coefficients)), constant_values=np.nan)
    return [
        float(np.mean(values)),
        float(np.std(values)),
        float(np.quantile(values, 0.10)),
        float(np.quantile(values, 0.50)),
        float(np.quantile(values, 0.90)),
        float(values[-1] - values[0]),
        float(np.mean(np.abs(values))),
        *[float(value) for value in coefficients],
    ]


def build_well_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    records: list[dict[str, object]] = []
    vectors: list[list[float]] = []
    channel_names: list[str] | None = None
    summary_names = (
        "mean",
        "std",
        "p10",
        "p50",
        "p90",
        "end_minus_start",
        "mean_abs",
        "leg0",
        "leg1",
        "leg2",
        "leg3",
    )
    for well, part in frame.groupby("well", sort=True):
        part = part.sort_values("row_idx")
        channels = trajectory_channels(part)
        if channel_names is None:
            channel_names = [
                f"{channel}_{stat}"
                for channel in channels
                for stat in summary_names
            ]
        vector = [float(len(part))]
        vector.extend(
            [value for channel in channels.values() for value in summarize_channel(channel)]
        )
        records.append(
            {
                "well": str(well),
                "rows": int(len(part)),
                "validation_split": str(part["validation_split"].iloc[0]),
            }
        )
        vectors.append(vector)
    feature_names = ["rows", *(channel_names or [])]
    return pd.DataFrame(records), np.asarray(vectors, float), feature_names


def make_proxy_paths(
    frame: pd.DataFrame, incumbent_weight: float
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    sp45 = frame["sp45_sgridge_d2_b050"].to_numpy(float)
    hedge = (
        frame["public_s060_cap200_artifact"].to_numpy(float)
        - frame["base_artifact"].to_numpy(float)
    )
    baselines = {
        name: frame[column].to_numpy(float)
        for name, column in PROXY_COLUMNS.items()
    }
    no_hedge = {
        "exact_public": baselines["exact_public"] - hedge,
        "artifact": frame["base_artifact"].to_numpy(float),
        "hgb": frame["base_hgb"].to_numpy(float),
        "ridge": frame["base_ridge"].to_numpy(float),
    }
    learned = {
        name: (base - incumbent_weight * sp45) / (1.0 - incumbent_weight)
        for name, base in no_hedge.items()
    }
    directions = {name: sp45 - value for name, value in learned.items()}
    return baselines, directions


def oracle_weight_shifts(
    frame: pd.DataFrame,
    target: np.ndarray,
    baselines: dict[str, np.ndarray],
    directions: dict[str, np.ndarray],
    bound: float,
) -> tuple[np.ndarray, dict[str, object]]:
    labels = []
    per_proxy: dict[str, list[float]] = {name: [] for name in baselines}
    for _, part in frame.groupby("well", sort=True):
        idx = part.index.to_numpy(int)
        numerator = 0.0
        denominator = 0.0
        for name in baselines:
            direction = directions[name][idx]
            residual = target[idx] - baselines[name][idx]
            numerator += float(np.dot(direction, residual))
            denominator += float(np.dot(direction, direction))
            local_denominator = float(np.dot(direction, direction))
            local = (
                float(np.dot(direction, residual)) / local_denominator
                if local_denominator > 1e-12
                else 0.0
            )
            per_proxy[name].append(float(np.clip(local, -bound, bound)))
        labels.append(float(np.clip(numerator / max(denominator, 1e-12), -bound, bound)))
    array = np.asarray(labels, float)
    return array, {
        "aggregate": {
            "mean": float(np.mean(array)),
            "std": float(np.std(array)),
            "p10": float(np.quantile(array, 0.10)),
            "p50": float(np.quantile(array, 0.50)),
            "p90": float(np.quantile(array, 0.90)),
            "at_lower_bound": int(np.sum(array <= -bound + 1e-12)),
            "at_upper_bound": int(np.sum(array >= bound - 1e-12)),
        },
        "per_proxy_correlation": {
            name: float(np.corrcoef(array, np.asarray(values))[0, 1])
            for name, values in per_proxy.items()
        },
    }


def row_masks(frame: pd.DataFrame, wells: pd.Series) -> list[np.ndarray]:
    lookup = pd.Series(np.arange(len(wells)), index=wells.astype(str))
    positions = frame["well"].astype(str).map(lookup)
    if positions.isna().any():
        raise RuntimeError("well feature rows do not cover candidate cache")
    mapped = positions.to_numpy(int)
    return [mapped == position for position in range(len(wells))]


def evaluate_shift(
    target: np.ndarray,
    baselines: dict[str, np.ndarray],
    directions: dict[str, np.ndarray],
    row_shift: np.ndarray,
    mask: np.ndarray,
) -> tuple[float, float, dict[str, float]]:
    improvements = {
        name: rmse(target[mask], baseline[mask])
        - rmse(target[mask], (baseline + row_shift * directions[name])[mask])
        for name, baseline in baselines.items()
    }
    return min(improvements.values()), float(np.mean(list(improvements.values()))), improvements


def build_well_sufficient_statistics(
    target: np.ndarray,
    baselines: dict[str, np.ndarray],
    directions: dict[str, np.ndarray],
    well_rows: list[np.ndarray],
) -> dict[str, np.ndarray]:
    """Compress row losses so nested hyperparameter selection stays cheap."""
    rows = np.asarray([int(mask.sum()) for mask in well_rows], float)
    statistics: dict[str, np.ndarray] = {"rows": rows}
    for name, baseline in baselines.items():
        residual = target - baseline
        direction = directions[name]
        statistics[f"{name}_base_sse"] = np.asarray(
            [float(np.dot(residual[mask], residual[mask])) for mask in well_rows]
        )
        statistics[f"{name}_cross"] = np.asarray(
            [float(np.dot(residual[mask], direction[mask])) for mask in well_rows]
        )
        statistics[f"{name}_direction_sse"] = np.asarray(
            [float(np.dot(direction[mask], direction[mask])) for mask in well_rows]
        )
    return statistics


def evaluate_well_shifts(
    statistics: dict[str, np.ndarray],
    baselines: dict[str, np.ndarray],
    well_shift: np.ndarray,
    selected_wells: np.ndarray,
) -> tuple[float, float, dict[str, float]]:
    count = float(statistics["rows"][selected_wells].sum())
    shift = well_shift[selected_wells]
    improvements = {}
    for name in baselines:
        base_sse = statistics[f"{name}_base_sse"][selected_wells]
        cross = statistics[f"{name}_cross"][selected_wells]
        direction_sse = statistics[f"{name}_direction_sse"][selected_wells]
        candidate_sse = base_sse - 2.0 * shift * cross + np.square(shift) * direction_sse
        improvements[name] = float(
            np.sqrt(base_sse.sum() / count) - np.sqrt(candidate_sse.sum() / count)
        )
    return min(improvements.values()), float(np.mean(list(improvements.values()))), improvements


def select_global_shift(
    statistics: dict[str, np.ndarray],
    baselines: dict[str, np.ndarray],
    selected_wells: np.ndarray,
    grid: np.ndarray,
) -> float:
    best_key = None
    best_shift = 0.0
    for shift in grid:
        well_shift = np.full(len(statistics["rows"]), float(shift))
        minimum, mean, _ = evaluate_well_shifts(
            statistics, baselines, well_shift, selected_wells
        )
        key = (minimum, mean, -abs(float(shift)))
        if best_key is None or key > best_key:
            best_key = key
            best_shift = float(shift)
    return best_shift


def select_inner_hyperparameters(
    frame: pd.DataFrame,
    target: np.ndarray,
    features: np.ndarray,
    labels: np.ndarray,
    well_rows: list[np.ndarray],
    baselines: dict[str, np.ndarray],
    directions: dict[str, np.ndarray],
    statistics: dict[str, np.ndarray],
    train_wells: np.ndarray,
    seed: int,
    folds: int,
    alphas: np.ndarray,
    shrinks: np.ndarray,
    clips: np.ndarray,
    global_grid: np.ndarray,
) -> tuple[dict[str, float], dict[str, object]]:
    splitter = KFold(n_splits=folds, shuffle=True, random_state=seed)
    inner_splits = list(splitter.split(train_wells))
    inner_global = np.full(len(features), np.nan)
    for inner_train_rel, inner_valid_rel in inner_splits:
        inner_train = train_wells[inner_train_rel]
        inner_valid = train_wells[inner_valid_rel]
        inner_global[inner_valid] = select_global_shift(
            statistics, baselines, inner_train, global_grid
        )
    candidates: list[tuple[tuple[float, float, float, float], dict[str, float], dict[str, float]]] = []
    for alpha in alphas:
        inner_raw = np.full(len(features), np.nan)
        for inner_train_rel, inner_valid_rel in inner_splits:
            inner_train = train_wells[inner_train_rel]
            inner_valid = train_wells[inner_valid_rel]
            model = make_pipeline(
                SimpleImputer(strategy="median"),
                StandardScaler(),
                Ridge(alpha=float(alpha)),
            )
            model.fit(features[inner_train], labels[inner_train])
            inner_raw[inner_valid] = model.predict(features[inner_valid])
        for shrink in shrinks:
            for clip in clips:
                well_shift = np.clip(
                    inner_global + float(shrink) * (inner_raw - inner_global),
                    -float(clip),
                    float(clip),
                )
                minimum, mean, improvements = evaluate_well_shifts(
                    statistics, baselines, well_shift, train_wells
                )
                params = {"alpha": float(alpha), "shrink": float(shrink), "clip": float(clip)}
                key = (minimum, mean, -float(np.nanmean(np.abs(well_shift[train_wells]))), -float(clip))
                candidates.append((key, params, improvements))
    key, params, improvements = max(candidates, key=lambda item: item[0])
    return params, {
        "minimum_proxy_improvement": float(key[0]),
        "mean_proxy_improvement": float(key[1]),
        "proxy_improvements": improvements,
    }


def paired_well_bootstrap(
    frame: pd.DataFrame,
    target: np.ndarray,
    baseline: np.ndarray,
    candidate: np.ndarray,
    draws: int,
    seed: int,
) -> dict[str, float | int]:
    local = pd.DataFrame(
        {
            "well": frame["well"].astype(str),
            "rows": 1,
            "baseline_se": np.square(target - baseline),
            "candidate_se": np.square(target - candidate),
        }
    ).groupby("well", sort=True).agg(
        rows=("rows", "sum"),
        baseline_sse=("baseline_se", "sum"),
        candidate_sse=("candidate_se", "sum"),
    )
    rng = np.random.default_rng(seed)
    rows = local["rows"].to_numpy(float)
    baseline_sse = local["baseline_sse"].to_numpy(float)
    candidate_sse = local["candidate_sse"].to_numpy(float)
    values = np.empty(draws, float)
    for draw in range(draws):
        sampled = rng.integers(0, len(local), len(local))
        count = rows[sampled].sum()
        values[draw] = np.sqrt(baseline_sse[sampled].sum() / count) - np.sqrt(
            candidate_sse[sampled].sum() / count
        )
    return {
        "draws": int(draws),
        "probability_positive": float(np.mean(values > 0.0)),
        "p01": float(np.quantile(values, 0.01)),
        "p05": float(np.quantile(values, 0.05)),
        "p50": float(np.quantile(values, 0.50)),
        "p95": float(np.quantile(values, 0.95)),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    frame = pd.read_parquet(args.candidate_cache).reset_index(drop=True)
    target = frame["target_tvt"].to_numpy(float)
    baselines, directions = make_proxy_paths(frame, args.incumbent_weight)
    wells, features, feature_names = build_well_features(frame)
    labels, oracle_report = oracle_weight_shifts(
        frame, target, baselines, directions, args.label_bound
    )
    well_rows = row_masks(frame, wells["well"])
    statistics = build_well_sufficient_statistics(
        target, baselines, directions, well_rows
    )
    alphas = parse_floats(args.alphas)
    shrinks = parse_floats(args.shrinks)
    clips = parse_floats(args.clips)
    global_grid = parse_floats(args.global_shifts)
    seeds = parse_ints(args.seeds)
    seed_well_shifts = []
    seed_reports = []
    selections = []

    for seed in seeds:
        splitter = KFold(n_splits=args.outer_folds, shuffle=True, random_state=seed)
        predicted = np.zeros(len(wells), float)
        for fold, (train_wells, valid_wells) in enumerate(splitter.split(wells), 1):
            params, inner_report = select_inner_hyperparameters(
                frame,
                target,
                features,
                labels,
                well_rows,
                baselines,
                directions,
                statistics,
                train_wells,
                seed + fold * 101,
                args.inner_folds,
                alphas,
                shrinks,
                clips,
                global_grid,
            )
            model = make_pipeline(
                SimpleImputer(strategy="median"),
                StandardScaler(),
                Ridge(alpha=params["alpha"]),
            )
            model.fit(features[train_wells], labels[train_wells])
            raw = model.predict(features[valid_wells])
            global_shift = select_global_shift(
                statistics, baselines, train_wells, global_grid
            )
            predicted[valid_wells] = np.clip(
                global_shift + params["shrink"] * (raw - global_shift),
                -params["clip"],
                params["clip"],
            )
            selections.append(
                {
                    "seed": int(seed),
                    "fold": int(fold),
                    "train_wells": int(len(train_wells)),
                    "validation_wells": int(len(valid_wells)),
                    **params,
                    "fit_outer_train_global_shift": float(global_shift),
                    **inner_report,
                }
            )
        row_shift = np.zeros(len(frame), float)
        for position in range(len(wells)):
            row_shift[well_rows[position]] = predicted[position]
        minimum, mean, improvements = evaluate_shift(
            target,
            baselines,
            directions,
            row_shift,
            np.ones(len(frame), bool),
        )
        seed_reports.append(
            {
                "seed": int(seed),
                "minimum_proxy_improvement": minimum,
                "mean_proxy_improvement": mean,
                "proxy_improvements": improvements,
                "shift_mean": float(np.mean(predicted)),
                "shift_std": float(np.std(predicted)),
                "shift_p95_abs": float(np.quantile(np.abs(predicted), 0.95)),
            }
        )
        seed_well_shifts.append(predicted)

    ensemble_well_shift = np.mean(seed_well_shifts, axis=0)
    ensemble_row_shift = np.zeros(len(frame), float)
    for position in range(len(wells)):
        ensemble_row_shift[well_rows[position]] = ensemble_well_shift[position]

    proxy_results = {}
    for name, baseline in baselines.items():
        candidate = baseline + ensemble_row_shift * directions[name]
        baseline_score = rmse(target, baseline)
        candidate_score = rmse(target, candidate)
        split_results = {}
        for split in (*SPLITS, "all"):
            mask = (
                np.ones(len(frame), bool)
                if split == "all"
                else frame["validation_split"].eq(split).to_numpy()
            )
            split_results[split] = {
                "rows": int(mask.sum()),
                "wells": int(frame.loc[mask, "well"].nunique()),
                "baseline_rmse": rmse(target[mask], baseline[mask]),
                "candidate_rmse": rmse(target[mask], candidate[mask]),
                "improvement": rmse(target[mask], baseline[mask])
                - rmse(target[mask], candidate[mask]),
            }
        proxy_results[name] = {
            "baseline_rmse": baseline_score,
            "candidate_rmse": candidate_score,
            "improvement": baseline_score - candidate_score,
            "splits": split_results,
        }

    exact_candidate = (
        baselines["exact_public"]
        + ensemble_row_shift * directions["exact_public"]
    )
    bootstrap = paired_well_bootstrap(
        frame,
        target,
        baselines["exact_public"],
        exact_candidate,
        args.bootstrap_draws,
        args.bootstrap_seed,
    )
    exact_improvement = proxy_results["exact_public"]["improvement"]
    promotion = {
        "all_proxies_improve": bool(
            all(result["improvement"] > 0.0 for result in proxy_results.values())
        ),
        "all_exact_legacy_splits_improve": bool(
            all(
                proxy_results["exact_public"]["splits"][split]["improvement"] > 0.0
                for split in SPLITS
            )
        ),
        "all_seeds_minimum_proxy_improve": bool(
            min(result["minimum_proxy_improvement"] for result in seed_reports) > 0.0
        ),
        "bootstrap_p05_positive": bool(bootstrap["p05"] > 0.0),
        "effect_gate_ft": float(args.effect_gate),
        "passes_effect_gate": bool(exact_improvement >= args.effect_gate),
    }
    promotion["passes_local_gate"] = bool(all(promotion.values()))
    output = {
        "method": "nested_field_free_well_level_sp45_disagreement_bag",
        "wells": int(len(wells)),
        "rows": int(len(frame)),
        "features": feature_names,
        "feature_count": int(features.shape[1]),
        "incumbent_sp45_weight": float(args.incumbent_weight),
        "label_bound": float(args.label_bound),
        "oracle_weight_shift": oracle_report,
        "contracts": {
            "outer_validation_well_excluded_from_model_fit": True,
            "outer_validation_well_excluded_from_hyperparameter_selection": True,
            "features_are_target_free_trajectory_disagreement": True,
            "field_and_xy_features_excluded": True,
            "selection_uses_four_legal_oof_proxies": True,
            "same_branch_hedge_preserved": True,
        },
        "hyperparameter_grid": {
            "alphas": alphas.tolist(),
            "shrinks": shrinks.tolist(),
            "clips": clips.tolist(),
            "global_shifts": global_grid.tolist(),
        },
        "seed_reports": seed_reports,
        "selection_records": selections,
        "ensemble_shift": {
            "mean": float(np.mean(ensemble_well_shift)),
            "std": float(np.std(ensemble_well_shift)),
            "minimum": float(np.min(ensemble_well_shift)),
            "maximum": float(np.max(ensemble_well_shift)),
            "p50_abs": float(np.quantile(np.abs(ensemble_well_shift), 0.50)),
            "p95_abs": float(np.quantile(np.abs(ensemble_well_shift), 0.95)),
        },
        "proxy_results": proxy_results,
        "bootstrap": bootstrap,
        "promotion": promotion,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "oracle": oracle_report,
                "ensemble_shift": output["ensemble_shift"],
                "proxy_results": proxy_results,
                "bootstrap": bootstrap,
                "promotion": promotion,
            },
            indent=2,
        )
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--outer-folds", type=int, default=5)
    parser.add_argument("--inner-folds", type=int, default=4)
    parser.add_argument(
        "--seeds", default="20260811,20260812,20260813,20260814,20260815"
    )
    parser.add_argument("--alphas", default="10,30,100,300,1000")
    parser.add_argument("--shrinks", default="0,0.25,0.5,0.75,1")
    parser.add_argument("--clips", default="0.025,0.05,0.075,0.10")
    parser.add_argument(
        "--global-shifts",
        default="-0.10,-0.08,-0.06,-0.04,-0.02,0,0.02,0.04,0.06,0.08,0.10",
    )
    parser.add_argument("--incumbent-weight", type=float, default=0.60)
    parser.add_argument("--label-bound", type=float, default=0.10)
    parser.add_argument("--bootstrap-draws", type=int, default=50000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260816)
    parser.add_argument("--effect-gate", type=float, default=0.03)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
