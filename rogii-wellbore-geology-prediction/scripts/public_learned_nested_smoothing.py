#!/usr/bin/env python3
"""Cross-fit Savgol smoothing for a learned delta OOF vector."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from artifact_nested_smoothing import metrics, smooth_by_well


def parse_grid(value: str, cast=int) -> list:
    return [cast(item.strip()) for item in value.split(",") if item.strip()]


def load_target(ids: pd.DataFrame, data_root: Path) -> np.ndarray:
    last_known: dict[str, float] = {}
    for well in pd.unique(ids["_oof_well"].astype(str)):
        horizontal = pd.read_csv(
            data_root / "train" / f"{well}__horizontal_well.csv",
            usecols=["TVT_input"],
        )
        known = pd.to_numeric(horizontal["TVT_input"], errors="coerce").dropna()
        if known.empty:
            raise RuntimeError(f"well has no TVT_input prefix: {well}")
        last_known[str(well)] = float(known.iloc[-1])
    return (
        ids["target_tvt"].to_numpy(float)
        - ids["_oof_well"].astype(str).map(last_known).to_numpy(float)
    )


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    ids = pd.read_csv(
        args.oof_ids,
        usecols=["_oof_well", "_oof_row_idx", "target_tvt"],
        dtype={"_oof_well": str},
    )
    raw = np.asarray(np.load(args.input_oof, mmap_mode="r"), dtype=np.float32)
    if len(raw) != len(ids) or not np.isfinite(raw).all():
        raise RuntimeError("input OOF does not align with ID file")
    target = load_target(ids, args.data_root).astype(np.float32)
    groups, well_names = pd.factorize(ids["_oof_well"].astype(str), sort=False)
    groups = groups.astype(np.int32)
    row_index = ids["_oof_row_idx"].to_numpy(np.int32)
    windows = parse_grid(args.window_grid, int)
    polynomials = parse_grid(args.poly_grid, int)

    candidates: dict[tuple[int, int], np.ndarray] = {(0, 0): raw.copy()}
    for window in windows:
        if window <= 0:
            continue
        for polynomial in polynomials:
            candidates[(window, polynomial)] = smooth_by_well(
                raw, groups, row_index, window, polynomial
            ).astype(np.float32)

    if args.selection_summary is not None:
        selection = json.loads(args.selection_summary.read_text(encoding="utf-8"))
        selected_folds = selection["folds"]
        if len(selected_folds) != args.folds:
            raise RuntimeError("external selection fold count mismatch")
        prediction = np.full(len(raw), np.nan, dtype=np.float32)
        fold_records = []
        splitter = GroupKFold(n_splits=args.folds)
        for selected, (train_index, valid_index) in zip(
            selected_folds,
            splitter.split(raw, target, groups=groups),
        ):
            key = (int(selected["window"]), int(selected["poly"]))
            if key not in candidates:
                raise RuntimeError(f"external selection not in candidate grid: {key}")
            prediction[valid_index] = (
                args.transfer_alpha * candidates[key][valid_index]
            )
            fold_records.append(
                {
                    "fold": int(selected["fold"]),
                    "window": key[0],
                    "poly": key[1],
                    "alpha": float(args.transfer_alpha),
                    "selection_source": str(args.selection_summary),
                    "raw_valid_rmse": float(
                        np.sqrt(np.mean((raw[valid_index] - target[valid_index]) ** 2))
                    ),
                    "candidate_valid_rmse": float(
                        np.sqrt(
                            np.mean(
                                (prediction[valid_index] - target[valid_index]) ** 2
                            )
                        )
                    ),
                }
            )
            print(json.dumps(fold_records[-1]), flush=True)
        deployment = selection["full_oof_fit_recommendation"].copy()
        deployment["alpha"] = float(args.transfer_alpha)
        result = {
            "method": "public_learned_artifact_outer_train_selected_savgol",
            "input_oof": str(args.input_oof),
            "selection_summary": str(args.selection_summary),
            "selection_target": "independent model-package artifact OOF",
            "rows": int(len(raw)),
            "wells": int(len(well_names)),
            "folds": int(args.folds),
            "raw": metrics(target, raw, groups),
            "nested_smoothing": metrics(target, prediction, groups),
            "fold_records": fold_records,
            "fit_all_recommendation": deployment,
            "transfer_alpha": float(args.transfer_alpha),
            "window_grid": windows,
            "poly_grid": polynomials,
            "elapsed_sec": float(time.perf_counter() - started),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        np.save(args.output, prediction)
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, indent=2))
        return result

    prediction = np.full(len(raw), np.nan, dtype=np.float32)
    fold_records: list[dict[str, object]] = []
    splitter = GroupKFold(n_splits=args.folds)
    for fold, (train_index, valid_index) in enumerate(
        splitter.split(raw, target, groups=groups), 1
    ):
        records = []
        for (window, polynomial), values in candidates.items():
            denominator = float(np.dot(values[train_index], values[train_index]))
            alpha = (
                float(np.dot(values[train_index], target[train_index]) / denominator)
                if denominator > 1e-12
                else 1.0
            )
            alpha = float(np.clip(alpha, args.alpha_min, args.alpha_max))
            score = float(
                np.sqrt(
                    np.mean(
                        (alpha * values[train_index] - target[train_index]) ** 2
                    )
                )
            )
            records.append(
                {
                    "window": int(window),
                    "poly": int(polynomial),
                    "alpha": alpha,
                    "train_rmse": score,
                }
            )
        selected = min(records, key=lambda record: record["train_rmse"])
        values = candidates[(selected["window"], selected["poly"])]
        prediction[valid_index] = selected["alpha"] * values[valid_index]
        selected.update(
            {
                "fold": int(fold),
                "train_wells": int(np.unique(groups[train_index]).size),
                "valid_wells": int(np.unique(groups[valid_index]).size),
                "valid_rmse": float(
                    np.sqrt(
                        np.mean(
                            (prediction[valid_index] - target[valid_index]) ** 2
                        )
                    )
                ),
            }
        )
        fold_records.append(selected)
        print(json.dumps(selected), flush=True)

    fit_all = []
    for (window, polynomial), values in candidates.items():
        denominator = float(np.dot(values, values))
        alpha = (
            float(np.dot(values, target) / denominator)
            if denominator > 1e-12
            else 1.0
        )
        alpha = float(np.clip(alpha, args.alpha_min, args.alpha_max))
        fit_all.append(
            {
                "window": int(window),
                "poly": int(polynomial),
                "alpha": alpha,
                "rmse": float(np.sqrt(np.mean((alpha * values - target) ** 2))),
            }
        )
    fit_all.sort(key=lambda record: record["rmse"])
    result = {
        "method": "public_learned_outer_train_selected_savgol",
        "input_oof": str(args.input_oof),
        "rows": int(len(raw)),
        "wells": int(len(well_names)),
        "folds": int(args.folds),
        "raw": metrics(target, raw, groups),
        "nested_smoothing": metrics(target, prediction, groups),
        "fold_records": fold_records,
        "fit_all_recommendation": fit_all[0],
        "fit_all_top10": fit_all[:10],
        "window_grid": windows,
        "poly_grid": polynomials,
        "alpha_bounds": [float(args.alpha_min), float(args.alpha_max)],
        "elapsed_sec": float(time.perf_counter() - started),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, prediction)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oof-ids", type=Path, required=True)
    parser.add_argument("--input-oof", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--window-grid", default="0,61,101,151,301,501,601,801")
    parser.add_argument("--poly-grid", default="1,2,3")
    parser.add_argument("--alpha-min", type=float, default=0.97)
    parser.add_argument("--alpha-max", type=float, default=1.03)
    parser.add_argument("--selection-summary", type=Path)
    parser.add_argument("--transfer-alpha", type=float, default=1.0)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
