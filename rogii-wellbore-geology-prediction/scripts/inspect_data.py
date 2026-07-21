#!/usr/bin/env python3
"""ROGIIコンペデータの構造を小さく要約する。"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def is_horizontal(path: Path) -> bool:
    return "horizontal_well" in path.stem.lower()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args()

    root = args.data_dir
    csvs = sorted(root.rglob("*.csv"))
    print(f"data_dir={root.resolve()}")
    print(f"csv_files={len(csvs)}")
    if not csvs:
        raise SystemExit("CSVがありません。Kaggleから data/raw に取得してください。")

    for split in ("train", "test"):
        files = [p for p in csvs if split in p.parts and is_horizontal(p)]
        if not files:
            continue
        print(f"[{split}] horizontal_wells={len(files)}")
        rows = []
        columns: set[str] = set()
        for path in files:
            df = pd.read_csv(path)
            columns.update(map(str, df.columns))
            rows.append(
                {
                    "well": path.stem.split("__horizontal_well")[0],
                    "rows": len(df),
                    "columns": len(df.columns),
                    "tvt_input_known": int(df.get("TVT_input", pd.Series(dtype=float)).notna().sum()),
                    "tvt_known": int(df.get("TVT", pd.Series(dtype=float)).notna().sum()),
                    "gr_missing": int(df.get("GR", pd.Series(dtype=float)).isna().sum()),
                }
            )
        summary = pd.DataFrame(rows)
        print(f"  total_rows={summary['rows'].sum()}")
        print(f"  columns={sorted(columns)}")
        print(summary.describe(include="all").to_string())
        print("  first_wells:")
        print(summary.head(5).to_string(index=False))


if __name__ == "__main__":
    main()
