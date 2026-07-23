"""Evaluate a calibrated, target-free Viterbi trajectory candidate.

The public high-scoring pipelines calibrate horizontal-well GR against the
typewell on the visible heel, then track a smooth trajectory through the full
test-time GR sequence.  This experiment implements that general idea without
pretrained public artifacts or public-well-specific postprocessing.

The hidden state is a correction to a legal center trajectory in
``U = TVT + Z`` space. Emissions compare calibrated horizontal GR with
typewell GR, while a bounded transition keeps the correction smooth. Suffix
TVT is used only for local scoring, never by ``predict_suffix``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ViterbiConfig:
    state_radius: float = 60.0
    state_step: float = 0.5
    row_stride: int = 8
    max_transition_steps: int = 4
    transition_penalty: float = 0.08
    start_penalty: float = 0.02
    gr_smooth_window: int = 7
    calibration_rows: int = 800
    calibration_iters: int = 4
    residual_clip: float = 6.0


def load_advanced(path: Path):
    spec = importlib.util.spec_from_file_location("advanced_baseline", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rolling_median(values: np.ndarray, window: int) -> np.ndarray:
    series = pd.Series(np.asarray(values, dtype=float))
    smoothed = series.rolling(
        max(1, int(window)),
        center=True,
        min_periods=1,
    ).median()
    if smoothed.isna().any():
        smoothed = smoothed.interpolate(limit_direction="both")
    return smoothed.to_numpy(float)


def _typewell_arrays(typewell: pd.DataFrame, smooth_window: int) -> tuple[np.ndarray, np.ndarray]:
    frame = typewell[["TVT", "GR"]].copy()
    frame["TVT"] = pd.to_numeric(frame["TVT"], errors="coerce")
    frame["GR"] = pd.to_numeric(frame["GR"], errors="coerce")
    frame = frame.dropna().groupby("TVT", as_index=False)["GR"].median().sort_values("TVT")
    tvt = frame["TVT"].to_numpy(float)
    gr = _rolling_median(frame["GR"].to_numpy(float), smooth_window)
    return tvt, gr


def _robust_affine_calibration(
    horizontal: pd.DataFrame,
    tw_tvt: np.ndarray,
    tw_gr: np.ndarray,
    config: ViterbiConfig,
) -> tuple[float, float, float, int]:
    known = horizontal.loc[horizontal["TVT_input"].notna(), ["TVT_input", "GR"]].copy()
    known["TVT_input"] = pd.to_numeric(known["TVT_input"], errors="coerce")
    known["GR"] = pd.to_numeric(known["GR"], errors="coerce")
    known = known.dropna().tail(max(50, int(config.calibration_rows)))
    if len(known) < 20 or len(tw_tvt) < 3:
        sigma = float(pd.to_numeric(horizontal["GR"], errors="coerce").std())
        return 1.0, 0.0, max(sigma, 5.0), int(len(known))

    observed = _rolling_median(
        known["GR"].to_numpy(float),
        config.gr_smooth_window,
    )
    reference = np.interp(known["TVT_input"].to_numpy(float), tw_tvt, tw_gr)
    valid = np.isfinite(observed) & np.isfinite(reference)
    observed = observed[valid]
    reference = reference[valid]
    if len(observed) < 20 or float(np.std(reference)) < 1e-6:
        sigma = float(np.nanstd(observed))
        return 1.0, float(np.nanmedian(observed - reference)), max(sigma, 5.0), int(len(observed))

    design = np.column_stack([reference, np.ones(len(reference))])
    coef, *_ = np.linalg.lstsq(design, observed, rcond=None)
    alpha, beta = float(coef[0]), float(coef[1])
    for _ in range(max(0, int(config.calibration_iters))):
        fitted = alpha * reference + beta
        residual = observed - fitted
        scale = float(np.median(np.abs(residual - np.median(residual))) * 1.4826 + 1e-6)
        huber = np.minimum(1.0, 2.0 * scale / np.maximum(np.abs(residual), 1e-6))
        weighted_design = design * np.sqrt(huber)[:, None]
        weighted_target = observed * np.sqrt(huber)
        coef, *_ = np.linalg.lstsq(weighted_design, weighted_target, rcond=None)
        alpha, beta = float(coef[0]), float(coef[1])

    alpha = float(np.clip(alpha, 0.25, 4.0))
    beta = float(np.median(observed - alpha * reference))
    residual = observed - (alpha * reference + beta)
    sigma = float(np.median(np.abs(residual - np.median(residual))) * 1.4826)
    sigma_floor = max(2.0, 0.05 * float(np.std(observed)))
    return alpha, beta, max(sigma, sigma_floor), int(len(observed))


def _sample_positions(length: int, stride: int) -> np.ndarray:
    if length <= 0:
        return np.array([], dtype=int)
    positions = np.arange(0, length, max(1, int(stride)), dtype=int)
    if positions[-1] != length - 1:
        positions = np.append(positions, length - 1)
    return positions


def _transition_min(
    previous: np.ndarray,
    max_steps: int,
    transition_penalty: float,
    state_step: float,
) -> tuple[np.ndarray, np.ndarray]:
    n_states = len(previous)
    shifts = np.arange(-max_steps, max_steps + 1, dtype=int)
    candidates = np.full((len(shifts), n_states), np.inf, dtype=float)
    for row, shift in enumerate(shifts):
        # current_state = previous_state + shift
        if shift >= 0:
            candidates[row, shift:] = previous[: n_states - shift]
        else:
            candidates[row, : n_states + shift] = previous[-shift:]
        candidates[row] += transition_penalty * abs(shift * state_step)
    choice = np.argmin(candidates, axis=0)
    best = candidates[choice, np.arange(n_states)]
    previous_index = np.arange(n_states) - shifts[choice]
    return best, previous_index.astype(np.int16)


def predict_suffix(
    horizontal: pd.DataFrame,
    typewell: pd.DataFrame,
    config: ViterbiConfig,
    center_prediction: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, float]]:
    """Predict unknown TVT using only columns available at inference time."""
    known = horizontal[horizontal["TVT_input"].notna()]
    unknown = horizontal[horizontal["TVT_input"].isna()]
    if len(known) == 0 or len(unknown) == 0:
        return np.array([], dtype=float), {"status": "empty"}

    last_tvt = float(pd.to_numeric(known["TVT_input"], errors="coerce").dropna().iloc[-1])
    if center_prediction is None:
        center_full = np.full(len(unknown), last_tvt, dtype=float)
    else:
        center_full = np.asarray(center_prediction, dtype=float).copy()
        if len(center_full) != len(unknown):
            raise ValueError("center_prediction length must match unknown suffix rows")
        center_full[~np.isfinite(center_full)] = last_tvt

    tw_tvt, tw_gr = _typewell_arrays(typewell, config.gr_smooth_window)
    if len(tw_tvt) < 3:
        return np.full(len(unknown), last_tvt), {"status": "typewell_too_short"}
    alpha, beta, sigma, calibration_n = _robust_affine_calibration(
        horizontal,
        tw_tvt,
        tw_gr,
        config,
    )

    all_gr = pd.to_numeric(horizontal["GR"], errors="coerce").to_numpy(float)
    smoothed_gr = _rolling_median(all_gr, config.gr_smooth_window)
    unknown_positions = unknown.index.to_numpy(int)
    observed_full = smoothed_gr[unknown_positions]
    if not np.isfinite(observed_full).all():
        observed_full = (
            pd.Series(observed_full)
            .interpolate(limit_direction="both")
            .fillna(float(np.nanmedian(smoothed_gr)))
            .to_numpy(float)
        )
    sample_pos = _sample_positions(len(unknown), config.row_stride)
    observed = observed_full[sample_pos]
    states = np.arange(
        -config.state_radius,
        config.state_radius + 0.5 * config.state_step,
        config.state_step,
        dtype=float,
    )
    # The center path already contains the geometry/low-frequency prior. In U
    # space this is center_prediction + Z; adding a state offset and converting
    # back to TVT is exactly center_prediction + offset.
    candidate_tvt = center_full[sample_pos, None] + states[None, :]
    reference_gr = np.interp(
        candidate_tvt,
        tw_tvt,
        tw_gr,
        left=np.nan,
        right=np.nan,
    )
    scaled_residual = (observed[:, None] - (alpha * reference_gr + beta)) / sigma
    emission = np.minimum(np.square(scaled_residual), config.residual_clip**2)
    emission[~np.isfinite(emission)] = config.residual_clip**2 + 10.0

    center = int(np.argmin(np.abs(states)))
    costs = emission[0] + config.start_penalty * np.square(states)
    costs[center] -= 1e-9
    backpointer = np.empty((len(sample_pos), len(states)), dtype=np.int16)
    backpointer[0] = np.arange(len(states), dtype=np.int16)
    for row in range(1, len(sample_pos)):
        best_previous, previous_index = _transition_min(
            costs,
            max_steps=max(1, int(config.max_transition_steps)),
            transition_penalty=float(config.transition_penalty),
            state_step=float(config.state_step),
        )
        costs = emission[row] + best_previous
        backpointer[row] = previous_index

    state_index = np.empty(len(sample_pos), dtype=np.int16)
    state_index[-1] = int(np.argmin(costs))
    for row in range(len(sample_pos) - 1, 0, -1):
        state_index[row - 1] = backpointer[row, state_index[row]]
    sampled_offsets = states[state_index]
    full_offsets = np.interp(
        np.arange(len(unknown), dtype=float),
        sample_pos.astype(float),
        sampled_offsets,
    )
    decoded = center_full + full_offsets
    decoded = np.where(np.isfinite(decoded), decoded, last_tvt)
    diagnostics = {
        "status": "ok",
        "alpha": alpha,
        "beta": beta,
        "sigma": sigma,
        "calibration_rows": float(calibration_n),
        "offset_min": float(np.min(full_offsets)),
        "offset_max": float(np.max(full_offsets)),
        "offset_std": float(np.std(full_offsets)),
        "sampled_rows": float(len(sample_pos)),
    }
    return decoded, diagnostics


def _parse_numbers(value: str, cast=float) -> tuple:
    return tuple(cast(part.strip()) for part in value.split(",") if part.strip())


def evaluate(
    data_root: Path,
    config: ViterbiConfig,
    base_method: str,
    blend_weights: tuple[float, ...],
    move_clips: tuple[float, ...],
    max_wells: int | None,
) -> dict:
    started = time.perf_counter()
    train_dir = data_root / "train"
    files = sorted(train_dir.glob("*__horizontal_well.csv"))
    if max_wells is not None:
        files = files[:max_wells]
    advanced = load_advanced(Path(__file__).with_name("advanced_baseline.py"))
    spatial_methods = {
        "safe_spatial_plane",
        "safe_spatial_beam_blend",
        "safe_spatial_beam_ncc_agree",
    }
    spatial_metadata = (
        advanced.build_spatial_metadata(train_dir)
        if base_method in spatial_methods
        else None
    )
    settings = [(weight, clip) for weight in blend_weights for clip in move_clips]
    sse = {"base": 0.0, "viterbi": 0.0}
    counts = {"base": 0, "viterbi": 0}
    blend_sse = {setting: 0.0 for setting in settings}
    blend_counts = {setting: 0 for setting in settings}
    well_errors = {"base": [], "viterbi": []}
    blend_well_errors = {setting: [] for setting in settings}
    row_oracle_sse = 0.0
    well_oracle_sse = 0.0
    total_rows = 0
    diagnostics: list[dict[str, float]] = []

    for index, path in enumerate(files, 1):
        well_id = path.name.split("__", 1)[0]
        typewell_path = train_dir / f"{well_id}__typewell.csv"
        if not typewell_path.exists():
            continue
        horizontal = pd.read_csv(path)
        mask = horizontal["TVT_input"].isna() & horizontal["TVT"].notna()
        if not mask.any() or not horizontal["TVT_input"].notna().any():
            continue
        typewell = pd.read_csv(typewell_path)
        base = advanced.predict_well(
            horizontal,
            typewell,
            base_method,
            spatial_metadata=spatial_metadata,
            well_id=well_id,
        )
        viterbi, diagnostic = predict_suffix(
            horizontal,
            typewell,
            config,
            center_prediction=base,
        )
        truth = horizontal.loc[mask, "TVT"].to_numpy(float)
        good = np.isfinite(base) & np.isfinite(viterbi) & np.isfinite(truth)
        if not good.any():
            continue
        base = base[good]
        viterbi = viterbi[good]
        truth = truth[good]
        base_sq = np.square(base - truth)
        viterbi_sq = np.square(viterbi - truth)
        sse["base"] += float(np.sum(base_sq))
        sse["viterbi"] += float(np.sum(viterbi_sq))
        counts["base"] += int(good.sum())
        counts["viterbi"] += int(good.sum())
        well_errors["base"].append(float(np.sqrt(np.mean(base_sq))))
        well_errors["viterbi"].append(float(np.sqrt(np.mean(viterbi_sq))))
        row_oracle_sse += float(np.sum(np.minimum(base_sq, viterbi_sq)))
        if float(np.mean(base_sq)) <= float(np.mean(viterbi_sq)):
            well_oracle_sse += float(np.sum(base_sq))
        else:
            well_oracle_sse += float(np.sum(viterbi_sq))
        total_rows += int(good.sum())

        move = viterbi - base
        for setting in settings:
            weight, clip = setting
            prediction = base + weight * np.clip(move, -clip, clip)
            squared = np.square(prediction - truth)
            blend_sse[setting] += float(np.sum(squared))
            blend_counts[setting] += int(good.sum())
            blend_well_errors[setting].append(float(np.sqrt(np.mean(squared))))
        diagnostic = dict(diagnostic)
        diagnostic["well"] = well_id
        diagnostic["base_rmse"] = float(np.sqrt(np.mean(base_sq)))
        diagnostic["viterbi_rmse"] = float(np.sqrt(np.mean(viterbi_sq)))
        diagnostics.append(diagnostic)
        if index % 25 == 0:
            print(f"evaluated {index}/{len(files)} wells", flush=True)

    ranking = []
    for setting in settings:
        rmses = blend_well_errors[setting]
        ranking.append(
            {
                "weight": setting[0],
                "clip": setting[1],
                "rmse": float(np.sqrt(blend_sse[setting] / blend_counts[setting])),
                "well_rmse_p50": float(np.percentile(rmses, 50)),
                "well_rmse_p90": float(np.percentile(rmses, 90)),
            }
        )
    ranking.sort(key=lambda item: item["rmse"])
    result = {
        "method": "calibrated_u_viterbi",
        "config": asdict(config),
        "base_method": base_method,
        "rows": total_rows,
        "wells": len(well_errors["base"]),
        "base_rmse": float(np.sqrt(sse["base"] / counts["base"])),
        "viterbi_rmse": float(np.sqrt(sse["viterbi"] / counts["viterbi"])),
        "base_well_rmse_p50": float(np.percentile(well_errors["base"], 50)),
        "base_well_rmse_p90": float(np.percentile(well_errors["base"], 90)),
        "viterbi_well_rmse_p50": float(np.percentile(well_errors["viterbi"], 50)),
        "viterbi_well_rmse_p90": float(np.percentile(well_errors["viterbi"], 90)),
        "row_oracle_rmse": float(np.sqrt(row_oracle_sse / total_rows)),
        "well_oracle_rmse": float(np.sqrt(well_oracle_sse / total_rows)),
        "blend_ranking": ranking,
        "diagnostics": {
            "calibration_alpha_p50": float(
                np.median([row.get("alpha", np.nan) for row in diagnostics])
            ),
            "calibration_sigma_p50": float(
                np.median([row.get("sigma", np.nan) for row in diagnostics])
            ),
            "offset_std_p50": float(
                np.median([row.get("offset_std", np.nan) for row in diagnostics])
            ),
        },
        "elapsed_sec": float(time.perf_counter() - started),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--base-method", default="safe_spatial_beam_ncc_agree")
    parser.add_argument("--max-wells", type=int)
    parser.add_argument("--state-radius", type=float, default=60.0)
    parser.add_argument("--state-step", type=float, default=0.5)
    parser.add_argument("--row-stride", type=int, default=8)
    parser.add_argument("--max-transition-steps", type=int, default=4)
    parser.add_argument("--transition-penalty", type=float, default=0.08)
    parser.add_argument("--start-penalty", type=float, default=0.02)
    parser.add_argument("--gr-smooth-window", type=int, default=7)
    parser.add_argument("--calibration-rows", type=int, default=800)
    parser.add_argument("--blend-weights", default="0.05,0.1,0.2,0.4")
    parser.add_argument("--move-clips", default="10,20,40")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    config = ViterbiConfig(
        state_radius=args.state_radius,
        state_step=args.state_step,
        row_stride=args.row_stride,
        max_transition_steps=args.max_transition_steps,
        transition_penalty=args.transition_penalty,
        start_penalty=args.start_penalty,
        gr_smooth_window=args.gr_smooth_window,
        calibration_rows=args.calibration_rows,
    )
    result = evaluate(
        args.data_root,
        config,
        args.base_method,
        _parse_numbers(args.blend_weights, float),
        _parse_numbers(args.move_clips, float),
        args.max_wells,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
