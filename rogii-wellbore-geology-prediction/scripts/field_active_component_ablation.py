"""Ablate the nested K6 correction on the active hidden fields 3 and 4.

The component weights remain outer-OOF: each evaluated well is excluded from
the fold-specific weight selection.  This script only applies predefined
post-selection component scales, so no suffix target enters the correction.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold


COMPONENTS = ("sg601", "matcher", "curve")
PROXY_COLUMNS = {
    "exact_public": "exact_7474_proxy",
    "artifact": "public_s060_cap200_artifact",
    "hgb": "public_s060_cap200_hgb",
    "ridge": "public_s060_cap200_ridge",
}


def rmse(target: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(target - prediction))))


def paired_well_bootstrap(
    frame: pd.DataFrame,
    target: np.ndarray,
    baseline: np.ndarray,
    candidate: np.ndarray,
    mask: np.ndarray,
    seed: int,
    draws: int,
) -> dict[str, float | int]:
    local = pd.DataFrame(
        {
            "well": frame.loc[mask, "well"].astype(str).to_numpy(),
            "rows": 1,
            "baseline_se": np.square(target[mask] - baseline[mask]),
            "candidate_se": np.square(target[mask] - candidate[mask]),
        }
    )
    by_well = local.groupby("well", sort=True).agg(
        rows=("rows", "sum"),
        baseline_sse=("baseline_se", "sum"),
        candidate_sse=("candidate_se", "sum"),
    )
    rng = np.random.default_rng(seed)
    rows = by_well["rows"].to_numpy(float)
    baseline_sse = by_well["baseline_sse"].to_numpy(float)
    candidate_sse = by_well["candidate_sse"].to_numpy(float)
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


def predefined_variants() -> dict[str, tuple[float, float, float]]:
    variants = {
        "no_correction": (0.0, 0.0, 0.0),
        "all_components": (1.0, 1.0, 1.0),
        "sg_only": (1.0, 0.0, 0.0),
        "matcher_only": (0.0, 1.0, 0.0),
        "curve_only": (0.0, 0.0, 1.0),
        "no_sg": (0.0, 1.0, 1.0),
        "no_matcher": (1.0, 0.0, 1.0),
        "no_curve": (1.0, 1.0, 0.0),
    }
    for scale in (0.25, 0.50, 0.75):
        suffix = f"{int(scale * 100):03d}"
        variants[f"all_shrink_{suffix}"] = (scale, scale, scale)
        variants[f"matcher_shrink_{suffix}"] = (0.0, scale, 0.0)
        variants[f"curve_shrink_{suffix}"] = (0.0, 0.0, scale)
        variants[f"matcher_curve_shrink_{suffix}"] = (0.0, scale, scale)
        variants[f"matcher_minus_curve_{suffix}"] = (0.0, scale, -scale)
    for scale in (0.10, 0.15, 0.20, 0.30, 0.40):
        suffix = f"{int(scale * 100):03d}"
        variants[f"matcher_shrink_{suffix}"] = (0.0, scale, 0.0)
        variants[f"sg_matcher_{suffix}"] = (1.0, scale, 0.0)
    return variants


def run(args: argparse.Namespace) -> dict[str, object]:
    summary = json.loads(args.nested_summary.read_text(encoding="utf-8"))
    frame = pd.read_parquet(args.candidate_cache).reset_index(drop=True)
    oof_ids = pd.read_parquet(args.oof_ids, columns=["id"])
    raw = np.asarray(np.load(args.raw_public_oof, mmap_mode="r"), float)
    smooth = np.asarray(np.load(args.smooth_public_oof, mmap_mode="r"), float)
    positions = frame["id"].astype(str).map(
        pd.Series(np.arange(len(oof_ids)), index=oof_ids["id"].astype(str))
    )
    if positions.isna().any():
        raise RuntimeError("candidate IDs are absent from the public OOF contract")
    index = positions.to_numpy(int)
    raw_components = np.column_stack(
        [
            0.40 * (smooth[index] - raw[index]),
            frame["matcher_direct_correction"].to_numpy(float),
            frame["complete_well_curve_correction"].to_numpy(float),
        ]
    )

    well_frame = frame.groupby("well", sort=True)["field"].first().reset_index()
    wells = frame["well"].astype(str)
    records = {
        (int(row["seed"]), int(row["fold"]), int(row["field"])): np.asarray(
            [row["weights"][name] for name in COMPONENTS], float
        )
        for row in summary["selection_records"]
    }
    seed_contributions = []
    for seed in summary["seeds"]:
        splitter = StratifiedKFold(
            n_splits=int(summary["folds"]), shuffle=True, random_state=int(seed)
        )
        fold_map: dict[str, int] = {}
        for fold, (_, valid) in enumerate(
            splitter.split(well_frame["well"], well_frame["field"])
        ):
            for well in well_frame.iloc[valid]["well"]:
                fold_map[str(well)] = int(fold)
        row_fold = wells.map(fold_map).to_numpy(int)
        weighted = np.zeros_like(raw_components)
        for fold in range(int(summary["folds"])):
            for field in range(int(summary["fields"])):
                mask = (row_fold == fold) & frame["field"].eq(field).to_numpy()
                weighted[mask] = raw_components[mask] * records[(seed, fold, field)]
        seed_contributions.append(weighted)
    contributions = np.mean(seed_contributions, axis=0)

    active_fields = tuple(int(part) for part in args.active_fields.split(","))
    active = frame["field"].isin(active_fields).to_numpy()
    discovery = active & frame["validation_split"].eq("discovery").to_numpy()
    holdout1 = active & frame["validation_split"].eq("holdout1").to_numpy()
    holdout2 = active & frame["validation_split"].eq("holdout2").to_numpy()
    holdout = holdout1 | holdout2
    target = frame["target_tvt"].to_numpy(float)
    proxies = {
        name: frame[column].to_numpy(float)
        for name, column in PROXY_COLUMNS.items()
    }
    masks = {
        "active_discovery": discovery,
        "active_holdout1": holdout1,
        "active_holdout2": holdout2,
        "active_holdout": holdout,
        "active_all": active,
        "all_wells": np.ones(len(frame), bool),
    }

    reports = {}
    for variant_position, (name, scales) in enumerate(predefined_variants().items()):
        correction = np.zeros(len(frame), float)
        correction[active] = contributions[active] @ np.asarray(scales, float)
        proxy_results = {}
        for proxy_name, baseline in proxies.items():
            candidate = baseline + correction
            proxy_results[proxy_name] = {}
            for mask_name, mask in masks.items():
                baseline_score = rmse(target[mask], baseline[mask])
                candidate_score = rmse(target[mask], candidate[mask])
                proxy_results[proxy_name][mask_name] = {
                    "rows": int(mask.sum()),
                    "wells": int(frame.loc[mask, "well"].nunique()),
                    "baseline_rmse": baseline_score,
                    "candidate_rmse": candidate_score,
                    "improvement": baseline_score - candidate_score,
                }
        exact_candidate = proxies["exact_public"] + correction
        reports[name] = {
            "scales": dict(zip(COMPONENTS, scales)),
            "proxy_results": proxy_results,
            "active_holdout_minimum_proxy_improvement": float(
                min(
                    result["active_holdout"]["improvement"]
                    for result in proxy_results.values()
                )
            ),
            "active_holdout_mean_proxy_improvement": float(
                np.mean(
                    [
                        result["active_holdout"]["improvement"]
                        for result in proxy_results.values()
                    ]
                )
            ),
            "active_exact_bootstrap": paired_well_bootstrap(
                frame,
                target,
                proxies["exact_public"],
                exact_candidate,
                active,
                args.bootstrap_seed + variant_position,
                args.bootstrap_draws,
            ),
            "active_correction_distribution": {
                "mean": float(np.mean(correction[active])),
                "p50_abs": float(np.quantile(np.abs(correction[active]), 0.50)),
                "p95_abs": float(np.quantile(np.abs(correction[active]), 0.95)),
                "maximum_abs": float(np.max(np.abs(correction[active]))),
            },
        }

    ranked = sorted(
        reports,
        key=lambda name: (
            reports[name]["active_holdout_minimum_proxy_improvement"],
            reports[name]["active_holdout_mean_proxy_improvement"],
        ),
        reverse=True,
    )
    output = {
        "method": "active_field_nested_component_ablation",
        "active_fields": list(active_fields),
        "active_wells": int(frame.loc[active, "well"].nunique()),
        "active_rows": int(active.sum()),
        "contracts": {
            "outer_oof_component_weights_preserved": True,
            "variant_scales_are_predefined": True,
            "suffix_target_not_used_in_correction": True,
            "kaggle_public_score_not_used_for_variant_ranking": True,
        },
        "ranking_by_active_holdout_minimum_proxy_improvement": ranked,
        "reports": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ranking": ranked, "top": reports[ranked[0]]}, indent=2))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-cache", type=Path, required=True)
    parser.add_argument("--nested-summary", type=Path, required=True)
    parser.add_argument("--oof-ids", type=Path, required=True)
    parser.add_argument("--raw-public-oof", type=Path, required=True)
    parser.add_argument("--smooth-public-oof", type=Path, required=True)
    parser.add_argument("--active-fields", default="3,4")
    parser.add_argument("--bootstrap-draws", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260801)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
