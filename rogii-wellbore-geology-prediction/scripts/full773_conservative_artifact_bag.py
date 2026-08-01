"""Evaluate the frozen conservative artifact bag on all 773 wells.

The first 200 wells were used by earlier screening.  The remaining 573 wells
are reported separately and are never used to change the primary weights.
All candidate components are inference-safe OOF trajectories; suffix TVT is
read only after predictions have been reconstructed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from bounded_complete_well_matcher import build_field_map, scan_complete_well
from generic_core_branch_hedge_local import branch_shift


PRIMARY = "artifact015_sg601_matcher010_centered"


def rmse(target: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(target - prediction))))


def load_screening_wells(paths: list[Path]) -> set[str]:
    wells: set[str] = set()
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        wells.update(map(str, record["sampled_wells"]))
    return wells


def load_branch_shifts(wells: pd.Series, cache: Path) -> np.ndarray:
    shifts = {}
    for well in sorted(wells.astype(str).unique()):
        path = cache / f"{well}.json"
        if not path.exists():
            raise RuntimeError(f"missing PF branch statistics: {path}")
        shifts[well] = branch_shift(
            json.loads(path.read_text(encoding="utf-8")),
            strength=0.60,
            cap=2.00,
        )[0]
    return wells.astype(str).map(shifts).to_numpy(float)


def matcher_direct_correction(
    frame: pd.DataFrame,
    data_root: Path,
    legacy_cache: Path,
    output_cache: Path,
) -> tuple[np.ndarray, dict[str, int]]:
    output_cache.mkdir(parents=True, exist_ok=True)
    parts = []
    counters = {"fixed_cached": 0, "legacy_cached": 0, "computed": 0}
    total = int(frame["well"].nunique())
    for position, (well, part) in enumerate(frame.groupby("well", sort=True), 1):
        well = str(well)
        part = part.sort_values("row_index")
        row_index = part["row_index"].to_numpy(int)
        fixed_path = output_cache / f"{well}.npz"
        legacy_path = legacy_cache / f"{well}.npz"
        if fixed_path.exists():
            with np.load(fixed_path, allow_pickle=False) as saved:
                if not np.array_equal(saved["row_index"].astype(int), row_index):
                    raise RuntimeError(f"{well}: fixed matcher cache rows changed")
                direct = saved["direct_correction"].astype(float)
            source = "fixed_cached"
        else:
            horizontal = pd.read_csv(
                data_root / "train" / f"{well}__horizontal_well.csv"
            )
            unknown = np.flatnonzero(horizontal["TVT_input"].isna().to_numpy())
            if not np.array_equal(unknown, row_index):
                raise RuntimeError(f"{well}: matcher rows do not equal hidden suffix")
            if legacy_path.exists():
                with np.load(legacy_path, allow_pickle=False) as saved:
                    if not np.array_equal(saved["row_idx"].astype(int), row_index):
                        raise RuntimeError(f"{well}: legacy matcher cache rows changed")
                    offset = saved["t0.1_offset_mean"].astype(float)
                source = "legacy_cached"
            else:
                typewell = pd.read_csv(
                    data_root / "train" / f"{well}__typewell.csv"
                )
                outputs, _ = scan_complete_well(
                    horizontal=horizontal,
                    typewell=typewell,
                    center=part["sp45"].to_numpy(float),
                    radius=60.0,
                    offset_step=1.0,
                    stride=32,
                    half_window=256,
                    window_step=4,
                    temperatures=(0.10,),
                    prior_strength=0.05,
                    gr_scale=1.30,
                )
                offset = outputs[0.10]["offset_mean"]
                source = "computed"
            md = pd.to_numeric(horizontal["MD"], errors="coerce").to_numpy(float)
            known = np.flatnonzero(horizontal["TVT_input"].notna().to_numpy())
            md_since = md[row_index] - md[known[-1]]
            ramp = 1.0 - np.exp(-np.maximum(md_since, 0.0) / 300.0)
            direct = 0.20 * ramp * np.clip(offset, -4.0, 4.0)
            np.savez_compressed(
                fixed_path,
                row_index=row_index.astype(np.int32),
                direct_correction=np.asarray(direct, np.float32),
            )
        counters[source] += 1
        parts.append(pd.Series(direct, index=part.index))
        if position % 25 == 0 or position == total:
            print(
                f"matcher {position}/{total}: cached={counters['fixed_cached']} "
                f"legacy={counters['legacy_cached']} computed={counters['computed']}",
                flush=True,
            )
    return pd.concat(parts).sort_index().to_numpy(float), counters


def paired_bootstrap(
    frame: pd.DataFrame,
    baseline: np.ndarray,
    candidate: np.ndarray,
    mask: np.ndarray,
    draws: int,
    seed: int,
) -> dict[str, float | int]:
    target = frame.loc[mask, "target_tvt"].to_numpy(float)
    local = pd.DataFrame(
        {
            "well": frame.loc[mask, "well"].astype(str).to_numpy(),
            "rows": 1,
            "base": np.square(target - baseline[mask]),
            "candidate": np.square(target - candidate[mask]),
        }
    ).groupby("well", sort=True).agg(
        rows=("rows", "sum"),
        base=("base", "sum"),
        candidate=("candidate", "sum"),
    )
    values = local.to_numpy(float)
    rng = np.random.default_rng(seed)
    improvements = np.empty(draws, float)
    for draw in range(draws):
        sampled = rng.integers(0, len(values), len(values))
        rows, base_sse, candidate_sse = values[sampled].sum(axis=0)
        improvements[draw] = np.sqrt(base_sse / rows) - np.sqrt(
            candidate_sse / rows
        )
    return {
        "wells": int(len(local)),
        "draws": int(draws),
        "probability_positive": float(np.mean(improvements > 0.0)),
        "p01": float(np.quantile(improvements, 0.01)),
        "p05": float(np.quantile(improvements, 0.05)),
        "p50": float(np.quantile(improvements, 0.50)),
        "p95": float(np.quantile(improvements, 0.95)),
    }


def metric_report(
    frame: pd.DataFrame,
    baseline: np.ndarray,
    candidate: np.ndarray,
    mask: np.ndarray,
) -> dict[str, float | int]:
    target = frame["target_tvt"].to_numpy(float)
    base_score = rmse(target[mask], baseline[mask])
    candidate_score = rmse(target[mask], candidate[mask])
    by_well = pd.DataFrame(
        {
            "well": frame.loc[mask, "well"].astype(str).to_numpy(),
            "se": np.square(target[mask] - candidate[mask]),
        }
    ).groupby("well")["se"].mean().pow(0.5)
    return {
        "rows": int(mask.sum()),
        "wells": int(frame.loc[mask, "well"].nunique()),
        "baseline_rmse": base_score,
        "candidate_rmse": candidate_score,
        "improvement": base_score - candidate_score,
        "candidate_well_rmse_p50": float(by_well.quantile(0.50)),
        "candidate_well_rmse_p90": float(by_well.quantile(0.90)),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.sp45_oof.suffix == ".parquet":
        sp45 = pd.read_parquet(
            args.sp45_oof,
            columns=["id", "row_idx", "sp45"],
        )
    else:
        sp45 = pd.read_csv(
            args.sp45_oof,
            usecols=["id", "row_idx", "projected_tvt"],
            dtype={"id": str},
        ).rename(columns={"projected_tvt": "sp45"})
    sp45 = sp45.rename(columns={"row_idx": "row_index"})
    truth = pd.read_parquet(args.train_gt).rename(columns={"well_id": "well"})
    frame = truth.merge(
        sp45,
        on=["id", "row_index"],
        how="left",
        validate="one_to_one",
    )
    if frame["sp45"].isna().any() or len(frame) != len(truth):
        raise RuntimeError("SP45 OOF does not exactly cover the 773-well contract")

    arrays = {
        "artifact": np.asarray(np.load(args.artifact_oof, mmap_mode="r"), float),
        "hgb": np.asarray(np.load(args.hgb_oof, mmap_mode="r"), float),
        "public": np.asarray(np.load(args.raw_public_oof, mmap_mode="r"), float),
        "smooth": np.asarray(np.load(args.smooth_public_oof, mmap_mode="r"), float),
    }
    if any(len(value) != len(frame) for value in arrays.values()):
        raise RuntimeError("OOF arrays do not share the train_gt row contract")
    last = frame["last_known_TVT"].to_numpy(float)
    sp45_values = frame["sp45"].to_numpy(float)
    branch = load_branch_shifts(frame["well"], args.branch_stats_cache)
    public_absolute = last + arrays["public"]
    artifact_absolute = last + arrays["artifact"]
    hgb_absolute = last + arrays["hgb"]
    exact = 0.60 * sp45_values + 0.40 * public_absolute + branch
    base_artifact = 0.60 * sp45_values + 0.40 * artifact_absolute
    public_artifact = base_artifact + branch
    base_hgb = 0.60 * sp45_values + 0.40 * hgb_absolute
    public_hgb = base_hgb + branch
    sg601 = 0.40 * (arrays["smooth"] - arrays["public"])
    matcher, matcher_counts = matcher_direct_correction(
        frame,
        args.data_root,
        args.legacy_matcher_cache,
        args.matcher_cache,
    )

    raw_artifact015 = (
        0.15 * (base_artifact - exact) + sg601 + 0.10 * matcher
    )
    corrections = {
        "artifact010": 0.10 * (base_artifact - exact),
        "artifact010_sg601": 0.10 * (base_artifact - exact) + sg601,
        "artifact010_sg601_matcher010": 0.10 * (base_artifact - exact)
        + sg601
        + 0.10 * matcher,
        "artifact015_sg601_matcher010": 0.15 * (base_artifact - exact)
        + sg601
        + 0.10 * matcher,
        PRIMARY: raw_artifact015 - np.mean(raw_artifact015),
    }
    screening_wells = load_screening_wells(args.screening_summary)
    screening = frame["well"].astype(str).isin(screening_wells).to_numpy()
    unseen = ~screening
    scopes = {
        "screening_200": screening,
        "unseen_573": unseen,
        "all_773": np.ones(len(frame), bool),
    }
    variant_results = {
        name: {
            scope: metric_report(frame, exact, exact + correction, mask)
            for scope, mask in scopes.items()
        }
        for name, correction in corrections.items()
    }

    primary = exact + corrections[PRIMARY]
    field_map = build_field_map(args.data_root)
    frame["field"] = frame["well"].astype(str).map(field_map).astype(int)
    field_results = {}
    for field in sorted(frame["field"].unique()):
        mask = unseen & frame["field"].eq(field).to_numpy()
        field_results[str(int(field))] = metric_report(
            frame, exact, primary, mask
        )

    proxy_results = {}
    proxy_paths = {
        "exact_public": (exact, base_artifact),
        "artifact": (public_artifact, base_artifact),
        "hgb": (public_hgb, base_hgb),
    }
    for name, (baseline, alternative) in proxy_paths.items():
        proxy_correction = (
            0.15 * (alternative - baseline) + sg601 + 0.10 * matcher
        )
        proxy_correction -= np.mean(proxy_correction)
        candidate = baseline + proxy_correction
        proxy_results[name] = {
            scope: metric_report(frame, baseline, candidate, mask)
            for scope, mask in scopes.items()
        }

    bootstraps = {
        scope: paired_bootstrap(
            frame,
            exact,
            primary,
            mask,
            args.bootstrap_draws,
            args.bootstrap_seed + position,
        )
        for position, (scope, mask) in enumerate(scopes.items())
    }
    correction = corrections[PRIMARY]
    unseen_improvement = variant_results[PRIMARY]["unseen_573"]["improvement"]
    unseen_proxy_floor = min(
        result["unseen_573"]["improvement"] for result in proxy_results.values()
    )
    unseen_field_floor = min(
        result["improvement"] for result in field_results.values()
    )
    promotion = {
        "required_effect_ft": float(args.effect_gate),
        "unseen_effect_pass": bool(unseen_improvement >= args.effect_gate),
        "unseen_bootstrap_p01_positive": bool(bootstraps["unseen_573"]["p01"] > 0.0),
        "all_unseen_proxies_improve": bool(unseen_proxy_floor > 0.0),
        "all_unseen_fields_improve": bool(unseen_field_floor > 0.0),
    }
    promotion["passes_local_submission_gate"] = bool(
        promotion["unseen_effect_pass"]
        and promotion["unseen_bootstrap_p01_positive"]
        and promotion["all_unseen_proxies_improve"]
        and promotion["all_unseen_fields_improve"]
    )
    output = {
        "method": "frozen_conservative_artifact_bag_full773",
        "primary_variant": PRIMARY,
        "screening_wells": int(len(screening_wells)),
        "unseen_wells": int(frame.loc[unseen, "well"].nunique()),
        "contracts": {
            "artifact015_predeclared_before_unseen573_metrics": True,
            "unseen_573_not_used_for_primary_weights": True,
            "same_well_contact_used": False,
            "suffix_target_used_only_for_metrics": True,
            "matcher_uses_visible_prefix_and_full_suffix_gr_only": True,
            "final_correction_is_target_free_test_row_mean_centered": True,
        },
        "matcher_cache_counts": matcher_counts,
        "variant_results": variant_results,
        "proxy_results": proxy_results,
        "unseen_field_results": field_results,
        "bootstrap": bootstraps,
        "primary_correction_distribution": {
            "mean": float(np.mean(correction)),
            "std": float(np.std(correction)),
            "p50_abs": float(np.quantile(np.abs(correction), 0.50)),
            "p95_abs": float(np.quantile(np.abs(correction), 0.95)),
            "maximum_abs": float(np.max(np.abs(correction))),
        },
        "promotion": promotion,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sp45-oof", type=Path, required=True)
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--artifact-oof", type=Path, required=True)
    parser.add_argument("--hgb-oof", type=Path, required=True)
    parser.add_argument("--raw-public-oof", type=Path, required=True)
    parser.add_argument("--smooth-public-oof", type=Path, required=True)
    parser.add_argument("--branch-stats-cache", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--legacy-matcher-cache", type=Path, required=True)
    parser.add_argument("--matcher-cache", type=Path, required=True)
    parser.add_argument("--screening-summary", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-draws", type=int, default=50000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260901)
    parser.add_argument("--effect-gate", type=float, default=0.08)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
