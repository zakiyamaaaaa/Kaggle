#!/usr/bin/env python3
"""TVT_input末尾の線形外挿による提出用ベースライン。"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def find_column(df: pd.DataFrame, *names: str) -> str | None:
    normalized = {str(c).strip().lower(): str(c) for c in df.columns}
    for name in names:
        if name.lower() in normalized:
            return normalized[name.lower()]
    return None


def well_name(path: Path) -> str:
    stem = path.stem
    marker = "__horizontal_well"
    if marker in stem.lower():
        pos = stem.lower().index(marker)
        return stem[:pos]
    return stem.split("__", 1)[0]


def horizontal_files(root: Path, split: str) -> list[Path]:
    base = root / split
    if not base.exists():
        base = root
    files = sorted(p for p in base.rglob("*.csv") if "horizontal_well" in p.stem.lower())
    if files:
        return files
    # 小さなサンプルや名前違いにも対応する。
    result = []
    for path in sorted(base.rglob("*.csv")):
        try:
            cols = pd.read_csv(path, nrows=0).columns
        except Exception:
            continue
        if find_column(pd.DataFrame(columns=cols), "MD") and (
            find_column(pd.DataFrame(columns=cols), "TVT_input")
            or find_column(pd.DataFrame(columns=cols), "TVT")
        ):
            result.append(path)
    return result


def fit_line(x: np.ndarray, y: np.ndarray, tail_points: int) -> tuple[float, float]:
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]
    if len(x) == 0:
        return 0.0, 0.0
    if len(x) == 1 or np.ptp(x) == 0:
        return 0.0, float(y[-1])
    tail = min(max(tail_points, 2), len(x))
    slope, intercept = np.polyfit(x[-tail:], y[-tail:], deg=1)
    return float(slope), float(intercept)


def predict_unknown(df: pd.DataFrame, tail_points: int, method: str = "last") -> pd.DataFrame:
    work = df.reset_index(drop=True).copy()
    md_col = find_column(work, "MD")
    input_col = find_column(work, "TVT_input")
    target_col = find_column(work, "TVT")
    if input_col is None and target_col is None:
        raise ValueError("TVT_input または TVT 列が見つかりません。")
    known_col = input_col or target_col
    assert known_col is not None
    if md_col is None:
        x = np.arange(len(work), dtype=float)
    else:
        x = pd.to_numeric(work[md_col], errors="coerce").to_numpy(dtype=float)
        x = np.where(np.isfinite(x), x, np.arange(len(work), dtype=float))
    known = pd.to_numeric(work[known_col], errors="coerce").to_numpy(dtype=float)
    known_mask = np.isfinite(known)
    unknown_mask = ~known_mask
    if not unknown_mask.any():
        return pd.DataFrame(columns=["row_index", "tvt_pred"])
    known_values = known[known_mask]
    if method == "last":
        pred = np.full(unknown_mask.sum(), known_values[-1], dtype=float)
    else:
        slope, intercept = fit_line(x[known_mask], known_values, tail_points)
        pred = slope * x[unknown_mask] + intercept
    return pd.DataFrame({"row_index": np.flatnonzero(unknown_mask), "tvt_pred": pred})


def validation_rmse(files: list[Path], tail_points: int, holdout_fraction: float, method: str) -> tuple[float, int]:
    errors: list[np.ndarray] = []
    for path in files:
        df = pd.read_csv(path).reset_index(drop=True)
        input_col = find_column(df, "TVT_input")
        target_col = find_column(df, "TVT")
        md_col = find_column(df, "MD")
        if not input_col or not target_col:
            continue
        given = pd.to_numeric(df[input_col], errors="coerce").to_numpy(dtype=float)
        truth = pd.to_numeric(df[target_col], errors="coerce").to_numpy(dtype=float)
        known = np.flatnonzero(np.isfinite(given) & np.isfinite(truth))
        if len(known) < 5:
            continue
        n_holdout = max(1, int(len(known) * holdout_fraction))
        train_idx, valid_idx = known[:-n_holdout], known[-n_holdout:]
        x = (pd.to_numeric(df[md_col], errors="coerce").to_numpy(dtype=float)
             if md_col else np.arange(len(df), dtype=float))
        x = np.where(np.isfinite(x), x, np.arange(len(df), dtype=float))
        if method == "last":
            pred = np.full(len(valid_idx), given[train_idx[-1]], dtype=float)
        else:
            slope, intercept = fit_line(x[train_idx], given[train_idx], tail_points)
            pred = slope * x[valid_idx] + intercept
        errors.append(truth[valid_idx] - pred)
    if not errors:
        return float("nan"), 0
    flat = np.concatenate(errors)
    return float(np.sqrt(np.mean(flat**2))), int(len(flat))


def evaluation_zone_rmse(files: list[Path], tail_points: int, method: str) -> tuple[float, int]:
    """学習データのTVT_input欠損区間を、実際の評価区間に見立てて採点する。"""
    errors: list[np.ndarray] = []
    for path in files:
        df = pd.read_csv(path).reset_index(drop=True)
        input_col = find_column(df, "TVT_input")
        target_col = find_column(df, "TVT")
        md_col = find_column(df, "MD")
        if not input_col or not target_col:
            continue
        given = pd.to_numeric(df[input_col], errors="coerce").to_numpy(dtype=float)
        truth = pd.to_numeric(df[target_col], errors="coerce").to_numpy(dtype=float)
        known_idx = np.flatnonzero(np.isfinite(given))
        eval_idx = np.flatnonzero(~np.isfinite(given) & np.isfinite(truth))
        if len(known_idx) < 2 or len(eval_idx) == 0:
            continue
        x = (pd.to_numeric(df[md_col], errors="coerce").to_numpy(dtype=float)
             if md_col else np.arange(len(df), dtype=float))
        x = np.where(np.isfinite(x), x, np.arange(len(df), dtype=float))
        if method == "last":
            pred = np.full(len(eval_idx), given[known_idx[-1]], dtype=float)
        else:
            slope, intercept = fit_line(x[known_idx], given[known_idx], tail_points)
            pred = slope * x[eval_idx] + intercept
        errors.append(truth[eval_idx] - pred)
    if not errors:
        return float("nan"), 0
    flat = np.concatenate(errors)
    return float(np.sqrt(np.mean(flat**2))), int(len(flat))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--submission-path", type=Path, default=Path("outputs/submissions/linear_extrapolation.csv"))
    parser.add_argument("--tail-points", type=int, default=100)
    parser.add_argument("--method", choices=["last", "linear"], default="last")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--holdout-fraction", type=float, default=0.2)
    args = parser.parse_args()

    train = horizontal_files(args.data_dir, "train")
    test = horizontal_files(args.data_dir, "test")
    if not test:
        raise SystemExit("test/ の水平坑井CSVが見つかりません。")
    if args.validate and train:
        score, n = evaluation_zone_rmse(train, args.tail_points, args.method)
        print(f"train_eval_zone_rmse={score:.6f} method={args.method} rows={n}")
        holdout_score, holdout_n = validation_rmse(train, args.tail_points, args.holdout_fraction, args.method)
        print(f"known_tail_holdout_rmse={holdout_score:.6f} rows={holdout_n}")

    predictions: dict[str, float] = {}
    for path in test:
        df = pd.read_csv(path)
        pred = predict_unknown(df, args.tail_points, args.method)
        name = well_name(path)
        for row in pred.itertuples(index=False):
            predictions[f"{name}_{int(row.row_index)}"] = float(row.tvt_pred)

    sample_path = args.data_dir / "sample_submission.csv"
    if sample_path.exists():
        sample = pd.read_csv(sample_path)
        id_col = find_column(sample, "id")
        if id_col is None:
            raise ValueError("sample_submission.csv に id 列がありません。")
        tvt_col = find_column(sample, "tvt") or "tvt"
        out = sample[[id_col]].copy()
        out[tvt_col] = out[id_col].map(predictions)
        missing = int(out[tvt_col].isna().sum())
        if missing:
            raise ValueError(f"提出IDの予測が {missing} 行不足しています。ファイル名/行番号の対応を確認してください。")
        out.columns = ["id", "tvt"]
    else:
        out = pd.DataFrame({"id": list(predictions), "tvt": list(predictions.values())})

    args.submission_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.submission_path, index=False)
    print(f"test_wells={len(test)} predictions={len(out)}")
    print(f"submission={args.submission_path.resolve()}")
    print(out.head().to_string(index=False))


if __name__ == "__main__":
    main()
