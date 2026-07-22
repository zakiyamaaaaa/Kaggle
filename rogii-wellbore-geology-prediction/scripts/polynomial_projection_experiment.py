"""Evaluate a target-free low-frequency projection on an existing candidate.

The projection is fit in U = TVT + Z - anchor space using only the candidate
prediction and the observed test-like suffix MD/Z. It is intentionally a
standalone experiment so the baseline decoder remains unchanged.
"""

from __future__ import annotations

import argparse
import importlib.util
import time
from pathlib import Path

import numpy as np
import pandas as pd


def load_advanced(path: Path):
    spec = importlib.util.spec_from_file_location("advanced_baseline", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def robust_polyfit_predict(
    s: np.ndarray,
    values: np.ndarray,
    degree: int,
    robust_iters: int = 4,
    robust_c: float = 2.0,
) -> np.ndarray:
    mask = np.isfinite(s) & np.isfinite(values)
    if mask.sum() < degree + 2:
        return values.copy()
    degree = min(int(degree), max(1, int(mask.sum()) - 2))
    coef = np.polyfit(s[mask], values[mask], degree)
    for _ in range(int(robust_iters)):
        residual = values[mask] - np.polyval(coef, s[mask])
        scale = float(np.median(np.abs(residual)) * 1.4826 + 1e-6)
        weights = 1.0 / (1.0 + (residual / (robust_c * scale)) ** 2)
        coef = np.polyfit(s[mask], values[mask], degree, w=weights)
    predicted = np.asarray(np.polyval(coef, s), dtype=float)
    predicted[~np.isfinite(predicted)] = values[~np.isfinite(predicted)]
    return predicted


def project_suffix(
    horizontal: pd.DataFrame,
    base_prediction: np.ndarray,
    degree: int = 4,
    projection_blend_weight: float = 0.75,
) -> np.ndarray:
    known = horizontal[horizontal["TVT_input"].notna()]
    unknown = horizontal[horizontal["TVT_input"].isna()]
    if len(known) == 0 or len(unknown) == 0:
        return base_prediction
    if len(base_prediction) != len(unknown):
        return base_prediction

    last = known.iloc[-1]
    md = pd.to_numeric(unknown["MD"], errors="coerce").to_numpy(float)
    z = pd.to_numeric(unknown["Z"], errors="coerce").to_numpy(float)
    anchor = float(last["TVT_input"]) + float(last["Z"])
    start_md = float(last["MD"])
    end_md = float(pd.to_numeric(horizontal["MD"], errors="coerce").iloc[-1])
    span = max(end_md - start_md, 1e-6)
    s = (md - start_md) / span
    u = np.asarray(base_prediction, dtype=float) + z - anchor
    u_fit = robust_polyfit_predict(s, u, degree=degree)
    projected = anchor + u_fit - z
    weight = float(np.clip(projection_blend_weight, 0.0, 1.0))
    return (1.0 - weight) * np.asarray(base_prediction, dtype=float) + weight * projected


def run(
    data_root: Path,
    base_method: str,
    degree: int,
    projection_blend_weight: float,
    output: Path | None,
    max_wells: int | None,
) -> dict[str, float]:
    started = time.perf_counter()
    advanced = load_advanced(Path(__file__).with_name("advanced_baseline.py"))
    train_dir = data_root / "train"
    files = sorted(train_dir.glob("*__horizontal_well.csv"))
    if max_wells is not None:
        files = files[:max_wells]
    metadata = advanced.build_spatial_metadata(train_dir)
    total_sse_base = 0.0
    total_sse_projected = 0.0
    total_rows = 0
    base_well_rmse: list[float] = []
    projected_well_rmse: list[float] = []
    output_values: dict[str, float] = {}

    for i, path in enumerate(files, 1):
        well_id = path.name.split("__", 1)[0]
        typewell_path = train_dir / f"{well_id}__typewell.csv"
        if not typewell_path.exists():
            continue
        horizontal = pd.read_csv(path)
        if "TVT" not in horizontal.columns:
            continue
        unknown = horizontal[horizontal["TVT_input"].isna() & horizontal["TVT"].notna()]
        if len(unknown) == 0 or not horizontal["TVT_input"].notna().any():
            continue
        base = advanced.predict_well(
            horizontal,
            pd.read_csv(typewell_path),
            base_method,
            spatial_metadata=metadata,
            well_id=well_id,
        )
        projected = project_suffix(
            horizontal,
            base,
            degree=degree,
            projection_blend_weight=projection_blend_weight,
        )
        truth = unknown["TVT"].to_numpy(float)
        good = np.isfinite(base) & np.isfinite(projected) & np.isfinite(truth)
        if not good.any():
            continue
        base_error = base[good] - truth[good]
        projected_error = projected[good] - truth[good]
        total_sse_base += float(np.sum(base_error * base_error))
        total_sse_projected += float(np.sum(projected_error * projected_error))
        total_rows += int(good.sum())
        base_well_rmse.append(float(np.sqrt(np.mean(base_error * base_error))))
        projected_well_rmse.append(float(np.sqrt(np.mean(projected_error * projected_error))))
        if output is not None:
            for row_idx, value in zip(unknown.index[good], projected[good]):
                output_values[f"{well_id}_{row_idx}"] = float(value)
        if i % 50 == 0:
            print(f"evaluated {i}/{len(files)} wells", flush=True)

    result = {
        "method": f"{base_method}_robust_poly_degree{degree}_blend{projection_blend_weight:g}",
        "base_rmse": float(np.sqrt(total_sse_base / total_rows)),
        "projected_rmse": float(np.sqrt(total_sse_projected / total_rows)),
        "delta_rmse": float(
            np.sqrt(total_sse_projected / total_rows)
            - np.sqrt(total_sse_base / total_rows)
        ),
        "rows": int(total_rows),
        "wells": int(len(base_well_rmse)),
        "base_well_rmse_p50": float(np.percentile(base_well_rmse, 50)),
        "base_well_rmse_p90": float(np.percentile(base_well_rmse, 90)),
        "projected_well_rmse_p50": float(np.percentile(projected_well_rmse, 50)),
        "projected_well_rmse_p90": float(np.percentile(projected_well_rmse, 90)),
        "elapsed_sec": float(time.perf_counter() - started),
    }
    if output is not None:
        sample_path = data_root / "sample_submission.csv"
        sample = pd.read_csv(sample_path)
        submission = sample[["id"]].copy()
        submission["tvt"] = submission["id"].map(output_values)
        if submission["tvt"].isna().any():
            raise RuntimeError("Projection output has missing sample_submission IDs")
        output.parent.mkdir(parents=True, exist_ok=True)
        submission.to_csv(output, index=False)
        result["output_rows"] = int(len(submission))
        result["output_nulls"] = int(submission["tvt"].isna().sum())
        print(f"output={output.resolve()}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="data/raw")
    parser.add_argument("--base-method", default="safe_spatial_beam_ncc_agree")
    parser.add_argument("--degree", type=int, default=4)
    parser.add_argument("--projection-blend-weight", type=float, default=0.75)
    parser.add_argument("--max-wells", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(
        run(
            Path(args.data_root),
            args.base_method,
            args.degree,
            args.projection_blend_weight,
            args.output,
            args.max_wells,
        )
    )


if __name__ == "__main__":
    main()
