"""Prefix-only, leakage-safe correction for per-well artifact bias."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def slope(x: np.ndarray, y: np.ndarray) -> float:
    good = np.isfinite(x) & np.isfinite(y)
    if good.sum() < 3 or np.std(x[good]) < 1e-8:
        return 0.0
    return float(np.polyfit(x[good], y[good], 1)[0])


def typewell_arrays(typewell: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    frame = typewell[["TVT", "GR"]].apply(pd.to_numeric, errors="coerce").dropna()
    frame = frame.groupby("TVT", as_index=False)["GR"].median().sort_values("TVT")
    return frame["TVT"].to_numpy(float), frame["GR"].to_numpy(float)


def build_prefix_features(data_root: Path, well_ids: set[str], split: str = "train") -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []
    split_dir = data_root / split
    for path in sorted(split_dir.glob("*__horizontal_well.csv")):
        well_id = path.name.split("__", 1)[0]
        if well_id not in well_ids:
            continue
        typewell_path = split_dir / f"{well_id}__typewell.csv"
        if not typewell_path.exists():
            continue
        horizontal = pd.read_csv(path)
        typewell = pd.read_csv(typewell_path)
        known = horizontal.loc[horizontal["TVT_input"].notna()].copy()
        if len(known) < 5:
            continue
        tw_tvt, tw_gr = typewell_arrays(typewell)
        known_tvt = pd.to_numeric(known["TVT_input"], errors="coerce").to_numpy(float)
        known_gr = pd.to_numeric(known["GR"], errors="coerce").to_numpy(float)
        valid_gr = np.isfinite(known_tvt) & np.isfinite(known_gr)
        reference = np.interp(known_tvt[valid_gr], tw_tvt, tw_gr) if len(tw_tvt) else np.array([])
        gr_residual = known_gr[valid_gr] - reference if len(reference) else np.array([])
        md = pd.to_numeric(known["MD"], errors="coerce").to_numpy(float)
        z = pd.to_numeric(known["Z"], errors="coerce").to_numpy(float)
        tvt = known_tvt
        recent = min(200, len(known))
        rows.append({
            "_oof_well": well_id,
            "prefix_rows": float(len(known)),
            "total_rows": float(len(horizontal)),
            "suffix_rows": float(horizontal["TVT_input"].isna().sum()),
            "last_tvt": float(tvt[-1]),
            "last_gr": float(known_gr[-1]) if np.isfinite(known_gr[-1]) else np.nan,
            "known_tvt_mean": float(np.nanmean(tvt)),
            "known_tvt_std": float(np.nanstd(tvt)),
            "known_tvt_range": float(np.nanmax(tvt) - np.nanmin(tvt)),
            "slope_md": slope(md, tvt),
            "slope_md_recent": slope(md[-recent:], tvt[-recent:]),
            "slope_z": slope(z, tvt),
            "slope_z_recent": slope(z[-recent:], tvt[-recent:]),
            "gr_mean": float(np.nanmean(known_gr)),
            "gr_std": float(np.nanstd(known_gr)),
            "gr_residual_mean": float(np.nanmean(gr_residual)) if len(gr_residual) else np.nan,
            "gr_residual_std": float(np.nanstd(gr_residual)) if len(gr_residual) else np.nan,
            "gr_residual_last": float(gr_residual[-1]) if len(gr_residual) else np.nan,
        })
    return pd.DataFrame(rows)


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    gt = pd.read_parquet(args.train_gt, columns=["id", "last_known_TVT"])
    artifact_delta = np.load(args.artifact_predictions).reshape(-1).astype(float)
    ids = gt["id"].astype(str)
    target_frame = pd.read_csv(args.target_oof, usecols=["_oof_id", "_oof_well", "_oof_row_idx", "target_tvt"])
    if len(target_frame) != len(gt) or not target_frame["_oof_id"].astype(str).equals(ids):
        raise ValueError("target OOF IDs do not exactly match train_gt order")
    target = target_frame["target_tvt"].to_numpy(float)
    artifact = gt["last_known_TVT"].to_numpy(float) + artifact_delta
    well_codes, well_names = pd.factorize(target_frame["_oof_well"].astype(str), sort=False)
    n_wells = len(well_names)
    artifact_frame = pd.DataFrame({
        "_oof_well": target_frame["_oof_well"].astype(str),
        "row_idx": target_frame["_oof_row_idx"].to_numpy(float),
        "artifact_delta": artifact - gt["last_known_TVT"].to_numpy(float),
    })
    artifact_stats = artifact_frame.groupby("_oof_well", sort=False).agg(
        artifact_delta_mean=("artifact_delta", "mean"),
        artifact_delta_std=("artifact_delta", "std"),
        artifact_delta_first=("artifact_delta", "first"),
        artifact_delta_last=("artifact_delta", "last"),
        artifact_delta_min=("artifact_delta", "min"),
        artifact_delta_max=("artifact_delta", "max"),
    ).reset_index()
    well_frame = pd.DataFrame({"well": target_frame["_oof_well"].astype(str), "residual": target - artifact})
    labels = well_frame.groupby("well", sort=False)["residual"].mean().to_numpy(float)
    prefix = build_prefix_features(args.data_root, set(well_names))
    prefix = pd.DataFrame({"_oof_well": well_names}).merge(prefix, on="_oof_well", how="left")
    prefix = prefix.merge(artifact_stats, on="_oof_well", how="left")
    feature_cols = [c for c in prefix.columns if c != "_oof_well"]
    X = prefix[feature_cols].replace([np.inf, -np.inf], np.nan).to_numpy(float)
    predicted_bias = np.full(n_wells, np.nan, dtype=float)
    global_bias = np.full(n_wells, np.nan, dtype=float)
    selected_scale = np.full(n_wells, np.nan, dtype=float)
    scale_grid = np.asarray([float(x) for x in args.scale_grid.split(",") if x.strip()])
    row_count_by_well = np.bincount(well_codes, minlength=n_wells).astype(float)
    cv = GroupKFold(n_splits=args.folds)
    for fold, (train_idx, valid_idx) in enumerate(cv.split(X, labels, groups=np.arange(n_wells)), 1):
        scale = 0.5
        if args.nested_scale:
            inner = GroupKFold(n_splits=args.inner_folds)
            inner_scores = np.zeros(len(scale_grid), dtype=float)
            inner_count = np.zeros(len(scale_grid), dtype=float)
            for inner_train_rel, inner_valid_rel in inner.split(
                train_idx, labels[train_idx], groups=train_idx
            ):
                inner_train = train_idx[inner_train_rel]
                inner_valid = train_idx[inner_valid_rel]
                inner_model = make_pipeline(
                    SimpleImputer(strategy="median"),
                    StandardScaler(),
                    Ridge(alpha=args.ridge_alpha),
                )
                inner_model.fit(X[inner_train], labels[inner_train])
                inner_bias = inner_model.predict(X[inner_valid])
                for pos, alpha in enumerate(scale_grid):
                    inner_scores[pos] += float(np.sum(
                        row_count_by_well[inner_valid]
                        * (labels[inner_valid] - alpha * inner_bias) ** 2
                    ))
                    inner_count[pos] += float(np.sum(row_count_by_well[inner_valid]))
            scale = float(scale_grid[int(np.argmin(inner_scores / np.maximum(inner_count, 1.0)))])
        model = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            Ridge(alpha=args.ridge_alpha),
        )
        model.fit(X[train_idx], labels[train_idx])
        predicted_bias[valid_idx] = model.predict(X[valid_idx])
        global_bias[valid_idx] = float(np.mean(labels[train_idx]))
        selected_scale[valid_idx] = scale
        print(f"fold {fold}: train_wells={len(train_idx)} valid_wells={len(valid_idx)} scale={scale:.3f}", flush=True)

    row_bias = predicted_bias[well_codes]
    row_global = global_bias[well_codes]
    predictions = {
        "artifact": artifact,
        "ridge_0.25": artifact + 0.25 * row_bias,
        "ridge_0.5": artifact + 0.5 * row_bias,
        "ridge_1.0": artifact + row_bias,
        "global_0.25": artifact + 0.25 * row_global,
        "nested_scale": artifact,
    }
    predictions["nested_scale"] = artifact + selected_scale[well_codes] * row_bias
    summary = {
        "method": "prefix_only_artifact_well_bias_ridge",
        "rows": int(len(target)),
        "wells": int(n_wells),
        "feature_cols": feature_cols,
        "ridge_alpha": args.ridge_alpha,
        "nested_scale": args.nested_scale,
        "scale_grid": scale_grid.tolist(),
        "selected_scale_counts": {str(x): int(np.sum(selected_scale == x)) for x in scale_grid},
        "folds": args.folds,
        "rmse": {name: float(np.sqrt(np.mean((pred - target) ** 2))) for name, pred in predictions.items()},
        "bias_label_rmse": float(np.sqrt(np.mean(labels * labels))),
        "predicted_bias_rmse": float(np.sqrt(np.mean((predicted_bias - labels) ** 2))),
        "elapsed_sec": float(time.perf_counter() - started),
    }
    output = prefix.copy()
    output["true_well_bias_oof"] = labels
    output["predicted_well_bias_oof"] = predicted_bias
    output["global_well_bias_oof"] = global_bias
    output["selected_scale_oof"] = selected_scale
    output.to_csv(args.output, index=False)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--artifact-predictions", type=Path, required=True)
    parser.add_argument("--target-oof", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--ridge-alpha", type=float, default=100.0)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--nested-scale", action="store_true")
    parser.add_argument("--inner-folds", type=int, default=5)
    parser.add_argument("--scale-grid", default="0.1,0.25,0.5,0.75,1.0")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    run(args)


if __name__ == "__main__":
    main()
