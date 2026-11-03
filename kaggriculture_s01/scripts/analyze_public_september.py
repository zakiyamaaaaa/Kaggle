#!/usr/bin/env python3
"""Aggregate the converted public Kaggriculture episodes for September."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


def market_summary(value: str) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    try:
        action = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False, (), ()
    market = action.get("market") if isinstance(action, dict) else None
    if not isinstance(market, list):
        return False, (), ()
    items: list[str] = []
    ops: list[str] = []
    for order in market:
        if not isinstance(order, list) or not order:
            continue
        ops.append(str(order[0]))
        if str(order[0]) == "SELL" and len(order) > 1:
            items.append(str(order[1]))
    return "SELL" in ops, tuple(items), tuple(sorted(set(ops)))


def analyze(input_root: Path, manifest_path: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    manifest = {row["date"]: row for row in csv.DictReader(manifest_path.open())}
    dates = sorted(
        path.name for path in input_root.glob("2026-09-*")
        if (path / "public_transitions.parquet").is_file()
    )
    if not dates:
        raise ValueError("no converted September datasets found")
    daily: list[dict[str, Any]] = []
    late: list[dict[str, Any]] = []
    agent_frames: list[pd.DataFrame] = []
    for date in dates:
        path = input_root / date / "public_transitions.parquet"
        columns = [
            "episode_id", "seat", "day", "agent", "chosen_action_json",
            "final_reward", "opponent_final_reward", "reward_difference", "win",
        ]
        frame = pd.read_parquet(path, columns=columns)
        actor = frame.drop_duplicates(["episode_id", "seat"]).copy()
        row = {
            "date": date,
            "episodes": int(actor["episode_id"].nunique()),
            "transition_rows": int(len(frame)),
            "mean_reward": float(actor["final_reward"].mean()),
            "median_reward": float(actor["final_reward"].median()),
            "mean_margin": float(actor["reward_difference"].mean()),
            "win_rate": float(actor["win"].mean()),
            "draw_rate": float((actor["reward_difference"] == 0).mean()),
            "manifest_top_avg_score": float(manifest.get(date, {}).get("top_avg_score", 0)),
            "manifest_median_avg_score": float(manifest.get(date, {}).get("median_avg_score", 0)),
        }
        daily.append(row)
        agent_frames.append(
            actor.groupby("agent", dropna=False).agg(
                episodes=("episode_id", "nunique"),
                mean_reward=("final_reward", "mean"),
                mean_margin=("reward_difference", "mean"),
                win_rate=("win", "mean"),
            ).reset_index().assign(date=date)
        )
        q10, q90 = actor["final_reward"].quantile([0.10, 0.90]).tolist()
        actor["tier"] = "middle80"
        actor.loc[actor["final_reward"] <= q10, "tier"] = "bottom10"
        actor.loc[actor["final_reward"] >= q90, "tier"] = "top10"
        frame = frame.merge(actor[["episode_id", "seat", "tier"]], on=["episode_id", "seat"], how="left")
        late_frame = frame[frame["day"] >= 25].copy()
        parsed = late_frame["chosen_action_json"].map(market_summary)
        late_frame["sell"] = parsed.map(lambda x: x[0])
        late_frame["sell_items"] = parsed.map(lambda x: x[1])
        late_frame["ops"] = parsed.map(lambda x: x[2])
        for tier, group in late_frame.groupby("tier", sort=False):
            for day, day_group in group.groupby("day", sort=True):
                item_counts = Counter(item for items in day_group["sell_items"] for item in items)
                op_counts = Counter(op for ops in day_group["ops"] for op in ops)
                total = len(day_group)
                late.append(
                    {
                        "date": date,
                        "tier": tier,
                        "day": int(day),
                        "rows": total,
                        "sell_rate": float(day_group["sell"].mean()),
                        "invalid_rate": float(day_group["ops"].map(lambda ops: "INVALID" in ops).mean()),
                        "sell_items": dict(item_counts.most_common()),
                        "operation_rows": dict(op_counts),
                    }
                )
    daily_frame = pd.DataFrame(daily).sort_values("date")
    agent_frame = pd.concat(agent_frames, ignore_index=True)
    agent_summary = (
        agent_frame.groupby("agent", dropna=False)
        .agg(
            episodes=("episodes", "sum"),
            mean_reward=("mean_reward", "mean"),
            mean_margin=("mean_margin", "mean"),
            mean_daily_win_rate=("win_rate", "mean"),
            active_days=("date", "nunique"),
        )
        .sort_values(["mean_daily_win_rate", "episodes"], ascending=False)
        .reset_index()
    )
    daily_frame.to_csv(output / "daily_summary.csv", index=False)
    agent_summary.to_csv(output / "agent_summary.csv", index=False)
    pd.DataFrame(late).to_csv(output / "late_strategy_summary.csv", index=False)
    top_agents = agent_summary.loc[agent_summary["episodes"] >= 20].head(15).to_dict(orient="records")
    payload: dict[str, Any] = {
        "format": "kaggriculture-public-september-analysis-v1",
        "dates": dates,
        "days": len(dates),
        "episodes": int(daily_frame["episodes"].sum()),
        "transition_rows": int(daily_frame["transition_rows"].sum()),
        "mean_daily_reward": float(daily_frame["mean_reward"].mean()),
        "mean_daily_win_rate": float(daily_frame["win_rate"].mean()),
        "first_date": dates[0],
        "last_date": dates[-1],
        "top_agent_summary_min_20_episodes": top_agents,
        "late_strategy_rows": len(late),
        "outputs": ["daily_summary.csv", "agent_summary.csv", "late_strategy_summary.csv"],
        "notes": [
            "Public episodes are not seat-swapped paired experiments.",
            "Late strategy tiers are defined separately within each date by actor final reward.",
            "Final outcomes are used only for grouping and reporting, not state features.",
        ],
    }
    (output / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(analyze(args.input_root, args.manifest, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
