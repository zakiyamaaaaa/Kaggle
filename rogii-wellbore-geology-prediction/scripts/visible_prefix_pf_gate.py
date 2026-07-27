"""Evaluate public-style visible-prefix PF/beam candidate selection locally."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from generic_core_sp45_local import load_selector_namespace
from visible_prefix_poly_gate import (
    PROFILES,
    CUT_FRACTIONS,
    load_frame,
    profile_move,
    summarize,
)

PF_PROFILES = {
    **PROFILES,
    "strict": {
        **PROFILES["conservative"],
        "min_gain": 3.0,
        "max_best": 4.0,
        "p95_hard": 15.0,
        "delta_hard": 10.0,
        "move_hard": 4.0,
    },
}


def variant_grid(namespace: dict[str, object]) -> list[str]:
    variants = set(namespace["SELECTOR_BIN_VARIANTS"].values())
    variants.add(str(namespace["SELECTOR_GLOBAL_VARIANT"]))
    for scale in (3, 5, 8, 12):
        for hold in (0.0, 0.05, 0.10, 0.15, 0.20, 0.25):
            variants.add(f"pf_scale_{scale:g}_hold_{hold:g}")
        for beam in (0.05, 0.10, 0.20, 0.30):
            for hold in (0.0, 0.05, 0.10, 0.15, 0.20):
                variants.add(
                    f"pf_scale_{scale:g}_beam_{beam:g}_hold_{hold:g}"
                )
    return sorted(variants)


def prediction_array(value: object) -> np.ndarray:
    if isinstance(value, tuple):
        value = value[0]
    return np.asarray(value, dtype=float)


def candidate_pool(
    horizontal: pd.DataFrame,
    typewell: pd.DataFrame,
    namespace: dict[str, object],
    variants: list[str],
    seeds: int,
    particles: int,
) -> dict[str, np.ndarray]:
    run_pf_scales = namespace["run_pf_lik_ensemble_scales"]
    run_beam = namespace["run_beam_ensemble"]
    apply_selector = namespace["apply_selector_variant"]
    pf_by_scale = run_pf_scales(
        horizontal,
        typewell,
        n_particles=particles,
        n_seeds=seeds,
    )
    try:
        beam = run_beam(horizontal, typewell)
    except Exception:
        beam = pf_by_scale.get(
            "pf_scale_8", next(iter(pf_by_scale.values()))
        )
    known = pd.to_numeric(
        horizontal.loc[horizontal["TVT_input"].notna(), "TVT_input"],
        errors="coerce",
    ).dropna()
    if len(known) < 30:
        return {}
    last_tvt = float(known.iloc[-1])
    pool: dict[str, np.ndarray] = {}
    for variant in variants:
        try:
            prediction = prediction_array(
                apply_selector(
                    variant,
                    pf_by_scale,
                    beam,
                    last_tvt,
                    hw=horizontal,
                    tw=typewell,
                )
            )
            if (
                len(prediction) == len(horizontal)
                and np.isfinite(prediction).sum() >= len(horizontal) // 20
            ):
                pool["pf|" + variant] = prediction
        except Exception:
            continue
    return pool


def select_pf_candidate(
    horizontal: pd.DataFrame,
    typewell: pd.DataFrame,
    namespace: dict[str, object],
    variants: list[str],
    calibration_seeds: int,
    final_seeds: int,
    particles: int,
) -> tuple[np.ndarray | None, dict[str, object]]:
    tvt_input = pd.to_numeric(
        horizontal["TVT_input"], errors="coerce"
    ).to_numpy(float)
    hidden = ~np.isfinite(tvt_input)
    if not hidden.any():
        return None, {"status": "skip_no_hidden"}
    first_hidden = int(np.flatnonzero(hidden)[0])
    known_prefix = np.flatnonzero(
        np.isfinite(tvt_input) & (np.arange(len(horizontal)) < first_hidden)
    )
    if len(known_prefix) < 140:
        return None, {
            "status": "skip_short_prefix",
            "known_prefix": int(len(known_prefix)),
        }

    selector_variant = str(
        namespace["selector_well_code"](horizontal)[1]
    )
    default_name = "pf|" + selector_variant
    scores: dict[str, list[float]] = {}
    cut_rows: list[dict[str, object]] = []
    for fraction in CUT_FRACTIONS:
        cut_position = int(round(len(known_prefix) * fraction))
        cut_position = max(50, min(cut_position, len(known_prefix) - 35))
        cutoff_index = int(known_prefix[cut_position - 1])
        holdout_indices = known_prefix[cut_position:]
        masked = horizontal.copy(deep=True)
        masked.loc[masked.index > cutoff_index, "TVT_input"] = np.nan
        pool = candidate_pool(
            masked,
            typewell,
            namespace,
            variants,
            calibration_seeds,
            particles,
        )
        local: list[tuple[float, str]] = []
        for name, prediction in pool.items():
            error = prediction[holdout_indices] - tvt_input[holdout_indices]
            rmse = float(np.sqrt(np.mean(error * error)))
            if np.isfinite(rmse):
                scores.setdefault(name, []).append(rmse)
                local.append((rmse, name))
        local.sort()
        row: dict[str, object] = {
            "cut_fraction": float(fraction),
            "holdout_rows": int(len(holdout_indices)),
            "candidates": int(len(pool)),
        }
        if local:
            row["best_name"] = local[0][1]
            row["best_rmse"] = float(local[0][0])
            row["default_rmse"] = float(
                next(
                    (
                        score
                        for score, name in local
                        if name == default_name
                    ),
                    np.nan,
                )
            )
        cut_rows.append(row)
    if not scores:
        return None, {"status": "skip_no_scores"}

    aggregate = {
        name: float(np.median(values) + 0.10 * np.std(values))
        for name, values in scores.items()
    }
    ordered = sorted((score, name) for name, score in aggregate.items())
    best_score, best_name = ordered[0]
    second_score = ordered[1][0] if len(ordered) > 1 else best_score
    pf_scores = [
        score for name, score in aggregate.items() if name.startswith("pf|")
    ]
    default_score = float(
        aggregate.get(default_name, np.median(pf_scores))
    )
    comparable = 0
    wins = 0
    for row in cut_rows:
        default_rmse = float(row.get("default_rmse", np.nan))
        if np.isfinite(default_rmse):
            comparable += 1
            if float(row.get("best_rmse", np.inf)) <= default_rmse - 0.25:
                wins += 1
    consistency = float(wins / comparable) if comparable else 0.0

    final_pool = candidate_pool(
        horizontal,
        typewell,
        namespace,
        variants,
        final_seeds,
        particles,
    )
    if best_name not in final_pool:
        return None, {
            "status": "skip_missing_final_candidate",
            "best_name": best_name,
        }
    return final_pool[best_name], {
        "status": "ok",
        "known_prefix": int(len(known_prefix)),
        "default_name": default_name,
        "best_name": best_name,
        "best_score": float(best_score),
        "second_score": float(second_score),
        "default_score": default_score,
        "gain": float(default_score - best_score),
        "rank_margin": float(second_score - best_score),
        "consistency": consistency,
        "cut_rows": cut_rows,
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    frame = load_frame(args)
    if args.evaluation_split:
        frame = frame[
            frame["validation_split"].isin(args.evaluation_split)
        ].copy()
        if frame.empty:
            raise RuntimeError("evaluation split filter selected no rows")
    namespace = load_selector_namespace(
        args.notebook,
        args.data_root,
        args.particles,
        args.final_seeds,
    )
    variants = variant_grid(namespace)
    args.candidate_cache.mkdir(parents=True, exist_ok=True)
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
        prediction_path = args.candidate_cache / f"{well}.npy"
        report_path = args.candidate_cache / f"{well}.json"
        if (
            prediction_path.exists()
            and report_path.exists()
            and not args.overwrite
        ):
            candidate = np.load(prediction_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            cached = True
        else:
            horizontal = pd.read_csv(
                args.data_root / "train" / f"{well}__horizontal_well.csv"
            )
            typewell = pd.read_csv(
                args.data_root / "train" / f"{well}__typewell.csv"
            )
            candidate_full, report = select_pf_candidate(
                horizontal,
                typewell,
                namespace,
                variants,
                args.calibration_seeds,
                args.final_seeds,
                args.particles,
            )
            row_indices = well_frame["row_idx"].to_numpy(int)
            candidate = (
                np.asarray(candidate_full, dtype=float)[row_indices]
                if candidate_full is not None
                else np.full(len(row_indices), np.nan)
            )
            np.save(prediction_path, candidate)
            report_path.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
            cached = False
        if len(candidate) != len(well_frame):
            raise RuntimeError(f"candidate length mismatch for {well}")
        report = dict(report)
        report.update(
            {
                "well": str(well),
                "validation_split": str(
                    well_frame["validation_split"].iloc[0]
                ),
            }
        )
        well_frame["pf_selected_candidate"] = candidate
        for proxy_name in proxies:
            base = well_frame[f"base_{proxy_name}"].to_numpy(float)
            for profile_name in PF_PROFILES:
                if not np.isfinite(candidate).all():
                    moved = base.copy()
                    move_report = {
                        "accepted": False,
                        "alpha": 0.0,
                        "max_move": 0.0,
                        "mean_abs_move": 0.0,
                        "max_abs_move": 0.0,
                        "delta_rmse": float("nan"),
                        "delta_p95": float("nan"),
                    }
                else:
                    moved, move_report = profile_move(
                        base,
                        candidate,
                        report,
                        profile_name,
                        PF_PROFILES,
                    )
                well_frame[f"{profile_name}_{proxy_name}"] = moved
                for key, value in move_report.items():
                    report[f"{profile_name}_{proxy_name}_{key}"] = value
        reports.append(report)
        output_parts.append(well_frame)
        print(
            f"{position}/{total_wells} {well}: "
            f"{'cached' if cached else 'computed'} "
            f"{report.get('status')} {report.get('best_name')} "
            f"gain={float(report.get('gain', np.nan)):.3f}",
            flush=True,
        )

    output = pd.concat(output_parts, ignore_index=True)
    prediction_columns = [
        f"base_{proxy}" for proxy in proxies
    ] + [
        f"{profile}_{proxy}"
        for profile in PF_PROFILES
        for proxy in proxies
    ]
    report_frame = pd.DataFrame(reports)
    summary: dict[str, object] = {
        "method": "visible_prefix_pf_gate_on_full_pipeline_oof_proxies",
        "calibration_seeds": int(args.calibration_seeds),
        "final_seeds": int(args.final_seeds),
        "particles": int(args.particles),
        "variant_count": int(len(variants)),
        "cut_fractions": CUT_FRACTIONS,
        "profiles": PF_PROFILES,
        "same_well_contact_used": False,
        "formation_surfaces_used": False,
        "suffix_target_used_for_selection": False,
        "splits": {},
    }
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
        for profile_name in PF_PROFILES:
            split_summary[f"{profile_name}_accepted_wells"] = int(
                report_subset[
                    f"{profile_name}_artifact_accepted"
                ].sum()
            )
        summary["splits"][split] = split_summary

    discovery = summary["splits"]["discovery"]
    objectives = {}
    if discovery["rows"]:
        for profile_name in PF_PROFILES:
            improvements = {
                proxy: float(
                    discovery[f"base_{proxy}"]
                    - discovery[f"{profile_name}_{proxy}"]
                )
                for proxy in proxies
            }
            objectives[profile_name] = {
                "proxy_improvements": improvements,
                "mean_improvement": float(
                    np.mean(list(improvements.values()))
                ),
                "minimum_improvement": float(
                    np.min(list(improvements.values()))
                ),
            }
    selected = args.selected_profile
    if selected is None and objectives:
        selected = max(
            objectives,
            key=lambda name: (
                objectives[name]["minimum_improvement"],
                objectives[name]["mean_improvement"],
            ),
        )
    summary["discovery_selection"] = {
        "objectives": objectives,
        "selected": selected,
    }
    holdout = summary["splits"]["holdout_combined"]
    if selected is not None:
        summary["selected_holdout_improvements"] = {
            proxy: float(
                holdout[f"base_{proxy}"] - holdout[f"{selected}_{proxy}"]
            )
            for proxy in proxies
        }
        summary["selected_holdout_all_proxies_improve"] = all(
            value > 0
            for value in summary[
                "selected_holdout_improvements"
            ].values()
        )
    else:
        summary["selected_holdout_improvements"] = None
        summary["selected_holdout_all_proxies_improve"] = None

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
    parser.add_argument("--calibration-seeds", type=int, default=4)
    parser.add_argument("--final-seeds", type=int, default=4)
    parser.add_argument("--particles", type=int, default=80)
    parser.add_argument(
        "--evaluation-split",
        choices=("discovery", "holdout1", "holdout2"),
        action="append",
        default=[],
    )
    parser.add_argument(
        "--selected-profile",
        choices=tuple(PF_PROFILES),
        default=None,
        help="Use a profile frozen by a prior discovery run.",
    )
    parser.add_argument("--candidate-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
