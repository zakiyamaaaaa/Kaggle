"""Select SP45/learned blend weights by target-free field and outer well OOF."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold


PROXIES = ("exact_public", "artifact", "hgb", "ridge")
SPLITS = ("discovery", "holdout1", "holdout2")


def rmse(target: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(target - prediction))))


def parse_floats(value: str) -> np.ndarray:
    return np.asarray(
        [float(part.strip()) for part in value.split(",") if part.strip()], float
    )


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


def select_weight(
    target: np.ndarray,
    baselines: dict[str, np.ndarray],
    directions: dict[str, np.ndarray],
    train: np.ndarray,
    grid: np.ndarray,
    incumbent_weight: float,
) -> tuple[float, dict[str, object]]:
    baseline_scores = {
        name: rmse(target[train], baseline[train])
        for name, baseline in baselines.items()
    }
    best_key = None
    best = None
    best_improvements = None
    for weight in grid:
        shift = float(weight - incumbent_weight)
        improvements = {
            name: baseline_scores[name]
            - rmse(target[train], (baseline + shift * directions[name])[train])
            for name, baseline in baselines.items()
        }
        key = (
            float(min(improvements.values())),
            float(np.mean(list(improvements.values()))),
            -abs(shift),
        )
        if best_key is None or key > best_key:
            best_key = key
            best = float(weight)
            best_improvements = improvements
    if best is None or best_improvements is None:
        raise RuntimeError("SP45 weight selection produced no candidate")
    return best, {
        "training_rows": int(train.sum()),
        "minimum_proxy_improvement": float(best_key[0]),
        "mean_proxy_improvement": float(best_key[1]),
        "proxy_improvements": best_improvements,
    }


def split_report(
    frame: pd.DataFrame,
    target: np.ndarray,
    baseline: np.ndarray,
    candidate: np.ndarray,
) -> dict[str, object]:
    report = {}
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
    frame = pd.read_parquet(args.candidate_cache).reset_index(drop=True)
    target = frame["target_tvt"].to_numpy(float)
    sp45 = frame["sp45_sgridge_d2_b050"].to_numpy(float)
    hedge = (
        frame["public_s060_cap200_artifact"].to_numpy(float)
        - frame["base_artifact"].to_numpy(float)
    )
    baselines = {
        "exact_public": frame["exact_7474_proxy"].to_numpy(float),
        "artifact": frame["public_s060_cap200_artifact"].to_numpy(float),
        "hgb": frame["public_s060_cap200_hgb"].to_numpy(float),
        "ridge": frame["public_s060_cap200_ridge"].to_numpy(float),
    }
    no_hedge = {
        "exact_public": baselines["exact_public"] - hedge,
        "artifact": frame["base_artifact"].to_numpy(float),
        "hgb": frame["base_hgb"].to_numpy(float),
        "ridge": frame["base_ridge"].to_numpy(float),
    }
    learned = {
        name: (base - args.incumbent_weight * sp45)
        / (1.0 - args.incumbent_weight)
        for name, base in no_hedge.items()
    }
    directions = {name: sp45 - values for name, values in learned.items()}

    wells = frame["well"].astype(str)
    well_frame = frame.groupby("well", sort=True)["field"].first().reset_index()
    grid = parse_floats(args.weight_grid)
    seeds = tuple(int(part) for part in args.seeds.split(","))
    seed_predictions = {name: [] for name in PROXIES}
    seed_reports = []
    selections = []

    for seed in seeds:
        splitter = StratifiedKFold(
            n_splits=args.folds, shuffle=True, random_state=seed
        )
        fold_map: dict[str, int] = {}
        for fold, (_, valid) in enumerate(
            splitter.split(well_frame["well"], well_frame["field"])
        ):
            for well in well_frame.iloc[valid]["well"]:
                fold_map[str(well)] = int(fold)
        row_fold = wells.map(fold_map).to_numpy(int)
        predictions = {name: baseline.copy() for name, baseline in baselines.items()}
        for fold in range(args.folds):
            for field in range(args.fields):
                train = (row_fold != fold) & frame["field"].eq(field).to_numpy()
                valid = (row_fold == fold) & frame["field"].eq(field).to_numpy()
                weight, selection = select_weight(
                    target,
                    baselines,
                    directions,
                    train,
                    grid,
                    args.incumbent_weight,
                )
                shift = weight - args.incumbent_weight
                for name in PROXIES:
                    predictions[name][valid] = (
                        baselines[name][valid] + shift * directions[name][valid]
                    )
                selections.append(
                    {
                        "seed": int(seed),
                        "fold": int(fold),
                        "field": int(field),
                        "selected_sp45_weight": float(weight),
                        "training_wells": int(frame.loc[train, "well"].nunique()),
                        "validation_wells": int(frame.loc[valid, "well"].nunique()),
                        **selection,
                    }
                )
        exact_score = rmse(target, predictions["exact_public"])
        seed_reports.append(
            {
                "seed": int(seed),
                "baseline_rmse": rmse(target, baselines["exact_public"]),
                "candidate_rmse": exact_score,
                "improvement": rmse(target, baselines["exact_public"])
                - exact_score,
            }
        )
        for name in PROXIES:
            seed_predictions[name].append(predictions[name])

    ensembles = {
        name: np.mean(predictions, axis=0)
        for name, predictions in seed_predictions.items()
    }
    proxy_results = {}
    for name in PROXIES:
        baseline_score = rmse(target, baselines[name])
        candidate_score = rmse(target, ensembles[name])
        proxy_results[name] = {
            "baseline_rmse": baseline_score,
            "candidate_rmse": candidate_score,
            "improvement": baseline_score - candidate_score,
            "splits": split_report(frame, target, baselines[name], ensembles[name]),
        }
    exact = ensembles["exact_public"]
    bootstrap = paired_well_bootstrap(
        frame,
        target,
        baselines["exact_public"],
        exact,
        args.bootstrap_draws,
        args.bootstrap_seed,
    )
    selection_frame = pd.DataFrame(selections)
    deployment = {
        str(int(field)): {
            "mean": float(part["selected_sp45_weight"].mean()),
            "std": float(part["selected_sp45_weight"].std()),
            "minimum": float(part["selected_sp45_weight"].min()),
            "maximum": float(part["selected_sp45_weight"].max()),
        }
        for field, part in selection_frame.groupby("field", sort=True)
    }
    seed_improvements = [row["improvement"] for row in seed_reports]
    promotion = {
        "all_proxies_improve": bool(
            all(row["improvement"] > 0.0 for row in proxy_results.values())
        ),
        "all_exact_legacy_splits_improve": bool(
            all(
                proxy_results["exact_public"]["splits"][split]["improvement"] > 0.0
                for split in SPLITS
            )
        ),
        "all_seeds_improve": bool(min(seed_improvements) > 0.0),
        "bootstrap_p05_positive": bool(bootstrap["p05"] > 0.0),
        "effect_gate_ft": float(args.effect_gate),
        "passes_effect_gate": bool(
            proxy_results["exact_public"]["improvement"] >= args.effect_gate
        ),
    }
    promotion["passes_local_gate"] = bool(
        promotion["all_proxies_improve"]
        and promotion["all_exact_legacy_splits_improve"]
        and promotion["all_seeds_improve"]
        and promotion["bootstrap_p05_positive"]
        and promotion["passes_effect_gate"]
    )
    output = {
        "method": "repeated_nested_field_sp45_weight",
        "fields": int(args.fields),
        "folds": int(args.folds),
        "seeds": list(seeds),
        "incumbent_sp45_weight": float(args.incumbent_weight),
        "weight_grid": grid.tolist(),
        "contracts": {
            "outer_validation_well_excluded_from_weight_selection": True,
            "field_labels_target_free": True,
            "selection_uses_four_oof_proxies": True,
            "same_branch_hedge_preserved": True,
        },
        "proxy_results": proxy_results,
        "seed_reports": seed_reports,
        "bootstrap": bootstrap,
        "deployment_weight_summary": deployment,
        "selection_records": selections,
        "promotion": promotion,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "exact": proxy_results["exact_public"],
                "bootstrap": bootstrap,
                "deployment": deployment,
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
    parser.add_argument("--fields", type=int, default=6)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument(
        "--seeds", default="20260801,20260802,20260803,20260804,20260805"
    )
    parser.add_argument(
        "--weight-grid",
        default="0.40,0.425,0.45,0.475,0.50,0.525,0.55,0.575,0.60,0.625,0.65,0.675,0.70,0.725,0.75,0.775,0.80",
    )
    parser.add_argument("--incumbent-weight", type=float, default=0.60)
    parser.add_argument("--bootstrap-draws", type=int, default=20000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260806)
    parser.add_argument("--effect-gate", type=float, default=0.03)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
