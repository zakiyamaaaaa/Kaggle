"""Build the exact SP45 Ridge30/Selector70 trajectory for all 773 wells."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from generic_core_sp45_ridge_blend import (
    build_public_pf_for_wells,
    load_public_pf,
    project_candidate,
    smooth_by_well,
)


def run(args: argparse.Namespace) -> dict[str, object]:
    selector = pd.read_csv(
        args.selector_oof,
        usecols=["id", "row_idx", "selector_tvt", "target_tvt"],
        dtype={"id": str},
    )
    truth = pd.read_parquet(
        args.train_gt,
        columns=["id", "well_id", "row_index", "last_known_TVT"],
    ).rename(columns={"well_id": "well", "row_index": "row_idx"})
    frame = truth.merge(
        selector,
        on=["id", "row_idx"],
        how="left",
        validate="one_to_one",
    )
    if frame[["selector_tvt", "target_tvt"]].isna().any().any():
        raise RuntimeError("selector OOF does not cover the full train contract")
    ridge = np.asarray(np.load(args.ridge_oof, mmap_mode="r"), float)
    if len(ridge) != len(frame):
        raise RuntimeError("Ridge OOF length differs from train contract")

    pf_namespace = load_public_pf(args.notebook, args.pf_cell)
    pf, md_since = build_public_pf_for_wells(
        frame,
        args.data_root,
        pf_namespace,
        args.pf_cache_dir,
        args.pf_seed,
        False,
    )
    last = frame["last_known_TVT"].to_numpy(float)
    warmup = 1.0 - np.exp(-np.maximum(md_since, 0.0) / 85.0)
    ridge_pp = last + warmup * (0.91 * ridge + 0.09 * (pf - last))
    ridge_smooth = smooth_by_well(
        ridge_pp,
        frame["well"].astype(str).to_numpy(),
        window=17,
        polynomial=3,
    )
    raw = 0.30 * ridge_smooth + 0.70 * frame["selector_tvt"].to_numpy(float)
    projected = project_candidate(
        frame,
        raw,
        args.data_root,
        degree=2,
        blend=0.50,
    )
    output = frame[["id", "well", "row_idx", "target_tvt"]].copy()
    output["sp45"] = projected
    output["ridge_pp_savgol17"] = ridge_smooth
    output["md_since"] = md_since
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_parquet(args.output, index=False)

    target = output["target_tvt"].to_numpy(float)
    score = float(np.sqrt(np.mean(np.square(target - projected))))
    summary = {
        "method": "full773_sp45_ridge030_selector070_projection_d2_b050",
        "rows": int(len(output)),
        "wells": int(output["well"].nunique()),
        "sp45_rmse": score,
        "contracts": {
            "ridge_is_group_oof": True,
            "selector_uses_visible_prefix_and_typewell": True,
            "same_well_contact_used": False,
            "suffix_target_used_for_prediction": False,
        },
        "output": str(args.output),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selector-oof", type=Path, required=True)
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--ridge-oof", type=Path, required=True)
    parser.add_argument("--notebook", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--pf-cache-dir", type=Path, required=True)
    parser.add_argument("--pf-cell", type=int, default=14)
    parser.add_argument("--pf-seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
