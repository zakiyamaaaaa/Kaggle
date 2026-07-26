"""Nested well-grouped selection of generic-core U-projection parameters."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from generic_core_sp45_local import project_sp45


def parse_grid(value: str, cast=float) -> list:
    return [cast(item.strip()) for item in value.split(",") if item.strip()]


def metrics(
    target: np.ndarray,
    prediction: np.ndarray,
    groups: np.ndarray,
) -> dict[str, float]:
    error = prediction - target
    by_well = pd.DataFrame(
        {"group": groups, "square_error": error * error}
    ).groupby("group", sort=False)["square_error"].mean()
    by_well_rmse = np.sqrt(by_well.to_numpy(float))
    return {
        "rmse": float(np.sqrt(np.mean(error * error))),
        "well_rmse_p50": float(np.quantile(by_well_rmse, 0.50)),
        "well_rmse_p90": float(np.quantile(by_well_rmse, 0.90)),
    }


def build_candidates(
    frame: pd.DataFrame,
    data_root: Path,
    degrees: list[int],
    blend_grid: list[float],
) -> dict[tuple[int, float], np.ndarray]:
    candidates = {
        (degree, blend): np.full(len(frame), np.nan, dtype=float)
        for degree in degrees
        for blend in blend_grid
    }
    for well, part in frame.groupby("well", sort=False):
        horizontal = pd.read_csv(
            data_root / "train" / f"{well}__horizontal_well.csv"
        )
        positions = part.index.to_numpy(int)
        row_indices = part["row_idx"].to_numpy(int)
        selector = part["selector_tvt"].to_numpy(float)
        for degree in degrees:
            for blend in blend_grid:
                candidates[(degree, blend)][positions] = project_sp45(
                    horizontal,
                    row_indices,
                    selector,
                    degree,
                    blend,
                )
    for key, values in candidates.items():
        if not np.isfinite(values).all():
            raise RuntimeError(f"non-finite projection candidate {key}")
    return candidates


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    frame = pd.read_csv(args.input).reset_index(drop=True)
    required = {"id", "well", "row_idx", "target_tvt", "selector_tvt"}
    if not required.issubset(frame.columns):
        raise ValueError(f"input missing columns: {sorted(required - set(frame.columns))}")
    degrees = parse_grid(args.degree_grid, int)
    blend_grid = parse_grid(args.blend_grid, float)
    candidates = build_candidates(frame, args.data_root, degrees, blend_grid)
    target = frame["target_tvt"].to_numpy(float)
    selector = frame["selector_tvt"].to_numpy(float)
    well_codes, well_names = pd.factorize(frame["well"].astype(str), sort=False)
    well_codes = well_codes.astype(int)

    nested_prediction = np.full(len(frame), np.nan, dtype=float)
    fold_records: list[dict[str, object]] = []
    well_indices = np.arange(len(well_names))
    outer = GroupKFold(n_splits=args.folds)
    for fold, (train_wells, valid_wells) in enumerate(
        outer.split(well_indices, groups=well_indices), 1
    ):
        train_rows = np.flatnonzero(np.isin(well_codes, train_wells))
        valid_rows = np.flatnonzero(np.isin(well_codes, valid_wells))
        scores = {
            key: float(
                np.sqrt(np.mean((values[train_rows] - target[train_rows]) ** 2))
            )
            for key, values in candidates.items()
        }
        selected = min(scores, key=scores.get)
        nested_prediction[valid_rows] = candidates[selected][valid_rows]
        fold_records.append(
            {
                "fold": fold,
                "train_wells": int(len(train_wells)),
                "valid_wells": int(len(valid_wells)),
                "degree": int(selected[0]),
                "blend": float(selected[1]),
                "train_rmse": scores[selected],
                "valid_rmse": float(
                    np.sqrt(
                        np.mean(
                            (
                                nested_prediction[valid_rows]
                                - target[valid_rows]
                            )
                            ** 2
                        )
                    )
                ),
            }
        )
        print(json.dumps(fold_records[-1]), flush=True)

    fit_all_scores = {
        key: float(np.sqrt(np.mean((values - target) ** 2)))
        for key, values in candidates.items()
    }
    fit_all = min(fit_all_scores, key=fit_all_scores.get)
    current_key = (args.current_degree, args.current_blend)
    if current_key not in candidates:
        raise ValueError(f"current projection {current_key} is not in candidate grid")
    challenger_key = (args.challenger_degree, args.challenger_blend)
    if challenger_key not in candidates:
        raise ValueError(f"challenger projection {challenger_key} is not in candidate grid")
    summary = {
        "method": "generic_core_selector_nested_u_projection",
        "rows": int(len(frame)),
        "wells": int(len(well_names)),
        "folds": args.folds,
        "degree_grid": degrees,
        "blend_grid": blend_grid,
        "selector": metrics(target, selector, well_codes),
        "current_projection": {
            "degree": args.current_degree,
            "blend": args.current_blend,
            **metrics(target, candidates[current_key], well_codes),
        },
        "fixed_challenger": {
            "degree": args.challenger_degree,
            "blend": args.challenger_blend,
            **metrics(target, candidates[challenger_key], well_codes),
        },
        "nested_projection": metrics(target, nested_prediction, well_codes),
        "fold_records": fold_records,
        "fit_all_recommendation": {
            "degree": int(fit_all[0]),
            "blend": float(fit_all[1]),
            "rmse": fit_all_scores[fit_all],
        },
        "elapsed_sec": float(time.perf_counter() - started),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, nested_prediction)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--degree-grid", default="1,2,3,4,5")
    parser.add_argument("--blend-grid", default="0,0.25,0.5,0.75,1.0")
    parser.add_argument("--current-degree", type=int, default=3)
    parser.add_argument("--current-blend", type=float, default=0.75)
    parser.add_argument("--challenger-degree", type=int, default=2)
    parser.add_argument("--challenger-blend", type=float, default=0.5)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
