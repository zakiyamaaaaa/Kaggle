"""Evaluate PF seed-branch midpoint hedge variants on legal local OOF proxies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from generic_core_sp45_local import load_selector_namespace
from visible_prefix_poly_gate import load_frame, summarize


VARIANTS = {
    "no_hedge": {"strength": 0.0, "cap": 0.0},
    "reduced_s040_cap100": {"strength": 0.40, "cap": 1.00},
    "reduced_s060_cap100": {"strength": 0.60, "cap": 1.00},
    "public_s060_cap200": {"strength": 0.60, "cap": 2.00},
    "strong_s080_cap200": {"strength": 0.80, "cap": 2.00},
    "extended_s060_cap300": {"strength": 0.60, "cap": 3.00},
}
MIN_MASS = 0.25
MIN_SEPARATION = 4.0
MAX_SEPARATION = 40.0


def branch_shift(
    stats: dict[str, object],
    strength: float,
    cap: float,
) -> tuple[float, str]:
    required = {
        "center_low",
        "center_high",
        "mass_low",
        "mass_high",
        "weighted_center",
    }
    if not required.issubset(stats):
        return 0.0, "missing_stats"
    center_low = float(stats["center_low"])
    center_high = float(stats["center_high"])
    mass_low = float(stats["mass_low"])
    mass_high = float(stats["mass_high"])
    weighted_center = float(stats["weighted_center"])
    separation = abs(center_high - center_low)
    if min(mass_low, mass_high) < MIN_MASS:
        return 0.0, "skip_minor_mass"
    if not (MIN_SEPARATION <= separation <= MAX_SEPARATION):
        return 0.0, "skip_separation"
    midpoint = 0.5 * (center_low + center_high)
    shift = float(np.clip(strength * (midpoint - weighted_center), -cap, cap))
    return shift, "applied" if abs(shift) >= 0.01 else "skip_zero"


def run(args: argparse.Namespace) -> dict[str, object]:
    frame = load_frame(args)
    namespace = load_selector_namespace(
        args.notebook,
        args.data_root,
        args.particles,
        args.pf_seeds,
    )
    run_pf_scales = namespace["run_pf_lik_ensemble_scales"]
    args.stats_cache.mkdir(parents=True, exist_ok=True)

    proxies = {
        "artifact": "artifact_tvt",
        "hgb": "hgb_oof_tvt",
        "ridge": "ridge_pp_savgol17",
    }
    for proxy_name, proxy_column in proxies.items():
        frame[f"base_{proxy_name}"] = (
            args.sp45_weight * frame["sp45_sgridge_d2_b050"]
            + (1.0 - args.sp45_weight) * frame[proxy_column]
        )

    reports: list[dict[str, object]] = []
    output_parts: list[pd.DataFrame] = []
    total_wells = int(frame["well"].nunique())
    for position, (well, well_frame) in enumerate(
        frame.groupby("well", sort=True), 1
    ):
        well_frame = well_frame.sort_values("row_idx").copy()
        cache_path = args.stats_cache / f"{well}.json"
        if cache_path.exists() and not args.overwrite:
            stats = json.loads(cache_path.read_text(encoding="utf-8"))
            cached = True
        else:
            horizontal = pd.read_csv(
                args.data_root / "train" / f"{well}__horizontal_well.csv"
            )
            typewell = pd.read_csv(
                args.data_root / "train" / f"{well}__typewell.csv"
            )
            stats: dict[str, object] = {}
            run_pf_scales(
                horizontal,
                typewell,
                n_particles=args.particles,
                n_seeds=args.pf_seeds,
                branch_stats=stats,
            )
            stats.update(
                {
                    "well": str(well),
                    "pf_seeds": int(args.pf_seeds),
                    "particles": int(args.particles),
                }
            )
            cache_path.write_text(
                json.dumps(stats, indent=2) + "\n", encoding="utf-8"
            )
            cached = False

        report: dict[str, object] = {
            **stats,
            "well": str(well),
            "validation_split": str(
                well_frame["validation_split"].iloc[0]
            ),
        }
        for variant_name, parameters in VARIANTS.items():
            shift, reason = branch_shift(stats, **parameters)
            report[f"{variant_name}_shift"] = shift
            report[f"{variant_name}_reason"] = reason
            for proxy_name in proxies:
                well_frame[f"{variant_name}_{proxy_name}"] = (
                    well_frame[f"base_{proxy_name}"] + shift
                )
        reports.append(report)
        output_parts.append(well_frame)
        print(
            f"{position}/{total_wells} {well}: "
            f"{'cached' if cached else 'computed'} "
            f"sep={float(stats.get('center_high', np.nan)) - float(stats.get('center_low', np.nan)):.3f} "
            f"public_shift={float(report['public_s060_cap200_shift']):+.3f}",
            flush=True,
        )

    output = pd.concat(output_parts, ignore_index=True)
    prediction_columns = [
        f"base_{proxy}" for proxy in proxies
    ] + [
        f"{variant}_{proxy}"
        for variant in VARIANTS
        for proxy in proxies
    ]
    summary: dict[str, object] = {
        "method": "generic_core_pf_seed_branch_hedge_local",
        "pf_seeds": int(args.pf_seeds),
        "particles": int(args.particles),
        "sp45_weight": float(args.sp45_weight),
        "qualification": {
            "minimum_minor_mass": MIN_MASS,
            "minimum_separation": MIN_SEPARATION,
            "maximum_separation": MAX_SEPARATION,
        },
        "variants": VARIANTS,
        "suffix_target_used_for_shift": False,
        "same_well_contact_used": False,
        "splits": {},
    }
    report_frame = pd.DataFrame(reports)
    for split in (
        "discovery",
        "holdout1",
        "holdout2",
        "holdout_combined",
        "all",
    ):
        if split == "holdout_combined":
            subset = output[
                output["validation_split"].isin(["holdout1", "holdout2"])
            ]
            report_subset = report_frame[
                report_frame["validation_split"].isin(
                    ["holdout1", "holdout2"]
                )
            ]
        elif split == "all":
            subset = output
            report_subset = report_frame
        else:
            subset = output[output["validation_split"].eq(split)]
            report_subset = report_frame[
                report_frame["validation_split"].eq(split)
            ]
        split_summary = summarize(subset, prediction_columns)
        for variant in VARIANTS:
            split_summary[f"{variant}_applied_wells"] = int(
                report_subset[f"{variant}_reason"].eq("applied").sum()
            )
        summary["splits"][split] = split_summary

    discovery = summary["splits"]["discovery"]
    public_variant = "public_s060_cap200"
    objectives = {}
    for variant in VARIANTS:
        improvements = {
            proxy: float(
                discovery[f"{public_variant}_{proxy}"]
                - discovery[f"{variant}_{proxy}"]
            )
            for proxy in proxies
        }
        objectives[variant] = {
            "proxy_improvements_vs_public": improvements,
            "mean_improvement": float(np.mean(list(improvements.values()))),
            "minimum_improvement": float(np.min(list(improvements.values()))),
        }
    selected = max(
        objectives,
        key=lambda name: (
            objectives[name]["minimum_improvement"],
            objectives[name]["mean_improvement"],
        ),
    )
    summary["discovery_selection"] = {
        "baseline": public_variant,
        "objectives": objectives,
        "selected": selected,
    }
    holdout = summary["splits"]["holdout_combined"]
    summary["selected_holdout_improvements_vs_public"] = {
        proxy: float(
            holdout[f"{public_variant}_{proxy}"]
            - holdout[f"{selected}_{proxy}"]
        )
        for proxy in proxies
    }
    summary["selected_holdout_all_proxies_improve"] = all(
        value > 0
        for value in summary[
            "selected_holdout_improvements_vs_public"
        ].values()
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_parquet(args.output, index=False)
    report_frame.to_csv(args.report, index=False)
    args.summary.write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sp45-cache", type=Path, action="append", required=True
    )
    parser.add_argument("--notebook", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--artifact-oof", type=Path, required=True)
    parser.add_argument("--local-oof", type=Path, required=True)
    parser.add_argument("--discovery-summary", type=Path, required=True)
    parser.add_argument("--holdout1-summary", type=Path, required=True)
    parser.add_argument("--holdout2-summary", type=Path, required=True)
    parser.add_argument("--sp45-weight", type=float, default=0.60)
    parser.add_argument("--pf-seeds", type=int, default=8)
    parser.add_argument("--particles", type=int, default=100)
    parser.add_argument("--stats-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
