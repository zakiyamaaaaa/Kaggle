"""Run the public generic-core SP45 selector branch locally on train wells.

This executes only the public notebook's control and selector function cells.
It does not use same-well contact lookup, visible-prefix overlays, model-package
correction, or suffix TVT while generating predictions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter


CONTROL_CELL_INDEX = 6
SELECTOR_CELL_INDEX = 11


def source_text(cell: dict) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def notebook_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_selector_namespace(
    notebook_path: Path,
    data_root: Path,
    particles: int,
    seeds: int,
) -> dict[str, object]:
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    namespace: dict[str, object] = {
        "__builtins__": __builtins__,
        "np": np,
        "pd": pd,
        "Path": Path,
        "savgol_filter": savgol_filter,
    }
    exec(compile(source_text(notebook["cells"][CONTROL_CELL_INDEX]), "control-cell", "exec"), namespace)

    class LocalCFG:
        dataset_path = data_root

    namespace.update(
        {
            "CFG": LocalCFG,
            "COMPETITION_DATA_ROOT": str(data_root),
            "SP45_SELECTOR_N_PARTICLES": int(particles),
            "SP45_SELECTOR_N_SEEDS": int(seeds),
            "SELECTOR_PF_SEEDS": int(seeds),
            "CV_SELECTOR_PF_SEEDS": int(seeds),
            "SELECTOR_PF_RETURN_STD": False,
            "RUN_BIMODAL_DETECTOR": False,
            "RUN_BIMODAL_SELECTOR_HEDGE": False,
            "RUN_PREFIX_TRUST_GATE": False,
            "RUN_HEEL_CALIBRATION": True,
        }
    )
    exec(
        compile(source_text(notebook["cells"][SELECTOR_CELL_INDEX]), "selector-cell", "exec"),
        namespace,
    )
    required = {
        "selector_well_code",
        "run_pf_lik_ensemble_scales",
        "run_beam_ensemble",
        "apply_selector_variant",
    }
    missing = required - namespace.keys()
    if missing:
        raise RuntimeError(f"public selector cell missing functions: {sorted(missing)}")
    return namespace


def robust_fit(s: np.ndarray, y: np.ndarray, degree: int) -> np.ndarray:
    if len(s) < degree + 2:
        return y.copy()
    coefficients = np.polyfit(s, y, degree)
    for _ in range(4):
        residual = y - np.polyval(coefficients, s)
        scale = np.median(np.abs(residual)) * 1.4826 + 1e-6
        weights = 1.0 / (1.0 + (residual / (2.0 * scale)) ** 2)
        coefficients = np.polyfit(s, y, degree, w=weights)
    return np.polyval(coefficients, s)


def project_sp45(
    horizontal: pd.DataFrame,
    row_indices: np.ndarray,
    prediction: np.ndarray,
    degree: int,
    blend_weight: float,
) -> np.ndarray:
    known = horizontal.loc[horizontal["TVT_input"].notna()]
    if len(known) < 5 or len(row_indices) < 5:
        return prediction.copy()
    last = known.iloc[-1]
    anchor = float(last["TVT_input"]) + float(last["Z"])
    start_md = float(last["MD"])
    end_md = float(horizontal["MD"].iloc[-1])
    z = horizontal["Z"].to_numpy(float)[row_indices]
    md = horizontal["MD"].to_numpy(float)[row_indices]
    position = (md - start_md) / max(end_md - start_md, 1e-6)
    fitted_u_delta = robust_fit(position, prediction + z - anchor, degree)
    projected = anchor + fitted_u_delta - z
    output = (1.0 - blend_weight) * prediction + blend_weight * projected
    return output if np.isfinite(output).all() else prediction.copy()


def select_wells(
    data_root: Path,
    n_wells: int,
    seed: int,
    excluded_wells: set[str] | None = None,
) -> list[str]:
    excluded_wells = excluded_wells or set()
    wells = sorted(
        path.name.replace("__horizontal_well.csv", "")
        for path in (data_root / "train").glob("*__horizontal_well.csv")
        if path.name.replace("__horizontal_well.csv", "") not in excluded_wells
    )
    if n_wells <= 0 or n_wells >= len(wells):
        return wells
    rng = np.random.default_rng(seed)
    return sorted(rng.choice(wells, size=n_wells, replace=False).tolist())


def well_metrics(frame: pd.DataFrame) -> dict[str, float | int]:
    by_well = frame.groupby("well", sort=True).agg(
        rows=("id", "size"),
        last_value_mse=("last_value_square_error", "mean"),
        selector_mse=("selector_square_error", "mean"),
        projected_mse=("projected_square_error", "mean"),
    )
    for column in ["last_value", "selector", "projected"]:
        by_well[f"{column}_rmse"] = np.sqrt(by_well[f"{column}_mse"])
    return {
        "rows": int(len(frame)),
        "wells": int(frame["well"].nunique()),
        "last_value_rmse": float(np.sqrt(frame["last_value_square_error"].mean())),
        "selector_rmse": float(np.sqrt(frame["selector_square_error"].mean())),
        "projected_rmse": float(np.sqrt(frame["projected_square_error"].mean())),
        "projected_well_rmse_p50": float(by_well["projected_rmse"].quantile(0.50)),
        "projected_well_rmse_p90": float(by_well["projected_rmse"].quantile(0.90)),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    excluded_wells: set[str] = set()
    for exclude_summary in args.exclude_summary:
        exclude_record = json.loads(exclude_summary.read_text(encoding="utf-8"))
        excluded_wells.update(map(str, exclude_record.get("sampled_wells", [])))
    wells = select_wells(
        args.data_root,
        args.n_wells,
        args.seed,
        excluded_wells,
    )
    namespace = load_selector_namespace(
        args.notebook,
        args.data_root,
        args.particles,
        args.pf_seeds,
    )
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    if args.branch_stats_cache is not None:
        args.branch_stats_cache.mkdir(parents=True, exist_ok=True)
    selector_well_code = namespace["selector_well_code"]
    run_pf_scales = namespace["run_pf_lik_ensemble_scales"]
    run_beam = namespace["run_beam_ensemble"]
    apply_selector = namespace["apply_selector_variant"]

    records: list[pd.DataFrame] = []
    diagnostics: list[dict[str, object]] = []
    for position, well in enumerate(wells, 1):
        cache_path = args.cache_dir / f"{well}.csv"
        diagnostic_path = args.cache_dir / f"{well}.json"
        if cache_path.exists() and diagnostic_path.exists() and not args.overwrite:
            records.append(pd.read_csv(cache_path, dtype={"id": str, "well": str}))
            diagnostics.append(json.loads(diagnostic_path.read_text(encoding="utf-8")))
            print(f"{position}/{len(wells)} {well}: cached", flush=True)
            continue
        well_started = time.perf_counter()
        horizontal = pd.read_csv(args.data_root / "train" / f"{well}__horizontal_well.csv")
        typewell = pd.read_csv(args.data_root / "train" / f"{well}__typewell.csv")
        eval_mask = horizontal["TVT_input"].isna().to_numpy()
        row_indices = np.flatnonzero(eval_mask).astype(int)
        if len(row_indices) < 10:
            continue
        selector_code, selector_variant, n_eval, z_span = selector_well_code(horizontal)
        branch_stats: dict[str, object] = {}
        pf_kwargs = {
            "n_particles": args.particles,
            "n_seeds": args.pf_seeds,
        }
        if args.branch_stats_cache is not None:
            pf_kwargs["branch_stats"] = branch_stats
        pf_by_scale = run_pf_scales(horizontal, typewell, **pf_kwargs)
        if args.branch_stats_cache is not None:
            branch_stats.update(
                {
                    "well": str(well),
                    "pf_seeds": int(args.pf_seeds),
                    "particles": int(args.particles),
                }
            )
            (args.branch_stats_cache / f"{well}.json").write_text(
                json.dumps(branch_stats, indent=2) + "\n",
                encoding="utf-8",
            )
        try:
            beam = run_beam(horizontal, typewell)
        except Exception:
            beam = pf_by_scale.get("pf_scale_8", next(iter(pf_by_scale.values()))).copy()
        known = pd.to_numeric(
            horizontal.loc[horizontal["TVT_input"].notna(), "TVT_input"],
            errors="coerce",
        ).dropna()
        last_tvt = float(known.iloc[-1])
        selector_full, info = apply_selector(
            selector_variant,
            pf_by_scale,
            beam,
            last_tvt,
            hw=horizontal,
            tw=typewell,
            return_info=True,
        )
        selector = np.asarray(selector_full, dtype=float)[row_indices]
        projected = project_sp45(
            horizontal,
            row_indices,
            selector,
            args.projection_degree,
            args.projection_blend,
        )
        target = pd.to_numeric(
            horizontal.loc[eval_mask, "TVT"], errors="coerce"
        ).to_numpy(float)
        frame = pd.DataFrame(
            {
                "id": [f"{well}_{row}" for row in row_indices],
                "well": well,
                "row_idx": row_indices,
                "target_tvt": target,
                "last_value_tvt": last_tvt,
                "selector_tvt": selector,
                "projected_tvt": projected,
            }
        )
        frame["last_value_square_error"] = (frame["last_value_tvt"] - target) ** 2
        frame["selector_square_error"] = (frame["selector_tvt"] - target) ** 2
        frame["projected_square_error"] = (frame["projected_tvt"] - target) ** 2
        if not np.isfinite(
            frame[["target_tvt", "selector_tvt", "projected_tvt"]].to_numpy(float)
        ).all():
            raise RuntimeError(f"non-finite prediction for well {well}")
        frame.to_csv(cache_path, index=False)
        diagnostic = {
            "well": well,
            "selector_code": int(selector_code),
            "selector_variant": str(selector_variant),
            "n_eval": float(n_eval),
            "z_span": float(z_span),
            "rows": int(len(frame)),
            "selector_rmse": float(np.sqrt(frame["selector_square_error"].mean())),
            "projected_rmse": float(np.sqrt(frame["projected_square_error"].mean())),
            "elapsed_sec": float(time.perf_counter() - well_started),
            "selector_info": {
                key: value
                for key, value in dict(info).items()
                if isinstance(value, (str, int, float, bool)) or value is None
            },
        }
        diagnostic_path.write_text(json.dumps(diagnostic, indent=2) + "\n", encoding="utf-8")
        records.append(frame)
        diagnostics.append(diagnostic)
        print(
            f"{position}/{len(wells)} {well}: "
            f"selector={diagnostic['selector_rmse']:.4f} "
            f"projected={diagnostic['projected_rmse']:.4f} "
            f"sec={diagnostic['elapsed_sec']:.1f}",
            flush=True,
        )

    if not records:
        raise RuntimeError("no wells were evaluated")
    output = pd.concat(records, ignore_index=True)
    if output["id"].duplicated().any():
        raise RuntimeError("duplicate ids in local SP45 OOF")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    summary = {
        "method": "public_generic_core_selector_projection_local_sample",
        "notebook": str(args.notebook),
        "notebook_sha256": notebook_sha256(args.notebook),
        "control_cell": CONTROL_CELL_INDEX,
        "selector_cell": SELECTOR_CELL_INDEX,
        "sample_seed": args.seed,
        "requested_wells": args.n_wells,
        "excluded_wells": int(len(excluded_wells)),
        "sampled_wells": wells,
        "pf_seeds": args.pf_seeds,
        "particles": args.particles,
        "projection_degree": args.projection_degree,
        "projection_blend": args.projection_blend,
        "metrics": well_metrics(output),
        "elapsed_sec": float(time.perf_counter() - started),
        "same_well_contact_included": False,
        "visible_prefix_overlay_included": False,
        "model_package_correction_included": False,
        "ridge_branch_included": False,
        "learned_branch_included": False,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notebook", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument("--n-wells", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--exclude-summary", type=Path, action="append", default=[])
    parser.add_argument("--pf-seeds", type=int, default=8)
    parser.add_argument("--particles", type=int, default=100)
    parser.add_argument("--projection-degree", type=int, default=3)
    parser.add_argument("--projection-blend", type=float, default=0.75)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--branch-stats-cache", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
