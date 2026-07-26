"""Screen generic-core projection changes with legal learned-branch OOF proxies.

The public fleongg learned models do not ship train OOF predictions, and their
all-train predictions would leak on train wells.  This script therefore tests
whether a projection change keeps the same sign after the public 60/40 blend
when the learned branch is replaced by multiple legal group-OOF proxies.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def metrics(
    target: np.ndarray,
    prediction: np.ndarray,
    wells: np.ndarray,
) -> dict[str, float]:
    error = prediction - target
    by_well = pd.DataFrame(
        {"well": wells, "square_error": error * error}
    ).groupby("well", sort=False)["square_error"].mean()
    well_rmse = np.sqrt(by_well.to_numpy(float))
    return {
        "rmse": float(np.sqrt(np.mean(error * error))),
        "well_rmse_p50": float(np.quantile(well_rmse, 0.50)),
        "well_rmse_p90": float(np.quantile(well_rmse, 0.90)),
    }


def paired_diagnostics(
    target: np.ndarray,
    current: np.ndarray,
    challenger: np.ndarray,
    wells: np.ndarray,
    seed: int,
    bootstrap_samples: int,
) -> dict[str, object]:
    rows = []
    for well in pd.unique(wells):
        mask = wells == well
        current_error = current[mask] - target[mask]
        challenger_error = challenger[mask] - target[mask]
        rows.append(
            {
                "well": str(well),
                "rows": int(mask.sum()),
                "current_sse": float(np.sum(current_error * current_error)),
                "challenger_sse": float(
                    np.sum(challenger_error * challenger_error)
                ),
                "current_rmse": float(np.sqrt(np.mean(current_error**2))),
                "challenger_rmse": float(
                    np.sqrt(np.mean(challenger_error**2))
                ),
            }
        )
    by_well = pd.DataFrame(rows)
    rng = np.random.default_rng(seed)
    improvements = np.empty(bootstrap_samples, dtype=float)
    sample_size = len(by_well)
    row_counts = by_well["rows"].to_numpy(float)
    current_sse = by_well["current_sse"].to_numpy(float)
    challenger_sse = by_well["challenger_sse"].to_numpy(float)
    for index in range(bootstrap_samples):
        sampled = rng.integers(0, sample_size, size=sample_size)
        denominator = row_counts[sampled].sum()
        current_rmse = np.sqrt(current_sse[sampled].sum() / denominator)
        challenger_rmse = np.sqrt(
            challenger_sse[sampled].sum() / denominator
        )
        improvements[index] = current_rmse - challenger_rmse
    return {
        "well_wins": int(
            (by_well["challenger_rmse"] < by_well["current_rmse"]).sum()
        ),
        "wells": int(sample_size),
        "bootstrap_samples": int(bootstrap_samples),
        "bootstrap_improvement_probability": float(
            np.mean(improvements > 0.0)
        ),
        "bootstrap_improvement_p05": float(
            np.quantile(improvements, 0.05)
        ),
        "bootstrap_improvement_p50": float(
            np.quantile(improvements, 0.50)
        ),
        "bootstrap_improvement_p95": float(
            np.quantile(improvements, 0.95)
        ),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    frame = pd.read_parquet(args.sp45_cache).reset_index(drop=True)
    required = {
        "id",
        "well",
        "split",
        "target_tvt",
        "ridge_pp_savgol17",
        "sp45_sgridge_d3_b075",
        "sp45_sgridge_d2_b050",
    }
    if not required.issubset(frame.columns):
        raise ValueError(f"SP45 cache missing: {sorted(required - set(frame.columns))}")

    truth = pd.read_parquet(
        args.train_gt,
        columns=["id", "last_known_TVT"],
    )
    artifact_delta = np.load(args.artifact_oof, mmap_mode="r")
    if len(truth) != len(artifact_delta):
        raise RuntimeError("artifact OOF and train_gt lengths differ")
    truth["artifact_tvt"] = (
        truth["last_known_TVT"].to_numpy(float)
        + np.asarray(artifact_delta, dtype=float)
    )
    frame = frame.merge(
        truth[["id", "artifact_tvt"]],
        on="id",
        how="left",
        validate="one_to_one",
    )
    local = pd.read_csv(
        args.local_oof,
        usecols=["_oof_id", "hgb_oof_tvt"],
    ).rename(columns={"_oof_id": "id"})
    frame = frame.merge(local, on="id", how="left", validate="one_to_one")
    if frame[["artifact_tvt", "hgb_oof_tvt"]].isna().any().any():
        raise RuntimeError("learned proxy ID alignment failed")

    target = frame["target_tvt"].to_numpy(float)
    wells = frame["well"].astype(str).to_numpy()
    current_sp45 = frame["sp45_sgridge_d3_b075"].to_numpy(float)
    challenger_sp45 = frame["sp45_sgridge_d2_b050"].to_numpy(float)
    proxies = {
        "model_package_artifact_oof": frame["artifact_tvt"].to_numpy(float),
        "local_hgb_group_oof": frame["hgb_oof_tvt"].to_numpy(float),
        "ridge_pp_proxy": frame["ridge_pp_savgol17"].to_numpy(float),
    }
    result: dict[str, object] = {
        "method": "generic_core_projection_sensitivity_with_legal_oof_proxies",
        "sp45_weight": args.sp45_weight,
        "learned_proxy_weight": 1.0 - args.sp45_weight,
        "current_projection": {"degree": 3, "blend": 0.75},
        "challenger_projection": {"degree": 2, "blend": 0.50},
        "public_learned_oof_available": False,
        "branch_hedge_included": False,
        "splits": {},
    }
    for split_index, split in enumerate(["discovery", "holdout", "combined"]):
        mask = (
            np.ones(len(frame), dtype=bool)
            if split == "combined"
            else frame["split"].eq(split).to_numpy()
        )
        split_result = {}
        for proxy_index, (name, proxy) in enumerate(proxies.items()):
            current = (
                args.sp45_weight * current_sp45
                + (1.0 - args.sp45_weight) * proxy
            )
            challenger = (
                args.sp45_weight * challenger_sp45
                + (1.0 - args.sp45_weight) * proxy
            )
            current_metrics = metrics(
                target[mask], current[mask], wells[mask]
            )
            challenger_metrics = metrics(
                target[mask], challenger[mask], wells[mask]
            )
            split_result[name] = {
                "current": current_metrics,
                "challenger": challenger_metrics,
                "rmse_improvement": (
                    current_metrics["rmse"] - challenger_metrics["rmse"]
                ),
                "paired": paired_diagnostics(
                    target[mask],
                    current[mask],
                    challenger[mask],
                    wells[mask],
                    args.seed + split_index * 10 + proxy_index,
                    args.bootstrap_samples,
                ),
            }
        result["splits"][split] = split_result

    holdout = result["splits"]["holdout"]
    result["holdout_all_proxies_improve"] = all(
        record["rmse_improvement"] > 0 for record in holdout.values()
    )
    result["interpretation"] = (
        "This is a projection-effect sensitivity test, not an exact reproduction "
        "of the public fleongg learned branch."
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sp45-cache", type=Path, required=True)
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--artifact-oof", type=Path, required=True)
    parser.add_argument("--local-oof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sp45-weight", type=float, default=0.60)
    parser.add_argument("--bootstrap-samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
