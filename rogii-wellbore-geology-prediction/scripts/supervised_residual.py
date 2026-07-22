"""Group-aware supervised residual experiment.

This is the next layer beyond the hand-built decoders: generate legal
candidate paths from the observed prefix, then let a tabular model learn when
to trust each candidate. It deliberately does not read suffix TVT except as
the training target.
"""

from __future__ import annotations

import argparse
import importlib.util
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_squared_error


def load_advanced(path: Path):
    spec = importlib.util.spec_from_file_location("advanced_baseline", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _slope(x: np.ndarray, y: np.ndarray) -> float:
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 3 or np.std(x[mask]) < 1e-8:
        return 0.0
    return float(np.polyfit(x[mask], y[mask], 1)[0])


def build_features(
    hw: pd.DataFrame,
    tw: pd.DataFrame,
    mod,
    spatial_metadata: dict[str, np.ndarray],
    well_id: str,
) -> tuple[pd.DataFrame, np.ndarray]:
    known = hw[hw["TVT_input"].notna()]
    suffix_mask = hw["TVT_input"].isna()
    if "TVT" in hw.columns:
        suffix_mask &= hw["TVT"].notna()
    unknown = hw[suffix_mask]
    if len(known) < 10 or len(unknown) == 0:
        return pd.DataFrame(), np.array([], dtype=float)
    last = float(known["TVT_input"].iloc[-1])
    last_row = known.iloc[-1]
    md = hw["MD"].to_numpy(float)
    idx = unknown.index.to_numpy(int)
    prefix_start = int(idx[0])
    md0 = float(last_row["MD"])
    x0, y0, z0 = (float(last_row[c]) for c in ["X", "Y", "Z"])
    tw_tvt, tw_gr = mod._typewell_arrays(tw)
    tw_gr_at_last = float(np.interp(last, tw_tvt, tw_gr))

    beam = mod.beam_suffix(hw, tw)
    physics = mod.physics_anchor_suffix(hw)
    spatial = mod.spatial_plane_suffix(hw, spatial_metadata, well_id=well_id)
    ncc = mod.ncc_suffix(hw, tw)
    # Rebuild the already validated spatial/beam/NCC blend from these arrays
    # instead of calling the decoder a second time.  This keeps the all-well
    # experiment within the local-loop time budget and exactly matches the
    # production candidate's guarded weights.
    beam_delta = 0.20 * np.clip(beam - last, -60.0, 60.0)
    ncc_delta = 0.15 * np.clip(ncc - last, -40.0, 40.0)
    spatial_delta = 0.10 * np.clip(spatial - last, -60.0, 60.0)
    agree = np.abs(beam - ncc) <= 12.0
    decoder_delta = np.where(agree, 0.5 * (beam_delta + ncc_delta), beam_delta)
    best_blend = last + 0.25 * decoder_delta + 0.75 * spatial_delta
    n = len(unknown)
    gr = pd.to_numeric(hw["GR"], errors="coerce")
    gr_causal = gr.expanding(min_periods=1)
    roll5 = gr.rolling(5, min_periods=1)
    roll21 = gr.rolling(21, min_periods=1)
    row = pd.DataFrame(index=range(n))
    row["MD"] = unknown["MD"].to_numpy(float)
    row["X"] = unknown["X"].to_numpy(float)
    row["Y"] = unknown["Y"].to_numpy(float)
    row["Z"] = unknown["Z"].to_numpy(float)
    row["GR"] = unknown["GR"].to_numpy(float)
    row["gr_missing"] = unknown["GR"].isna().to_numpy(float)
    row["row_from_start"] = idx - prefix_start
    row["row_frac"] = idx / max(len(hw) - 1, 1)
    row["md_from_start"] = unknown["MD"].to_numpy(float) - md0
    row["x_from_start"] = unknown["X"].to_numpy(float) - x0
    row["y_from_start"] = unknown["Y"].to_numpy(float) - y0
    row["z_from_start"] = unknown["Z"].to_numpy(float) - z0
    row["xy_distance"] = np.hypot(row["x_from_start"], row["y_from_start"])
    row["xyz_distance"] = np.sqrt(row["xy_distance"] ** 2 + row["z_from_start"] ** 2)
    row["last_tvt"] = last
    row["known_tvt_mean"] = float(known["TVT_input"].mean())
    row["known_tvt_std"] = float(known["TVT_input"].std())
    row["known_tvt_range"] = float(known["TVT_input"].max() - known["TVT_input"].min())
    row["slope_md"] = _slope(known["MD"].to_numpy(float), known["TVT_input"].to_numpy(float))
    recent = known.tail(min(200, len(known)))
    row["slope_md_recent"] = _slope(recent["MD"].to_numpy(float), recent["TVT_input"].to_numpy(float))
    row["slope_z_recent"] = _slope(recent["Z"].to_numpy(float), recent["TVT_input"].to_numpy(float))
    row["gr_mean_prefix"] = float(known["GR"].mean())
    row["gr_std_prefix"] = float(known["GR"].std())
    row["tw_gr_at_last"] = tw_gr_at_last
    row["gr_minus_tw_last"] = row["GR"] - tw_gr_at_last
    row["gr_causal_mean"] = gr_causal.mean().iloc[idx].to_numpy(float)
    row["gr_roll5_mean"] = roll5.mean().iloc[idx].to_numpy(float)
    row["gr_roll5_std"] = roll5.std().iloc[idx].to_numpy(float)
    row["gr_roll21_mean"] = roll21.mean().iloc[idx].to_numpy(float)
    row["gr_roll21_std"] = roll21.std().iloc[idx].to_numpy(float)
    row["gr_diff1"] = gr.diff().iloc[idx].to_numpy(float)
    row["gr_diff5"] = gr.diff(5).iloc[idx].to_numpy(float)
    row["baseline"] = last
    row["physics"] = physics
    row["beam"] = beam
    row["spatial"] = spatial
    row["ncc"] = ncc
    row["best_blend"] = best_blend
    row["physics_delta"] = physics - last
    row["beam_delta"] = beam_delta
    row["spatial_delta"] = spatial_delta
    row["ncc_delta"] = ncc_delta
    row["best_blend_delta"] = best_blend - last
    row["decoder_gap"] = beam - physics
    row["beam_spatial_gap"] = beam - spatial
    row["beam_ncc_gap"] = beam - ncc
    row["spatial_ncc_gap"] = spatial - ncc
    row["ncc_agrees"] = (np.abs(beam - ncc) <= 12.0).astype(float)
    for window in (25, 100, 250):
        recent = known.tail(min(window, len(known)))
        row[f"slope_md_{window}"] = _slope(
            recent["MD"].to_numpy(float), recent["TVT_input"].to_numpy(float)
        )
        row[f"slope_z_{window}"] = _slope(
            recent["Z"].to_numpy(float), recent["TVT_input"].to_numpy(float)
        )
    row = row.replace([np.inf, -np.inf], np.nan)
    # Hidden/test horizontal files intentionally do not contain the target.
    # Keeping the feature builder usable there lets the fitted selector be
    # applied without creating a fake target column.
    target = (
        unknown["TVT"].to_numpy(float)
        if "TVT" in unknown.columns
        else np.array([], dtype=float)
    )
    return row.reset_index(drop=True), target


def run(data_root: Path, max_wells: int | None, rows_per_well: int, folds: int) -> dict[str, float]:
    started = time.perf_counter()
    mod = load_advanced(Path(__file__).with_name("advanced_baseline.py"))
    files = sorted((data_root / "train").glob("*__horizontal_well.csv"))
    if max_wells is not None:
        files = files[:max_wells]
    spatial_metadata = mod.build_spatial_metadata(data_root / "train")
    frames: list[pd.DataFrame] = []
    targets: list[np.ndarray] = []
    groups: list[np.ndarray] = []
    rng = np.random.default_rng(20260722)
    for i, fp in enumerate(files, 1):
        wid = fp.name.split("__", 1)[0]
        tw_path = data_root / "train" / f"{wid}__typewell.csv"
        if not tw_path.exists():
            continue
        hw = pd.read_csv(fp)
        frame, target = build_features(
            hw, pd.read_csv(tw_path), mod, spatial_metadata, wid
        )
        if frame.empty:
            continue
        if len(frame) > rows_per_well:
            selected = np.sort(rng.choice(len(frame), size=rows_per_well, replace=False))
            frame = frame.iloc[selected].reset_index(drop=True)
            target = target[selected]
        frames.append(frame)
        targets.append(target)
        groups.append(np.full(len(frame), wid, dtype=object))
        if i % 50 == 0:
            print(f"built {i}/{len(files)} wells", flush=True)

    X = pd.concat(frames, ignore_index=True).astype(np.float32)
    y = np.concatenate(targets).astype(np.float32)
    group = np.concatenate(groups)
    candidate = X["best_blend"].to_numpy(float)
    residual = y - candidate
    oof = np.full(len(y), np.nan, dtype=float)
    cv = GroupKFold(n_splits=folds)
    for fold, (train_idx, valid_idx) in enumerate(cv.split(X, residual, group), 1):
        model = HistGradientBoostingRegressor(
            max_iter=350,
            learning_rate=0.045,
            max_leaf_nodes=63,
            l2_regularization=3.0,
            random_state=20260722 + fold,
        )
        model.fit(X.iloc[train_idx], residual[train_idx])
        oof[valid_idx] = candidate[valid_idx] + model.predict(X.iloc[valid_idx])
        print(
            f"fold {fold}: candidate={mean_squared_error(y[valid_idx], candidate[valid_idx])**0.5:.6f} "
            f"hgb={mean_squared_error(y[valid_idx], oof[valid_idx])**0.5:.6f}",
            flush=True,
        )

    good = np.isfinite(oof)
    by_well_candidate: list[float] = []
    by_well_hgb: list[float] = []
    for wid in pd.unique(group):
        mask = good & (group == wid)
        if mask.any():
            by_well_candidate.append(float(np.sqrt(np.mean((candidate[mask] - y[mask]) ** 2))))
            by_well_hgb.append(float(np.sqrt(np.mean((oof[mask] - y[mask]) ** 2))))
    hgb_pred = oof[good]
    candidate_pred = candidate[good]
    truth = y[good]
    return {
        "method": "group_hgb_candidate_selector_all_wells",
        "rows": int(good.sum()),
        "wells": int(pd.Series(group).nunique()),
        "candidate_rmse": float(mean_squared_error(y[good], candidate[good]) ** 0.5),
        "hgb_rmse": float(mean_squared_error(y[good], oof[good]) ** 0.5),
        "candidate_well_rmse_p50": float(np.percentile(by_well_candidate, 50)),
        "candidate_well_rmse_p90": float(np.percentile(by_well_candidate, 90)),
        "hgb_well_rmse_p50": float(np.percentile(by_well_hgb, 50)),
        "hgb_well_rmse_p90": float(np.percentile(by_well_hgb, 90)),
        "hgb_clip40_rmse": float(
            mean_squared_error(
                truth,
                candidate_pred + np.clip(hgb_pred - candidate_pred, -40.0, 40.0),
            )
            ** 0.5
        ),
        "hgb_clip60_rmse": float(
            mean_squared_error(
                truth,
                candidate_pred + np.clip(hgb_pred - candidate_pred, -60.0, 60.0),
            )
            ** 0.5
        ),
        "rows_per_well": rows_per_well,
        "folds": folds,
        "elapsed_sec": float(time.perf_counter() - started),
    }


def fit_and_write_submission(
    data_root: Path, output: Path, rows_per_well: int
) -> dict[str, float]:
    """Fit the selector on balanced train suffix rows and predict local test."""
    started = time.perf_counter()
    mod = load_advanced(Path(__file__).with_name("advanced_baseline.py"))
    spatial_metadata = mod.build_spatial_metadata(data_root / "train")
    rng = np.random.default_rng(20260722)
    frames: list[pd.DataFrame] = []
    targets: list[np.ndarray] = []
    for fp in sorted((data_root / "train").glob("*__horizontal_well.csv")):
        wid = fp.name.split("__", 1)[0]
        tw_path = data_root / "train" / f"{wid}__typewell.csv"
        if not tw_path.exists():
            continue
        frame, target = build_features(
            pd.read_csv(fp), pd.read_csv(tw_path), mod, spatial_metadata, wid
        )
        if frame.empty:
            continue
        if len(frame) > rows_per_well:
            selected = np.sort(rng.choice(len(frame), size=rows_per_well, replace=False))
            frame = frame.iloc[selected].reset_index(drop=True)
            target = target[selected]
        frames.append(frame)
        targets.append(target)
    X = pd.concat(frames, ignore_index=True).astype(np.float32)
    y = np.concatenate(targets).astype(np.float32)
    model = HistGradientBoostingRegressor(
        max_iter=350,
        learning_rate=0.045,
        max_leaf_nodes=63,
        l2_regularization=3.0,
        random_state=20260722,
    )
    model.fit(X, y - X["best_blend"].to_numpy(float))

    sample = pd.read_csv(data_root / "sample_submission.csv")
    values: dict[str, float] = {}
    for fp in sorted((data_root / "test").glob("*__horizontal_well.csv")):
        wid = fp.name.split("__", 1)[0]
        tw_path = data_root / "test" / f"{wid}__typewell.csv"
        if not tw_path.exists():
            continue
        frame, _ = build_features(
            pd.read_csv(fp), pd.read_csv(tw_path), mod, spatial_metadata, wid
        )
        if frame.empty:
            continue
        candidate = frame["best_blend"].to_numpy(float)
        pred = candidate + model.predict(frame.astype(np.float32))
        suffix_rows = pd.read_csv(fp).index[pd.read_csv(fp)["TVT_input"].isna()]
        for row_idx, value in zip(suffix_rows, pred):
            values[f"{wid}_{row_idx}"] = float(value)
    out = sample[["id"]].copy()
    fallback = float(np.nanmedian(list(values.values()))) if values else 0.0
    out["tvt"] = out["id"].map(values).fillna(fallback)
    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False)
    return {
        "rows": int(len(out)),
        "non_null": int(out["tvt"].notna().sum()),
        "elapsed_sec": float(time.perf_counter() - started),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="data/raw")
    parser.add_argument("--max-wells", type=int)
    parser.add_argument("--rows-per-well", type=int, default=500)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.data_root)
    if args.output:
        print(fit_and_write_submission(root, Path(args.output), args.rows_per_well))
    else:
        print(run(root, args.max_wells, args.rows_per_well, args.folds))


if __name__ == "__main__":
    main()
