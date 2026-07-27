"""Evaluate a target-free well-level OOD fallback for the all13 meta branch.

The all13 Ridge improves independent held-out wells, but its package TCN can
shift strongly on the three competition test wells.  This experiment measures
package/public disagreement per well using predictions only.  Wells beyond a
robust training-distribution threshold fall back to a public5-only Ridge.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from sklearn.linear_model import Ridge

from generic_core_learned_branch_holdout import load_inputs, load_wells
from learned_branch_meta_oof import RIDGE_PARAMS, VARIANTS, rmse


def robust_location_scale(values: pd.Series) -> tuple[float, float]:
    location = float(values.median())
    mad = float((values - location).abs().median())
    return location, max(1.4826 * mad, 1e-6)


def well_signals(
    truth: pd.DataFrame,
    arrays: dict[str, np.ndarray],
    positions: np.ndarray,
) -> pd.DataFrame:
    public = np.median(
        np.column_stack(
            [arrays[f"public_{index}"][positions] for index in range(5)]
        ),
        axis=1,
    )
    frame = pd.DataFrame(
        {
            "well": truth["well_id"].astype(str).to_numpy(),
            "tcn_gap": arrays["package_sequence_tcn"][positions] - public,
            "post_gap": arrays["package_postprocessed"][positions] - public,
        }
    )
    return (
        frame.groupby("well", sort=True)[["tcn_gap", "post_gap"]]
        .median()
        .reset_index()
    )


def fit_ood_reference(signals: pd.DataFrame) -> dict[str, float]:
    tcn_location, tcn_scale = robust_location_scale(signals["tcn_gap"])
    post_location, post_scale = robust_location_scale(signals["post_gap"])
    return {
        "tcn_location": tcn_location,
        "tcn_scale": tcn_scale,
        "post_location": post_location,
        "post_scale": post_scale,
    }


def apply_ood_reference(
    signals: pd.DataFrame,
    reference: dict[str, float],
) -> pd.DataFrame:
    output = signals.copy()
    output["tcn_z"] = (
        output["tcn_gap"] - reference["tcn_location"]
    ).abs() / reference["tcn_scale"]
    output["post_z"] = (
        output["post_gap"] - reference["post_location"]
    ).abs() / reference["post_scale"]
    output["ood_z"] = output[["tcn_z", "post_z"]].max(axis=1)
    return output


def smooth_by_well(
    frame: pd.DataFrame,
    values: np.ndarray,
    window: int,
    polynomial: int = 3,
) -> np.ndarray:
    output = np.asarray(values, dtype=float).copy()
    for _, part in frame.groupby("well", sort=False):
        positions = part.index.to_numpy(int)
        local_window = min(window, len(positions))
        if local_window % 2 == 0:
            local_window -= 1
        if local_window >= polynomial + 2:
            output[positions] = savgol_filter(
                output[positions],
                window_length=local_window,
                polyorder=polynomial,
                mode="interp",
            )
    return output


def metrics(
    frame: pd.DataFrame,
    prediction: str,
) -> dict[str, float]:
    error = frame[prediction].to_numpy(float) - frame["target_tvt"].to_numpy(float)
    work = pd.DataFrame({"well": frame["well"], "square_error": error**2})
    per_well = np.sqrt(work.groupby("well")["square_error"].mean())
    return {
        "rmse": float(np.sqrt(np.mean(error**2))),
        "well_rmse_p50": float(per_well.quantile(0.50)),
        "well_rmse_p90": float(per_well.quantile(0.90)),
    }


def run(args: argparse.Namespace) -> dict:
    evaluation_wells = load_wells(args.evaluation_summary)
    truth, arrays = load_inputs(args)
    is_evaluation = truth["well_id"].astype(str).isin(evaluation_wells)
    train_positions = np.flatnonzero(~is_evaluation.to_numpy())
    evaluation_positions = np.flatnonzero(is_evaluation.to_numpy())
    train = truth.loc[~is_evaluation].reset_index(drop=True)
    evaluation = truth.loc[is_evaluation].reset_index(drop=True)
    train_target = train["target_delta_from_last_known"].to_numpy(np.float32)

    predictions: dict[str, np.ndarray] = {}
    fit_records: dict[str, object] = {}
    for variant in ("public5", "all13"):
        features = VARIANTS[variant]
        train_matrix = np.column_stack(
            [arrays[name][train_positions] for name in features]
        )
        evaluation_matrix = np.column_stack(
            [arrays[name][evaluation_positions] for name in features]
        )
        model = Ridge(**RIDGE_PARAMS)
        model.fit(train_matrix, train_target)
        predictions[variant] = model.predict(evaluation_matrix)
        fit_records[variant] = {
            "features": list(features),
            "coef": [float(value) for value in model.coef_],
            "intercept": float(model.intercept_),
            "train_rmse": rmse(train_target, model.predict(train_matrix)),
        }

    train_signals = well_signals(train, arrays, train_positions)
    evaluation_signals = well_signals(
        evaluation, arrays, evaluation_positions
    )
    reference = fit_ood_reference(train_signals)
    evaluation_signals = apply_ood_reference(evaluation_signals, reference)
    evaluation_signals["use_all13"] = (
        evaluation_signals["ood_z"] <= args.ood_threshold
    )

    branch = evaluation[["id", "well_id", "last_known_TVT"]].copy()
    branch = branch.rename(columns={"well_id": "well"})
    for variant in ("public5", "all13"):
        values = branch["last_known_TVT"].to_numpy(float) + predictions[variant]
        branch[f"{variant}_tvt"] = smooth_by_well(
            branch, values, args.smooth_window
        )
    branch = branch.merge(
        evaluation_signals[["well", "ood_z", "use_all13"]],
        on="well",
        how="left",
        validate="many_to_one",
    )
    branch["gated_tvt"] = np.where(
        branch["use_all13"],
        branch["all13_tvt"],
        branch["public5_tvt"],
    )

    holdout = pd.read_parquet(args.holdout_frame)
    required = {
        "id",
        "well",
        "row_idx",
        "target_tvt",
        "sp45_sgridge_d2_b050",
        "artifact_proxy_full",
        "evaluation_split",
    }
    if not required.issubset(holdout):
        raise RuntimeError(f"holdout frame misses {sorted(required - set(holdout))}")
    frame = holdout[list(required)].merge(
        branch[
            [
                "id",
                "public5_tvt",
                "all13_tvt",
                "gated_tvt",
                "ood_z",
                "use_all13",
            ]
        ],
        on="id",
        how="inner",
        validate="one_to_one",
    )
    if len(frame) != len(evaluation):
        raise RuntimeError("holdout/branch ID mismatch")
    for variant in ("public5", "all13", "gated"):
        frame[f"{variant}_full"] = (
            args.sp45_weight * frame["sp45_sgridge_d2_b050"].to_numpy(float)
            + (1.0 - args.sp45_weight) * frame[f"{variant}_tvt"].to_numpy(float)
        )

    prediction_columns = [
        "artifact_proxy_full",
        "public5_full",
        "all13_full",
        "gated_full",
    ]
    metric_records: dict[str, object] = {
        "all": {
            column: metrics(frame, column) for column in prediction_columns
        }
    }
    for split, part in frame.groupby("evaluation_split", sort=True):
        metric_records[str(split)] = {
            column: metrics(part, column) for column in prediction_columns
        }

    gate_records = (
        evaluation_signals.sort_values("ood_z", ascending=False)
        .reset_index(drop=True)
        .to_dict(orient="records")
    )
    production_positions = np.arange(len(truth))
    production_signals = well_signals(truth, arrays, production_positions)
    production_reference = fit_ood_reference(production_signals)
    production_signals = apply_ood_reference(
        production_signals, production_reference
    )
    production_models: dict[str, object] = {}
    production_target = truth[
        "target_delta_from_last_known"
    ].to_numpy(np.float32)
    for variant in ("public5", "all13"):
        features = VARIANTS[variant]
        matrix = np.column_stack([arrays[name] for name in features])
        model = Ridge(**RIDGE_PARAMS)
        model.fit(matrix, production_target)
        production_models[variant] = {
            "features": list(features),
            "coef": [float(value) for value in model.coef_],
            "intercept": float(model.intercept_),
            "train_rmse": rmse(production_target, model.predict(matrix)),
        }
    high_ood_wells = set(
        production_signals.loc[
            production_signals["ood_z"] > args.ood_threshold, "well"
        ].astype(str)
    )
    high_is_evaluation = truth["well_id"].astype(str).isin(high_ood_wells)
    high_train_positions = np.flatnonzero(~high_is_evaluation.to_numpy())
    high_evaluation_positions = np.flatnonzero(high_is_evaluation.to_numpy())
    high_target = production_target[high_evaluation_positions]
    high_ood_metrics: dict[str, object] = {}
    for variant in ("public5", "all13"):
        features = VARIANTS[variant]
        model = Ridge(**RIDGE_PARAMS)
        model.fit(
            np.column_stack(
                [arrays[name][high_train_positions] for name in features]
            ),
            production_target[high_train_positions],
        )
        prediction = model.predict(
            np.column_stack(
                [arrays[name][high_evaluation_positions] for name in features]
            )
        )
        errors = pd.DataFrame(
            {
                "well": truth.loc[
                    high_is_evaluation, "well_id"
                ].astype(str).to_numpy(),
                "square_error": (prediction - high_target) ** 2,
            }
        )
        per_well = np.sqrt(
            errors.groupby("well", sort=True)["square_error"].mean()
        )
        high_ood_metrics[variant] = {
            "rmse": rmse(high_target, prediction),
            "well_rmse": {
                str(well): float(value)
                for well, value in per_well.items()
            },
        }
    high_ood_audit = {
        "selection_uses_predictions_only": True,
        "threshold": float(args.ood_threshold),
        "wells": sorted(high_ood_wells),
        "rows": int(len(high_evaluation_positions)),
        "meta_fit_excludes_all_selected_wells": True,
        "metrics": high_ood_metrics,
        "public5_minus_all13_rmse": float(
            high_ood_metrics["public5"]["rmse"]
            - high_ood_metrics["all13"]["rmse"]
        ),
        "fallback_supported": bool(
            high_ood_metrics["public5"]["rmse"]
            <= high_ood_metrics["all13"]["rmse"]
        ),
    }
    summary = {
        "method": "independent_holdout_well_ood_fallback_all13_to_public5",
        "train_wells": int(train["well_id"].nunique()),
        "evaluation_wells": int(evaluation["well_id"].nunique()),
        "evaluation_rows": int(len(evaluation)),
        "ood_threshold": float(args.ood_threshold),
        "ood_reference": reference,
        "fit_records": fit_records,
        "production_fit_all_773": {
            "ood_reference": production_reference,
            "models": production_models,
        },
        "high_ood_target_free_holdout_audit": high_ood_audit,
        "gated_wells": int((~evaluation_signals["use_all13"]).sum()),
        "metrics": metric_records,
        "improvement_vs_artifact": float(
            metric_records["all"]["artifact_proxy_full"]["rmse"]
            - metric_records["all"]["gated_full"]["rmse"]
        ),
        "improvement_vs_all13": float(
            metric_records["all"]["all13_full"]["rmse"]
            - metric_records["all"]["gated_full"]["rmse"]
        ),
        "gate_records": gate_records,
        "leakage_controls": {
            "evaluation_wells_excluded_from_meta_fit": True,
            "evaluation_wells_excluded_from_ood_reference": True,
            "gate_uses_predictions_only": True,
            "ood_threshold_fixed_before_evaluation": True,
            "same_well_target_used": False,
            "public_well_ids_used": False,
        },
        "output": str(args.output),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.output, index=False)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in summary.items() if key != "gate_records"}, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-gt", type=Path, required=True)
    parser.add_argument("--public-oof-dir", type=Path, required=True)
    parser.add_argument("--package-oof-dir", type=Path, required=True)
    parser.add_argument("--local-oof", type=Path, required=True)
    parser.add_argument(
        "--evaluation-summary", type=Path, action="append", required=True
    )
    parser.add_argument("--holdout-frame", type=Path, required=True)
    parser.add_argument("--ood-threshold", type=float, default=5.0)
    parser.add_argument("--sp45-weight", type=float, default=0.60)
    parser.add_argument("--smooth-window", type=int, default=61)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
