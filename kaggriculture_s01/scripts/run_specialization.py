#!/usr/bin/env python3
"""Build a resumable four-stage Kaggriculture specialization plan.

This command is intentionally a planner.  It validates registered agent names,
emits deterministic opponent allocations and Champion Arena jobs, and records
manifest/checkpoint metadata.  It does not train a model or run PPO.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kaggriculture_agent.registry import agent_names
from kaggriculture_agent.specialization import (
    SpecializationConfigError,
    build_checkpoint_metadata,
    build_plan,
    build_run_manifest,
    load_config,
    read_json,
    write_checkpoint_metadata,
    write_json,
    write_run_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "specialization.json"
DEFAULT_OUTPUT = ROOT / "outputs" / "specialization"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output-dir",
        "--output",
        dest="output_dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="directory for the JSON plan, manifest, and checkpoint metadata",
    )
    parser.add_argument(
        "--stage",
        choices=("stage_1", "stage_2", "stage_3", "stage_4"),
        action="append",
        help="emit per-stage files for selected stages (default: all four)",
    )
    parser.add_argument("--games", type=int, help="override training and evaluation games per stage")
    parser.add_argument("--seed", type=int, help="override the base seed for every stage")
    parser.add_argument("--run-id", help="stable identifier used in the run manifest")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="replace planned metadata; mismatched config fingerprints still fail",
    )
    return parser.parse_args(argv)


def _existing_manifest(output: Path, config_sha256: str) -> dict[str, Any] | None:
    path = output / "manifest.json"
    if not path.exists():
        return None
    manifest = read_json(path)
    existing_sha = manifest.get("config_sha256")
    if existing_sha != config_sha256:
        raise SystemExit(
            "manifest config_sha256 differs from the requested config; "
            "choose a new --output-dir or update the config intentionally"
        )
    return manifest


def _merge_manifest(previous: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    """Keep completed stage/checkpoint status when a plan is regenerated."""

    merged = dict(fresh)
    merged["created_at"] = previous.get("created_at", fresh["created_at"])
    merged["updated_at"] = fresh["updated_at"]
    merged["status"] = previous.get("status", fresh["status"])
    old_stages = previous.get("stages", {})
    for stage_id, stage_data in merged.get("stages", {}).items():
        prior = old_stages.get(stage_id, {}) if isinstance(old_stages, dict) else {}
        if isinstance(prior, dict):
            for key in ("status", "metrics", "promotion", "completed_at"):
                if key in prior:
                    stage_data[key] = prior[key]
    checkpoints = previous.get("checkpoints", {})
    if isinstance(checkpoints, dict):
        merged["checkpoints"] = checkpoints
    return merged


def _write_stage_outputs(
    output: Path,
    plan: dict[str, Any],
    config: Any,
    manifest: dict[str, Any],
    selected: set[str],
    *,
    resume: bool,
) -> None:
    stages_dir = output / "stages"
    checkpoints_dir = output / "checkpoints"
    stages_dir.mkdir(parents=True, exist_ok=True)
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    old_checkpoints = manifest.get("checkpoints", {})
    if not isinstance(old_checkpoints, dict):
        old_checkpoints = {}
    parent_checkpoint: str | None = None
    for stage_plan in plan["stages"]:
        stage_id = stage_plan["id"]
        metadata_path = checkpoints_dir / f"{stage_id}.json"
        if stage_id in selected:
            write_json(stages_dir / f"{stage_id}.json", stage_plan)
        if resume and metadata_path.exists():
            metadata = read_json(metadata_path)
        else:
            metadata = build_checkpoint_metadata(
                config,
                stage_id,
                plan=plan,
                parent_checkpoint=parent_checkpoint,
            )
            write_checkpoint_metadata(metadata_path, metadata)
        old_checkpoints[stage_id] = {
            "metadata_path": str(metadata_path.resolve()),
            "status": metadata.get("status", "planned"),
            "checkpoint_sha256": metadata.get("checkpoint_sha256"),
        }
        parent_checkpoint = metadata.get("checkpoint_path") or str(metadata_path.resolve())
    manifest["checkpoints"] = old_checkpoints


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.games is not None and (args.games < 2 or args.games % 2):
        raise SystemExit("--games must be a positive even number")
    if args.seed is not None and args.seed < 0:
        raise SystemExit("--seed must be non-negative")
    try:
        config = load_config(args.config, available_agents=agent_names())
        plan = build_plan(
            config,
            available_agents=agent_names(),
            games_override=args.games,
            seed_override=args.seed,
        )
    except (SpecializationConfigError, ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    prior = None if args.no_resume else _existing_manifest(output, plan["config_sha256"])
    created_at = prior.get("created_at") if prior else datetime.now(timezone.utc).isoformat()
    manifest = build_run_manifest(
        config,
        plan,
        run_id=args.run_id or (prior.get("run_id") if prior else None),
        config_path=args.config,
        output_dir=output,
        created_at=created_at,
    )
    if prior:
        manifest = _merge_manifest(prior, manifest)
    selected = set(args.stage or ("stage_1", "stage_2", "stage_3", "stage_4"))
    _write_stage_outputs(output, plan, config, manifest, selected, resume=prior is not None)
    write_json(output / "specialization_plan.json", plan)
    write_json(
        output / "arena_plan.json",
        {
            "framework": plan["framework"],
            "config_sha256": plan["config_sha256"],
            "candidate_agent": plan["candidate_agent"],
            "stages": [
                {"id": stage["id"], "champion_arena": stage["champion_arena"]}
                for stage in plan["stages"]
            ],
        },
    )
    write_run_manifest(output / "manifest.json", manifest)
    write_json(
        output / "summary.json",
        {
            "run_id": manifest["run_id"],
            "status": manifest["status"],
            "config_sha256": plan["config_sha256"],
            "candidate_agent": plan["candidate_agent"],
            "stages": [stage["id"] for stage in plan["stages"]],
            "output_dir": str(output),
            "ppo_implemented": False,
            "resumed": prior is not None,
        },
    )
    print(
        f"planned={len(plan['stages'])} stages candidate={plan['candidate_agent']} "
        f"resumed={prior is not None} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
