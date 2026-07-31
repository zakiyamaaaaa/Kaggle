"""Repeated nested field blend for target-free complete-well corrections.

The candidate keeps the exact local proxy of the 7.474 submission fixed and
combines three independently generated corrections:

* public learned SG601 smoothing;
* bounded complete-well matcher;
* target-free complete-well residual curve.

Field labels are created from train-well median X/Y only.  For every outer
well fold, component weights are selected from the remaining wells by
maximising the minimum improvement across four legal OOF proxies.  Averaging
the repeated outer-OOF predictions therefore preserves the exclusion of each
evaluated well from its own weight selection.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.model_selection import StratifiedKFold


COMPONENTS = ("sg601", "matcher", "curve")
SPLITS = ("discovery", "holdout1", "holdout2")


def parse_ints(value: str) -> tuple[int, ...]:
    return tuple(int(part.strip()) for part in value.split(",") if part.strip())


def parse_floats(value: str) -> tuple[float, ...]:
    return tuple(float(part.strip()) for part in value.split(",") if part.strip())


def rmse(target: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(target - prediction))))


def build_geometry(data_root: Path, fields: int, seed: int) -> tuple[dict[str, int], list[dict[str, float | int]]]:
    records = []
    for path in sorted((data_root / "train").glob("*__horizontal_well.csv")):
        frame = pd.read_csv(path, usecols=["X", "Y"])
        records.append(
            {
                "well": path.name.split("__", 1)[0],
                "x": float(pd.to_numeric(frame["X"], errors="coerce").median()),
                "y": float(pd.to_numeric(frame["Y"], errors="coerce").median()),
            }
        )
    geometry = pd.DataFrame(records)
    if len(geometry) == 0:
        raise RuntimeError("no train well geometry was found")
    model = KMeans(n_clusters=fields, n_init=20, random_state=seed)
    geometry["field"] = model.fit_predict(geometry[["x", "y"]].to_numpy(float))
    field_map = dict(zip(geometry["well"].astype(str), geometry["field"].astype(int)))
    centroids = [
        {
            "field": int(field),
            "x": float(center[0]),
            "y": float(center[1]),
            "train_wells": int(geometry["field"].eq(field).sum()),
        }
        for field, center in enumerate(model.cluster_centers_)
    ]
    return field_map, centroids


def quadratic_stats(
    target: np.ndarray,
    baseline: np.ndarray,
    components: np.ndarray,
    mask: np.ndarray,
) -> tuple[int, float, np.ndarray, np.ndarray]:
    error = target[mask] - baseline[mask]
    design = components[mask]
    return (
        int(mask.sum()),
        float(error @ error),
        error @ design,
        design.T @ design,
    )


def quadratic_rmse(
    stats: tuple[int, float, np.ndarray, np.ndarray],
    weights: np.ndarray,
) -> float:
    rows, baseline_sse, error_cross, component_cross = stats
    candidate_sse = (
        baseline_sse
        - 2.0 * float(error_cross @ weights)
        + float(weights @ component_cross @ weights)
    )
    return float(np.sqrt(max(candidate_sse, 0.0) / max(rows, 1)))


def select_weights(
    target: np.ndarray,
    proxies: dict[str, np.ndarray],
    components: np.ndarray,
    mask: np.ndarray,
    grid: np.ndarray,
) -> tuple[np.ndarray, dict[str, object]]:
    stats = {
        name: quadratic_stats(target, baseline, components, mask)
        for name, baseline in proxies.items()
    }
    baseline_scores = {
        name: quadratic_rmse(values, np.zeros(components.shape[1]))
        for name, values in stats.items()
    }
    best_key: tuple[float, float, float] | None = None
    best_weights: np.ndarray | None = None
    best_improvements: dict[str, float] | None = None
    for weights in grid:
        improvements = {
            name: baseline_scores[name] - quadratic_rmse(values, weights)
            for name, values in stats.items()
        }
        key = (
            float(min(improvements.values())),
            float(np.mean(list(improvements.values()))),
            -float(np.linalg.norm(weights)),
        )
        if best_key is None or key > best_key:
            best_key = key
            best_weights = weights.copy()
            best_improvements = improvements
    if best_weights is None or best_improvements is None or best_key is None:
        raise RuntimeError("component weight selection produced no candidate")
    return best_weights, {
        "training_rows": int(mask.sum()),
        "training_wells": None,
        "minimum_proxy_improvement": best_key[0],
        "mean_proxy_improvement": best_key[1],
        "proxy_improvements": best_improvements,
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
            "well": frame["well"].astype(str).to_numpy(),
            "rows": 1,
            "baseline_se": np.square(target - baseline),
            "candidate_se": np.square(target - candidate),
        }
    )
    by_well = local.groupby("well", sort=True).agg(
        rows=("rows", "sum"),
        baseline_sse=("baseline_se", "sum"),
        candidate_sse=("candidate_se", "sum"),
    )
    rows = by_well["rows"].to_numpy(float)
    baseline_sse = by_well["baseline_sse"].to_numpy(float)
    candidate_sse = by_well["candidate_sse"].to_numpy(float)
    rng = np.random.default_rng(seed)
    values = np.empty(draws, float)
    for draw in range(draws):
        sampled = rng.integers(0, len(by_well), len(by_well))
        count = rows[sampled].sum()
        values[draw] = np.sqrt(baseline_sse[sampled].sum() / count) - np.sqrt(
            candidate_sse[sampled].sum() / count
        )
    return {
        "wells": int(len(by_well)),
        "draws": int(draws),
        "probability_positive": float(np.mean(values > 0.0)),
        "p01": float(np.quantile(values, 0.01)),
        "p05": float(np.quantile(values, 0.05)),
        "p50": float(np.quantile(values, 0.50)),
        "p95": float(np.quantile(values, 0.95)),
    }


def split_report(
    frame: pd.DataFrame,
    target: np.ndarray,
    baseline: np.ndarray,
    candidate: np.ndarray,
) -> dict[str, object]:
    report: dict[str, object] = {}
    for split in (*SPLITS, "all"):
        mask = (
            np.ones(len(frame), bool)
            if split == "all"
            else frame["validation_split"].eq(split).to_numpy()
        )
        baseline_score = rmse(target[mask], baseline[mask])
        candidate_score = rmse(target[mask], candidate[mask])
        report[split] = {
            "rows": int(mask.sum()),
            "wells": int(frame.loc[mask, "well"].nunique()),
            "baseline_rmse": baseline_score,
            "candidate_rmse": candidate_score,
            "improvement": baseline_score - candidate_score,
        }
    return report


def run(args: argparse.Namespace) -> dict[str, object]:
    curve = pd.read_parquet(args.curve_cache).sort_values(
        ["well", "row_idx"]
    ).reset_index(drop=True)
    matcher = pd.read_parquet(
        args.matcher_cache,
        columns=["id", "matcher_direct_correction"],
    )
    frame = curve.merge(matcher, on="id", validate="one_to_one")

    oof_ids = pd.read_parquet(
        args.oof_ids,
        columns=["id", "last_known_TVT"],
    )
    position_map = pd.Series(
        np.arange(len(oof_ids)),
        index=oof_ids["id"].astype(str),
    )
    positions = frame["id"].astype(str).map(position_map)
    if positions.isna().any():
        raise RuntimeError("fixed evaluation IDs are absent from the OOF contract")
    positions_array = positions.to_numpy(int)
    raw_public = np.asarray(np.load(args.raw_public_oof, mmap_mode="r"), float)
    smooth_public = np.asarray(np.load(args.smooth_public_oof, mmap_mode="r"), float)
    if not (
        len(raw_public) == len(smooth_public) == len(oof_ids)
        and np.isfinite(raw_public).all()
        and np.isfinite(smooth_public).all()
    ):
        raise RuntimeError("public OOF arrays do not share one finite contract")

    hedge_shift = (
        frame["public_s060_cap200_artifact"].to_numpy(float)
        - frame["base_artifact"].to_numpy(float)
    )
    public_absolute = (
        oof_ids["last_known_TVT"].to_numpy(float)[positions_array]
        + raw_public[positions_array]
    )
    exact_public = (
        args.sp45_weight * frame["sp45_sgridge_d2_b050"].to_numpy(float)
        + (1.0 - args.sp45_weight) * public_absolute
        + hedge_shift
    )
    proxies = {
        "exact_public": exact_public,
        "artifact": frame["public_s060_cap200_artifact"].to_numpy(float),
        "hgb": frame["public_s060_cap200_hgb"].to_numpy(float),
        "ridge": frame["public_s060_cap200_ridge"].to_numpy(float),
    }
    components = np.column_stack(
        [
            (1.0 - args.sp45_weight)
            * (smooth_public[positions_array] - raw_public[positions_array]),
            frame["matcher_direct_correction"].to_numpy(float),
            frame["complete_well_curve_correction"].to_numpy(float),
        ]
    )
    target = frame["target_tvt"].to_numpy(float)

    field_map, centroids = build_geometry(
        args.data_root,
        args.fields,
        args.field_seed,
    )
    frame["field"] = frame["well"].astype(str).map(field_map)
    if frame["field"].isna().any():
        raise RuntimeError("fixed evaluation wells are absent from field geometry")
    frame["field"] = frame["field"].astype(int)
    well_frame = (
        frame.groupby("well", sort=True)["field"].first().reset_index()
    )
    minimum_field_wells = int(well_frame.groupby("field").size().min())
    if minimum_field_wells < args.folds:
        raise RuntimeError(
            f"smallest field has {minimum_field_wells} wells for {args.folds} folds"
        )

    values = parse_floats(args.weight_grid)
    grid = np.asarray(list(itertools.product(values, repeat=len(COMPONENTS))), float)
    seeds = parse_ints(args.seeds)
    seed_predictions: list[np.ndarray] = []
    seed_reports: list[dict[str, object]] = []
    selections: list[dict[str, object]] = []

    for seed in seeds:
        splitter = StratifiedKFold(
            n_splits=args.folds,
            shuffle=True,
            random_state=seed,
        )
        fold_map: dict[str, int] = {}
        for fold, (_, valid_indices) in enumerate(
            splitter.split(well_frame["well"], well_frame["field"])
        ):
            for well in well_frame.iloc[valid_indices]["well"]:
                fold_map[str(well)] = int(fold)
        row_fold = frame["well"].astype(str).map(fold_map).to_numpy(int)
        prediction = exact_public.copy()

        for fold in range(args.folds):
            train_fold = row_fold != fold
            valid_fold = ~train_fold
            for field in range(args.fields):
                train = train_fold & frame["field"].eq(field).to_numpy()
                valid = valid_fold & frame["field"].eq(field).to_numpy()
                weights, selection = select_weights(
                    target,
                    proxies,
                    components,
                    train,
                    grid,
                )
                prediction[valid] = (
                    exact_public[valid] + components[valid] @ weights
                )
                selection["training_wells"] = int(
                    frame.loc[train, "well"].nunique()
                )
                selections.append(
                    {
                        "seed": int(seed),
                        "fold": int(fold),
                        "field": int(field),
                        "validation_wells": int(
                            frame.loc[valid, "well"].nunique()
                        ),
                        "weights": {
                            name: float(value)
                            for name, value in zip(COMPONENTS, weights)
                        },
                        **selection,
                    }
                )

        baseline_score = rmse(target, exact_public)
        candidate_score = rmse(target, prediction)
        seed_reports.append(
            {
                "seed": int(seed),
                "baseline_rmse": baseline_score,
                "candidate_rmse": candidate_score,
                "improvement": baseline_score - candidate_score,
                "splits": split_report(
                    frame,
                    target,
                    exact_public,
                    prediction,
                ),
                "bootstrap": paired_well_bootstrap(
                    frame,
                    target,
                    exact_public,
                    prediction,
                    args.seed_bootstrap_draws,
                    seed,
                ),
            }
        )
        seed_predictions.append(prediction)

    ensemble = np.mean(seed_predictions, axis=0)
    correction = ensemble - exact_public
    frame["exact_7474_proxy"] = exact_public
    frame["field_nested_candidate"] = ensemble
    frame["field_nested_correction"] = correction

    proxy_results = {}
    for name, baseline in proxies.items():
        candidate = baseline + correction
        baseline_score = rmse(target, baseline)
        candidate_score = rmse(target, candidate)
        proxy_results[name] = {
            "baseline_rmse": baseline_score,
            "candidate_rmse": candidate_score,
            "improvement": baseline_score - candidate_score,
        }

    selection_frame = pd.DataFrame(
        [
            {
                "field": row["field"],
                **row["weights"],
            }
            for row in selections
        ]
    )
    deployment_weights = {}
    for field, part in selection_frame.groupby("field", sort=True):
        deployment_weights[str(int(field))] = {
            name: {
                "mean": float(part[name].mean()),
                "std": float(part[name].std()),
                "minimum": float(part[name].min()),
                "maximum": float(part[name].max()),
            }
            for name in COMPONENTS
        }

    ensemble_splits = split_report(
        frame,
        target,
        exact_public,
        ensemble,
    )
    bootstrap = paired_well_bootstrap(
        frame,
        target,
        exact_public,
        ensemble,
        args.bootstrap_draws,
        args.bootstrap_seed,
    )
    baseline_score = rmse(target, exact_public)
    candidate_score = rmse(target, ensemble)
    improvement = baseline_score - candidate_score
    seed_improvements = [float(row["improvement"]) for row in seed_reports]
    promotion = {
        "strict_effect_gate_ft": float(args.strict_effect_gate),
        "ensemble_passes_effect_gate": bool(
            improvement >= args.strict_effect_gate
        ),
        "mean_seed_passes_effect_gate": bool(
            np.mean(seed_improvements) >= args.strict_effect_gate
        ),
        "ensemble_bootstrap_p05_positive": bool(bootstrap["p05"] > 0.0),
        "all_legacy_splits_improve": bool(
            all(
                ensemble_splits[split]["improvement"] > 0.0
                for split in SPLITS
            )
        ),
        "all_proxies_improve": bool(
            all(row["improvement"] > 0.0 for row in proxy_results.values())
        ),
    }
    promotion["passes_local_gate"] = bool(all(promotion.values()))
    promotion["recommendation"] = (
        "build and audit hidden-dynamic notebook; do not submit automatically"
        if promotion["passes_local_gate"]
        else "continue local experiments"
    )

    summary: dict[str, object] = {
        "method": "repeated_nested_field_component_blend",
        "rows": int(len(frame)),
        "wells": int(frame["well"].nunique()),
        "fields": int(args.fields),
        "field_seed": int(args.field_seed),
        "field_centroids": centroids,
        "folds": int(args.folds),
        "seeds": list(seeds),
        "weight_grid": list(values),
        "components": list(COMPONENTS),
        "selection_objective": (
            "maximize minimum improvement across exact_public, artifact, hgb, "
            "and ridge OOF proxies"
        ),
        "contracts": {
            "outer_validation_well_excluded_from_weight_selection": True,
            "field_labels_use_target_free_train_geometry_only": True,
            "curve_model_excludes_all_fixed_200_wells": True,
            "matcher_uses_no_suffix_target": True,
            "same_well_contact_used": False,
            "suffix_target_used_only_for_evaluation": True,
        },
        "ensemble": {
            "baseline_rmse": baseline_score,
            "candidate_rmse": candidate_score,
            "improvement": improvement,
            "seed_improvement_mean": float(np.mean(seed_improvements)),
            "seed_improvement_minimum": float(np.min(seed_improvements)),
            "seed_improvement_maximum": float(np.max(seed_improvements)),
            "bootstrap": bootstrap,
            "splits": ensemble_splits,
            "proxy_results": proxy_results,
            "correction_distribution": {
                "mean": float(np.mean(correction)),
                "p50_abs": float(np.quantile(np.abs(correction), 0.50)),
                "p95_abs": float(np.quantile(np.abs(correction), 0.95)),
                "maximum_abs": float(np.max(np.abs(correction))),
            },
        },
        "seed_reports": seed_reports,
        "deployment_weight_summary": deployment_weights,
        "selection_records": selections,
        "promotion": promotion,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.output, index=False)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--curve-cache", type=Path, required=True)
    parser.add_argument("--matcher-cache", type=Path, required=True)
    parser.add_argument("--oof-ids", type=Path, required=True)
    parser.add_argument("--raw-public-oof", type=Path, required=True)
    parser.add_argument("--smooth-public-oof", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--fields", type=int, default=6)
    parser.add_argument("--field-seed", type=int, default=0)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument(
        "--seeds",
        default="20260736,20260737,20260738,20260739,20260740",
    )
    parser.add_argument(
        "--weight-grid",
        default="0,0.25,0.50,0.75,1.00,1.25,1.50",
    )
    parser.add_argument("--sp45-weight", type=float, default=0.60)
    parser.add_argument("--strict-effect-gate", type=float, default=0.08)
    parser.add_argument("--seed-bootstrap-draws", type=int, default=5_000)
    parser.add_argument("--bootstrap-draws", type=int, default=20_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260801)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
