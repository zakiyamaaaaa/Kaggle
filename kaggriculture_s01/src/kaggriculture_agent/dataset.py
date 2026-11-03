"""Build and audit versioned common trajectory datasets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

TABLES = ("transitions", "episodes", "pairs")


class DatasetError(ValueError):
    """Raised when trajectory inputs cannot be combined safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _duplicate_count(table: pa.Table, columns: Sequence[str]) -> int:
    frame = table.select(columns).to_pandas()
    return int(frame.duplicated(list(columns)).sum())


def audit_trajectory_tables(tables: dict[str, pa.Table]) -> dict[str, Any]:
    """Validate referential integrity, leakage boundaries, and row counts."""

    missing = sorted(set(TABLES) - set(tables))
    if missing:
        raise DatasetError("missing tables: " + ", ".join(missing))
    transitions, episodes, pairs = (tables[name] for name in TABLES)
    required_transition = {
        "game_id",
        "pair_id",
        "seed",
        "seat",
        "step",
        "policy",
        "opponent",
        "chosen_action_json",
        "final_reward",
        "opponent_final_reward",
        "reward_difference",
        "win",
    }
    absent = sorted(required_transition - set(transitions.column_names))
    if absent:
        raise DatasetError("transitions missing columns: " + ", ".join(absent))
    for name, table in tables.items():
        if table.num_rows == 0:
            raise DatasetError(f"{name} is empty")
    duplicate_transitions = _duplicate_count(transitions, ("game_id", "seat", "step"))
    duplicate_episodes = _duplicate_count(episodes, ("game_id",))
    duplicate_pairs = _duplicate_count(pairs, ("pair_id",))
    if duplicate_transitions or duplicate_episodes or duplicate_pairs:
        raise DatasetError(
            "duplicate keys: "
            f"transitions={duplicate_transitions}, episodes={duplicate_episodes}, "
            f"pairs={duplicate_pairs}"
        )

    transition_games = set(transitions["game_id"].to_pylist())
    episode_games = set(episodes["game_id"].to_pylist())
    transition_pairs = set(transitions["pair_id"].to_pylist())
    pair_ids = set(pairs["pair_id"].to_pylist())
    if transition_games != episode_games:
        raise DatasetError("transition and episode game_id sets differ")
    if transition_pairs != pair_ids:
        raise DatasetError("transition and pair_id sets differ")
    null_count = sum(column.null_count for column in transitions.columns)
    if null_count:
        raise DatasetError("transitions contain null values")

    counts = transitions.select(("game_id", "seat")).to_pandas().value_counts()
    unexpected_counts = counts[counts != 719]
    if not unexpected_counts.empty:
        raise DatasetError("every game/seat must contain exactly 719 transitions")
    paired_games = pairs["games"].to_pylist()
    if any(int(value) != 2 for value in paired_games):
        raise DatasetError("every pair row must contain two seat-swapped games")
    statuses = set(str(value) for value in episodes["status"].to_pylist())
    if statuses != {"completed"}:
        raise DatasetError(f"episodes contain non-completed status: {sorted(statuses)}")

    seeds = sorted({int(value) for value in transitions["seed"].to_pylist()})
    policies = sorted({str(value) for value in transitions["policy"].to_pylist()})
    opponents = sorted({str(value) for value in transitions["opponent"].to_pylist()})
    return {
        "format": "kaggriculture-common-dataset-audit-v1",
        "rows": {name: tables[name].num_rows for name in TABLES},
        "unique_games": len(episode_games),
        "unique_pairs": len(pair_ids),
        "unique_seeds": len(seeds),
        "seed_start": min(seeds),
        "seed_end": max(seeds),
        "policies": policies,
        "opponents": opponents,
        "duplicate_keys": {
            "transitions": duplicate_transitions,
            "episodes": duplicate_episodes,
            "pairs": duplicate_pairs,
        },
        "null_transition_values": 0,
        "transitions_per_game_seat": 719,
        "leakage_contract": {
            "group_split_columns": ["seed", "pair_id"],
            "outcome_columns_excluded_from_features": [
                "final_reward",
                "opponent_final_reward",
                "reward_difference",
                "win",
            ],
            "hidden_opponent_inventory_is_zero_placeholder": True,
        },
    }


def build_common_dataset(inputs: Sequence[Path], output: Path) -> dict[str, Any]:
    """Combine compatible Arena trajectory directories into one dataset."""

    if not inputs:
        raise DatasetError("at least one input directory is required")
    input_tables: dict[str, list[pa.Table]] = {name: [] for name in TABLES}
    manifests = []
    shared_seeds: set[int] | None = None
    schemas: dict[str, pa.Schema] = {}
    for raw_dir in inputs:
        directory = raw_dir.resolve()
        summary_path = directory / "summary.json"
        if not summary_path.is_file():
            raise DatasetError(f"missing summary.json in {directory}")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if not summary.get("trajectory"):
            raise DatasetError(f"input was not captured with --trajectory: {directory}")
        if int(summary.get("failed_games", -1)) != 0:
            raise DatasetError(f"input contains failed games: {directory}")
        current_seeds: set[int] | None = None
        files = {}
        for name in TABLES:
            path = directory / f"{name}.parquet"
            if not path.is_file():
                raise DatasetError(f"missing {path.name} in {directory}")
            table = pq.read_table(path)
            if name in schemas and table.schema != schemas[name]:
                raise DatasetError(f"incompatible {name} schema in {directory}")
            schemas.setdefault(name, table.schema)
            input_tables[name].append(table)
            files[path.name] = _sha256(path)
            if name == "transitions":
                current_seeds = {int(value) for value in table["seed"].to_pylist()}
        assert current_seeds is not None
        if shared_seeds is None:
            shared_seeds = current_seeds
        elif current_seeds != shared_seeds:
            raise DatasetError("all inputs must use the same seed set")
        manifests.append(
            {
                "path": str(directory),
                "agents": summary.get("agents", []),
                "scheduled_games": summary.get("scheduled_games"),
                "files": files,
            }
        )

    combined = {
        name: pa.concat_tables(tables, promote_options="none")
        for name, tables in input_tables.items()
    }
    audit = audit_trajectory_tables(combined)
    output.mkdir(parents=True, exist_ok=True)
    for name, table in combined.items():
        pq.write_table(table, output / f"{name}.parquet", compression="zstd")
    payload = {
        "format": "kaggriculture-common-dataset-v1",
        "inputs": manifests,
        "audit": audit,
    }
    (output / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


__all__ = ["DatasetError", "audit_trajectory_tables", "build_common_dataset"]
