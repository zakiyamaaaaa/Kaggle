"""Apply the OOF-trained well-bias corrector to an artifact test submission."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from artifact_well_bias_correction import build_prefix_features


def artifact_stats(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.groupby("_oof_well", sort=False).agg(
        artifact_delta_mean=("artifact_delta", "mean"),
        artifact_delta_std=("artifact_delta", "std"),
        artifact_delta_first=("artifact_delta", "first"),
        artifact_delta_last=("artifact_delta", "last"),
        artifact_delta_min=("artifact_delta", "min"),
        artifact_delta_max=("artifact_delta", "max"),
    ).reset_index()


def build_test_artifact_frame(data_root: Path, base_submission: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []
    test_dir = data_root / "test"
    base_map = base_submission.set_index("id")["tvt"]
    for path in sorted(test_dir.glob("*__horizontal_well.csv")):
        well_id = path.name.split("__", 1)[0]
        horizontal = pd.read_csv(path)
        known = horizontal.loc[horizontal["TVT_input"].notna(), "TVT_input"].dropna()
        if len(known) == 0:
            continue
        last_tvt = float(known.iloc[-1])
        suffix_idx = horizontal.index[horizontal["TVT_input"].isna()].to_numpy(int)
        for row_idx in suffix_idx:
            row_id = f"{well_id}_{int(row_idx)}"
            if row_id not in base_map.index:
                continue
            absolute = float(base_map.loc[row_id])
            rows.append({
                "_oof_id": row_id,
                "_oof_well": well_id,
                "_oof_row_idx": int(row_idx),
                "last_tvt": last_tvt,
                "artifact_delta": absolute - last_tvt,
                "artifact_tvt": absolute,
            })
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("No test artifact rows matched sample submission IDs")
    return frame


def smooth_test_artifact(frame: pd.DataFrame, window: int, poly: int, alpha: float) -> pd.DataFrame:
    if window <= 0:
        return frame
    output = frame.copy()
    for _, part in frame.groupby("_oof_well", sort=False):
        positions = part.sort_values("_oof_row_idx").index.to_numpy()
        local_window = min(int(window), len(positions))
        if local_window % 2 == 0:
            local_window -= 1
        if local_window < int(poly) + 2:
            continue
        delta = frame.loc[positions, "artifact_delta"].to_numpy(float)
        output.loc[positions, "artifact_delta"] = float(alpha) * savgol_filter(
            delta, window_length=local_window, polyorder=min(int(poly), local_window - 1), mode="interp"
        )
        output.loc[positions, "artifact_tvt"] = output.loc[positions, "last_tvt"] + output.loc[positions, "artifact_delta"]
    return output


def run(args: argparse.Namespace) -> dict[str, object]:
    train_gt = pd.read_parquet(args.train_gt, columns=["id", "last_known_TVT"])
    artifact_delta = np.load(args.artifact_predictions).reshape(-1).astype(float)
    target_oof = pd.read_csv(args.target_oof, usecols=["_oof_id", "_oof_well", "target_tvt"])
    if len(target_oof) != len(train_gt) or not target_oof["_oof_id"].astype(str).equals(train_gt["id"].astype(str)):
        raise ValueError("training OOF IDs do not match train_gt order")
    train_artifact = train_gt["last_known_TVT"].to_numpy(float) + artifact_delta
    train_rows = pd.DataFrame({
        "_oof_well": target_oof["_oof_well"].astype(str),
        "artifact_delta": train_artifact - train_gt["last_known_TVT"].to_numpy(float),
    })
    train_stats = artifact_stats(train_rows)
    train_bias = pd.DataFrame({
        "_oof_well": target_oof["_oof_well"].astype(str),
        "residual": target_oof["target_tvt"].to_numpy(float) - train_artifact,
    }).groupby("_oof_well", sort=False)["residual"].mean().rename("bias").reset_index()
    train_wells = train_bias["_oof_well"].astype(str).to_numpy()
    train_prefix = build_prefix_features(args.data_root, set(train_wells), split="train")
    train_features = pd.DataFrame({"_oof_well": train_wells}).merge(train_prefix, on="_oof_well", how="left").merge(train_stats, on="_oof_well", how="left")

    base_submission = pd.read_csv(args.base_submission)[["id", "tvt"]]
    test_frame = build_test_artifact_frame(args.data_root, base_submission)
    test_frame = smooth_test_artifact(test_frame, args.savgol_window, args.savgol_poly, args.savgol_alpha)
    test_wells = test_frame["_oof_well"].astype(str).drop_duplicates().to_numpy()
    test_prefix = build_prefix_features(args.data_root, set(test_wells), split="test")
    test_features = pd.DataFrame({"_oof_well": test_wells}).merge(test_prefix, on="_oof_well", how="left").merge(
        artifact_stats(test_frame[["_oof_well", "artifact_delta"]]), on="_oof_well", how="left"
    )
    feature_cols = [c for c in train_features.columns if c != "_oof_well"]
    X_train = train_features[feature_cols].replace([np.inf, -np.inf], np.nan).to_numpy(float)
    X_test = test_features[feature_cols].replace([np.inf, -np.inf], np.nan).to_numpy(float)
    model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=args.ridge_alpha))
    model.fit(X_train, train_bias["bias"].to_numpy(float))
    predicted_bias = model.predict(X_test)
    bias_map = dict(zip(test_wells, predicted_bias))
    test_frame["predicted_bias"] = test_frame["_oof_well"].map(bias_map).astype(float)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for scale in args.scales:
        corrected = base_submission.copy()
        move = test_frame["_oof_well"].map(bias_map).to_numpy(float) * float(scale)
        correction_map = dict(zip(test_frame["_oof_id"], test_frame["artifact_tvt"].to_numpy(float) + move))
        corrected["tvt"] = corrected["id"].map(correction_map).fillna(corrected["tvt"])
        path = args.output_dir / f"artifact_well_bias_scale_{scale:.3f}.csv"
        corrected.to_csv(path, index=False)
        outputs[str(scale)] = str(path)
    summary = {
        "method": "apply_prefix_only_artifact_well_bias_ridge",
        "train_wells": int(len(train_wells)),
        "test_wells": int(len(test_wells)),
        "test_rows": int(len(test_frame)),
        "ridge_alpha": args.ridge_alpha,
        "scales": args.scales,
        "savgol_window": args.savgol_window,
        "savgol_poly": args.savgol_poly,
        "savgol_alpha": args.savgol_alpha,
        "predicted_bias_summary": {
            "mean": float(np.mean(predicted_bias)),
            "std": float(np.std(predicted_bias)),
            "min": float(np.min(predicted_bias)),
            "max": float(np.max(predicted_bias)),
        },
        "outputs": outputs,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--artifact-predictions", type=Path, required=True)
    parser.add_argument("--target-oof", type=Path, required=True)
    parser.add_argument("--base-submission", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--ridge-alpha", type=float, default=100.0)
    parser.add_argument("--scales", type=float, nargs="+", default=[0.1, 0.25, 0.5])
    parser.add_argument("--savgol-window", type=int, default=0)
    parser.add_argument("--savgol-poly", type=int, default=2)
    parser.add_argument("--savgol-alpha", type=float, default=1.0)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
