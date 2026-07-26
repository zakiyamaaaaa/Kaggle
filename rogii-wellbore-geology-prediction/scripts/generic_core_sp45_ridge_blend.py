"""Evaluate the public SP45 Ridge 30% + selector 70% branch locally.

Predictions use only prefix-visible well data, the public group-OOF Ridge
prediction, horizontal inference columns, and the paired typewell.  Suffix TVT
is read only after all candidates have been produced.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit
from scipy.signal import savgol_filter

from generic_core_sp45_local import project_sp45


PF_ASSIGNMENTS = {
    "PF_GR_SIG_MIN",
    "PF_GR_SIG_MAX",
    "PF_GR_SIG_DEF",
    "ANCC_N",
    "ANCC_ALPHA",
    "ANCC_RN",
    "ANCC_PN",
    "ANCC_IR",
    "ANCC_IS",
    "ANCC_RP",
    "ANCC_RR",
    "PF_RESAMP",
}
PF_FUNCTIONS = {
    "_interp1",
    "_resamp",
    "_pf_ancc",
    "_grid",
    "_gr_sig",
    "run_pf_ancc",
}


def source_text(cell: dict) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def load_public_pf(notebook: Path, cell_index: int) -> dict[str, object]:
    """Compile only the public PF-ANCC constants and functions from one cell."""

    payload = json.loads(notebook.read_text(encoding="utf-8"))
    source = source_text(payload["cells"][cell_index])
    tree = ast.parse(source)
    selected: list[ast.stmt] = []
    found_assignments: set[str] = set()
    found_functions: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {
                target.id
                for target in targets
                if isinstance(target, ast.Name)
            }
            if names & PF_ASSIGNMENTS:
                selected.append(node)
                found_assignments.update(names & PF_ASSIGNMENTS)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in PF_FUNCTIONS:
                selected.append(node)
                found_functions.add(node.name)
    missing = (PF_ASSIGNMENTS - found_assignments) | (PF_FUNCTIONS - found_functions)
    if missing:
        raise RuntimeError(f"public PF cell is missing definitions: {sorted(missing)}")
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, object] = {
        "__builtins__": __builtins__,
        "np": np,
        "pd": pd,
        "njit": njit,
    }
    exec(compile(module, str(notebook), "exec"), namespace)

    @njit
    def seed_numba(value: int) -> None:
        np.random.seed(value)

    namespace["seed_numba"] = seed_numba
    return namespace


def stable_seed(well: str, base_seed: int) -> int:
    digest = hashlib.sha256(f"{base_seed}:{well}".encode()).digest()
    return int.from_bytes(digest[:4], "little") & 0x7FFFFFFF


def metrics(
    target: np.ndarray,
    prediction: np.ndarray,
    wells: np.ndarray,
) -> dict[str, float]:
    error = prediction - target
    by_well = pd.DataFrame(
        {"well": wells, "square_error": error * error}
    ).groupby("well", sort=False)["square_error"].mean()
    well_rmse = np.sqrt(by_well.to_numpy(float))
    return {
        "rmse": float(np.sqrt(np.mean(error * error))),
        "well_rmse_p50": float(np.quantile(well_rmse, 0.50)),
        "well_rmse_p90": float(np.quantile(well_rmse, 0.90)),
    }


def parse_float_grid(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def smooth_by_well(
    values: np.ndarray,
    wells: np.ndarray,
    window: int = 17,
    polynomial: int = 3,
) -> np.ndarray:
    output = values.copy()
    work = pd.DataFrame({"well": wells, "position": np.arange(len(values))})
    for _, part in work.groupby("well", sort=False):
        positions = part["position"].to_numpy(int)
        length = len(positions)
        local_window = min(window, length)
        if local_window % 2 == 0:
            local_window -= 1
        if local_window >= polynomial + 2:
            output[positions] = savgol_filter(
                values[positions], local_window, polynomial
            )
    return output


def load_partial_pf(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame(columns=["id", "pf_ancc", "md_since"])
    frame = pd.read_csv(
        path,
        usecols=["id", "pf_ancc", "md_since"],
        on_bad_lines="skip",
        dtype={"id": str},
    )
    frame["pf_ancc"] = pd.to_numeric(frame["pf_ancc"], errors="coerce")
    frame["md_since"] = pd.to_numeric(frame["md_since"], errors="coerce")
    return frame.dropna().drop_duplicates("id", keep="first")


def build_public_pf_for_wells(
    frame: pd.DataFrame,
    data_root: Path,
    pf_namespace: dict[str, object],
    cache_dir: Path,
    seed: int,
    overwrite: bool,
) -> tuple[np.ndarray, np.ndarray]:
    run_pf_ancc = pf_namespace["run_pf_ancc"]
    seed_numba = pf_namespace["seed_numba"]
    cache_dir.mkdir(parents=True, exist_ok=True)
    pf_values = np.full(len(frame), np.nan, dtype=float)
    md_since = np.full(len(frame), np.nan, dtype=float)
    for position, (well, part) in enumerate(frame.groupby("well", sort=False), 1):
        cache_path = cache_dir / f"{well}.csv"
        if cache_path.exists() and not overwrite:
            cached = pd.read_csv(cache_path)
        else:
            horizontal = pd.read_csv(
                data_root / "train" / f"{well}__horizontal_well.csv"
            )
            typewell = pd.read_csv(
                data_root / "train" / f"{well}__typewell.csv"
            ).sort_values("TVT")
            row_indices = part["row_idx"].to_numpy(int)
            expected = np.flatnonzero(horizontal["TVT_input"].isna().to_numpy())
            if not np.array_equal(row_indices, expected):
                raise RuntimeError(f"suffix row mismatch for {well}")
            seed_numba(stable_seed(str(well), seed))
            prediction, _ = run_pf_ancc(
                horizontal,
                typewell["TVT"].to_numpy(np.float32),
                typewell["GR"].to_numpy(np.float32),
            )
            known = horizontal.loc[horizontal["TVT_input"].notna()]
            if len(prediction) != len(row_indices) or len(known) == 0:
                raise RuntimeError(f"invalid public PF output for {well}")
            last_md = float(known.iloc[-1]["MD"])
            local_md_since = (
                horizontal["MD"].to_numpy(float)[row_indices] - last_md
            )
            cached = pd.DataFrame(
                {
                    "id": part["id"].astype(str).to_numpy(),
                    "pf_ancc": np.asarray(prediction, dtype=float),
                    "md_since": local_md_since,
                }
            )
            cached.to_csv(cache_path, index=False)
        aligned = part[["id"]].merge(
            cached[["id", "pf_ancc", "md_since"]],
            on="id",
            how="left",
            validate="one_to_one",
        )
        positions = part.index.to_numpy(int)
        pf_values[positions] = aligned["pf_ancc"].to_numpy(float)
        md_since[positions] = aligned["md_since"].to_numpy(float)
        print(f"PF {position}/{frame['well'].nunique()} {well}", flush=True)
    if not np.isfinite(pf_values).all() or not np.isfinite(md_since).all():
        raise RuntimeError("public PF cache is incomplete")
    return pf_values, md_since


def project_candidate(
    frame: pd.DataFrame,
    prediction: np.ndarray,
    data_root: Path,
    degree: int,
    blend: float,
) -> np.ndarray:
    output = np.full(len(frame), np.nan, dtype=float)
    for well, part in frame.groupby("well", sort=False):
        horizontal = pd.read_csv(
            data_root / "train" / f"{well}__horizontal_well.csv"
        )
        positions = part.index.to_numpy(int)
        output[positions] = project_sp45(
            horizontal,
            part["row_idx"].to_numpy(int),
            prediction[positions],
            degree,
            blend,
        )
    if not np.isfinite(output).all():
        raise RuntimeError("projection produced non-finite values")
    return output


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    frames = []
    for label, path in (("discovery", args.discovery), ("holdout", args.holdout)):
        part = pd.read_csv(path)
        part["split"] = label
        frames.append(part)
    frame = pd.concat(frames, ignore_index=True)
    frame["well"] = frame["well"].astype(str)
    required = {"id", "well", "row_idx", "target_tvt", "selector_tvt", "split"}
    if not required.issubset(frame.columns):
        raise ValueError(f"selector cache missing: {sorted(required - set(frame.columns))}")
    if frame["id"].duplicated().any():
        raise RuntimeError("selector caches contain duplicate IDs")

    train_gt = pd.read_parquet(
        args.train_gt,
        columns=["id", "last_known_TVT"],
    )
    ridge_oof = np.load(args.ridge_oof, mmap_mode="r")
    if len(train_gt) != len(ridge_oof):
        raise RuntimeError("Ridge OOF and train_gt lengths differ")
    ridge_frame = pd.DataFrame(
        {
            "id": train_gt["id"].astype(str),
            "last_known_tvt": train_gt["last_known_TVT"].to_numpy(float),
            "ridge_delta": np.asarray(ridge_oof, dtype=float),
        }
    )
    frame = frame.merge(ridge_frame, on="id", how="left", validate="one_to_one")
    if frame[["last_known_tvt", "ridge_delta"]].isna().any().any():
        raise RuntimeError("Ridge OOF ID alignment failed")

    pf_namespace = load_public_pf(args.notebook, args.pf_cell)
    pf_values, md_since = build_public_pf_for_wells(
        frame,
        args.data_root,
        pf_namespace,
        args.pf_cache_dir,
        args.pf_seed,
        args.overwrite_pf,
    )
    base = frame["last_known_tvt"].to_numpy(float)
    warmup = 1.0 - np.exp(-np.maximum(md_since, 0.0) / 85.0)
    ridge_delta = frame["ridge_delta"].to_numpy(float)
    ridge_pp = base + warmup * (
        0.91 * ridge_delta + 0.09 * (pf_values - base)
    )
    ridge_pp_smoothed = smooth_by_well(
        ridge_pp,
        frame["well"].to_numpy(),
        window=17,
        polynomial=3,
    )
    selector = frame["selector_tvt"].to_numpy(float)
    sp45_raw = 0.30 * ridge_pp + 0.70 * selector
    sp45_smoothed_ridge_raw = 0.30 * ridge_pp_smoothed + 0.70 * selector

    predictions = {
        "selector_raw": selector,
        "ridge_pp": ridge_pp,
        "ridge_pp_savgol17": ridge_pp_smoothed,
        "sp45_raw": sp45_raw,
        "sp45_d3_b075": project_candidate(
            frame, sp45_raw, args.data_root, 3, 0.75
        ),
        "sp45_d2_b050": project_candidate(
            frame, sp45_raw, args.data_root, 2, 0.50
        ),
        "sp45_sgridge_raw": sp45_smoothed_ridge_raw,
        "sp45_sgridge_d3_b075": project_candidate(
            frame, sp45_smoothed_ridge_raw, args.data_root, 3, 0.75
        ),
        "sp45_sgridge_d2_b050": project_candidate(
            frame, sp45_smoothed_ridge_raw, args.data_root, 2, 0.50
        ),
    }
    target = frame["target_tvt"].to_numpy(float)
    wells = frame["well"].to_numpy()
    weight_grid_predictions: dict[float, np.ndarray] = {}
    for weight in parse_float_grid(args.ridge_weight_grid):
        raw = weight * ridge_pp_smoothed + (1.0 - weight) * selector
        weight_grid_predictions[weight] = project_candidate(
            frame, raw, args.data_root, 2, 0.50
        )
    partial = load_partial_pf(args.artifact_partial)
    comparison = frame[["id"]].copy()
    comparison["recomputed_pf"] = pf_values
    comparison = comparison.merge(partial, on="id", how="inner")
    pf_validation = {
        "rows": int(len(comparison)),
        "wells": int(comparison["id"].str.rsplit("_", n=1).str[0].nunique())
        if len(comparison)
        else 0,
    }
    if len(comparison):
        difference = comparison["recomputed_pf"] - comparison["pf_ancc"]
        pf_validation.update(
            {
                "rmse": float(np.sqrt(np.mean(difference**2))),
                "mean_difference": float(difference.mean()),
                "p90_abs_difference": float(np.quantile(np.abs(difference), 0.90)),
            }
        )

    split_results: dict[str, object] = {}
    for split in ["discovery", "holdout", "combined"]:
        mask = (
            np.ones(len(frame), dtype=bool)
            if split == "combined"
            else frame["split"].eq(split).to_numpy()
        )
        split_results[split] = {
            "rows": int(mask.sum()),
            "wells": int(np.unique(wells[mask]).size),
            "metrics": {
                name: metrics(target[mask], values[mask], wells[mask])
                for name, values in predictions.items()
            },
        }
    discovery_mask = frame["split"].eq("discovery").to_numpy()
    holdout_mask = frame["split"].eq("holdout").to_numpy()
    weight_grid_records = []
    for weight, values in weight_grid_predictions.items():
        weight_grid_records.append(
            {
                "ridge_weight": weight,
                "discovery_rmse": metrics(
                    target[discovery_mask],
                    values[discovery_mask],
                    wells[discovery_mask],
                )["rmse"],
                "holdout_rmse": metrics(
                    target[holdout_mask],
                    values[holdout_mask],
                    wells[holdout_mask],
                )["rmse"],
                "combined_rmse": metrics(target, values, wells)["rmse"],
            }
        )
    discovery_selected = min(
        weight_grid_records, key=lambda record: record["discovery_rmse"]
    )

    output = frame[
        [
            "id",
            "well",
            "row_idx",
            "split",
            "target_tvt",
            "selector_tvt",
            "last_known_tvt",
            "ridge_delta",
        ]
    ].copy()
    output["pf_ancc_recomputed"] = pf_values
    output["md_since"] = md_since
    for name, values in predictions.items():
        output[name] = values
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_parquet(args.output, index=False)

    summary = {
        "method": "public_new_strategy_sp45_ridge30_selector70_local",
        "notebook": str(args.notebook),
        "notebook_sha256": hashlib.sha256(args.notebook.read_bytes()).hexdigest(),
        "ridge_weight": 0.30,
        "selector_weight": 0.70,
        "postprocess": {"tau": 85.0, "ridge_weight": 0.91, "pf_weight": 0.09},
        "pf": {
            "method": "public run_pf_ancc AST-extracted from notebook",
            "particles": 600,
            "deterministic_seed_base": args.pf_seed,
            "artifact_partial_validation": pf_validation,
        },
        "ridge_weight_grid": {
            "projection": {"degree": 2, "blend": 0.50},
            "ridge_savgol": {"window": 17, "polynomial": 3},
            "selection_source": "discovery split only",
            "records": weight_grid_records,
            "discovery_selected": discovery_selected,
            "interpretation": (
                "The public 0.30 weight remains the prespecified candidate. "
                "A discovery-selected weight is accepted only if it also transfers "
                "to the untouched holdout."
            ),
        },
        "split_results": split_results,
        "prediction_output": str(args.output),
        "elapsed_sec": float(time.perf_counter() - started),
        "leakage_controls": {
            "suffix_tvt_used_for_prediction": False,
            "same_well_contact_used": False,
            "visible_prefix_overlay_used": False,
            "learned_branch_used": False,
        },
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--ridge-oof", type=Path, required=True)
    parser.add_argument("--notebook", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--pf-cell", type=int, default=14)
    parser.add_argument("--pf-seed", type=int, default=42)
    parser.add_argument(
        "--ridge-weight-grid",
        default="0,0.1,0.2,0.3,0.4,0.5,0.6",
    )
    parser.add_argument("--pf-cache-dir", type=Path, required=True)
    parser.add_argument("--artifact-partial", type=Path)
    parser.add_argument("--overwrite-pf", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
