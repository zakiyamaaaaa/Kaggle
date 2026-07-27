"""Build the validated all13 learned branch for the three competition test wells.

The meta coefficients come from ``learned_branch_meta_oof.py``.  Public Ridge
test deltas are reproduced with the original generic-core feature builder and
saved fold models.  Model-package deltas are reproduced with the package's own
feature builder and all-train checkpoints.  Expensive base predictions are
cached before the deterministic meta/blend assembly step.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.util
import json
import sys
import time
import types
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.signal import savgol_filter


PUBLIC_PICKLES = (
    "lgbmregressor_trainer_20260526182612.pkl",
    "lgbmregressor_trainer_20260526190415.pkl",
    "lgbmregressor_trainer_20260526192806.pkl",
    "catboostregressor_trainer_20260526193740.pkl",
    "catboostregressor_trainer_20260526194838.pkl",
)

PACKAGE_COLUMNS = {
    "pred_delta_drift_ncc_lgb_alltrain": "package_lgb",
    "pred_delta_drift_ncc_xgb_alltrain": "package_xgb",
    "pred_delta_drift_ncc_catboost_alltrain": "package_catboost",
    "pred_delta_drift_ncc_hgb_alltrain": "package_hgb",
    "pred_delta_sequence_tcn_tcn_residual": "package_sequence_tcn",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_ids(
    frame: pd.DataFrame,
    sample: pd.DataFrame,
    label: str,
) -> pd.DataFrame:
    if "id" not in frame:
        raise RuntimeError(f"{label}: id column is missing")
    work = frame.copy()
    work["id"] = work["id"].astype(str)
    sample_ids = sample["id"].astype(str)
    if work["id"].duplicated().any():
        raise RuntimeError(f"{label}: duplicate ids")
    if len(work) != len(sample) or set(work["id"]) != set(sample_ids):
        raise RuntimeError(f"{label}: sample id set mismatch")
    work = sample[["id"]].astype(str).merge(work, on="id", how="left")
    numeric = [column for column in work if column != "id"]
    if work[numeric].isna().any().any():
        raise RuntimeError(f"{label}: missing values after sample alignment")
    if not np.isfinite(work[numeric].to_numpy(float)).all():
        raise RuntimeError(f"{label}: non-finite predictions")
    return work


def notebook_source(notebook: Path, index: int) -> str:
    cells = read_json(notebook)["cells"]
    source = cells[index]["source"]
    return "".join(source) if isinstance(source, list) else source


def predict_saved_trainer(trainer: object, features: pd.DataFrame) -> np.ndarray:
    estimators = getattr(trainer, "estimators", None)
    if estimators is None:
        estimators = getattr(trainer, "models", None)
    if estimators:
        values = [
            np.asarray(estimator.predict(features), dtype=np.float64)
            for estimator in estimators
        ]
        return np.mean(values, axis=0)
    if hasattr(trainer, "predict"):
        return np.asarray(trainer.predict(features), dtype=np.float64)
    raise RuntimeError("saved public trainer has no estimators or predict method")


def build_public_components(args: argparse.Namespace, sample: pd.DataFrame) -> pd.DataFrame:
    if args.public_cache.exists() and not args.force:
        return validate_ids(
            pd.read_parquet(args.public_cache), sample, "public cache"
        )

    namespace: dict[str, object] = {
        "__name__": "rogii_generic_core_public_test_runtime",
        "COMPETITION_DATA_ROOT": str(args.data_root),
        "RIDGE_ARTIFACT_ROOT": str(args.ridge_artifacts),
        "KOOLBOX_OFFLINE_ROOTS": (),
    }
    for index in (8, 9, 10):
        code = notebook_source(args.notebook, index)
        if index == 9:
            code = code.replace("import matplotlib.pyplot as plt\n", "")
            code = code.replace("import seaborn as sns\n", "")
        exec(compile(code, str(args.notebook), "exec"), namespace)
        if index == 8:
            koolbox = sys.modules["koolbox"]
            trainer_package = types.ModuleType("koolbox.trainer")
            trainer_package.__path__ = []
            trainer_module = types.ModuleType("koolbox.trainer.trainer")
            trainer_package.Trainer = koolbox.Trainer
            trainer_module.Trainer = koolbox.Trainer
            sys.modules["koolbox.trainer"] = trainer_package
            sys.modules["koolbox.trainer.trainer"] = trainer_module
    code = notebook_source(args.notebook, 14).replace(
        "@njit(cache=True)", "@njit(cache=False)"
    )
    exec(compile(code, str(args.notebook), "exec"), namespace)

    test_paths = sorted((args.data_root / "test").glob("*__horizontal_well.csv"))
    test_frame = namespace["build_dataset"](test_paths, False, "test")
    train_columns = pd.read_csv(
        args.ridge_artifacts / "train.csv", nrows=0
    ).columns
    feature_columns = [
        column
        for column in train_columns
        if column not in {"well", "id", "target"}
    ]
    missing = sorted(set(feature_columns) - set(test_frame.columns))
    if missing:
        raise RuntimeError(
            f"public test feature frame misses {len(missing)} columns: {missing[:10]}"
        )
    matrix = test_frame[feature_columns]
    output = pd.DataFrame({"id": test_frame["id"].astype(str)})
    for index, filename in enumerate(PUBLIC_PICKLES):
        path = args.ridge_artifacts / filename
        print(f"public component {index + 1}/{len(PUBLIC_PICKLES)}: {path.name}")
        trainer = joblib.load(path)
        prediction = predict_saved_trainer(trainer, matrix)
        if prediction.shape != (len(matrix),):
            raise RuntimeError(f"public_{index}: prediction shape {prediction.shape}")
        output[f"public_{index}"] = prediction
        del trainer, prediction
        gc.collect()

    output = validate_ids(output, sample, "public components")
    args.public_cache.parent.mkdir(parents=True, exist_ok=True)
    output.to_parquet(args.public_cache, index=False)
    return output


def load_feature_builder(package_root: Path):
    path = package_root / "feature_builders" / "build_features.py"
    spec = importlib.util.spec_from_file_location(
        "rogii_model_package_test_features", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not import feature builder: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.build_features


def feature_columns_for_model(config: object, entry: dict) -> list[str]:
    if isinstance(entry.get("feature_columns"), list):
        return list(entry["feature_columns"])
    feature_set = entry.get("feature_set")
    if isinstance(config, list):
        return list(config)
    if isinstance(config, dict):
        if feature_set and isinstance(config.get(feature_set), list):
            return list(config[feature_set])
        if isinstance(config.get("columns"), list):
            return list(config["columns"])
    raise RuntimeError(f"could not resolve feature columns for {entry}")


def load_package_model(package_root: Path, entry: dict):
    model_type = entry["model_type"]
    path = package_root / entry["path"]
    if model_type == "lightgbm_booster":
        import lightgbm as lgb

        return lgb.Booster(model_file=str(path))
    if model_type == "xgboost_json":
        import xgboost as xgb

        model = xgb.Booster()
        model.load_model(str(path))
        return model
    if model_type == "catboost_cbm":
        from catboost import CatBoostRegressor

        model = CatBoostRegressor()
        model.load_model(str(path))
        return model
    if model_type == "sklearn_pickle":
        # The package was serialized in a notebook that exposed
        # sklearn._loss.loss under the short module name ``_loss``.
        import sklearn._loss.loss as sklearn_loss

        sys.modules.setdefault("_loss", sklearn_loss)
        return joblib.load(path)
    if model_type == "torch_tcn":
        import torch

        try:
            return torch.load(path, map_location="cpu", weights_only=False)
        except TypeError:
            return torch.load(path, map_location="cpu")
    raise RuntimeError(f"unsupported model type: {model_type}")


def build_tcn(n_features: int, config: dict):
    import torch
    from torch import nn

    class TCNBlock(nn.Module):
        def __init__(
            self,
            in_channels: int,
            out_channels: int,
            kernel_size: int,
            dilation: int,
            dropout: float,
        ):
            super().__init__()
            padding = dilation * (kernel_size - 1) // 2
            self.conv1 = nn.Conv1d(
                in_channels,
                out_channels,
                kernel_size,
                padding=padding,
                dilation=dilation,
            )
            self.conv2 = nn.Conv1d(
                out_channels,
                out_channels,
                kernel_size,
                padding=padding,
                dilation=dilation,
            )
            self.act = nn.GELU()
            self.drop = nn.Dropout(float(dropout))
            self.skip = (
                nn.Identity()
                if in_channels == out_channels
                else nn.Conv1d(in_channels, out_channels, 1)
            )

        def forward(self, values):
            residual = self.skip(values)
            output = self.drop(self.act(self.conv1(values)))
            output = self.drop(self.act(self.conv2(output)))
            if output.shape[-1] != residual.shape[-1]:
                length = min(output.shape[-1], residual.shape[-1])
                output = output[..., :length]
                residual = residual[..., :length]
            return self.act(output + residual)

    class TCNRegressor(nn.Module):
        def __init__(self):
            super().__init__()
            blocks = []
            in_channels = n_features
            channels = int(config.get("channels", 64))
            kernel_size = int(config.get("kernel_size", 5))
            dropout = float(config.get("dropout", 0.0))
            for index in range(int(config.get("blocks", 6))):
                blocks.append(
                    TCNBlock(
                        in_channels,
                        channels,
                        kernel_size,
                        2**index,
                        dropout,
                    )
                )
                in_channels = channels
            self.net = nn.Sequential(*blocks)
            self.head = nn.Conv1d(channels, 1, 1)

        def forward(self, values):
            return self.head(self.net(values)).squeeze(1)

    return TCNRegressor()


def predict_tcn(
    payload: dict,
    frame: pd.DataFrame,
    columns: list[str],
    entry: dict,
) -> np.ndarray:
    import torch

    values = (
        frame[columns]
        .replace([np.inf, -np.inf], np.nan)
        .to_numpy(dtype=np.float32)
    )
    standardizer = payload.get("standardizer", {}) or {}
    mean = np.asarray(standardizer.get("mean"), dtype=np.float32)
    scale = np.asarray(standardizer.get("scale"), dtype=np.float32)
    values = (values - mean[None, :]) / np.maximum(scale[None, :], 1e-6)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    group_column = entry.get("sequence_group_column", "well_id")
    order_column = entry.get("sequence_order_column", "row_index")
    order = pd.DataFrame(
        {
            "position": np.arange(len(frame)),
            "group": frame[group_column].astype(str).to_numpy(),
            "order": pd.to_numeric(frame[order_column], errors="coerce").to_numpy(),
        }
    )
    model = build_tcn(len(columns), payload.get("config", {}) or {})
    model.load_state_dict(payload["state_dict"])
    model.eval()
    prediction = np.full(len(frame), np.nan, dtype=np.float32)
    with torch.no_grad():
        for _, part in order.groupby("group", sort=False):
            positions = part.sort_values("order")["position"].to_numpy(int)
            tensor = torch.from_numpy(values[positions].T[None, :, :].copy())
            prediction[positions] = (
                model(tensor).detach().cpu().numpy().reshape(-1)[: len(positions)]
            )
    return prediction.astype(np.float64)


def predict_package_model(
    model: object,
    frame: pd.DataFrame,
    columns: list[str],
    entry: dict,
    manifest: dict,
) -> np.ndarray:
    model_type = entry["model_type"]
    if model_type == "torch_tcn":
        return predict_tcn(model, frame, columns, entry)
    matrix = frame[columns].replace([np.inf, -np.inf], np.nan)
    fill_value = entry.get("fillna")
    policy = str(
        entry.get(
            "missing_value_policy",
            manifest.get("missing_value_policy", "native"),
        )
    ).lower()
    if fill_value is not None:
        matrix = matrix.fillna(float(fill_value))
    elif policy in {"zero", "fill_zero"}:
        matrix = matrix.fillna(0.0)
    if model_type == "xgboost_json":
        import xgboost as xgb

        prediction = model.predict(
            xgb.DMatrix(matrix.to_numpy(dtype=np.float32))
        )
    else:
        prediction = model.predict(matrix)
    return np.asarray(prediction, dtype=np.float64).reshape(len(frame), -1)[:, 0]


def smooth_by_well(
    frame: pd.DataFrame,
    values: np.ndarray,
    window: int,
    polynomial: int,
) -> np.ndarray:
    output = np.asarray(values, dtype=np.float64).copy()
    grouping = frame["id"].astype(str).str.rsplit("_", n=1).str[0]
    order = frame["id"].astype(str).str.rsplit("_", n=1).str[1].astype(int)
    positions = pd.DataFrame(
        {"position": np.arange(len(frame)), "well": grouping, "order": order}
    )
    for _, part in positions.groupby("well", sort=False):
        local = part.sort_values("order")["position"].to_numpy(int)
        local_window = min(window, len(local))
        if local_window % 2 == 0:
            local_window -= 1
        if local_window >= polynomial + 2:
            output[local] = savgol_filter(
                output[local],
                window_length=local_window,
                polyorder=min(polynomial, local_window - 1),
                mode="interp",
            )
    return output


def build_package_components(args: argparse.Namespace, sample: pd.DataFrame) -> pd.DataFrame:
    if args.package_cache.exists() and not args.force:
        return validate_ids(
            pd.read_parquet(args.package_cache), sample, "package cache"
        )

    manifest = read_json(
        args.model_package / "metadata" / "model_package_manifest.json"
    )
    feature_config = read_json(
        args.model_package / manifest["feature_columns"]
    )
    blend_config = read_json(args.model_package / manifest["blend_config"])
    builder = load_feature_builder(args.model_package)
    frame = builder(
        data_dir=args.data_root,
        sample_submission=sample,
        package_root=args.model_package,
        manifest=manifest,
    )
    frame = frame.copy()
    frame["id"] = frame["id"].astype(str)
    if frame["id"].duplicated().any():
        raise RuntimeError("package feature frame: duplicate ids")
    if len(frame) != len(sample) or set(frame["id"]) != set(sample["id"]):
        raise RuntimeError("package feature frame: sample id set mismatch")
    frame = sample[["id"]].merge(frame, on="id", how="left")
    if (
        frame["last_known_TVT"].isna().any()
        or not np.isfinite(frame["last_known_TVT"].to_numpy(float)).all()
    ):
        raise RuntimeError("package feature frame: invalid last_known_TVT")
    output = pd.DataFrame(
        {
            "id": frame["id"],
            "last_known_TVT": frame["last_known_TVT"].to_numpy(float),
        }
    )
    reference = validate_ids(
        pd.read_csv(args.package_reference)[["id", "tvt"]],
        sample,
        "package reference",
    )
    post = blend_config.get("postprocess", {}) or {}
    alpha = float(post.get("alpha", 1.0))
    reference_postprocessed = (
        reference["tvt"].to_numpy(float)
        - output["last_known_TVT"].to_numpy(float)
    )
    reference_raw_proxy = reference_postprocessed / alpha
    raw_predictions: dict[str, np.ndarray] = {}
    for index, entry in enumerate(manifest["models"], 1):
        prediction_column = entry["prediction_column"]
        output_column = PACKAGE_COLUMNS[prediction_column]
        if (
            args.package_mode == "fast-reference"
            and output_column
            not in {"package_catboost", "package_sequence_tcn"}
        ):
            output[output_column] = reference_raw_proxy
            print(
                f"package component {index}/{len(manifest['models'])}: "
                f"{prediction_column} -> reference proxy"
            )
            continue
        print(
            f"package component {index}/{len(manifest['models'])}: "
            f"{prediction_column}"
        )
        columns = feature_columns_for_model(feature_config, entry)
        model = load_package_model(args.model_package, entry)
        prediction = predict_package_model(
            model, frame, columns, entry, manifest
        )
        if prediction.shape != (len(frame),) or not np.isfinite(prediction).all():
            raise RuntimeError(f"invalid package prediction: {prediction_column}")
        raw_predictions[prediction_column] = prediction
        output[output_column] = prediction
        del model, prediction
        gc.collect()

    if args.package_mode == "exact":
        blend = np.full(len(frame), float(blend_config.get("intercept", 0.0)))
        for column, weight in blend_config["weights"].items():
            blend += float(weight) * raw_predictions[column]
        output["package_blend"] = blend
        postprocessed = blend * alpha
        postprocessed = smooth_by_well(
            frame,
            postprocessed,
            int(post.get("savgol_window", 0) or 0),
            int(post.get("savgol_poly", 2) or 2),
        )
        output["package_postprocessed"] = postprocessed
    else:
        # Existing Kaggle output supplies the exact package postprocessed path.
        # OOF shows that postprocessed/alpha is a close raw-blend proxy:
        # RMSE 0.1359 ft, or 0.0150 ft after the all13 blend coefficient.
        output["package_blend"] = reference_raw_proxy
        output["package_postprocessed"] = reference_postprocessed
    output = validate_ids(output, sample, "package components")
    args.package_cache.parent.mkdir(parents=True, exist_ok=True)
    output.to_parquet(args.package_cache, index=False)
    args.package_cache.with_suffix(".json").write_text(
        json.dumps(
            {
                "mode": args.package_mode,
                "exact_components": (
                    list(PACKAGE_COLUMNS.values())
                    + ["package_blend", "package_postprocessed"]
                    if args.package_mode == "exact"
                    else [
                        "package_catboost",
                        "package_sequence_tcn",
                        "package_postprocessed",
                    ]
                ),
                "proxy_components": (
                    []
                    if args.package_mode == "exact"
                    else [
                        "package_lgb",
                        "package_xgb",
                        "package_hgb",
                        "package_blend",
                    ]
                ),
                "proxy_oof_raw_blend_rmse_ft": (
                    None if args.package_mode == "exact" else 0.13593225
                ),
                "proxy_oof_weighted_meta_impact_rmse_ft": (
                    None if args.package_mode == "exact" else 0.015001617
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def summary_stats(values: np.ndarray) -> dict[str, float]:
    return {
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
    }


def assemble_candidate(
    args: argparse.Namespace,
    sample: pd.DataFrame,
    public: pd.DataFrame,
    package: pd.DataFrame,
) -> dict:
    meta_summary = read_json(args.meta_summary)
    features = list(meta_summary["selected_features"])
    ood_summary = read_json(args.ood_summary)
    production = ood_summary["production_fit_all_773"]
    all13_model = production["models"]["all13"]
    public5_model = production["models"]["public5"]
    coefficients = np.asarray(all13_model["coef"], dtype=float)
    intercept = float(all13_model["intercept"])
    if (
        features != all13_model["features"]
        or len(features) != len(coefficients)
    ):
        raise RuntimeError("all13 meta model does not match OOD summary")

    frame = sample[["id"]].astype(str).merge(public, on="id", how="left")
    frame = frame.merge(package, on="id", how="left")
    local = validate_ids(
        pd.read_csv(args.local_hgb)[["id", "tvt"]],
        sample,
        "local HGB",
    )
    frame = frame.merge(
        local.rename(columns={"tvt": "local_hgb_tvt"}),
        on="id",
        how="left",
    )
    frame["local_hgb"] = (
        frame["local_hgb_tvt"] - frame["last_known_TVT"]
    )
    frame["well"] = frame["id"].str.rsplit("_", n=1).str[0]
    all13_matrix = frame[features].to_numpy(float)
    public5_features = list(public5_model["features"])
    public5_matrix = frame[public5_features].to_numpy(float)
    if not np.isfinite(all13_matrix).all():
        raise RuntimeError("meta matrix contains non-finite values")
    last_known = frame["last_known_TVT"].to_numpy(float)
    all13_delta = intercept + all13_matrix @ coefficients
    public5_delta = (
        float(public5_model["intercept"])
        + public5_matrix @ np.asarray(public5_model["coef"], dtype=float)
    )
    all13_tvt = smooth_by_well(
        frame,
        last_known + all13_delta,
        args.meta_savgol_window,
        args.meta_savgol_poly,
    )
    public5_tvt = smooth_by_well(
        frame,
        last_known + public5_delta,
        args.meta_savgol_window,
        args.meta_savgol_poly,
    )

    public_median = np.median(
        frame[[f"public_{index}" for index in range(5)]].to_numpy(float),
        axis=1,
    )
    signal_rows = pd.DataFrame(
        {
            "well": frame["well"],
            "tcn_gap": frame["package_sequence_tcn"].to_numpy(float)
            - public_median,
            "post_gap": frame["package_postprocessed"].to_numpy(float)
            - public_median,
        }
    )
    well_signals = (
        signal_rows.groupby("well", sort=True)[["tcn_gap", "post_gap"]]
        .median()
        .reset_index()
    )
    reference = production["ood_reference"]
    well_signals["tcn_z"] = (
        well_signals["tcn_gap"] - float(reference["tcn_location"])
    ).abs() / float(reference["tcn_scale"])
    well_signals["post_z"] = (
        well_signals["post_gap"] - float(reference["post_location"])
    ).abs() / float(reference["post_scale"])
    well_signals["ood_z"] = well_signals[["tcn_z", "post_z"]].max(axis=1)
    well_signals["use_all13"] = (
        well_signals["ood_z"] <= float(ood_summary["ood_threshold"])
    )
    use_all13 = frame["well"].map(
        well_signals.set_index("well")["use_all13"]
    )
    if use_all13.isna().any():
        raise RuntimeError("missing test-well OOD decision")
    if args.ood_action == "fallback":
        meta_tvt = np.where(
            use_all13.to_numpy(bool), all13_tvt, public5_tvt
        )
    else:
        meta_tvt = all13_tvt

    sp45 = validate_ids(
        pd.read_csv(args.sp45)[["id", "tvt"]], sample, "SP45"
    )
    final = (
        args.sp45_weight * sp45["tvt"].to_numpy(float)
        + (1.0 - args.sp45_weight) * meta_tvt
    )
    candidate = pd.DataFrame({"id": sample["id"].astype(str), "tvt": final})
    candidate = validate_ids(candidate, sample, "all13 candidate")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    candidate.to_csv(args.output, index=False)

    package_reference = validate_ids(
        pd.read_csv(args.package_reference)[["id", "tvt"]],
        sample,
        "package reference",
    )
    reconstructed_package = (
        frame["last_known_TVT"].to_numpy(float)
        + frame["package_postprocessed"].to_numpy(float)
    )
    package_difference = (
        reconstructed_package - package_reference["tvt"].to_numpy(float)
    )
    baseline = validate_ids(
        pd.read_csv(args.baseline)[["id", "tvt"]], sample, "baseline"
    )
    final_difference = final - baseline["tvt"].to_numpy(float)
    component_stats = {
        column: summary_stats(frame[column].to_numpy(float))
        for column in features
    }
    report = {
        "method": (
            "well_ood_gated_all13_to_public5_savgol61_sp45_w060"
            if args.ood_action == "fallback"
            else "all13_savgol61_sp45_w060_with_ood_audit"
        ),
        "rows": int(len(candidate)),
        "wells": int(
            candidate["id"].str.rsplit("_", n=1).str[0].nunique()
        ),
        "selected_features": features,
        "coefficients": coefficients.tolist(),
        "intercept": intercept,
        "coefficient_sum": float(coefficients.sum()),
        "fallback_model": public5_model,
        "ood_gate": {
            "action": args.ood_action,
            "threshold": float(ood_summary["ood_threshold"]),
            "reference": reference,
            "test_wells": well_signals.to_dict(orient="records"),
            "all13_wells": int(well_signals["use_all13"].sum()),
            "public5_fallback_wells": int(
                (~well_signals["use_all13"]).sum()
            ),
            "independent_holdout_gated_wells": int(
                ood_summary["gated_wells"]
            ),
            "independent_holdout_gated_rmse": float(
                ood_summary["metrics"]["all"]["gated_full"]["rmse"]
            ),
            "high_ood_target_free_holdout_audit": ood_summary.get(
                "high_ood_target_free_holdout_audit", {}
            ),
        },
        "meta_savgol": {
            "window": int(args.meta_savgol_window),
            "poly": int(args.meta_savgol_poly),
        },
        "sp45_weight": float(args.sp45_weight),
        "candidate": {
            "path": str(args.output),
            "sha256": sha256(args.output),
            "tvt": summary_stats(final),
        },
        "difference_vs_baseline": {
            "baseline": str(args.baseline),
            "mean_signed": float(np.mean(final_difference)),
            "mean_absolute": float(np.mean(np.abs(final_difference))),
            "rmse": float(np.sqrt(np.mean(final_difference**2))),
            "p95_absolute": float(np.quantile(np.abs(final_difference), 0.95)),
            "max_absolute": float(np.max(np.abs(final_difference))),
            "correlation": float(
                np.corrcoef(final, baseline["tvt"].to_numpy(float))[0, 1]
            ),
        },
        "package_reproduction": {
            "reference": str(args.package_reference),
            "max_absolute_difference": float(
                np.max(np.abs(package_difference))
            ),
            "rmse_difference": float(
                np.sqrt(np.mean(package_difference**2))
            ),
        },
        "package_component_provenance": (
            read_json(args.package_cache.with_suffix(".json"))
            if args.package_cache.with_suffix(".json").exists()
            else {}
        ),
        "component_stats_delta_ft": component_stats,
        "audits": {
            "sample_order_exact": bool(
                np.array_equal(
                    candidate["id"].to_numpy(),
                    sample["id"].astype(str).to_numpy(),
                )
            ),
            "unique_ids": bool(not candidate["id"].duplicated().any()),
            "finite_tvt": bool(np.isfinite(final).all()),
            "row_count_exact": bool(len(candidate) == 14151),
            "absolute_tvt_units": bool(
                5_000.0 < float(np.median(final)) < 20_000.0
            ),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("all", "public", "package", "assemble"), default="all")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--notebook",
        type=Path,
        default=Path(
            "kaggle-push/new-strategy-6213-ablations/generic_core/"
            "rogii-new-strategy-6-213-generic-core.ipynb"
        ),
    )
    parser.add_argument(
        "--ridge-artifacts",
        type=Path,
        default=Path("/private/tmp/rogii-ridge-artifacts"),
    )
    parser.add_argument(
        "--model-package",
        type=Path,
        default=Path("/private/tmp/rogii-model-package"),
    )
    parser.add_argument(
        "--public-cache",
        type=Path,
        default=Path("outputs/cache/learned_branch_test/public_components.parquet"),
    )
    parser.add_argument(
        "--package-cache",
        type=Path,
        default=Path("outputs/cache/learned_branch_test/package_components.parquet"),
    )
    parser.add_argument(
        "--package-mode",
        choices=("fast-reference", "exact"),
        default="fast-reference",
    )
    parser.add_argument(
        "--meta-summary",
        type=Path,
        default=Path("outputs/runs/learned_branch_meta_all13_oof_summary.json"),
    )
    parser.add_argument(
        "--ood-summary",
        type=Path,
        default=Path(
            "outputs/runs/learned_branch_ood_gate_holdout_200w_summary.json"
        ),
    )
    parser.add_argument(
        "--ood-action",
        choices=("audit-only", "fallback"),
        default="audit-only",
    )
    parser.add_argument(
        "--local-hgb",
        type=Path,
        default=Path("outputs/submissions/learned_selector_hgb_clip40.csv"),
    )
    parser.add_argument(
        "--sp45",
        type=Path,
        default=Path(
            "/private/tmp/rogii-full-d2-b050-v3-output.JjkPoJ/"
            "sp45_projection_submission.csv"
        ),
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path(
            "/private/tmp/rogii-full-d2-b050-v3-output.JjkPoJ/"
            "submission_sp45_learned_w0.60.csv"
        ),
    )
    parser.add_argument(
        "--package-reference",
        type=Path,
        default=Path(
            "/private/tmp/rogii-original6213-output/"
            "submission_model_package_only.csv"
        ),
    )
    parser.add_argument("--sp45-weight", type=float, default=0.60)
    parser.add_argument("--meta-savgol-window", type=int, default=61)
    parser.add_argument("--meta-savgol-poly", type=int, default=3)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "outputs/submissions/learned_meta_all13_sp45_w060.csv"
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(
            "outputs/runs/learned_meta_all13_sp45_w060_test_summary.json"
        ),
    )
    args = parser.parse_args()
    started = time.perf_counter()
    sample = pd.read_csv(args.data_root / "sample_submission.csv")[["id"]]
    sample["id"] = sample["id"].astype(str)

    public = None
    package = None
    if args.stage in {"all", "public", "assemble"}:
        public = build_public_components(args, sample)
    if args.stage in {"all", "package", "assemble"}:
        package = build_package_components(args, sample)
    if args.stage in {"all", "assemble"}:
        if public is None or package is None:
            raise RuntimeError("assemble requires public and package components")
        assemble_candidate(args, sample, public, package)
    print(f"elapsed_sec={time.perf_counter() - started:.1f}")


if __name__ == "__main__":
    main()
