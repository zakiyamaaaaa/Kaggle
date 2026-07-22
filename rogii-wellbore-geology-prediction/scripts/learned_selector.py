"""Fit the causal candidate selector and write a local-only test prediction.

The script trains on prefix-valid rows from the horizontal training wells,
using GroupKFold-safe candidate features from ``supervised_residual.py``. It
does not call the Kaggle API or submit anything.
"""

from __future__ import annotations

import argparse
import importlib.util
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("supervised_residual", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def train_model(data_root: Path, rows_per_well: int, max_wells: int | None):
    helper = load_module(Path(__file__).with_name("supervised_residual.py"))
    advanced = helper.load_advanced(Path(__file__).with_name("advanced_baseline.py"))
    train_dir = data_root / "train"
    metadata = advanced.build_spatial_metadata(train_dir)
    files = sorted(train_dir.glob("*__horizontal_well.csv"))
    if max_wells is not None:
        files = files[:max_wells]
    rng = np.random.default_rng(20260722)
    frames: list[pd.DataFrame] = []
    targets: list[np.ndarray] = []
    for i, path in enumerate(files, 1):
        well_id = path.name.split("__", 1)[0]
        typewell_path = train_dir / f"{well_id}__typewell.csv"
        if not typewell_path.exists():
            continue
        frame, target = helper.build_features(
            pd.read_csv(path),
            pd.read_csv(typewell_path),
            advanced,
            metadata,
            well_id,
        )
        if frame.empty or len(target) != len(frame):
            continue
        if len(frame) > rows_per_well:
            selected = np.sort(rng.choice(len(frame), rows_per_well, replace=False))
            frame = frame.iloc[selected].reset_index(drop=True)
            target = target[selected]
        frames.append(frame)
        targets.append(target)
        if i % 50 == 0:
            print(f"train features {i}/{len(files)} wells", flush=True)

    X = pd.concat(frames, ignore_index=True).astype(np.float32)
    y = np.concatenate(targets).astype(np.float32)
    candidate = X["best_blend"].to_numpy(np.float32)
    residual = y - candidate
    model = HistGradientBoostingRegressor(
        max_iter=350,
        learning_rate=0.045,
        max_leaf_nodes=63,
        l2_regularization=3.0,
        random_state=20260722,
    )
    model.fit(X, residual)
    print({"train_rows": len(X), "train_wells": len(frames)})
    return helper, advanced, metadata, model


def write_prediction(
    data_root: Path,
    output: Path,
    helper,
    advanced,
    metadata,
    model,
    clip: float | None,
) -> None:
    test_dir = data_root / "test"
    sample = pd.read_csv(data_root / "sample_submission.csv")
    values: dict[str, float] = {}
    for path in sorted(test_dir.glob("*__horizontal_well.csv")):
        well_id = path.name.split("__", 1)[0]
        typewell_path = test_dir / f"{well_id}__typewell.csv"
        if not typewell_path.exists():
            continue
        horizontal = pd.read_csv(path)
        frame, target = helper.build_features(
            horizontal,
            pd.read_csv(typewell_path),
            advanced,
            metadata,
            well_id,
        )
        unknown = horizontal[horizontal["TVT_input"].isna()]
        if frame.empty or len(frame) != len(unknown) or len(target) != 0:
            continue
        residual = model.predict(frame.astype(np.float32))
        candidate = frame["best_blend"].to_numpy(float)
        if clip is None:
            prediction = candidate + residual
        else:
            prediction = candidate + np.clip(residual, -clip, clip)
        for row_idx, value in zip(unknown.index, prediction):
            values[f"{well_id}_{row_idx}"] = float(value)

    out = sample[["id"]].copy()
    fallback = float(np.nanmedian(list(values.values()))) if values else 0.0
    out["tvt"] = out["id"].map(values).fillna(fallback)
    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False)
    print({"test_rows": len(values), "submission_rows": len(out), "output": str(output)})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="data/raw")
    parser.add_argument("--rows-per-well", type=int, default=300)
    parser.add_argument("--max-wells", type=int)
    parser.add_argument(
        "--output",
        default="outputs/submissions/learned_selector_hgb_trend100_clip10.csv",
    )
    parser.add_argument("--clip", type=float, default=10.0)
    args = parser.parse_args()
    started = time.perf_counter()
    root = Path(args.data_root)
    helper, advanced, metadata, model = train_model(
        root, args.rows_per_well, args.max_wells
    )
    write_prediction(
        root,
        Path(args.output),
        helper,
        advanced,
        metadata,
        model,
        args.clip,
    )
    print({"elapsed_sec": round(time.perf_counter() - started, 3)})


if __name__ == "__main__":
    main()
