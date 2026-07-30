"""Predict an entire suffix residual curve from one target-free well sample.

The model is trained on the 573 wells outside the fixed 200-well validation
contract.  Each well becomes one feature vector made from its visible prefix,
full horizontal trajectory/GR, paired typewell, and legal artifact trajectory.
The target is a six-coefficient Legendre representation of the artifact
residual curve.  Model/curve features are selected by 5-fold whole-well OOF;
only the final bounded transfer scale is selected on the 50 discovery wells.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from lightgbm import LGBMRegressor
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.impute import SimpleImputer
from sklearn.model_selection import KFold
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import make_pipeline


PROXIES = {
    "artifact": "public_s060_cap200_artifact",
    "hgb": "public_s060_cap200_hgb",
    "ridge": "public_s060_cap200_ridge",
}
BASE_MODEL_NAMES = ("extra_trees", "catboost", "lightgbm")
MODEL_NAMES = (*BASE_MODEL_NAMES, "mean_tree", "mean_all")


def rmse(target: np.ndarray, prediction: np.ndarray) -> float:
    error = np.asarray(target, float) - np.asarray(prediction, float)
    return float(np.sqrt(np.mean(np.square(error))))


def legendre_coefficients(values: np.ndarray, degree: int) -> np.ndarray:
    values = np.asarray(values, float)
    finite = np.isfinite(values)
    if finite.sum() < 3:
        return np.full(degree + 1, np.nan)
    if not finite.all():
        positions = np.arange(len(values))
        values = np.interp(positions, positions[finite], values[finite])
    axis = np.linspace(-1.0, 1.0, len(values))
    return np.polynomial.legendre.legfit(axis, values, degree)


def safe_scale(values: np.ndarray, fallback: float = 1.0) -> float:
    value = float(np.nanstd(values))
    return value if np.isfinite(value) and value > 1e-6 else fallback


def build_well_features(
    horizontal: pd.DataFrame,
    typewell: pd.DataFrame,
    row_indices: np.ndarray,
    artifact_tvt: np.ndarray,
    sequence_degree: int,
) -> np.ndarray:
    """Build features without reading horizontal TVT in the hidden suffix."""
    row_indices = np.asarray(row_indices, int)
    artifact_tvt = np.asarray(artifact_tvt, float)
    known = horizontal["TVT_input"].notna().to_numpy()
    prefix = horizontal.loc[known]
    if len(prefix) < 3:
        raise RuntimeError("visible TVT_input prefix is too short")

    md = pd.to_numeric(horizontal["MD"], errors="coerce").to_numpy(float)[row_indices]
    x = pd.to_numeric(horizontal["X"], errors="coerce").to_numpy(float)[row_indices]
    y = pd.to_numeric(horizontal["Y"], errors="coerce").to_numpy(float)[row_indices]
    z = pd.to_numeric(horizontal["Z"], errors="coerce").to_numpy(float)[row_indices]
    gr = pd.to_numeric(horizontal["GR"], errors="coerce").to_numpy(float)[row_indices]

    tw = (
        typewell[["TVT", "GR"]]
        .apply(pd.to_numeric, errors="coerce")
        .dropna()
        .groupby("TVT", as_index=False)["GR"]
        .median()
        .sort_values("TVT")
    )
    if len(tw) < 3:
        reference_gr = np.full(len(artifact_tvt), np.nan)
    else:
        reference_gr = np.interp(
            artifact_tvt,
            tw["TVT"].to_numpy(float),
            tw["GR"].to_numpy(float),
        )

    prefix_gr = pd.to_numeric(prefix["GR"], errors="coerce").to_numpy(float)
    gr_center = float(np.nanmedian(prefix_gr))
    gr_scale = safe_scale(prefix_gr, fallback=20.0)
    gr_normalized = (gr - gr_center) / gr_scale
    reference_normalized = (reference_gr - gr_center) / gr_scale

    suffix_channels = [
        (md - md[0]) / max(float(md[-1] - md[0]), 1.0),
        (x - x[0]) / 1000.0,
        (y - y[0]) / 1000.0,
        (z - z[0]) / 100.0,
        (artifact_tvt - artifact_tvt[0]) / 20.0,
        (artifact_tvt + z - (artifact_tvt[0] + z[0])) / 20.0,
        gr_normalized,
        reference_normalized,
        gr_normalized - reference_normalized,
    ]
    features: list[float] = []
    for channel in suffix_channels:
        features.extend(legendre_coefficients(channel, sequence_degree))

    prefix_md = pd.to_numeric(prefix["MD"], errors="coerce").to_numpy(float)
    prefix_x = pd.to_numeric(prefix["X"], errors="coerce").to_numpy(float)
    prefix_y = pd.to_numeric(prefix["Y"], errors="coerce").to_numpy(float)
    prefix_z = pd.to_numeric(prefix["Z"], errors="coerce").to_numpy(float)
    prefix_tvt = pd.to_numeric(
        prefix["TVT_input"], errors="coerce"
    ).to_numpy(float)
    prefix_u = prefix_tvt + prefix_z
    prefix_channels = [
        (prefix_tvt - prefix_tvt[-1]) / 20.0,
        (prefix_u - prefix_u[-1]) / 20.0,
        (prefix_z - prefix_z[-1]) / 100.0,
        (prefix_x - prefix_x[-1]) / 1000.0,
        (prefix_y - prefix_y[-1]) / 1000.0,
        (prefix_gr - gr_center) / gr_scale,
    ]
    for channel in prefix_channels:
        features.extend(legendre_coefficients(channel, sequence_degree))

    features.extend(
        [
            float(len(prefix)),
            float(len(row_indices)),
            float(len(row_indices) / max(len(horizontal), 1)),
            float(x[0] / 1_000_000.0),
            float(y[0] / 1_000_000.0),
            float(z[0] / 10_000.0),
            float(artifact_tvt[0] / 10_000.0),
            float(np.nanmean(gr_normalized)),
            float(np.nanstd(gr_normalized)),
            float(np.nanmean(gr_normalized - reference_normalized)),
            float(np.nanstd(gr_normalized - reference_normalized)),
            float(prefix_md[-1] - prefix_md[0]),
        ]
    )
    return np.asarray(features, float)


def make_model(name: str, seed: int):
    if name == "extra_trees":
        return make_pipeline(
            SimpleImputer(strategy="median"),
            ExtraTreesRegressor(
                n_estimators=500,
                min_samples_leaf=10,
                max_features=0.70,
                n_jobs=-1,
                random_state=seed,
            ),
        )
    if name == "catboost":
        return make_pipeline(
            SimpleImputer(strategy="median"),
            CatBoostRegressor(
                loss_function="MultiRMSE",
                iterations=700,
                depth=4,
                learning_rate=0.03,
                l2_leaf_reg=30.0,
                verbose=False,
                random_seed=seed,
                thread_count=6,
            ),
        )
    if name == "lightgbm":
        return make_pipeline(
            SimpleImputer(strategy="median"),
            MultiOutputRegressor(
                LGBMRegressor(
                    n_estimators=500,
                    num_leaves=7,
                    max_depth=4,
                    learning_rate=0.025,
                    min_child_samples=35,
                    reg_alpha=5.0,
                    reg_lambda=30.0,
                    subsample=0.85,
                    colsample_bytree=0.75,
                    random_state=seed,
                    n_jobs=4,
                    verbosity=-1,
                ),
                n_jobs=1,
            ),
        )
    raise KeyError(name)


def row_curve(coefficients: np.ndarray, rows: int, degree: int) -> np.ndarray:
    basis = np.polynomial.legendre.legvander(
        np.linspace(-1.0, 1.0, rows),
        coefficients.shape[-1] - 1,
    )
    return basis[:, : degree + 1] @ coefficients[: degree + 1]


def train_oof_models(
    features: np.ndarray,
    labels: np.ndarray,
    train_indices: np.ndarray,
    seed: int,
    folds: int,
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    splitter = KFold(n_splits=folds, shuffle=True, random_state=seed)
    predictions: dict[str, np.ndarray] = {}
    report: dict[str, object] = {}
    for model_position, model_name in enumerate(BASE_MODEL_NAMES):
        oof = np.full_like(labels, np.nan)
        for fold, (train_rel, valid_rel) in enumerate(
            splitter.split(train_indices), 1
        ):
            train = train_indices[train_rel]
            valid = train_indices[valid_rel]
            model = make_model(model_name, seed + model_position * 100 + fold)
            model.fit(features[train], labels[train])
            oof[valid] = model.predict(features[valid])
            print(
                f"{model_name} fold {fold}/{folds}: "
                f"train={len(train)} valid={len(valid)}",
                flush=True,
            )
        predictions[model_name] = oof
        report[model_name] = {
            "coefficient_rmse": [
                float(value)
                for value in np.sqrt(
                    np.mean(
                        np.square(labels[train_indices] - oof[train_indices]),
                        axis=0,
                    )
                )
            ]
        }
    predictions["mean_tree"] = 0.5 * (
        predictions["extra_trees"] + predictions["catboost"]
    )
    predictions["mean_all"] = (
        predictions["extra_trees"]
        + predictions["catboost"]
        + predictions["lightgbm"]
    ) / 3.0
    return predictions, report


def fit_full_models(
    features: np.ndarray,
    labels: np.ndarray,
    train_indices: np.ndarray,
    predict_indices: np.ndarray,
    seed: int,
) -> dict[str, np.ndarray]:
    predictions: dict[str, np.ndarray] = {}
    for model_position, model_name in enumerate(BASE_MODEL_NAMES):
        model = make_model(model_name, seed + 1000 + model_position)
        model.fit(features[train_indices], labels[train_indices])
        predictions[model_name] = model.predict(features[predict_indices])
    predictions["mean_tree"] = 0.5 * (
        predictions["extra_trees"] + predictions["catboost"]
    )
    predictions["mean_all"] = (
        predictions["extra_trees"]
        + predictions["catboost"]
        + predictions["lightgbm"]
    ) / 3.0
    return predictions


def bootstrap_improvement(
    frame: pd.DataFrame,
    baseline: np.ndarray,
    candidate: np.ndarray,
    mask: np.ndarray,
    seed: int,
    draws: int = 3000,
) -> dict[str, float]:
    subset = frame.loc[mask, ["well", "target_tvt"]].copy()
    target = subset["target_tvt"].to_numpy(float)
    subset["base_se"] = np.square(baseline[mask] - target)
    subset["candidate_se"] = np.square(candidate[mask] - target)
    by_well = subset.groupby("well", sort=False).agg(
        rows=("well", "size"),
        base_sse=("base_se", "sum"),
        candidate_sse=("candidate_se", "sum"),
    )
    rng = np.random.default_rng(seed)
    improvements = np.empty(draws)
    rows = by_well["rows"].to_numpy(float)
    base_sse = by_well["base_sse"].to_numpy(float)
    candidate_sse = by_well["candidate_sse"].to_numpy(float)
    for draw in range(draws):
        sampled = rng.integers(0, len(by_well), len(by_well))
        count = rows[sampled].sum()
        improvements[draw] = np.sqrt(base_sse[sampled].sum() / count) - np.sqrt(
            candidate_sse[sampled].sum() / count
        )
    return {
        "probability_positive": float(np.mean(improvements > 0.0)),
        "p05": float(np.quantile(improvements, 0.05)),
        "p50": float(np.quantile(improvements, 0.50)),
        "p95": float(np.quantile(improvements, 0.95)),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    artifact = pd.read_csv(
        args.artifact_oof,
        usecols=["well", "row_index", "target_tvt", "artifact_tvt"],
    ).sort_values(["well", "row_index"])
    incumbent = pd.read_parquet(args.incumbent_cache).sort_values(
        ["well", "row_idx"]
    ).reset_index(drop=True)
    fixed_wells = set(incumbent["well"].astype(str).unique())
    artifact_groups = {
        str(well): group.reset_index(drop=True)
        for well, group in artifact.groupby("well", sort=True)
    }
    incumbent_groups = {
        str(well): group.reset_index(drop=True)
        for well, group in incumbent.groupby("well", sort=True)
    }
    all_wells = np.asarray(sorted(artifact_groups))
    well_to_position = {well: position for position, well in enumerate(all_wells)}
    train_indices = np.asarray(
        [
            well_to_position[well]
            for well in all_wells
            if well not in fixed_wells
        ],
        dtype=int,
    )
    fixed_indices = np.asarray(
        [well_to_position[well] for well in all_wells if well in fixed_wells],
        dtype=int,
    )
    if len(train_indices) != 573 or len(fixed_indices) != 200:
        raise RuntimeError(
            f"expected 573/200 well split, got {len(train_indices)}/{len(fixed_indices)}"
        )

    features = []
    labels = []
    row_counts = []
    for position, well in enumerate(all_wells, 1):
        if well in fixed_wells:
            prediction_frame = incumbent_groups[well]
            row_indices = prediction_frame["row_idx"].to_numpy(int)
            artifact_tvt = prediction_frame["artifact_tvt"].to_numpy(float)
        else:
            prediction_frame = artifact_groups[well]
            row_indices = prediction_frame["row_index"].to_numpy(int)
            artifact_tvt = prediction_frame["artifact_tvt"].to_numpy(float)
        horizontal = pd.read_csv(
            args.data_root / "train" / f"{well}__horizontal_well.csv"
        )
        typewell = pd.read_csv(
            args.data_root / "train" / f"{well}__typewell.csv"
        )
        expected = np.flatnonzero(horizontal["TVT_input"].isna().to_numpy())
        if not np.array_equal(expected, row_indices):
            raise RuntimeError(f"{well}: prediction rows do not match hidden suffix")
        features.append(
            build_well_features(
                horizontal,
                typewell,
                row_indices,
                artifact_tvt,
                args.sequence_degree,
            )
        )
        artifact_group = artifact_groups[well]
        residual = (
            artifact_group["target_tvt"].to_numpy(float)
            - artifact_group["artifact_tvt"].to_numpy(float)
        )
        labels.append(legendre_coefficients(residual, args.target_degree))
        row_counts.append(len(row_indices))
        if position % 100 == 0 or position == len(all_wells):
            print(f"features {position}/{len(all_wells)}", flush=True)
    features_array = np.vstack(features)
    labels_array = np.vstack(labels)

    oof_coefficients, oof_report = train_oof_models(
        features_array,
        labels_array,
        train_indices,
        args.seed,
        args.folds,
    )
    train_oof_scores = {}
    for model_name in MODEL_NAMES:
        total_sse = 0.0
        total_rows = 0
        for well_position in train_indices:
            well = all_wells[well_position]
            group = artifact_groups[well]
            residual = (
                group["target_tvt"].to_numpy(float)
                - group["artifact_tvt"].to_numpy(float)
            )
            curve = row_curve(
                oof_coefficients[model_name][well_position],
                len(group),
                args.target_degree,
            )
            total_sse += float(np.sum(np.square(residual - curve)))
            total_rows += len(group)
        train_oof_scores[model_name] = float(np.sqrt(total_sse / total_rows))

    full_coefficients = fit_full_models(
        features_array,
        labels_array,
        train_indices,
        fixed_indices,
        args.seed,
    )
    fixed_position_map = {
        int(well_position): local_position
        for local_position, well_position in enumerate(fixed_indices)
    }
    raw_curves = {name: np.zeros(len(incumbent), float) for name in MODEL_NAMES}
    for well, group in incumbent.groupby("well", sort=True):
        positions = group.index.to_numpy(int)
        well_position = well_to_position[str(well)]
        local_position = fixed_position_map[well_position]
        for model_name in MODEL_NAMES:
            raw_curves[model_name][positions] = row_curve(
                full_coefficients[model_name][local_position],
                len(group),
                args.target_degree,
            )
    for model_name, values in raw_curves.items():
        incumbent[
            f"complete_well_{model_name}_degree{args.target_degree}_raw"
        ] = values

    discovery = incumbent["validation_split"].eq("discovery").to_numpy()
    target = incumbent["target_tvt"].to_numpy(float)
    baseline_scores = {
        proxy: rmse(target[discovery], incumbent.loc[discovery, column])
        for proxy, column in PROXIES.items()
    }
    records = []
    for model_name in MODEL_NAMES:
        for degree in range(args.target_degree + 1):
            degree_curve = np.zeros(len(incumbent), float)
            for well, group in incumbent.groupby("well", sort=True):
                positions = group.index.to_numpy(int)
                well_position = well_to_position[str(well)]
                local_position = fixed_position_map[well_position]
                degree_curve[positions] = row_curve(
                    full_coefficients[model_name][local_position],
                    len(group),
                    degree,
                )
            for cap in args.caps:
                clipped = np.clip(degree_curve, -cap, cap)
                for tau in args.taus:
                    md_since = np.maximum(
                        incumbent["md_since"].to_numpy(float), 0.0
                    )
                    ramp = (
                        np.ones(len(incumbent))
                        if tau <= 0
                        else 1.0 - np.exp(-md_since / tau)
                    )
                    move = ramp * clipped
                    move_discovery = move[discovery]
                    move_square = float(np.mean(np.square(move_discovery)))
                    correlations = {}
                    for proxy, column in PROXIES.items():
                        error = (
                            target[discovery]
                            - incumbent.loc[discovery, column].to_numpy(float)
                        )
                        correlations[proxy] = float(np.mean(error * move_discovery))
                    for scale in args.scales:
                        scores = {
                            proxy: float(
                                np.sqrt(
                                    baseline_scores[proxy] ** 2
                                    - 2.0 * scale * correlations[proxy]
                                    + scale * scale * move_square
                                )
                            )
                            for proxy in PROXIES
                        }
                        improvements = {
                            proxy: baseline_scores[proxy] - scores[proxy]
                            for proxy in PROXIES
                        }
                        records.append(
                            {
                                "model": model_name,
                                "degree": int(degree),
                                "cap": float(cap),
                                "tau": float(tau),
                                "scale": float(scale),
                                "scores": scores,
                                "improvements": improvements,
                                "minimum_improvement": float(
                                    min(improvements.values())
                                ),
                                "mean_improvement": float(
                                    np.mean(list(improvements.values()))
                                ),
                            }
                        )
    selected = max(
        records,
        key=lambda row: (
            row["minimum_improvement"],
            row["mean_improvement"],
            -abs(row["scale"]),
            -row["cap"],
        ),
    )
    selected_curve = np.zeros(len(incumbent), float)
    for well, group in incumbent.groupby("well", sort=True):
        positions = group.index.to_numpy(int)
        well_position = well_to_position[str(well)]
        local_position = fixed_position_map[well_position]
        selected_curve[positions] = row_curve(
            full_coefficients[selected["model"]][local_position],
            len(group),
            selected["degree"],
        )
    ramp = (
        np.ones(len(incumbent))
        if selected["tau"] <= 0
        else 1.0
        - np.exp(
            -np.maximum(incumbent["md_since"].to_numpy(float), 0.0)
            / selected["tau"]
        )
    )
    correction = (
        selected["scale"]
        * ramp
        * np.clip(selected_curve, -selected["cap"], selected["cap"])
    )
    incumbent["complete_well_curve_raw"] = selected_curve
    incumbent["complete_well_curve_correction"] = correction

    summary: dict[str, object] = {
        "method": "complete_well_target_free_curve_model",
        "train_wells": int(len(train_indices)),
        "fixed_validation_wells": int(len(fixed_indices)),
        "feature_count": int(features_array.shape[1]),
        "sequence_degree": int(args.sequence_degree),
        "target_degree": int(args.target_degree),
        "contracts": {
            "whole_well_oof": True,
            "fixed_validation_wells_excluded_from_model_fit": True,
            "same_well_contact_used": False,
            "formation_surfaces_used": False,
            "suffix_tvt_used_as_features": False,
            "full_hidden_gr_lookahead_used": True,
        },
        "artifact_train_baseline_rmse": rmse(
            artifact.loc[
                artifact["well"].astype(str).isin(
                    set(all_wells[train_indices])
                ),
                "target_tvt",
            ],
            artifact.loc[
                artifact["well"].astype(str).isin(
                    set(all_wells[train_indices])
                ),
                "artifact_tvt",
            ],
        ),
        "train_oof_scores": train_oof_scores,
        "oof_report": oof_report,
        "discovery_selection": {
            "baseline_scores": baseline_scores,
            "selected": selected,
            "top10": sorted(
                records,
                key=lambda row: (
                    row["minimum_improvement"],
                    row["mean_improvement"],
                ),
                reverse=True,
            )[:10],
        },
        "splits": {},
    }
    for split_index, split in enumerate(
        ("discovery", "holdout1", "holdout2", "holdout_combined", "all")
    ):
        if split == "holdout_combined":
            mask = incumbent["validation_split"].isin(
                ["holdout1", "holdout2"]
            ).to_numpy()
        elif split == "all":
            mask = np.ones(len(incumbent), bool)
        else:
            mask = incumbent["validation_split"].eq(split).to_numpy()
        proxy_results = {}
        for proxy_index, (proxy, column) in enumerate(PROXIES.items()):
            baseline = incumbent[column].to_numpy(float)
            candidate = baseline + correction
            baseline_score = rmse(target[mask], baseline[mask])
            candidate_score = rmse(target[mask], candidate[mask])
            proxy_results[proxy] = {
                "baseline_rmse": baseline_score,
                "candidate_rmse": candidate_score,
                "improvement": baseline_score - candidate_score,
                "bootstrap": bootstrap_improvement(
                    incumbent,
                    baseline,
                    candidate,
                    mask,
                    args.seed + split_index * 20 + proxy_index,
                ),
            }
        summary["splits"][split] = {
            "rows": int(mask.sum()),
            "wells": int(incumbent.loc[mask, "well"].nunique()),
            "proxies": proxy_results,
        }
    holdout = summary["splits"]["holdout_combined"]["proxies"]
    minimum_holdout = float(
        min(value["improvement"] for value in holdout.values())
    )
    summary["promotion"] = {
        "all_holdout_proxies_improve": bool(
            all(value["improvement"] > 0.0 for value in holdout.values())
        ),
        "minimum_holdout_improvement": minimum_holdout,
        "required_effect_ft": float(args.required_effect),
        "passes_effect_gate": bool(minimum_holdout >= args.required_effect),
    }
    summary["elapsed_sec"] = float(time.perf_counter() - started)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    incumbent.to_parquet(args.output, index=False)
    args.summary.write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, default=str))
    return summary


def parse_tuple(value: str) -> tuple[float, ...]:
    return tuple(float(part.strip()) for part in value.split(",") if part.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--artifact-oof", type=Path, required=True)
    parser.add_argument("--incumbent-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--sequence-degree", type=int, default=12)
    parser.add_argument("--target-degree", type=int, default=5)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--caps", default="2,4,8,12,20,1000")
    parser.add_argument("--taus", default="0,100,300")
    parser.add_argument("--scales", default="0,0.05,0.10,0.15,0.20,0.30,0.40,0.50,0.75,1.0")
    parser.add_argument("--required-effect", type=float, default=0.08)
    parser.add_argument("--seed", type=int, default=20260730)
    args = parser.parse_args()
    args.caps = parse_tuple(args.caps)
    args.taus = parse_tuple(args.taus)
    args.scales = parse_tuple(args.scales)
    run(args)


if __name__ == "__main__":
    main()
