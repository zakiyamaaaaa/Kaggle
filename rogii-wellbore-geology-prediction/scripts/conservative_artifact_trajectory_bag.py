"""Audit a conservative field-free bag around the exact 7.474 proxy.

The candidate combines three previously deployable, target-free signals:
10% of the model-package artifact trajectory, the frozen SG601 public-learned
delta, and 10% of the bounded complete-well matcher correction.  The weights
are fixed inputs; suffix TVT is used only for reporting metrics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


PROXY_COLUMNS = {
    "exact_public": "exact_7474_proxy",
    "artifact": "public_s060_cap200_artifact",
    "hgb": "public_s060_cap200_hgb",
    "ridge": "public_s060_cap200_ridge",
}
PROXY_ALTERNATIVES = {
    "exact_public": "base_artifact",
    "artifact": "base_artifact",
    "hgb": "base_hgb",
    "ridge": "base_ridge",
}
SPLITS = ("discovery", "holdout1", "holdout2")


def rmse(target: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(target - prediction))))


def bootstrap(
    frame: pd.DataFrame,
    target: np.ndarray,
    baseline: np.ndarray,
    candidate: np.ndarray,
    mask: np.ndarray,
    draws: int,
    seed: int,
) -> dict[str, float | int]:
    local = pd.DataFrame(
        {
            "well": frame.loc[mask, "well"].astype(str).to_numpy(),
            "rows": 1,
            "baseline_se": np.square(target[mask] - baseline[mask]),
            "candidate_se": np.square(target[mask] - candidate[mask]),
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
        "wells": int(len(local)),
        "draws": int(draws),
        "probability_positive": float(np.mean(values > 0.0)),
        "p01": float(np.quantile(values, 0.01)),
        "p05": float(np.quantile(values, 0.05)),
        "p50": float(np.quantile(values, 0.50)),
        "p95": float(np.quantile(values, 0.95)),
    }


def score_splits(
    frame: pd.DataFrame,
    target: np.ndarray,
    baseline: np.ndarray,
    candidate: np.ndarray,
) -> dict[str, object]:
    report = {}
    for split in (*SPLITS, "holdout", "all"):
        if split == "all":
            mask = np.ones(len(frame), bool)
        elif split == "holdout":
            mask = ~frame["validation_split"].eq("discovery").to_numpy()
        else:
            mask = frame["validation_split"].eq(split).to_numpy()
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
    oof_ids = pd.read_parquet(args.oof_ids, columns=["id"])
    raw = np.asarray(np.load(args.raw_public_oof, mmap_mode="r"), float)
    smooth = np.asarray(np.load(args.smooth_public_oof, mmap_mode="r"), float)
    positions = frame["id"].astype(str).map(
        pd.Series(np.arange(len(oof_ids)), index=oof_ids["id"].astype(str))
    )
    if positions.isna().any():
        raise RuntimeError("candidate IDs are absent from public OOF contract")
    index = positions.to_numpy(int)
    sg601 = args.learned_weight * (smooth[index] - raw[index])
    matcher = frame["matcher_direct_correction"].to_numpy(float)
    target = frame["target_tvt"].to_numpy(float)

    results = {}
    candidates = {}
    for name, baseline_column in PROXY_COLUMNS.items():
        baseline = frame[baseline_column].to_numpy(float)
        alternative = frame[PROXY_ALTERNATIVES[name]].to_numpy(float)
        candidate = (
            baseline
            + args.artifact_weight * (alternative - baseline)
            + args.sg_scale * sg601
            + args.matcher_scale * matcher
        )
        candidates[name] = candidate
        results[name] = score_splits(frame, target, baseline, candidate)

    exact_baseline = frame[PROXY_COLUMNS["exact_public"]].to_numpy(float)
    exact_candidate = candidates["exact_public"]
    all_mask = np.ones(len(frame), bool)
    holdout_mask = ~frame["validation_split"].eq("discovery").to_numpy()
    all_bootstrap = bootstrap(
        frame,
        target,
        exact_baseline,
        exact_candidate,
        all_mask,
        args.bootstrap_draws,
        args.bootstrap_seed,
    )
    holdout_bootstrap = bootstrap(
        frame,
        target,
        exact_baseline,
        exact_candidate,
        holdout_mask,
        args.bootstrap_draws,
        args.bootstrap_seed + 1,
    )
    correction = exact_candidate - exact_baseline
    exact_all = results["exact_public"]["all"]
    sensitivity_floor = min(
        results[name]["all"]["improvement"] for name in PROXY_COLUMNS
    )
    promotion = {
        "exact_effect_gate_ft": float(args.effect_gate),
        "passes_exact_effect_gate": bool(
            exact_all["improvement"] >= args.effect_gate
        ),
        "all_exact_splits_improve": bool(
            all(
                results["exact_public"][split]["improvement"] > 0.0
                for split in SPLITS
            )
        ),
        "all_well_bootstrap_p01_positive": bool(all_bootstrap["p01"] > 0.0),
        "holdout_bootstrap_p01_positive": bool(holdout_bootstrap["p01"] > 0.0),
        "all_proxy_sensitivity_nonnegative": bool(sensitivity_floor >= 0.0),
    }
    promotion["passes_strict_local_gate"] = bool(
        promotion["passes_exact_effect_gate"]
        and promotion["all_exact_splits_improve"]
        and promotion["all_well_bootstrap_p01_positive"]
        and promotion["holdout_bootstrap_p01_positive"]
        and promotion["all_proxy_sensitivity_nonnegative"]
    )
    output = {
        "method": "conservative_field_free_artifact_trajectory_bag",
        "weights": {
            "artifact": float(args.artifact_weight),
            "public_learned_sg601": float(args.sg_scale),
            "matcher": float(args.matcher_scale),
            "public_learned_branch": float(args.learned_weight),
        },
        "contracts": {
            "weights_are_fixed_for_reproduction": True,
            "candidate_selected_during_current_200w_screening": True,
            "legacy_holdout_is_not_fully_untouched_after_screening": True,
            "suffix_target_used_only_for_evaluation": True,
            "field_and_xy_not_used": True,
            "same_well_contact_not_used": True,
            "artifact_and_components_are_legal_well_oof": True,
        },
        "proxy_results": results,
        "bootstrap": {
            "all_wells": all_bootstrap,
            "holdout_only": holdout_bootstrap,
        },
        "exact_correction_distribution": {
            "mean": float(np.mean(correction)),
            "std": float(np.std(correction)),
            "p50_abs": float(np.quantile(np.abs(correction), 0.50)),
            "p95_abs": float(np.quantile(np.abs(correction), 0.95)),
            "maximum_abs": float(np.max(np.abs(correction))),
        },
        "proxy_sensitivity_floor": float(sensitivity_floor),
        "promotion": promotion,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-cache", type=Path, required=True)
    parser.add_argument("--oof-ids", type=Path, required=True)
    parser.add_argument("--raw-public-oof", type=Path, required=True)
    parser.add_argument("--smooth-public-oof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifact-weight", type=float, default=0.10)
    parser.add_argument("--sg-scale", type=float, default=1.0)
    parser.add_argument("--matcher-scale", type=float, default=0.10)
    parser.add_argument("--learned-weight", type=float, default=0.40)
    parser.add_argument("--bootstrap-draws", type=int, default=50000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260831)
    parser.add_argument("--effect-gate", type=float, default=0.03)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
