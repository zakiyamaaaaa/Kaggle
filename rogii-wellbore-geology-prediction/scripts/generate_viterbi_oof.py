"""Generate row-level, target-free Viterbi predictions for train suffixes."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    data_root = args.data_root
    advanced = load_module(Path(__file__).with_name("advanced_baseline.py"), "advanced_baseline")
    viterbi = load_module(Path(__file__).with_name("calibrated_u_viterbi_experiment.py"), "calibrated_u_viterbi")
    config = viterbi.ViterbiConfig(
        state_radius=args.state_radius,
        state_step=args.state_step,
        row_stride=args.row_stride,
        max_transition_steps=args.max_transition_steps,
        transition_penalty=args.transition_penalty,
        start_penalty=args.start_penalty,
        gr_smooth_window=args.gr_smooth_window,
        calibration_rows=args.calibration_rows,
    )
    files = sorted((data_root / "train").glob("*__horizontal_well.csv"))
    if args.max_wells is not None:
        files = files[: args.max_wells]
    spatial_metadata = advanced.build_spatial_metadata(data_root / "train")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.unlink(missing_ok=True)
    header_written = False
    base_sse = 0.0
    viterbi_sse = 0.0
    rows = 0
    base_well_rmse: list[float] = []
    viterbi_well_rmse: list[float] = []
    wells = 0

    for index, path in enumerate(files, 1):
        well_id = path.name.split("__", 1)[0]
        typewell_path = data_root / "train" / f"{well_id}__typewell.csv"
        if not typewell_path.exists():
            continue
        horizontal = pd.read_csv(path)
        unknown_mask = horizontal["TVT_input"].isna().to_numpy()
        target_mask = unknown_mask & horizontal["TVT"].notna().to_numpy()
        if not target_mask.any() or not horizontal["TVT_input"].notna().any():
            continue
        typewell = pd.read_csv(typewell_path)
        base_full = advanced.predict_well(
            horizontal,
            typewell,
            "safe_spatial_beam_ncc_agree",
            spatial_metadata=spatial_metadata,
            well_id=well_id,
        )
        viterbi_full, diagnostic = viterbi.predict_suffix(
            horizontal,
            typewell,
            config,
            center_prediction=base_full,
        )
        unknown_idx = np.flatnonzero(unknown_mask)
        target_idx = np.flatnonzero(target_mask)
        local_idx = np.searchsorted(unknown_idx, target_idx)
        base = np.asarray(base_full, dtype=float)[local_idx]
        candidate = np.asarray(viterbi_full, dtype=float)[local_idx]
        truth = horizontal.loc[target_idx, "TVT"].to_numpy(float)
        good = np.isfinite(base) & np.isfinite(candidate) & np.isfinite(truth)
        if not good.any():
            continue
        target_idx = target_idx[good]
        base = base[good]
        candidate = candidate[good]
        truth = truth[good]
        base_error = base - truth
        candidate_error = candidate - truth
        base_sse += float(np.sum(base_error * base_error))
        viterbi_sse += float(np.sum(candidate_error * candidate_error))
        rows += int(good.sum())
        base_well_rmse.append(float(np.sqrt(np.mean(base_error * base_error))))
        viterbi_well_rmse.append(float(np.sqrt(np.mean(candidate_error * candidate_error))))
        wells += 1
        diag = {key: float(value) for key, value in diagnostic.items() if key != "status"}
        output = pd.DataFrame(
            {
                "_oof_id": [f"{well_id}_{int(row)}" for row in target_idx],
                "_oof_well": well_id,
                "_oof_row_idx": target_idx,
                "target_tvt": truth,
                "base_tvt": base,
                "viterbi_tvt": candidate,
                "viterbi_offset": candidate - base,
                "calibration_alpha": diag.get("alpha", np.nan),
                "calibration_beta": diag.get("beta", np.nan),
                "calibration_sigma": diag.get("sigma", np.nan),
                "offset_std": diag.get("offset_std", np.nan),
                "offset_min": diag.get("offset_min", np.nan),
                "offset_max": diag.get("offset_max", np.nan),
            }
        )
        output.to_csv(args.output, mode="a", header=not header_written, index=False)
        header_written = True
        if index % 25 == 0:
            print(f"evaluated {index}/{len(files)} wells", flush=True)

    summary = {
        "method": "target_free_calibrated_u_viterbi_oof",
        "rows": rows,
        "wells": wells,
        "base_rmse": float(np.sqrt(base_sse / rows)),
        "viterbi_rmse": float(np.sqrt(viterbi_sse / rows)),
        "base_well_rmse_p50": float(np.percentile(base_well_rmse, 50)),
        "base_well_rmse_p90": float(np.percentile(base_well_rmse, 90)),
        "viterbi_well_rmse_p50": float(np.percentile(viterbi_well_rmse, 50)),
        "viterbi_well_rmse_p90": float(np.percentile(viterbi_well_rmse, 90)),
        "config": vars(args),
        "elapsed_sec": float(time.perf_counter() - started),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--max-wells", type=int)
    parser.add_argument("--state-radius", type=float, default=60.0)
    parser.add_argument("--state-step", type=float, default=0.5)
    parser.add_argument("--row-stride", type=int, default=8)
    parser.add_argument("--max-transition-steps", type=int, default=4)
    parser.add_argument("--transition-penalty", type=float, default=0.08)
    parser.add_argument("--start-penalty", type=float, default=0.02)
    parser.add_argument("--gr-smooth-window", type=int, default=7)
    parser.add_argument("--calibration-rows", type=int, default=800)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
