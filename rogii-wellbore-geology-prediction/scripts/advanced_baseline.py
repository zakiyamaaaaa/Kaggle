"""Leakage-safe, lightweight typewell GR tracking baselines.

The competition's public notebooks use particle filters and beam search. This
file keeps the same central idea in a small, CPU-friendly implementation so
that experiments can be reproduced locally before making a Kaggle notebook.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd


def _data_root(path: str | Path) -> Path:
    root = Path(path)
    if (root / "train").exists() and (root / "test").exists():
        return root
    candidates = sorted(root.rglob("sample_submission.csv"))
    if not candidates:
        raise FileNotFoundError(f"Could not find competition data under {root}")
    return candidates[0].parent


def _typewell_arrays(typewell: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    tw = typewell[["TVT", "GR"]].dropna().sort_values("TVT")
    tvt = tw["TVT"].to_numpy(float)
    gr = tw["GR"].to_numpy(float)
    order = np.argsort(tvt)
    tvt, gr = tvt[order], gr[order]
    unique, first = np.unique(tvt, return_index=True)
    if len(unique) != len(tvt):
        gr = np.array([np.median(gr[tvt == value]) for value in unique])
        tvt = unique
    return tvt, gr


def _nearest_index(values: np.ndarray, value: float) -> int:
    pos = int(np.searchsorted(values, value))
    if pos <= 0:
        return 0
    if pos >= len(values):
        return len(values) - 1
    return pos - 1 if abs(values[pos - 1] - value) <= abs(values[pos] - value) else pos


def _smooth(values: pd.Series, window: int) -> np.ndarray:
    s = values.astype(float).interpolate(limit_direction="both")
    if s.isna().all():
        return np.zeros(len(s), dtype=float)
    s = s.fillna(float(s.median()))
    if window <= 1:
        return s.to_numpy(float)
    return s.rolling(window, center=True, min_periods=1).median().to_numpy(float)


def _gr_sigma(horizontal: pd.DataFrame, tw_tvt: np.ndarray, tw_gr: np.ndarray) -> float:
    known = horizontal[horizontal["TVT_input"].notna() & horizontal["GR"].notna()]
    if len(known) < 20:
        return 30.0
    expected = np.interp(known["TVT_input"].to_numpy(float), tw_tvt, tw_gr)
    residual = known["GR"].to_numpy(float) - expected
    return float(np.clip(np.nanstd(residual), 10.0, 60.0))


def _normalized_corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) != len(b) or len(a) < 2:
        return 0.0
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a - float(np.mean(a))
    b = b - float(np.mean(b))
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-8:
        return 0.0
    return float(np.dot(a, b) / denom)


def beam_suffix(
    horizontal: pd.DataFrame,
    typewell: pd.DataFrame,
    beam_size: int = 8,
    max_step_indices: int = 3,
    movement_penalty: float = 0.75,
    smooth_window: int = 5,
) -> np.ndarray:
    """Track a TVT path from the last known TVT using a bounded beam.

    The method only reads GR and the observed TVT_input prefix. The suffix
    target TVT is never consulted, making it suitable for local validation.
    """
    known = horizontal[horizontal["TVT_input"].notna()]
    unknown = horizontal[horizontal["TVT_input"].isna()]
    if len(unknown) == 0 or len(known) == 0:
        return np.array([], dtype=float)

    tw_tvt, tw_gr = _typewell_arrays(typewell)
    if len(tw_tvt) < 3:
        return np.full(len(unknown), float(known["TVT_input"].iloc[-1]))

    start_tvt = float(known["TVT_input"].iloc[-1])
    start_idx = _nearest_index(tw_tvt, start_tvt)
    sigma = _gr_sigma(horizontal, tw_tvt, tw_gr)
    obs = _smooth(unknown["GR"], smooth_window)
    offsets = np.arange(-max_step_indices, max_step_indices + 1, dtype=int)

    # A beam is represented by its current typewell index and cumulative cost.
    # Backpointers make it possible to return the globally best path at the end.
    prev_idx = np.array([start_idx], dtype=int)
    prev_cost = np.array([0.0], dtype=float)
    history_idx: list[np.ndarray] = []
    history_parent: list[np.ndarray] = []
    tvt_step = float(np.nanmedian(np.diff(tw_tvt))) if len(tw_tvt) > 1 else 1.0
    tvt_step = max(abs(tvt_step), 1e-3)

    for value in obs:
        candidate_idx = np.clip(prev_idx[:, None] + offsets[None, :], 0, len(tw_tvt) - 1)
        candidate_idx = candidate_idx.ravel()
        parent = np.repeat(np.arange(len(prev_idx)), len(offsets))
        movement = np.abs(candidate_idx - prev_idx[parent])
        costs = prev_cost[parent] + ((float(value) - tw_gr[candidate_idx]) / sigma) ** 2
        costs += movement_penalty * movement

        order = np.argsort(costs, kind="stable")
        chosen_idx: list[int] = []
        chosen_parent: list[int] = []
        chosen_cost: list[float] = []
        for oi in order:
            ci = int(candidate_idx[oi])
            if ci in chosen_idx:
                continue
            chosen_idx.append(ci)
            chosen_parent.append(int(parent[oi]))
            chosen_cost.append(float(costs[oi]))
            if len(chosen_idx) >= beam_size:
                break
        if not chosen_idx:
            chosen_idx = [int(prev_idx[0])]
            chosen_parent = [0]
            chosen_cost = [float(prev_cost[0])]
        history_idx.append(np.asarray(chosen_idx, dtype=int))
        history_parent.append(np.asarray(chosen_parent, dtype=int))
        prev_idx = np.asarray(chosen_idx, dtype=int)
        prev_cost = np.asarray(chosen_cost, dtype=float)

    path = np.empty(len(history_idx), dtype=float)
    parent = int(np.argmin(prev_cost))
    for row in range(len(history_idx) - 1, -1, -1):
        path[row] = tw_tvt[history_idx[row][parent]]
        parent = int(history_parent[row][parent])

    # The first decoded row should not jump solely because the typewell has a
    # different absolute datum. Align the decoded suffix to the known prefix.
    path += start_tvt - path[0]
    return path


def ncc_suffix(
    horizontal: pd.DataFrame,
    typewell: pd.DataFrame,
    smooth_window: int = 7,
    lookback: int = 21,
    search_radius: int = 12,
    move_penalty: float = 0.02,
) -> np.ndarray:
    """Causal NCC decoder using only the observed prefix and past suffix GR."""
    known = horizontal[horizontal["TVT_input"].notna()]
    unknown = horizontal[horizontal["TVT_input"].isna()]
    if len(unknown) == 0 or len(known) == 0:
        return np.array([], dtype=float)

    tw_tvt, tw_gr = _typewell_arrays(typewell)
    if len(tw_tvt) < lookback + 2:
        return np.full(len(unknown), float(known["TVT_input"].iloc[-1]))

    start_tvt = float(known["TVT_input"].iloc[-1])
    start_idx = _nearest_index(tw_tvt, start_tvt)

    known_gr = _smooth(known["GR"], smooth_window)
    unknown_gr = _smooth(unknown["GR"], smooth_window)
    history = np.concatenate([known_gr[-(lookback - 1):], unknown_gr]) if lookback > 1 else unknown_gr

    path_idx = np.empty(len(unknown), dtype=int)
    prev_idx = start_idx
    for row in range(len(unknown)):
        end = (lookback - 1) + row + 1
        start = max(0, end - lookback)
        segment = history[start:end]
        best_idx = prev_idx
        best_score = -np.inf
        left = max(len(segment) - 1, prev_idx - search_radius)
        right = min(len(tw_gr) - 1, prev_idx + search_radius)
        for candidate in range(left, right + 1):
            ref = tw_gr[candidate - len(segment) + 1 : candidate + 1]
            score = _normalized_corr(segment, ref) - move_penalty * abs(candidate - prev_idx)
            if score > best_score:
                best_score = score
                best_idx = candidate
        path_idx[row] = best_idx
        prev_idx = best_idx

    path = tw_tvt[path_idx].astype(float)
    path += start_tvt - path[0]
    return path


def particle_suffix(
    horizontal: pd.DataFrame,
    typewell: pd.DataFrame,
    particle_count: int = 48,
    process_sigma: float = 2.0,
    smooth_window: int = 5,
    seed: int = 1729,
) -> np.ndarray:
    """Track a TVT state with a small, deterministic bootstrap particle filter.

    Particles live on the typewell sample index.  Each row first propagates
    with a zero-mean local random walk and then receives a GR likelihood.  The
    suffix GR is available at inference time, while the suffix TVT is never
    read, so this remains valid for prefix-to-suffix validation.
    """
    known = horizontal[horizontal["TVT_input"].notna()]
    unknown = horizontal[horizontal["TVT_input"].isna()]
    if len(unknown) == 0 or len(known) == 0:
        return np.array([], dtype=float)

    tw_tvt, tw_gr = _typewell_arrays(typewell)
    if len(tw_tvt) < 3:
        return np.full(len(unknown), float(known["TVT_input"].iloc[-1]))

    start_tvt = float(known["TVT_input"].iloc[-1])
    start_idx = _nearest_index(tw_tvt, start_tvt)
    sigma = _gr_sigma(horizontal, tw_tvt, tw_gr)
    obs = _smooth(unknown["GR"], smooth_window)
    n_particles = max(8, int(particle_count))
    rng = np.random.default_rng(seed)

    # Keep the initial cloud local but retain an exact particle at the
    # observed datum.  This avoids injecting a large absolute-datum error.
    positions = np.clip(
        start_idx + np.rint(rng.normal(0.0, process_sigma, n_particles)).astype(int),
        0,
        len(tw_tvt) - 1,
    )
    positions[0] = start_idx
    weights = np.full(n_particles, 1.0 / n_particles, dtype=float)
    decoded = np.empty(len(obs), dtype=float)

    for row, value in enumerate(obs):
        steps = np.rint(rng.normal(0.0, process_sigma, n_particles)).astype(int)
        candidates = np.clip(positions + steps, 0, len(tw_tvt) - 1)
        residual = (float(value) - tw_gr[candidates]) / sigma
        log_weights = -0.5 * residual * residual - 0.10 * np.abs(steps)
        log_weights += np.log(np.maximum(weights, 1e-12))
        log_weights -= float(np.max(log_weights))
        weights = np.exp(log_weights)
        weight_sum = float(np.sum(weights))
        if not np.isfinite(weight_sum) or weight_sum <= 0.0:
            weights.fill(1.0 / n_particles)
        else:
            weights /= weight_sum

        # Weighted mean is less jumpy than selecting the MAP particle and is
        # intentionally kept as a conservative decoder output.
        decoded[row] = float(np.sum(tw_tvt[candidates] * weights))
        ess = 1.0 / float(np.sum(weights * weights))
        if ess < 0.55 * n_particles:
            # Systematic resampling is deterministic given the fixed RNG and
            # keeps the implementation vectorized for the full 773-well run.
            sample_idx = np.searchsorted(
                np.cumsum(weights),
                (np.arange(n_particles) + rng.random()) / n_particles,
            )
            positions = candidates[np.minimum(sample_idx, n_particles - 1)]
            weights.fill(1.0 / n_particles)
        else:
            positions = candidates

    decoded += start_tvt - decoded[0]
    return decoded


def physics_anchor_suffix(
    horizontal: pd.DataFrame,
    anchor_window: int = 20,
) -> np.ndarray:
    """Predict from a causal ``TVT + Z`` anchor.

    The anchor is estimated only from the observed TVT_input prefix.  Test
    wells expose Z in the suffix, while their formation columns are absent,
    so this deliberately uses no hidden TVT or training-only surface column.
    """
    known = horizontal[horizontal["TVT_input"].notna()]
    unknown = horizontal[horizontal["TVT_input"].isna()]
    if len(unknown) == 0 or len(known) == 0:
        return np.array([], dtype=float)
    last = float(known["TVT_input"].iloc[-1])
    known_z = pd.to_numeric(known["Z"], errors="coerce").to_numpy(float)
    known_tvt = known["TVT_input"].to_numpy(float)
    valid = np.isfinite(known_z) & np.isfinite(known_tvt)
    if not valid.any():
        return np.full(len(unknown), last, dtype=float)
    anchor_values = (known_tvt[valid] + known_z[valid])[-anchor_window:]
    anchor = float(np.median(anchor_values))
    z = pd.to_numeric(unknown["Z"], errors="coerce").to_numpy(float)
    decoded = anchor - z
    return np.where(np.isfinite(decoded), decoded, last)


def build_spatial_metadata(train_dir: Path) -> dict[str, np.ndarray]:
    """Collect prefix-only TVT+Z anchors and XY locations for local KNN.

    The formation columns are absent from test horizontal wells.  A usable
    spatial proxy is therefore the local TVT+Z datum measured before the
    prediction boundary.  Every metadata row is built from its own observed
    TVT_input prefix and Z only; hidden suffix TVT is never read.
    """
    well_ids: list[str] = []
    x_values: list[float] = []
    y_values: list[float] = []
    anchors: list[float] = []
    for fp in sorted(train_dir.glob("*__horizontal_well.csv")):
        try:
            hw = pd.read_csv(fp, usecols=["X", "Y", "Z", "TVT_input"])
        except (FileNotFoundError, ValueError):
            continue
        known = hw[hw["TVT_input"].notna()]
        if len(known) == 0:
            continue
        tail = known.tail(20)
        anchor_values = pd.to_numeric(tail["TVT_input"], errors="coerce") + pd.to_numeric(
            tail["Z"], errors="coerce"
        )
        anchor_values = anchor_values[np.isfinite(anchor_values)]
        if len(anchor_values) == 0:
            continue
        x = float(pd.to_numeric(tail["X"], errors="coerce").median())
        y = float(pd.to_numeric(tail["Y"], errors="coerce").median())
        if not (np.isfinite(x) and np.isfinite(y)):
            continue
        well_ids.append(fp.name.split("__", 1)[0])
        x_values.append(x)
        y_values.append(y)
        anchors.append(float(np.median(anchor_values)))
    return {
        "well_ids": np.asarray(well_ids, dtype=object),
        "x": np.asarray(x_values, dtype=float),
        "y": np.asarray(y_values, dtype=float),
        "anchor": np.asarray(anchors, dtype=float),
    }


def spatial_plane_suffix(
    horizontal: pd.DataFrame,
    spatial_metadata: dict[str, np.ndarray],
    well_id: str | None = None,
    neighbor_count: int = 12,
) -> np.ndarray:
    """Predict a suffix from a local XY plane of prefix-only TVT+Z anchors."""
    known = horizontal[horizontal["TVT_input"].notna()]
    unknown = horizontal[horizontal["TVT_input"].isna()]
    if len(unknown) == 0 or len(known) == 0:
        return np.array([], dtype=float)
    fallback = physics_anchor_suffix(horizontal)
    meta_x = spatial_metadata.get("x", np.array([], dtype=float))
    meta_y = spatial_metadata.get("y", np.array([], dtype=float))
    meta_anchor = spatial_metadata.get("anchor", np.array([], dtype=float))
    meta_ids = spatial_metadata.get("well_ids", np.array([], dtype=object))
    if len(meta_x) < 3:
        return fallback

    known_tail = known.tail(20)
    query_x = float(pd.to_numeric(known_tail["X"], errors="coerce").median())
    query_y = float(pd.to_numeric(known_tail["Y"], errors="coerce").median())
    if not (np.isfinite(query_x) and np.isfinite(query_y)):
        return fallback
    distance = np.hypot((meta_x - query_x) / 1000.0, (meta_y - query_y) / 1000.0)
    allowed = np.isfinite(distance) & np.isfinite(meta_anchor)
    if well_id is not None and len(meta_ids) == len(allowed):
        allowed &= meta_ids != well_id
    neighbor_idx = np.flatnonzero(allowed)
    if len(neighbor_idx) < 3:
        return fallback
    neighbor_idx = neighbor_idx[np.argsort(distance[neighbor_idx], kind="stable")[: max(3, neighbor_count)]]
    scale = max(float(np.median(distance[neighbor_idx])), 0.01)
    dx = (meta_x[neighbor_idx] - query_x) / 1000.0 / scale
    dy = (meta_y[neighbor_idx] - query_y) / 1000.0 / scale
    design = np.column_stack([np.ones(len(neighbor_idx)), dx, dy])
    weights = 1.0 / np.maximum(distance[neighbor_idx], 0.01)
    weighted_design = design * np.sqrt(weights)[:, None]
    weighted_target = meta_anchor[neighbor_idx] * np.sqrt(weights)
    try:
        coef, *_ = np.linalg.lstsq(weighted_design, weighted_target, rcond=None)
    except np.linalg.LinAlgError:
        return fallback
    suffix_x = pd.to_numeric(unknown["X"], errors="coerce").to_numpy(float)
    suffix_y = pd.to_numeric(unknown["Y"], errors="coerce").to_numpy(float)
    suffix_z = pd.to_numeric(unknown["Z"], errors="coerce").to_numpy(float)
    pred_anchor = coef[0] + coef[1] * (suffix_x - query_x) / 1000.0 / scale + coef[2] * (
        suffix_y - query_y
    ) / 1000.0 / scale
    decoded = pred_anchor - suffix_z
    return np.where(np.isfinite(decoded), decoded, fallback)


def predict_well(
    horizontal: pd.DataFrame,
    typewell: pd.DataFrame,
    method: str,
    spatial_metadata: dict[str, np.ndarray] | None = None,
    well_id: str | None = None,
) -> np.ndarray:
    known = horizontal[horizontal["TVT_input"].notna()]
    unknown = horizontal[horizontal["TVT_input"].isna()]
    if len(unknown) == 0:
        return np.array([], dtype=float)
    last = float(known["TVT_input"].iloc[-1]) if len(known) else 0.0
    if method == "last":
        return np.full(len(unknown), last, dtype=float)
    if method in {"beam", "safe_beam"}:
        decoded = beam_suffix(horizontal, typewell)
    elif method in {"ncc", "safe_ncc"}:
        decoded = ncc_suffix(horizontal, typewell)
    elif method in {"particle", "safe_particle"}:
        decoded = particle_suffix(horizontal, typewell)
    elif method == "safe_physics":
        decoded = physics_anchor_suffix(horizontal)
    elif method == "safe_spatial_plane":
        if spatial_metadata is None:
            decoded = physics_anchor_suffix(horizontal)
        else:
            decoded = spatial_plane_suffix(horizontal, spatial_metadata, well_id=well_id)
    else:
        raise ValueError(f"Unknown method: {method}")
    if method == "beam":
        return decoded
    if method == "safe_beam":
        # A deliberately conservative blend. The fallback is useful when the
        # GR signature is ambiguous, a failure mode noted in Discussion.
        if len(decoded) == 0:
            return np.full(len(unknown), last, dtype=float)
        delta = decoded - last
        return last + 0.20 * np.clip(delta, -60.0, 60.0)
    if method == "ncc":
        return decoded
    if method == "safe_ncc":
        if len(decoded) == 0:
            return np.full(len(unknown), last, dtype=float)
        delta = decoded - last
        return last + 0.15 * np.clip(delta, -40.0, 40.0)
    if method == "particle":
        return decoded
    if method == "safe_particle":
        if len(decoded) == 0:
            return np.full(len(unknown), last, dtype=float)
        delta = decoded - last
        return last + 0.20 * np.clip(delta, -60.0, 60.0)
    if method == "safe_physics":
        if len(decoded) == 0:
            return np.full(len(unknown), last, dtype=float)
        delta = decoded - last
        return last + 0.04 * np.clip(delta, -40.0, 40.0)
    if method == "safe_spatial_plane":
        if len(decoded) == 0:
            return np.full(len(unknown), last, dtype=float)
        delta = decoded - last
        return last + 0.10 * np.clip(delta, -60.0, 60.0)
    raise ValueError(f"Unknown method: {method}")


def evaluate(train_dir: Path, method: str, max_wells: int | None = None) -> dict[str, float]:
    files = sorted(train_dir.glob("*__horizontal_well.csv"))
    if max_wells is not None:
        files = files[:max_wells]
    if method == "grid":
        return evaluate_grid(train_dir, max_wells)
    spatial_metadata = build_spatial_metadata(train_dir) if method == "safe_spatial_plane" else None
    sse = 0.0
    n = 0
    well_rmses = []
    for fp in files:
        wid = fp.name.split("__", 1)[0]
        tw_path = train_dir / f"{wid}__typewell.csv"
        if not tw_path.exists():
            continue
        hw = pd.read_csv(fp)
        if "TVT" not in hw or "TVT_input" not in hw:
            continue
        mask = hw["TVT_input"].isna() & hw["TVT"].notna()
        if not mask.any() or not hw["TVT_input"].notna().any():
            continue
        pred = predict_well(
            hw,
            pd.read_csv(tw_path),
            method,
            spatial_metadata=spatial_metadata,
            well_id=wid,
        )
        truth = hw.loc[mask, "TVT"].to_numpy(float)
        good = np.isfinite(pred) & np.isfinite(truth)
        if not good.any():
            continue
        error = pred[good] - truth[good]
        sse += float(np.sum(error * error))
        n += int(good.sum())
        well_rmses.append(float(np.sqrt(np.mean(error * error))))
    return {
        "method": method,
        "rmse": float(np.sqrt(sse / n)) if n else float("nan"),
        "rows": float(n),
        "wells": float(len(well_rmses)),
        "well_rmse_p50": float(np.percentile(well_rmses, 50)) if well_rmses else float("nan"),
        "well_rmse_p90": float(np.percentile(well_rmses, 90)) if well_rmses else float("nan"),
    }


def evaluate_grid(train_dir: Path, max_wells: int | None = None) -> dict[str, float]:
    """Decode each well once and search conservative blend settings."""
    files = sorted(train_dir.glob("*__horizontal_well.csv"))
    if max_wells is not None:
        files = files[:max_wells]
    settings = [(a, c) for a in [0.10, 0.20, 0.35, 0.50, 0.70, 1.0] for c in [15.0, 30.0, 60.0, 1e9]]
    sse = {key: 0.0 for key in settings}
    counts = {key: 0 for key in settings}
    by_well = {key: [] for key in settings}
    for fp in files:
        wid = fp.name.split("__", 1)[0]
        tw_path = train_dir / f"{wid}__typewell.csv"
        if not tw_path.exists():
            continue
        hw = pd.read_csv(fp)
        mask = hw["TVT_input"].isna() & hw["TVT"].notna()
        if not mask.any() or not hw["TVT_input"].notna().any():
            continue
        last = float(hw.loc[hw["TVT_input"].notna(), "TVT_input"].iloc[-1])
        decoded = beam_suffix(hw, pd.read_csv(tw_path))
        truth = hw.loc[mask, "TVT"].to_numpy(float)
        for key in settings:
            alpha, clip = key
            pred = last + alpha * np.clip(decoded - last, -clip, clip)
            good = np.isfinite(pred) & np.isfinite(truth)
            err = pred[good] - truth[good]
            sse[key] += float(np.sum(err * err))
            counts[key] += int(good.sum())
            by_well[key].append(float(np.sqrt(np.mean(err * err))))
    summaries = []
    for key in settings:
        alpha, clip = key
        vals = by_well[key]
        summaries.append({
            "alpha": alpha,
            "clip": clip,
            "rmse": float(np.sqrt(sse[key] / counts[key])),
            "rows": counts[key],
            "well_rmse_p50": float(np.percentile(vals, 50)),
            "well_rmse_p90": float(np.percentile(vals, 90)),
        })
    best = min(summaries, key=lambda x: x["rmse"])
    print(pd.DataFrame(summaries).sort_values("rmse").to_string(index=False))
    return {"method": "grid", **best}


def write_submission(data_root: Path, output: Path, method: str) -> None:
    test_dir = data_root / "test"
    sample = pd.read_csv(data_root / "sample_submission.csv")
    values: dict[str, float] = {}
    spatial_metadata = build_spatial_metadata(data_root / "train") if method == "safe_spatial_plane" else None
    for fp in sorted(test_dir.glob("*__horizontal_well.csv")):
        wid = fp.name.split("__", 1)[0]
        tw_path = test_dir / f"{wid}__typewell.csv"
        if not tw_path.exists():
            continue
        hw = pd.read_csv(fp)
        mask = hw["TVT_input"].isna()
        pred = predict_well(
            hw,
            pd.read_csv(tw_path),
            method,
            spatial_metadata=spatial_metadata,
            well_id=wid,
        )
        for row_idx, value in zip(hw.index[mask], pred):
            values[f"{wid}_{row_idx}"] = float(value)
    out = sample[["id"]].copy()
    fallback = float(np.nanmedian(list(values.values()))) if values else 0.0
    out["tvt"] = out["id"].map(values).fillna(fallback)
    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="data/raw")
    parser.add_argument(
        "--method",
        choices=["last", "beam", "safe_beam", "ncc", "safe_ncc", "particle", "safe_particle", "safe_physics", "safe_spatial_plane", "grid"],
        default="safe_beam",
    )
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--max-wells", type=int)
    parser.add_argument("--output")
    args = parser.parse_args()
    root = _data_root(args.data_root)
    started = time.perf_counter()
    if args.evaluate:
        print(evaluate(root / "train", args.method, args.max_wells))
    if args.output:
        write_submission(root, Path(args.output), args.method)
    print({"elapsed_sec": round(time.perf_counter() - started, 3)})


if __name__ == "__main__":
    main()
