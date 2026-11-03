#!/usr/bin/env python3
"""Build a compact, state-conditioned action-bundle proposal index.

The index stores complete actions observed in the public logs.  It is used as
a proposal library only; it does not assign a counterfactual reward to an
unseen action.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


def _parse_action(value: Any) -> dict[str, Any] | None:
    try:
        action = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return action if isinstance(action, dict) else None


def build(samples_root: Path, report_path: Path, output: Path, per_group: int = 48) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    features = list(report["leakage_audit"]["state_features"])
    labels = list(report["behavior_model"]["test"]["labels"])
    if per_group < 1:
        raise ValueError("per_group must be positive")
    train = pd.read_parquet(samples_root / "train_sample.parquet", columns=features)
    means = train.mean(numeric_only=True).reindex(features).fillna(0.0)
    stds = train.std(numeric_only=True).reindex(features).replace(0.0, 1.0).fillna(1.0)
    groups: dict[str, list[dict[str, Any]]] = {}
    source_rows = 0
    for path in sorted(samples_root.glob("sample_2026-09-*.parquet")):
        columns = list(dict.fromkeys(features + ["phase", "farmer_action", "chosen_action_json"]))
        frame = pd.read_parquet(path, columns=columns)
        source_rows += len(frame)
        for (phase, farmer_action), group in frame.groupby(["phase", "farmer_action"], sort=True):
            if str(farmer_action) not in labels:
                continue
            parsed = group["chosen_action_json"].map(_parse_action)
            valid = group.loc[parsed.notna()].copy()
            if valid.empty:
                continue
            valid["_action"] = parsed.loc[valid.index]
            # Prefer complete no-secondary-op bundles for the first safe policy.
            valid["_safe_empty_bundle"] = valid["_action"].map(
                lambda action: isinstance(action.get("hands"), list)
                and isinstance(action.get("market"), list)
                and not action.get("hands")
                and not action.get("market")
            )
            valid = valid.sort_values(["_safe_empty_bundle"], ascending=False)
            key = f"{int(phase)}|{farmer_action}"
            current = groups.setdefault(key, [])
            for _, row in valid.head(per_group - len(current)).iterrows():
                action = row["_action"]
                current.append({
                    "phase": int(phase),
                    "farmer_action": str(farmer_action),
                    "action": action,
                    "features": [float(row[column]) for column in features],
                    "safe_empty_bundle": bool(row["_safe_empty_bundle"]),
                    "source_date": path.stem.replace("sample_", ""),
                })
            if len(current) > per_group:
                groups[key] = current[:per_group]
    payload = {
        "format": "kaggriculture-public-proposal-index-v1",
        "source": str(samples_root),
        "state_features": features,
        "labels": labels,
        "means": [float(means[column]) for column in features],
        "stds": [float(stds[column]) for column in features],
        "per_group": per_group,
        "source_rows": source_rows,
        "groups": groups,
        "notes": [
            "Templates are complete logged action bundles from public episodes.",
            "The initial hybrid policy accepts only empty-hands/empty-market bundles when the incumbent also has no secondary orders.",
            "No terminal outcome is used to rank a proposal.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "format": payload["format"],
        "source_rows": source_rows,
        "groups": len(groups),
        "templates": sum(len(value) for value in groups.values()),
        "safe_empty_templates": sum(
            int(template["safe_empty_bundle"])
            for group in groups.values()
            for template in group
        ),
        "output": str(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-group", type=int, default=48)
    args = parser.parse_args()
    print(json.dumps(build(args.samples_root, args.report, args.output, args.per_group), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
