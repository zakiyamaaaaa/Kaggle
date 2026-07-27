"""Evaluate a legal visible-prefix polynomial overlay on generic-core proxies.

The public high-scoring notebooks choose trajectory candidates by masking
several portions of the observed prefix and backtesting on the held-out prefix.
This local experiment keeps only the generic, inference-safe part of that idea:
robust low-order fits of U = TVT + Z.  It excludes same-well train lookup,
formation surfaces, public well IDs, and suffix TVT during candidate creation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


CONFIGS = tuple(
    (degree, tail)
    for degree in (1, 2, 3)
    for tail in (80, 160, 320, 640, 1_000_000)
)
CUT_FRACTIONS = (0.50, 0.65, 0.75)
PROFILES = {
    "conservative": {
        "min_gain": 1.00,
        "max_best": 12.0,
        "min_consistency": 0.67,
        "min_margin": 0.0,
        "base": 0.06,
        "gain_scale": 0.12,
        "margin_scale": 0.04,
        "quality_bonus": 0.02,
        "alpha_cap": 0.22,
        "clip_base": 8.0,
        "clip_gain": 3.0,
        "clip_max": 18.0,
        "delta_soft": 22.0,
        "p95_hard": 55.0,
    },
    "balanced": {
        "min_gain": 1.00,
        "max_best": 12.0,
        "min_consistency": 0.80,
        "min_margin": 0.10,
        "base": 0.08,
        "gain_scale": 0.20,
        "margin_scale": 0.06,
        "quality_bonus": 0.04,
        "alpha_cap": 0.36,
        "clip_base": 10.0,
        "clip_gain": 4.5,
        "clip_max": 28.0,
        "delta_soft": 30.0,
        "p95_hard": 75.0,
    },
    "aggressive": {
        "min_gain": 0.25,
        "max_best": 15.0,
        "min_consistency": 0.34,
        "min_margin": 0.0,
        "base": 0.12,
        "gain_scale": 0.32,
        "margin_scale": 0.10,
        "quality_bonus": 0.06,
        "alpha_cap": 0.56,
        "clip_base": 14.0,
        "clip_gain": 7.0,
        "clip_max": 45.0,
        "delta_soft": 42.0,
        "p95_hard": 110.0,
    },
}


def robust_poly_predict(
    x_known: np.ndarray,
    y_known: np.ndarray,
    x_all: np.ndarray,
    degree: int,
) -> np.ndarray:
    finite = np.isfinite(x_known) & np.isfinite(y_known)
    x_known = np.asarray(x_known[finite], dtype=float)
    y_known = np.asarray(y_known[finite], dtype=float)
    x_all = np.asarray(x_all, dtype=float)
    if len(x_known) < degree + 2:
        return np.full(len(x_all), np.nanmedian(y_known), dtype=float)
    x0 = float(x_known[0])
    scale = float(np.nanmax(x_known) - np.nanmin(x_known))
    if not np.isfinite(scale) or scale < 1e-6:
        scale = 1.0
    x_fit = (x_known - x0) / scale
    x_pred = (x_all - x0) / scale
    coefficients = np.polyfit(x_fit, y_known, degree)
    for _ in range(5):
        residual = y_known - np.polyval(coefficients, x_fit)
        mad = np.nanmedian(np.abs(residual - np.nanmedian(residual)))
        robust_scale = 1.4826 * float(mad) + 1e-6
        weights = 1.0 / (1.0 + (residual / (2.5 * robust_scale)) ** 2)
        coefficients = np.polyfit(x_fit, y_known, degree, w=weights)
    return np.polyval(coefficients, x_pred)


def config_name(config: tuple[int, int]) -> str:
    degree, tail = config
    tail_name = "all" if tail >= 1_000_000 else str(tail)
    return f"degree{degree}_tail{tail_name}"


def fit_config(
    horizontal: pd.DataFrame,
    train_indices: np.ndarray,
    config: tuple[int, int],
) -> np.ndarray:
    degree, tail = config
    selected = train_indices[-min(tail, len(train_indices)) :]
    md = pd.to_numeric(horizontal["MD"], errors="coerce").to_numpy(float)
    z = pd.to_numeric(horizontal["Z"], errors="coerce").to_numpy(float)
    tvt_input = pd.to_numeric(
        horizontal["TVT_input"], errors="coerce"
    ).to_numpy(float)
    u_known = tvt_input[selected] + z[selected]
    return robust_poly_predict(md[selected], u_known, md, degree) - z


def select_prefix_candidate(
    horizontal: pd.DataFrame,
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

    scores: dict[tuple[int, int], list[float]] = {}
    cut_winners: list[tuple[int, int]] = []
    cut_scores: list[dict[tuple[int, int], float]] = []
    for fraction in CUT_FRACTIONS:
        cut_position = int(round(len(known_prefix) * fraction))
        cut_position = max(50, min(cut_position, len(known_prefix) - 35))
        train_indices = known_prefix[:cut_position]
        holdout_indices = known_prefix[cut_position:]
        local: dict[tuple[int, int], float] = {}
        for config in CONFIGS:
            prediction = fit_config(horizontal, train_indices, config)
            error = prediction[holdout_indices] - tvt_input[holdout_indices]
            rmse = float(np.sqrt(np.mean(error * error)))
            if np.isfinite(rmse):
                scores.setdefault(config, []).append(rmse)
                local[config] = rmse
        if local:
            cut_winners.append(min(local, key=local.get))
            cut_scores.append(local)
    if not scores:
        return None, {"status": "skip_no_scores"}

    aggregate = {
        config: float(np.median(values) + 0.10 * np.std(values))
        for config, values in scores.items()
    }
    ordered = sorted((score, config) for config, score in aggregate.items())
    best_score, best_config = ordered[0]
    second_score = ordered[1][0] if len(ordered) > 1 else best_score
    default_config = (2, 1_000_000)
    default_score = aggregate.get(default_config, second_score)
    comparable = 0
    wins = 0
    for local in cut_scores:
        if best_config in local and default_config in local:
            comparable += 1
            if local[best_config] <= local[default_config] - 0.25:
                wins += 1
    consistency = float(wins / comparable) if comparable else 0.0
    candidate = fit_config(horizontal, known_prefix, best_config)
    return candidate, {
        "status": "ok",
        "known_prefix": int(len(known_prefix)),
        "best_name": config_name(best_config),
        "best_score": float(best_score),
        "second_score": float(second_score),
        "default_score": float(default_score),
        "gain": float(default_score - best_score),
        "rank_margin": float(second_score - best_score),
        "consistency": consistency,
        "cut_winners": [config_name(config) for config in cut_winners],
    }


def profile_move(
    base: np.ndarray,
    candidate: np.ndarray,
    report: dict[str, object],
    profile_name: str,
    profiles: dict[str, dict[str, float]] | None = None,
) -> tuple[np.ndarray, dict[str, object]]:
    profile = (PROFILES if profiles is None else profiles)[profile_name]
    difference = candidate - base
    delta_rmse = float(np.sqrt(np.mean(difference * difference)))
    delta_p95 = float(np.quantile(np.abs(difference), 0.95))
    gain = float(report.get("gain", 0.0))
    best = float(report.get("best_score", np.inf))
    margin = float(report.get("rank_margin", 0.0))
    consistency = float(report.get("consistency", 0.0))
    accepted = (
        report.get("status") == "ok"
        and np.isfinite(best)
        and best <= profile["max_best"]
        and gain >= profile["min_gain"]
        and consistency >= profile["min_consistency"]
        and margin >= profile["min_margin"]
        and delta_p95 <= profile["p95_hard"]
        and delta_rmse <= profile.get("delta_hard", np.inf)
    )
    alpha = 0.0
    if accepted:
        alpha = profile["base"]
        alpha += profile["gain_scale"] * min(max(gain, 0.0), 5.0) / 5.0
        alpha += (
            profile["margin_scale"] * min(max(margin, 0.0), 3.0) / 3.0
        )
        if best <= 5.0:
            alpha += profile["quality_bonus"]
        if delta_rmse > profile["delta_soft"]:
            alpha *= max(0.20, profile["delta_soft"] / delta_rmse)
        alpha = min(profile["alpha_cap"], max(0.0, alpha * 1.30))
    max_move = min(
        profile["clip_max"],
        profile["clip_base"] + profile["clip_gain"] * np.sqrt(max(gain, 0.0)),
    )
    ramp = 1.0 - np.exp(
        -np.arange(len(base), dtype=float) / max(80.0, 0.12 * len(base))
    )
    move = np.clip(alpha * ramp * difference, -max_move, max_move)
    proposed_max_abs_move = float(np.max(np.abs(move)))
    if accepted and proposed_max_abs_move > profile.get(
        "move_hard", np.inf
    ):
        accepted = False
        alpha = 0.0
        move = np.zeros_like(move)
    return base + move, {
        "accepted": bool(accepted and alpha > 0.0),
        "alpha": float(alpha),
        "max_move": float(max_move),
        "mean_abs_move": float(np.mean(np.abs(move))),
        "max_abs_move": float(np.max(np.abs(move))),
        "proposed_max_abs_move": proposed_max_abs_move,
        "delta_rmse": delta_rmse,
        "delta_p95": delta_p95,
    }


def load_well_set(path: Path) -> set[str]:
    record = json.loads(path.read_text(encoding="utf-8"))
    return set(map(str, record["sampled_wells"]))


def load_frame(args: argparse.Namespace) -> pd.DataFrame:
    frames = [pd.read_parquet(path) for path in args.sp45_cache]
    frame = pd.concat(frames, ignore_index=True)
    frame = frame.drop_duplicates("id", keep="first").reset_index(drop=True)
    discovery = load_well_set(args.discovery_summary)
    holdout1 = load_well_set(args.holdout1_summary)
    holdout2 = load_well_set(args.holdout2_summary)
    if discovery & holdout1 or discovery & holdout2 or holdout1 & holdout2:
        raise RuntimeError("well validation sets overlap")
    split_map = {
        **{well: "discovery" for well in discovery},
        **{well: "holdout1" for well in holdout1},
        **{well: "holdout2" for well in holdout2},
    }
    frame["validation_split"] = frame["well"].astype(str).map(split_map)
    if frame["validation_split"].isna().any():
        raise RuntimeError("cache contains wells outside validation summaries")

    truth = pd.read_parquet(
        args.train_gt, columns=["id", "last_known_TVT"]
    )
    artifact_delta = np.load(args.artifact_oof, mmap_mode="r")
    if len(truth) != len(artifact_delta):
        raise RuntimeError("artifact OOF and train GT lengths differ")
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
        args.local_oof, usecols=["_oof_id", "hgb_oof_tvt"]
    ).rename(columns={"_oof_id": "id"})
    frame = frame.merge(local, on="id", how="left", validate="one_to_one")
    if frame[["artifact_tvt", "hgb_oof_tvt"]].isna().any().any():
        raise RuntimeError("proxy OOF ID alignment failed")
    return frame


def metric(target: np.ndarray, prediction: np.ndarray) -> float:
    if len(target) == 0:
        return float("nan")
    return float(np.sqrt(np.mean((prediction - target) ** 2)))


def summarize(
    frame: pd.DataFrame,
    prediction_columns: list[str],
) -> dict[str, object]:
    target = frame["target_tvt"].to_numpy(float)
    result: dict[str, object] = {
        "rows": int(len(frame)),
        "wells": int(frame["well"].nunique()),
    }
    for column in prediction_columns:
        result[column] = metric(target, frame[column].to_numpy(float))
    return result


def run(args: argparse.Namespace) -> dict[str, object]:
    frame = load_frame(args)
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
    for position, (well, well_frame) in enumerate(
        frame.groupby("well", sort=True), 1
    ):
        well_frame = well_frame.sort_values("row_idx").copy()
        horizontal = pd.read_csv(
            args.data_root / "train" / f"{well}__horizontal_well.csv"
        )
        candidate_full, report = select_prefix_candidate(horizontal)
        report = dict(report)
        report.update(
            {
                "well": str(well),
                "validation_split": str(
                    well_frame["validation_split"].iloc[0]
                ),
            }
        )
        row_indices = well_frame["row_idx"].to_numpy(int)
        if candidate_full is None:
            candidate = np.full(len(well_frame), np.nan)
        else:
            candidate = np.asarray(candidate_full, dtype=float)[row_indices]
        well_frame["poly_candidate"] = candidate
        for proxy_name in proxies:
            base = well_frame[f"base_{proxy_name}"].to_numpy(float)
            for profile_name in PROFILES:
                if candidate_full is None or not np.isfinite(candidate).all():
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
                        base, candidate, report, profile_name
                    )
                well_frame[f"{profile_name}_{proxy_name}"] = moved
                for key, value in move_report.items():
                    report[
                        f"{profile_name}_{proxy_name}_{key}"
                    ] = value
        reports.append(report)
        output_parts.append(well_frame)
        print(
            f"{position}/{frame['well'].nunique()} {well}: "
            f"{report.get('status')} {report.get('best_name')} "
            f"score={report.get('best_score', float('nan')):.3f}",
            flush=True,
        )

    output = pd.concat(output_parts, ignore_index=True)
    prediction_columns = [
        f"base_{proxy}" for proxy in proxies
    ] + [
        f"{profile}_{proxy}"
        for profile in PROFILES
        for proxy in proxies
    ]
    summary: dict[str, object] = {
        "method": "visible_prefix_poly_gate_on_full_pipeline_oof_proxies",
        "sp45_weight": float(args.sp45_weight),
        "candidate_family": "prefix-only robust U polynomial",
        "configs": [config_name(config) for config in CONFIGS],
        "cut_fractions": CUT_FRACTIONS,
        "profiles": PROFILES,
        "same_well_contact_used": False,
        "formation_surfaces_used": False,
        "suffix_target_used_for_selection": False,
        "splits": {},
    }
    for split in ("discovery", "holdout1", "holdout2", "holdout_combined", "all"):
        if split == "holdout_combined":
            subset = output[
                output["validation_split"].isin(["holdout1", "holdout2"])
            ]
        elif split == "all":
            subset = output
        else:
            subset = output[output["validation_split"].eq(split)]
        split_summary = summarize(subset, prediction_columns)
        split_reports = pd.DataFrame(reports)
        if split == "holdout_combined":
            split_reports = split_reports[
                split_reports["validation_split"].isin(
                    ["holdout1", "holdout2"]
                )
            ]
        elif split != "all":
            split_reports = split_reports[
                split_reports["validation_split"].eq(split)
            ]
        for profile_name in PROFILES:
            accepted_column = f"{profile_name}_artifact_accepted"
            split_summary[f"{profile_name}_accepted_wells"] = int(
                split_reports[accepted_column].sum()
            )
        summary["splits"][split] = split_summary

    discovery = summary["splits"]["discovery"]
    profile_objectives = {}
    for profile_name in PROFILES:
        improvements = [
            discovery[f"base_{proxy}"]
            - discovery[f"{profile_name}_{proxy}"]
            for proxy in proxies
        ]
        profile_objectives[profile_name] = {
            "mean_improvement": float(np.mean(improvements)),
            "minimum_improvement": float(np.min(improvements)),
            "proxy_improvements": dict(zip(proxies, improvements)),
        }
    selected_profile = max(
        profile_objectives,
        key=lambda name: (
            profile_objectives[name]["minimum_improvement"],
            profile_objectives[name]["mean_improvement"],
        ),
    )
    summary["discovery_profile_selection"] = {
        "objectives": profile_objectives,
        "selected": selected_profile,
    }
    holdout = summary["splits"]["holdout_combined"]
    summary["selected_holdout_improvements"] = {
        proxy: float(
            holdout[f"base_{proxy}"]
            - holdout[f"{selected_profile}_{proxy}"]
        )
        for proxy in proxies
    }
    summary["selected_holdout_all_proxies_improve"] = all(
        value > 0
        for value in summary["selected_holdout_improvements"].values()
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_parquet(args.output, index=False)
    pd.DataFrame(reports).to_csv(args.report, index=False)
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
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--artifact-oof", type=Path, required=True)
    parser.add_argument("--local-oof", type=Path, required=True)
    parser.add_argument("--discovery-summary", type=Path, required=True)
    parser.add_argument("--holdout1-summary", type=Path, required=True)
    parser.add_argument("--holdout2-summary", type=Path, required=True)
    parser.add_argument("--sp45-weight", type=float, default=0.60)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
