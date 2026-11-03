#!/usr/bin/env python3
"""Convert Kaggriculture public episode JSON files to leakage-safe Parquet.

The public daily datasets contain one JSON object per episode.  This converter
keeps one row per player and decision step, extracting only the acting
player's observation and selected action.  Opponent-private state and final
outcomes are not features; outcomes are retained only as labels for offline
analysis.  The output is intentionally separate from the paired Arena dataset
because public episodes do not provide seat-swapped pairs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from kaggriculture_agent.local_arena import _trajectory_features


def _safe_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _episode_rows(path: Path, source_date: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    steps = payload.get("steps") or []
    rewards = payload.get("rewards") or [None, None]
    statuses = payload.get("statuses") or [None, None]
    episode_id = int(payload.get("info", {}).get("EpisodeId", path.stem))
    seed = payload.get("info", {}).get("seed")
    agents = payload.get("info", {}).get("Agents") or []
    names = []
    for agent in agents:
        names.append(str(agent.get("Name", "unknown")) if isinstance(agent, dict) else str(agent))
    rows: list[dict[str, Any]] = []
    for step_index, step in enumerate(steps):
        if not isinstance(step, list):
            continue
        for seat, actor in enumerate(step[:2]):
            if not isinstance(actor, dict):
                continue
            observation = actor.get("observation") or {}
            action = actor.get("action")
            features = _trajectory_features(observation, seat)
            own_reward = rewards[seat] if seat < len(rewards) else None
            other_reward = rewards[1 - seat] if (1 - seat) < len(rewards) else None
            row: dict[str, Any] = {
                "source_date": source_date,
                "episode_id": episode_id,
                "seed": int(seed) if seed is not None else -1,
                "seat": seat,
                "step": int(observation.get("step", step_index)),
                "day": int(observation.get("day", 0)),
                "hour": int(observation.get("hour", 0)),
                "agent": names[seat] if seat < len(names) else "unknown",
                "opponent_agent": names[1 - seat] if (1 - seat) < len(names) else "unknown",
                "chosen_action_json": _safe_json(action),
                "final_reward": float(own_reward) if own_reward is not None else None,
                "opponent_final_reward": float(other_reward) if other_reward is not None else None,
                "reward_difference": (float(own_reward) - float(other_reward))
                if own_reward is not None and other_reward is not None
                else None,
                "win": bool(own_reward > other_reward)
                if own_reward is not None and other_reward is not None
                else None,
                "status": str(actor.get("status", "")),
            }
            row.update(features)
            rows.append(row)
    summary = {
        "source_file": path.name,
        "source_date": source_date,
        "episode_id": episode_id,
        "seed": seed,
        "steps": len(steps),
        "statuses": statuses,
        "rewards": rewards,
        "agents": names,
        "rows": len(rows),
    }
    return rows, summary


def convert(files: Iterable[Path], source_date: str, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []
    for path in files:
        current, summary = _episode_rows(path, source_date)
        rows.extend(current)
        episodes.append(summary)
    if not rows:
        raise ValueError("no episode rows found")
    frame = pd.DataFrame(rows).sort_values(["episode_id", "seat", "step"]).reset_index(drop=True)
    frame.to_parquet(output / "public_transitions.parquet", index=False, compression="zstd")
    pd.DataFrame(episodes).to_parquet(output / "public_episodes.parquet", index=False, compression="zstd")
    audit = {
        "format": "kaggriculture-public-dataset-v1",
        "source_date": source_date,
        "episodes": len(episodes),
        "transition_rows": len(frame),
        "unique_episode_ids": int(frame["episode_id"].nunique()),
        "unique_seeds": int(frame["seed"].nunique()),
        "rows_per_episode_seat": sorted(frame.groupby(["episode_id", "seat"]).size().unique().tolist()),
        "completed_episodes": int((pd.DataFrame(episodes)["statuses"].apply(lambda x: x == ["DONE", "DONE"])).sum()),
        "feature_columns": [c for c in frame.columns if c not in {
            "source_date", "episode_id", "seed", "seat", "step", "day", "hour",
            "agent", "opponent_agent", "chosen_action_json", "final_reward",
            "opponent_final_reward", "reward_difference", "win", "status",
        }],
        "outcome_columns_excluded_from_features": [
            "final_reward", "opponent_final_reward", "reward_difference", "win",
        ],
        "opponent_private_state_excluded": True,
    }
    (output / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(convert(args.input, args.date, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
