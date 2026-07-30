"""Evaluate a bounded complete-well GR matcher on the fixed 7.474 proxy.

The matcher uses only the visible TVT prefix, the full horizontal GR trace, the
matching typewell, and an already-legal SP45 center trajectory.  It never reads
suffix TVT while producing matcher features.  Discovery wells select one
bounded posterior correction; holdout1 and holdout2 remain untouched until the
final report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.model_selection import GroupKFold

from calibrated_u_viterbi_experiment import (
    ViterbiConfig,
    _robust_affine_calibration,
    _rolling_median,
    _typewell_arrays,
)


PROXIES = {
    "artifact": "public_s060_cap200_artifact",
    "hgb": "public_s060_cap200_hgb",
    "ridge": "public_s060_cap200_ridge",
}
SPLITS = ("discovery", "holdout1", "holdout2", "holdout_combined", "all")


def rmse(y: np.ndarray, prediction: np.ndarray) -> float:
    valid = np.isfinite(y) & np.isfinite(prediction)
    if not valid.any():
        return float("nan")
    error = y[valid] - prediction[valid]
    return float(np.sqrt(np.mean(error * error)))


def split_mask(frame: pd.DataFrame, split: str) -> np.ndarray:
    if split == "holdout_combined":
        return frame["validation_split"].isin(["holdout1", "holdout2"]).to_numpy()
    if split == "all":
        return np.ones(len(frame), dtype=bool)
    return frame["validation_split"].eq(split).to_numpy()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def softmax_posterior(cost: np.ndarray, temperature: float) -> np.ndarray:
    finite = np.isfinite(cost)
    if not finite.any():
        return np.full(len(cost), 1.0 / max(len(cost), 1))
    safe = np.where(finite, cost, np.nanmax(cost[finite]) + 100.0)
    logits = -(safe - np.min(safe)) / max(float(temperature), 1e-6)
    logits -= np.max(logits)
    weights = np.exp(np.clip(logits, -60.0, 0.0))
    return weights / max(float(weights.sum()), 1e-12)


def scan_complete_well(
    horizontal: pd.DataFrame,
    typewell: pd.DataFrame,
    center: np.ndarray,
    radius: float,
    offset_step: float,
    stride: int,
    half_window: int,
    window_step: int,
    temperatures: tuple[float, ...],
    prior_strength: float,
    gr_scale: float,
) -> tuple[dict[float, dict[str, np.ndarray]], dict[str, float | int | str]]:
    """Return posterior offset paths without consulting suffix TVT."""
    unknown_mask = horizontal["TVT_input"].isna().to_numpy()
    unknown_idx = np.flatnonzero(unknown_mask)
    if len(unknown_idx) != len(center):
        raise RuntimeError("SP45 center does not cover every hidden suffix row")

    config = ViterbiConfig(gr_smooth_window=7, calibration_rows=800)
    tw_tvt, tw_gr = _typewell_arrays(typewell, config.gr_smooth_window)
    if len(tw_tvt) < 3:
        raise RuntimeError("typewell is too short")
    alpha, beta, sigma, calibration_rows = _robust_affine_calibration(
        horizontal,
        tw_tvt,
        tw_gr,
        config,
    )
    sigma = max(float(sigma) * float(gr_scale), 5.0)

    horizontal_gr = pd.to_numeric(horizontal["GR"], errors="coerce").to_numpy(float)
    horizontal_gr = _rolling_median(horizontal_gr, config.gr_smooth_window)
    fallback = float(np.nanmedian(horizontal_gr))
    observed = (
        pd.Series(horizontal_gr[unknown_idx])
        .interpolate(limit_direction="both")
        .fillna(fallback)
        .to_numpy(float)
    )
    offsets = np.arange(
        -float(radius),
        float(radius) + 0.5 * float(offset_step),
        float(offset_step),
    )
    sample_pos = np.arange(0, len(center), max(1, int(stride)), dtype=int)
    if len(sample_pos) == 0 or sample_pos[-1] != len(center) - 1:
        sample_pos = np.append(sample_pos, len(center) - 1)

    costs = np.full((len(sample_pos), len(offsets)), np.nan, dtype=np.float32)
    for sample_index, position in enumerate(sample_pos):
        lo = max(0, int(position) - int(half_window))
        hi = min(len(center), int(position) + int(half_window) + 1)
        rows = np.arange(lo, hi, max(1, int(window_step)), dtype=int)
        valid = (
            np.isfinite(observed[rows])
            & np.isfinite(center[rows])
        )
        rows = rows[valid]
        if len(rows) < 12:
            continue
        candidate_tvt = center[rows, None] + offsets[None, :]
        reference = np.interp(
            candidate_tvt.ravel(),
            tw_tvt,
            tw_gr,
            left=np.nan,
            right=np.nan,
        ).reshape(candidate_tvt.shape)
        residual = (
            observed[rows, None] - (float(alpha) * reference + float(beta))
        ) / sigma
        robust = np.minimum(np.square(residual), 36.0)
        robust[~np.isfinite(robust)] = 46.0
        cost = np.mean(robust, axis=0)
        cost += float(prior_strength) * np.square(offsets / max(float(radius), 1e-6))
        costs[sample_index] = cost.astype(np.float32)

    x_full = np.arange(len(center), dtype=float)
    outputs: dict[float, dict[str, np.ndarray]] = {}
    for temperature in temperatures:
        sampled_mean = np.zeros(len(sample_pos), dtype=float)
        sampled_std = np.full(len(sample_pos), float(radius), dtype=float)
        sampled_entropy = np.ones(len(sample_pos), dtype=float)
        sampled_pmax = np.zeros(len(sample_pos), dtype=float)
        sampled_margin = np.zeros(len(sample_pos), dtype=float)
        for index, cost in enumerate(costs):
            posterior = softmax_posterior(cost.astype(float), temperature)
            mean = float(np.sum(posterior * offsets))
            variance = float(np.sum(posterior * np.square(offsets - mean)))
            order = np.sort(posterior)
            sampled_mean[index] = mean
            sampled_std[index] = np.sqrt(max(variance, 0.0))
            sampled_entropy[index] = float(
                -np.sum(posterior * np.log(np.maximum(posterior, 1e-12)))
                / np.log(max(len(posterior), 2))
            )
            sampled_pmax[index] = float(order[-1])
            sampled_margin[index] = float(order[-1] - order[-2]) if len(order) > 1 else 1.0
        outputs[float(temperature)] = {
            "offset_mean": np.interp(x_full, sample_pos, sampled_mean),
            "offset_std": np.interp(x_full, sample_pos, sampled_std),
            "entropy": np.interp(x_full, sample_pos, sampled_entropy),
            "pmax": np.interp(x_full, sample_pos, sampled_pmax),
            "margin": np.interp(x_full, sample_pos, sampled_margin),
        }

    diagnostics: dict[str, float | int | str] = {
        "status": "ok",
        "alpha": float(alpha),
        "beta": float(beta),
        "sigma": float(sigma),
        "calibration_rows": int(calibration_rows),
        "sampled_rows": int(len(sample_pos)),
        "offset_states": int(len(offsets)),
    }
    return outputs, diagnostics


def load_or_build_matcher(
    well: str,
    well_frame: pd.DataFrame,
    args: argparse.Namespace,
) -> tuple[dict[float, dict[str, np.ndarray]], dict[str, object]]:
    cache_path = args.scan_cache / f"{well}.npz"
    expected_rows = well_frame["row_idx"].to_numpy(int)
    if cache_path.exists() and not args.overwrite:
        with np.load(cache_path, allow_pickle=False) as cached:
            cached_rows = cached["row_idx"].astype(int)
            if np.array_equal(cached_rows, expected_rows):
                outputs = {}
                for temperature in args.temperatures:
                    key = f"t{temperature:g}"
                    outputs[temperature] = {
                        name: cached[f"{key}_{name}"].astype(float)
                        for name in ("offset_mean", "offset_std", "entropy", "pmax", "margin")
                    }
                diagnostic = json.loads(str(cached["diagnostic"].item()))
                diagnostic["cached"] = True
                return outputs, diagnostic

    horizontal = pd.read_csv(
        args.data_root / "train" / f"{well}__horizontal_well.csv"
    )
    typewell = pd.read_csv(
        args.data_root / "train" / f"{well}__typewell.csv"
    )
    unknown_idx = np.flatnonzero(horizontal["TVT_input"].isna().to_numpy())
    if not np.array_equal(unknown_idx, expected_rows):
        raise RuntimeError(f"{well}: incumbent rows do not equal the hidden suffix")
    center = well_frame["sp45_sgridge_d2_b050"].to_numpy(float)
    outputs, diagnostic = scan_complete_well(
        horizontal=horizontal,
        typewell=typewell,
        center=center,
        radius=args.radius,
        offset_step=args.offset_step,
        stride=args.stride,
        half_window=args.half_window,
        window_step=args.window_step,
        temperatures=args.temperatures,
        prior_strength=args.prior_strength,
        gr_scale=args.gr_scale,
    )
    payload: dict[str, np.ndarray] = {
        "row_idx": expected_rows.astype(np.int32),
        "diagnostic": np.asarray(json.dumps(diagnostic)),
    }
    for temperature, values in outputs.items():
        key = f"t{temperature:g}"
        for name, value in values.items():
            payload[f"{key}_{name}"] = np.asarray(value, dtype=np.float32)
    np.savez_compressed(cache_path, **payload)
    diagnostic["cached"] = False
    return outputs, diagnostic


def build_field_map(data_root: Path) -> dict[str, int]:
    rows = []
    for path in sorted((data_root / "train").glob("*__horizontal_well.csv")):
        well = path.name.split("__", 1)[0]
        frame = pd.read_csv(path, usecols=["X", "Y"])
        rows.append(
            {
                "well": well,
                "x": float(pd.to_numeric(frame["X"], errors="coerce").median()),
                "y": float(pd.to_numeric(frame["Y"], errors="coerce").median()),
            }
        )
    centroids = pd.DataFrame(rows)
    model = KMeans(n_clusters=5, n_init=20, random_state=0)
    centroids["field"] = model.fit_predict(centroids[["x", "y"]].to_numpy(float))
    return dict(zip(centroids["well"], centroids["field"]))


def correction(
    frame: pd.DataFrame,
    temperature: float,
    cap: float,
    tau: float,
) -> np.ndarray:
    raw = frame[f"matcher_t{temperature:g}_offset_mean"].to_numpy(float)
    md_since = np.maximum(frame["md_since"].to_numpy(float), 0.0)
    ramp = (
        np.ones(len(frame), dtype=float)
        if tau <= 0
        else 1.0 - np.exp(-md_since / float(tau))
    )
    return ramp * np.clip(raw, -float(cap), float(cap))


def score_candidate(
    frame: pd.DataFrame,
    move: np.ndarray,
    scale: float,
    mask: np.ndarray,
) -> dict[str, float]:
    y = frame["target_tvt"].to_numpy(float)
    return {
        proxy: rmse(
            y[mask],
            frame[column].to_numpy(float)[mask] + float(scale) * move[mask],
        )
        for proxy, column in PROXIES.items()
    }


def fit_uncertainty_combiner(
    frame: pd.DataFrame,
    move: np.ndarray,
    temperature: float,
    cap: float,
    alpha_grid: tuple[float, ...],
) -> tuple[np.ndarray, float, dict[str, object]]:
    discovery = frame["validation_split"].eq("discovery").to_numpy()
    std = frame[f"matcher_t{temperature:g}_offset_std"].to_numpy(float)
    entropy = frame[f"matcher_t{temperature:g}_entropy"].to_numpy(float)
    margin = frame[f"matcher_t{temperature:g}_margin"].to_numpy(float)
    confidence = np.clip(1.0 - std / max(float(cap) * 4.0, 1.0), 0.0, 1.0)
    margin_scaled = margin / max(float(np.nanquantile(margin[discovery], 0.95)), 1e-8)
    frac = frame.groupby("well", sort=False).cumcount().to_numpy(float)
    denom = frame.groupby("well", sort=False)["well"].transform("size").to_numpy(float)
    frac = frac / np.maximum(denom - 1.0, 1.0)
    design = np.column_stack(
        [
            move,
            move * confidence,
            move * (1.0 - entropy),
            move * np.clip(margin_scaled, 0.0, 2.0),
            move * (frac - 0.5),
        ]
    )
    design[~np.isfinite(design)] = 0.0

    discovery_wells = frame.loc[discovery, "well"].astype(str).to_numpy()
    unique_wells = np.unique(discovery_wells)
    folds = GroupKFold(n_splits=5)
    alpha_scores = []
    for alpha in alpha_grid:
        sse = 0.0
        count = 0
        for train_well_idx, valid_well_idx in folds.split(
            unique_wells,
            groups=unique_wells,
        ):
            train_wells = set(unique_wells[train_well_idx])
            valid_wells = set(unique_wells[valid_well_idx])
            train = discovery & frame["well"].astype(str).isin(train_wells).to_numpy()
            valid = discovery & frame["well"].astype(str).isin(valid_wells).to_numpy()
            x_train = np.tile(design[train], (len(PROXIES), 1))
            residual_parts = []
            y = frame["target_tvt"].to_numpy(float)
            for column in PROXIES.values():
                residual_parts.append(y[train] - frame[column].to_numpy(float)[train])
            residual = np.concatenate(residual_parts)
            gram = x_train.T @ x_train + np.eye(x_train.shape[1]) * float(alpha)
            coef = np.linalg.solve(gram, x_train.T @ residual)
            coef = np.clip(coef, -0.5, 0.5)
            row_correction = design[valid] @ coef
            for column in PROXIES.values():
                error = (
                    y[valid]
                    - frame[column].to_numpy(float)[valid]
                    - row_correction
                )
                sse += float(np.sum(error * error))
                count += int(len(error))
        alpha_scores.append(
            {"alpha": float(alpha), "rmse": float(np.sqrt(sse / max(count, 1)))}
        )
    selected_alpha = min(alpha_scores, key=lambda row: row["rmse"])["alpha"]

    x_train = np.tile(design[discovery], (len(PROXIES), 1))
    y = frame["target_tvt"].to_numpy(float)
    residual = np.concatenate(
        [
            y[discovery] - frame[column].to_numpy(float)[discovery]
            for column in PROXIES.values()
        ]
    )
    gram = x_train.T @ x_train + np.eye(x_train.shape[1]) * float(selected_alpha)
    coef = np.linalg.solve(gram, x_train.T @ residual)
    coef = np.clip(coef, -0.5, 0.5)
    return design @ coef, float(selected_alpha), {
        "features": [
            "move",
            "move_x_confidence",
            "move_x_one_minus_entropy",
            "move_x_margin",
            "move_x_centered_progress",
        ],
        "alpha_scores": alpha_scores,
        "selected_alpha": float(selected_alpha),
        "coefficients": [float(value) for value in coef],
        "training_rows": int(discovery.sum()),
        "training_wells": int(len(unique_wells)),
        "suffix_target_used_as_features": False,
    }


def bootstrap_improvement(
    frame: pd.DataFrame,
    baseline: np.ndarray,
    candidate: np.ndarray,
    mask: np.ndarray,
    seed: int,
    draws: int = 2000,
) -> dict[str, float]:
    subset = frame.loc[mask, ["well", "target_tvt"]].copy()
    subset["base_se"] = np.square(baseline[mask] - subset["target_tvt"].to_numpy(float))
    subset["candidate_se"] = np.square(candidate[mask] - subset["target_tvt"].to_numpy(float))
    by_well = subset.groupby("well", sort=False).agg(
        rows=("well", "size"),
        base_sse=("base_se", "sum"),
        candidate_sse=("candidate_se", "sum"),
    )
    rng = np.random.default_rng(seed)
    values = np.empty(draws, dtype=float)
    for draw in range(draws):
        sampled = rng.integers(0, len(by_well), len(by_well))
        rows = by_well["rows"].to_numpy(float)[sampled].sum()
        base_rmse = np.sqrt(by_well["base_sse"].to_numpy(float)[sampled].sum() / rows)
        candidate_rmse = np.sqrt(
            by_well["candidate_sse"].to_numpy(float)[sampled].sum() / rows
        )
        values[draw] = base_rmse - candidate_rmse
    return {
        "probability_positive": float(np.mean(values > 0.0)),
        "p05": float(np.quantile(values, 0.05)),
        "p50": float(np.quantile(values, 0.50)),
        "p95": float(np.quantile(values, 0.95)),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    args.scan_cache.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(args.incumbent_cache).sort_values(
        ["well", "row_idx"]
    ).reset_index(drop=True)
    required = {
        "well",
        "row_idx",
        "target_tvt",
        "validation_split",
        "sp45_sgridge_d2_b050",
        "md_since",
        *PROXIES.values(),
    }
    missing = required - set(frame.columns)
    if missing:
        raise RuntimeError(f"incumbent cache missing columns: {sorted(missing)}")
    if set(frame["validation_split"].unique()) != {"discovery", "holdout1", "holdout2"}:
        raise RuntimeError("unexpected validation split contract")

    reports = []
    parts = []
    grouped = frame.groupby("well", sort=True)
    for position, (well, well_frame) in enumerate(grouped, 1):
        well_frame = well_frame.copy()
        outputs, diagnostic = load_or_build_matcher(
            str(well),
            well_frame,
            args,
        )
        for temperature, values in outputs.items():
            for name, value in values.items():
                well_frame[f"matcher_t{temperature:g}_{name}"] = value
        reports.append(
            {
                "well": str(well),
                "validation_split": str(well_frame["validation_split"].iloc[0]),
                **diagnostic,
            }
        )
        parts.append(well_frame)
        print(
            f"{position}/{frame['well'].nunique()} {well} "
            f"{'cached' if diagnostic.get('cached') else 'computed'} "
            f"sigma={float(diagnostic.get('sigma', np.nan)):.3f}",
            flush=True,
        )
    frame = pd.concat(parts, ignore_index=True)
    field_map = build_field_map(args.data_root)
    frame["field"] = frame["well"].astype(str).map(field_map).astype(int)
    report_frame = pd.DataFrame(reports)
    report_frame["field"] = report_frame["well"].map(field_map)

    discovery = split_mask(frame, "discovery")
    baseline_discovery = {
        proxy: rmse(
            frame.loc[discovery, "target_tvt"].to_numpy(float),
            frame.loc[discovery, column].to_numpy(float),
        )
        for proxy, column in PROXIES.items()
    }
    records = []
    moves: dict[tuple[float, float, float], np.ndarray] = {}
    for temperature in args.temperatures:
        for cap in args.caps:
            for tau in args.taus:
                move = correction(frame, temperature, cap, tau)
                moves[(temperature, cap, tau)] = move
                for scale in args.scales:
                    scores = score_candidate(frame, move, scale, discovery)
                    improvements = {
                        proxy: baseline_discovery[proxy] - value
                        for proxy, value in scores.items()
                    }
                    records.append(
                        {
                            "temperature": float(temperature),
                            "cap": float(cap),
                            "tau": float(tau),
                            "scale": float(scale),
                            "scores": scores,
                            "improvements": improvements,
                            "minimum_improvement": float(min(improvements.values())),
                            "mean_improvement": float(np.mean(list(improvements.values()))),
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
    selected_key = (
        selected["temperature"],
        selected["cap"],
        selected["tau"],
    )
    selected_move = moves[selected_key]
    direct_correction = selected["scale"] * selected_move
    learned_correction, selected_alpha, learned_report = fit_uncertainty_combiner(
        frame,
        selected_move,
        selected["temperature"],
        selected["cap"],
        args.alpha_grid,
    )
    frame["matcher_selected_move"] = selected_move
    frame["matcher_direct_correction"] = direct_correction
    frame["matcher_learned_correction"] = learned_correction

    y = frame["target_tvt"].to_numpy(float)
    summary: dict[str, object] = {
        "method": "bounded_complete_well_posterior_matcher",
        "incumbent_cache": str(args.incumbent_cache),
        "incumbent_cache_sha256": sha256(args.incumbent_cache),
        "rows": int(len(frame)),
        "wells": int(frame["well"].nunique()),
        "split_wells": frame.groupby("validation_split")["well"].nunique().to_dict(),
        "matcher_contract": {
            "radius_ft": float(args.radius),
            "offset_step_ft": float(args.offset_step),
            "stride_rows": int(args.stride),
            "half_window_rows": int(args.half_window),
            "window_step_rows": int(args.window_step),
            "temperatures": list(args.temperatures),
            "prior_strength": float(args.prior_strength),
            "gr_scale": float(args.gr_scale),
            "center": "legal SP45 ridge30 selector70 projection d2/b0.50 OOF",
            "same_well_contact_used": False,
            "formation_or_dense_imputer_used_by_matcher": False,
            "suffix_target_used_by_matcher": False,
            "full_hidden_gr_lookahead_used": True,
        },
        "discovery_grid": {
            "baseline_scores": baseline_discovery,
            "selected": selected,
            "top10": sorted(
                records,
                key=lambda row: (row["minimum_improvement"], row["mean_improvement"]),
                reverse=True,
            )[:10],
        },
        "uncertainty_combiner": {
            **learned_report,
            "selected_alpha": selected_alpha,
        },
        "splits": {},
    }

    for split_index, split in enumerate(SPLITS):
        mask = split_mask(frame, split)
        proxy_results = {}
        for proxy_index, (proxy, column) in enumerate(PROXIES.items()):
            base = frame[column].to_numpy(float)
            direct = base + direct_correction
            learned = base + learned_correction
            base_score = rmse(y[mask], base[mask])
            direct_score = rmse(y[mask], direct[mask])
            learned_score = rmse(y[mask], learned[mask])
            proxy_results[proxy] = {
                "baseline_rmse": base_score,
                "direct_rmse": direct_score,
                "direct_improvement": base_score - direct_score,
                "learned_rmse": learned_score,
                "learned_improvement": base_score - learned_score,
                "direct_bootstrap": bootstrap_improvement(
                    frame,
                    base,
                    direct,
                    mask,
                    args.seed + split_index * 20 + proxy_index,
                ),
                "learned_bootstrap": bootstrap_improvement(
                    frame,
                    base,
                    learned,
                    mask,
                    args.seed + split_index * 20 + proxy_index + 10,
                ),
            }
        field_rows = []
        if split in {"holdout1", "holdout2", "holdout_combined"}:
            for field in sorted(frame.loc[mask, "field"].unique()):
                field_mask = mask & frame["field"].eq(field).to_numpy()
                for proxy, column in PROXIES.items():
                    base = frame[column].to_numpy(float)
                    field_rows.append(
                        {
                            "field": int(field),
                            "proxy": proxy,
                            "rows": int(field_mask.sum()),
                            "wells": int(frame.loc[field_mask, "well"].nunique()),
                            "baseline_rmse": rmse(y[field_mask], base[field_mask]),
                            "direct_rmse": rmse(
                                y[field_mask],
                                (base + direct_correction)[field_mask],
                            ),
                            "learned_rmse": rmse(
                                y[field_mask],
                                (base + learned_correction)[field_mask],
                            ),
                        }
                    )
        summary["splits"][split] = {
            "rows": int(mask.sum()),
            "wells": int(frame.loc[mask, "well"].nunique()),
            "proxies": proxy_results,
            "field_results": field_rows,
        }

    holdout_results = summary["splits"]["holdout_combined"]["proxies"]
    summary["promotion"] = {
        "direct_all_holdout_proxies_improve": all(
            values["direct_improvement"] > 0.0
            for values in holdout_results.values()
        ),
        "learned_all_holdout_proxies_improve": all(
            values["learned_improvement"] > 0.0
            for values in holdout_results.values()
        ),
        "direct_minimum_holdout_improvement": float(
            min(values["direct_improvement"] for values in holdout_results.values())
        ),
        "learned_minimum_holdout_improvement": float(
            min(values["learned_improvement"] for values in holdout_results.values())
        ),
        "required_effect_ft": 0.08,
    }
    summary["promotion"]["direct_passes_effect_gate"] = bool(
        summary["promotion"]["direct_minimum_holdout_improvement"] >= 0.08
    )
    summary["promotion"]["learned_passes_effect_gate"] = bool(
        summary["promotion"]["learned_minimum_holdout_improvement"] >= 0.08
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.output, index=False)
    report_frame.to_csv(args.report, index=False)
    args.summary.write_text(
        json.dumps(summary, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, default=str))
    return summary


def parse_tuple(value: str, cast=float) -> tuple:
    return tuple(cast(part.strip()) for part in value.split(",") if part.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--incumbent-cache", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--scan-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--radius", type=float, default=60.0)
    parser.add_argument("--offset-step", type=float, default=1.0)
    parser.add_argument("--stride", type=int, default=32)
    parser.add_argument("--half-window", type=int, default=256)
    parser.add_argument("--window-step", type=int, default=4)
    parser.add_argument("--temperatures", default="0.05,0.10,0.20,0.50,1.0")
    parser.add_argument("--prior-strength", type=float, default=0.05)
    parser.add_argument("--gr-scale", type=float, default=1.30)
    parser.add_argument("--caps", default="2,4,8")
    parser.add_argument("--taus", default="0,100,300")
    parser.add_argument("--scales", default="0,0.02,0.05,0.10,0.20,0.30")
    parser.add_argument("--alpha-grid", default="1,10,100,1000,10000")
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    args.temperatures = parse_tuple(args.temperatures)
    args.caps = parse_tuple(args.caps)
    args.taus = parse_tuple(args.taus)
    args.scales = parse_tuple(args.scales)
    args.alpha_grid = parse_tuple(args.alpha_grid)
    run(args)


if __name__ == "__main__":
    main()
