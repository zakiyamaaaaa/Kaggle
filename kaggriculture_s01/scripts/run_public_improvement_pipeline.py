#!/usr/bin/env python3
"""Run the leakage-safe September public-data improvement pipeline.

The pipeline is deliberately offline-first.  It creates a chronological
train/validation/test split, audits the feature boundary, trains a small
behavior-cloning model and a state/action-conditioned value model, and emits
an offline candidate-reranking report.  The reranking uplift is explicitly
marked model-based: logged public episodes do not identify unseen actions.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import balanced_accuracy_score, top_k_accuracy_score


META_COLUMNS = {
    "source_date", "episode_id", "seed", "seat", "step", "day", "hour",
    "agent", "opponent_agent", "chosen_action_json", "status",
}
OUTCOME_COLUMNS = {
    "final_reward", "opponent_final_reward", "reward_difference", "win", "terminal_score",
}
ACTION_COLUMNS = {"farmer_action", "market_op_count", "market_has_sell", "market_has_buy"}
REQUIRED_COLUMNS = {
    "source_date", "episode_id", "seat", "step", "day", "hour", "chosen_action_json",
    "final_reward", "opponent_final_reward", "reward_difference", "win",
}


def _parse_action(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _derive(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    actions = result["chosen_action_json"].map(_parse_action)
    result["farmer_action"] = actions.map(
        lambda action: str((action.get("farmer") or ["NONE"])[0])
        if isinstance(action.get("farmer"), list) and action.get("farmer")
        else "NONE"
    )
    result["market_op_count"] = actions.map(
        lambda action: sum(1 for item in (action.get("market") or []) if isinstance(item, list) and item)
    ).astype("int16")
    result["market_has_sell"] = actions.map(
        lambda action: int(any(isinstance(item, list) and item and item[0] == "SELL"
                               for item in (action.get("market") or [])))
    ).astype("int8")
    result["market_has_buy"] = actions.map(
        lambda action: int(any(isinstance(item, list) and item and str(item[0]).startswith("BUY")
                               for item in (action.get("market") or [])))
    ).astype("int8")
    result["phase"] = (result["day"] // 10).astype("int8")
    result["hours_remaining"] = (720 - result["step"]).clip(lower=0).astype("int16")
    result["market_price_spread"] = result["market_max_price"] - result["market_min_price"]
    result["own_inventory_share"] = result["own_inventory_total"] / (
        result["own_inventory_total"] + result["market_inventory_total"] + 1.0
    )
    result["own_cash_share"] = result["own_money"] / (
        result["own_money"] + result["opponent_money"] + 1.0
    )
    result["inventory_advantage"] = result["own_inventory_total"] - result["opponent_inventory_total"]
    result["terminal_score"] = np.where(
        result["final_reward"] > result["opponent_final_reward"], 1.0,
        np.where(result["final_reward"] < result["opponent_final_reward"], 0.0, 0.5),
    )
    return result


def _load_date(path: Path, sample_every: int, cap: int, seed: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = pd.read_parquet(path)
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"{path} missing columns: {missing}")
    derived = _derive(frame)
    sampled = derived.loc[derived["step"] % sample_every == 0].copy()
    if len(sampled) > cap:
        sampled = sampled.sample(cap, random_state=seed).sort_values(["episode_id", "seat", "step"])
    audit = {
        "date": str(path.parent.name),
        "rows": int(len(frame)),
        "episodes": int(frame["episode_id"].nunique()),
        "sampled_rows": int(len(sampled)),
        "completed_episodes": int(frame[["episode_id", "seat"]].drop_duplicates().shape[0] / 2),
        "nan_count": int(frame.isna().sum().sum()),
        "inf_count": int(np.isinf(frame.select_dtypes(include=[np.number])).sum().sum()),
    }
    return sampled, audit


def _state_features(frame: pd.DataFrame) -> list[str]:
    excluded = META_COLUMNS | OUTCOME_COLUMNS | ACTION_COLUMNS
    return [
        col for col in frame.columns
        if col not in excluded and pd.api.types.is_numeric_dtype(frame[col])
    ]


def _metrics(target: Iterable[float], prediction: Iterable[float]) -> dict[str, float | int]:
    y = np.asarray(list(target), dtype=float)
    p = np.clip(np.asarray(list(prediction), dtype=float), 0.0, 1.0)
    error = y - p
    brier = float(np.mean(error * error)) if len(y) else float("nan")
    return {
        "n": int(len(y)),
        "brier": brier,
        "rmse": float(math.sqrt(brier)) if math.isfinite(brier) else float("nan"),
        "mae": float(np.mean(np.abs(error))) if len(y) else float("nan"),
    }


def _action_metrics(model: HistGradientBoostingClassifier, frame: pd.DataFrame,
                    features: list[str]) -> dict[str, Any]:
    y = frame["farmer_action"].to_numpy()
    probabilities = model.predict_proba(frame[features].astype(float))
    predicted = model.classes_[np.argmax(probabilities, axis=1)]
    labels = list(model.classes_)
    k = min(3, len(labels))
    topk = float(top_k_accuracy_score(y, probabilities, k=k, labels=labels)) if k >= 2 else float("nan")
    per_phase = (
        frame.assign(correct=predicted == y)
        .groupby("phase", sort=True)["correct"]
        .agg(["count", "mean"])
        .reset_index()
        .rename(columns={"mean": "accuracy"})
        .to_dict(orient="records")
    )
    return {
        "rows": int(len(frame)),
        "accuracy": float(np.mean(predicted == y)),
        "balanced_accuracy": float(balanced_accuracy_score(y, predicted)),
        "top3_accuracy": topk,
        "labels": labels,
        "accuracy_by_phase": per_phase,
    }


def _action_slug(index: int) -> str:
    return f"action_{index:03d}"


def _add_action_one_hot(frame: pd.DataFrame, labels: list[str], action_col: str = "farmer_action") -> pd.DataFrame:
    result = frame.copy()
    index = {label: i for i, label in enumerate(labels)}
    encoded = result[action_col].map(index).fillna(-1).astype(int)
    for i in range(len(labels)):
        result[_action_slug(i)] = (encoded == i).astype("int8")
    return result


def _evaluate_action_value(model: HistGradientBoostingRegressor, frame: pd.DataFrame,
                           state_features: list[str], labels: list[str], action_model: HistGradientBoostingClassifier,
                           sample_limit: int = 4000) -> dict[str, Any]:
    if len(frame) > sample_limit:
        frame = frame.sample(sample_limit, random_state=20260923)
    base = frame.copy()
    action_cols = [_action_slug(i) for i in range(len(labels))]
    feature_columns = state_features + action_cols
    logged = _add_action_one_hot(base, labels)
    logged_prediction = model.predict(logged[feature_columns].astype(float))
    probabilities = action_model.predict_proba(base[state_features].astype(float))
    top_k = min(3, len(labels))
    top_indices = np.argsort(probabilities, axis=1)[:, -top_k:][:, ::-1]
    scores = []
    for row_index, candidate_indices in enumerate(top_indices):
        candidates = []
        for action_index in candidate_indices:
            row = base.iloc[[row_index]].copy()
            row["farmer_action"] = labels[action_index]
            row = _add_action_one_hot(row, labels)
            candidates.append(float(model.predict(row[feature_columns].astype(float))[0]))
        scores.append(candidates)
    best_prediction = np.asarray([max(values) for values in scores], dtype=float)
    uplift = best_prediction - logged_prediction
    return {
        "rows": int(len(base)),
        "candidate_k": int(top_k),
        "mean_logged_predicted_score": float(np.mean(logged_prediction)),
        "mean_best_candidate_predicted_score": float(np.mean(best_prediction)),
        "mean_predicted_uplift": float(np.mean(uplift)),
        "positive_uplift_rate": float(np.mean(uplift > 1e-9)),
        "max_predicted_uplift": float(np.max(uplift)) if len(uplift) else 0.0,
        "interpretation": "model_based_off_policy_only; unseen_action uplift is not causal",
    }


def _write_markdown(output: Path, report: dict[str, Any]) -> None:
    action = report["behavior_model"]
    value = report["state_value_model"]
    rerank = report["candidate_reranking"]
    lines = [
        "# September public-data improvement pipeline",
        "",
        "## Evaluation contract",
        f"- Train: {', '.join(report['splits']['train_dates'])}",
        f"- Validation: {', '.join(report['splits']['validation_dates'])}",
        f"- Test: {', '.join(report['splits']['test_dates'])}",
        f"- Temporal leakage audit: `{report['leakage_audit']['passed']}`",
        "- Outcomes and action labels are excluded from state features.",
        "",
        "## Held-out results",
        f"- Behavior cloning test accuracy: {action['test']['accuracy']:.4f}",
        f"- Behavior cloning test top-3 accuracy: {action['test']['top3_accuracy']:.4f}",
        f"- State-value test Brier: {value['test']['brier']:.6f}",
        f"- Constant baseline test Brier: {value['test_baseline']['brier']:.6f}",
        f"- Candidate reranking predicted uplift: {rerank['mean_predicted_uplift']:.6f}",
        "",
        "## Interpretation",
        "The action model is a proposal policy, not a complete game policy.",
        "The candidate reranker is an offline model-based diagnostic; public logs do not identify unseen actions causally.",
        "Final adoption requires the paired local Arena report in `arena/`.",
    ]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(input_root: Path, manifest: Path, output: Path, sample_every: int, per_date_cap: int,
        max_iter: int) -> dict[str, Any]:
    dates = sorted(
        path.name for path in input_root.glob("2026-09-*")
        if (path / "public_transitions.parquet").is_file()
    )
    if len(dates) < 21:
        raise ValueError(f"expected the 21 September dates, found {len(dates)}")
    train_dates = [date for date in dates if date <= "2026-09-14"]
    validation_dates = [date for date in dates if "2026-09-15" <= date <= "2026-09-17"]
    test_dates = [date for date in dates if date >= "2026-09-18"]
    if not train_dates or not validation_dates or not test_dates:
        raise ValueError("chronological split is empty")

    output.mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame] = {}
    audits: list[dict[str, Any]] = []
    for index, date in enumerate(dates):
        frame, audit = _load_date(
            input_root / date / "public_transitions.parquet",
            sample_every, per_date_cap, 20260923 + index,
        )
        frames[date] = frame
        audits.append(audit)
        frame.to_parquet(output / f"sample_{date}.parquet", index=False, compression="zstd")

    all_sample = pd.concat(frames.values(), ignore_index=True)
    state_features = _state_features(all_sample)
    leakage = {
        "outcome_columns": sorted(OUTCOME_COLUMNS),
        "action_columns": sorted(ACTION_COLUMNS),
        "state_features": state_features,
        "outcome_in_state_features": sorted(set(state_features) & OUTCOME_COLUMNS),
        "action_in_state_features": sorted(set(state_features) & ACTION_COLUMNS),
        "passed": not (set(state_features) & OUTCOME_COLUMNS or set(state_features) & ACTION_COLUMNS),
        "train_latest_date": max(train_dates),
        "validation_earliest_date": min(validation_dates),
        "validation_latest_date": max(validation_dates),
        "test_earliest_date": min(test_dates),
    }
    if not leakage["passed"]:
        raise AssertionError(f"feature leakage detected: {leakage}")

    train = pd.concat([frames[date] for date in train_dates], ignore_index=True)
    validation = pd.concat([frames[date] for date in validation_dates], ignore_index=True)
    test = pd.concat([frames[date] for date in test_dates], ignore_index=True)
    train.to_parquet(output / "train_sample.parquet", index=False, compression="zstd")
    validation.to_parquet(output / "validation_sample.parquet", index=False, compression="zstd")
    test.to_parquet(output / "test_sample.parquet", index=False, compression="zstd")

    action_model = HistGradientBoostingClassifier(
        learning_rate=0.08, max_iter=max_iter, max_leaf_nodes=31,
        min_samples_leaf=32, l2_regularization=1.0, random_state=20260923,
    )
    action_model.fit(train[state_features].astype(float), train["farmer_action"])
    behavior = {
        "train": _action_metrics(action_model, train, state_features),
        "validation": _action_metrics(action_model, validation, state_features),
        "test": _action_metrics(action_model, test, state_features),
        "model_type": "HistGradientBoostingClassifier",
        "features": state_features,
    }
    behavior_dir = output / "behavior_model"
    behavior_dir.mkdir(exist_ok=True)
    joblib.dump({"model": action_model, "feature_columns": state_features,
                 "target": "farmer_action", "labels": list(action_model.classes_)},
                behavior_dir / "model.joblib")

    value_model = HistGradientBoostingRegressor(
        learning_rate=0.08, max_iter=max_iter, max_leaf_nodes=31,
        min_samples_leaf=32, l2_regularization=1.0, random_state=20260923,
    )
    value_model.fit(train[state_features].astype(float), train["terminal_score"])
    train_mean = float(train["terminal_score"].mean())
    value = {"features": state_features, "model_type": "HistGradientBoostingRegressor"}
    for name, frame in (("validation", validation), ("test", test)):
        pred = value_model.predict(frame[state_features].astype(float))
        baseline = np.full(len(frame), train_mean)
        value[name] = _metrics(frame["terminal_score"], pred)
        value[f"{name}_baseline"] = _metrics(frame["terminal_score"], baseline)
        last = frame.sort_values(["episode_id", "seat", "step"]).groupby(
            ["episode_id", "seat"], sort=False
        ).tail(1)
        value[f"{name}_last_state"] = _metrics(
            last["terminal_score"], value_model.predict(last[state_features].astype(float))
        )
    value["train_mean"] = train_mean
    value_dir = output / "state_value_model"
    value_dir.mkdir(exist_ok=True)
    joblib.dump({"model": value_model, "feature_columns": state_features,
                 "target": "terminal_score"}, value_dir / "model.joblib")

    labels = list(action_model.classes_)
    action_value_train = _add_action_one_hot(train, labels)
    action_value_features = state_features + [_action_slug(i) for i in range(len(labels))]
    action_value_model = HistGradientBoostingRegressor(
        learning_rate=0.08, max_iter=max_iter, max_leaf_nodes=31,
        min_samples_leaf=32, l2_regularization=1.0, random_state=20260923,
    )
    action_value_model.fit(action_value_train[action_value_features].astype(float),
                           action_value_train["terminal_score"])
    action_value_dir = output / "action_value_model"
    action_value_dir.mkdir(exist_ok=True)
    joblib.dump({"model": action_value_model, "state_features": state_features,
                 "feature_columns": action_value_features, "labels": labels,
                 "target": "terminal_score"}, action_value_dir / "model.joblib")
    rerank = _evaluate_action_value(action_value_model, test, state_features, labels, action_model)

    report: dict[str, Any] = {
        "format": "kaggriculture-public-improvement-pipeline-v1",
        "source": str(input_root),
        "manifest": str(manifest),
        "sample_every": sample_every,
        "per_date_cap": per_date_cap,
        "dates": dates,
        "splits": {"train_dates": train_dates, "validation_dates": validation_dates, "test_dates": test_dates},
        "rows": {"all_sampled": int(len(all_sample)), "train": int(len(train)),
                 "validation": int(len(validation)), "test": int(len(test))},
        "date_audits": audits,
        "leakage_audit": leakage,
        "behavior_model": behavior,
        "state_value_model": value,
        "candidate_reranking": rerank,
        "storage_policy": {
            "raw_data_is_read_only": True,
            "intermediate_samples_are_zstd_parquet": True,
            "no_raw_data_deleted": True,
        },
        "limitations": [
            "Public episodes are logged-policy data and do not provide causal labels for unseen actions.",
            "The action-conditioned reranker is a model-based diagnostic until validated in the local Arena.",
            "The public agent population is not a randomized opponent sample.",
        ],
    }
    (output / "pipeline_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    _write_markdown(output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-every", type=int, default=12)
    parser.add_argument("--per-date-cap", type=int, default=12000)
    parser.add_argument("--max-iter", type=int, default=80)
    args = parser.parse_args()
    if args.sample_every < 1 or args.per_date_cap < 1 or args.max_iter < 1:
        raise SystemExit("sample-every, per-date-cap and max-iter must be positive")
    print(json.dumps(run(args.input_root, args.manifest, args.output,
                         args.sample_every, args.per_date_cap, args.max_iter),
                     ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
