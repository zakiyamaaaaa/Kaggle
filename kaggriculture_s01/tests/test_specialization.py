from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from kaggriculture_agent.specialization import (
    SpecializationConfigError,
    allocate_weighted_games,
    build_checkpoint_metadata,
    build_plan,
    build_run_manifest,
    build_stage_assignments,
    config_fingerprint,
    effective_weights,
    evaluate_promotion,
    load_config,
    sample_opponents,
    write_checkpoint_metadata,
    write_run_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "specialization.json"


def test_checked_in_config_has_four_progressively_narrower_stages() -> None:
    config = load_config(
        CONFIG_PATH, available_agents={"baseline", "candidate", "public_salem"}
    )

    assert [stage.id for stage in config.stages] == [
        "stage_1",
        "stage_2",
        "stage_3",
        "stage_4",
    ]
    assert len(config.stages[0].pool) > len(config.stages[1].pool)
    assert set(config.stages[1].pool) >= set(config.stages[2].pool)
    assert config.stages[3].specialist_agent == "candidate"
    assert config.candidate_agent in {"baseline", "candidate"}


def test_config_references_are_validated() -> None:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["stages"][1]["pool"] = ["does_not_exist"]

    with pytest.raises(SpecializationConfigError, match="unknown opponent definitions"):
        load_config_from_mapping(raw)


def load_config_from_mapping(value: dict) -> object:
    """Keep the test call explicit while using the public validator path."""

    from kaggriculture_agent.specialization import validate_config

    return validate_config(
        value, available_agents={"baseline", "candidate", "public_salem"}
    )


def test_effective_weights_emphasize_hard_opponents() -> None:
    config = load_config(
        CONFIG_PATH, available_agents={"baseline", "candidate", "public_salem"}
    )
    weights = effective_weights(config, "stage_1")

    assert weights["public_salem"] == pytest.approx(3.0)
    assert weights["public_salem"] > weights["baseline"]


def test_largest_remainder_is_exact_and_seat_balanced() -> None:
    allocation = allocate_weighted_games(
        ["easy", "hard", "other"], {"easy": 1, "hard": 3, "other": 1}, 20
    )

    assert allocation == {"easy": 4, "hard": 12, "other": 4}
    assert sum(allocation.values()) == 20
    assert all(value % 2 == 0 for value in allocation.values())
    assert allocate_weighted_games(
        ["easy", "hard", "other"], {"easy": 1, "hard": 3, "other": 1}, 20
    ) == allocation


def test_sampling_is_deterministic_and_respects_counts() -> None:
    opponents = ["a", "b"]
    weights = {"a": 1.0, "b": 3.0}
    first = sample_opponents(opponents, weights, 40, seed=1234, paired=True)
    second = sample_opponents(opponents, weights, 40, seed=1234, paired=True)
    other_seed = sample_opponents(opponents, weights, 40, seed=1235, paired=True)

    assert first == second
    assert first != other_seed
    assert Counter(first) == {"a": 10, "b": 30}


def test_assignments_pair_seats_and_keep_training_eval_seed_ranges_disjoint() -> None:
    config = load_config(
        CONFIG_PATH, available_agents={"baseline", "candidate", "public_salem"}
    )
    training = build_stage_assignments(config, "stage_1", phase="training")
    evaluation = build_stage_assignments(config, "stage_1", phase="evaluation")

    assert len(training) == 24
    assert len(evaluation) == 24
    for rows in (training, evaluation):
        by_pair = {}
        for row in rows:
            by_pair.setdefault(row["pair_index"], []).append(row)
        assert all({row["seat"] for row in pair} == {0, 1} for pair in by_pair.values())
        assert all(len({row["seed"] for row in pair}) == 1 for pair in by_pair.values())
    assert {row["seed"] for row in training}.isdisjoint({row["seed"] for row in evaluation})


def test_plan_contains_arena_contract_and_no_ppo() -> None:
    config = load_config(
        CONFIG_PATH, available_agents={"baseline", "candidate", "public_salem"}
    )
    plan = build_plan(
        config,
        available_agents={"baseline", "candidate", "public_salem"},
        games_override=8,
    )

    assert plan["ppo_implemented"] is False
    assert plan["progressive_narrowing"] is True
    assert plan["stage_order"] == ["stage_1", "stage_2", "stage_3", "stage_4"]
    for stage in plan["stages"]:
        assert stage["champion_arena"]["swap_seats"] is True
        assert stage["training"]["games"] == 8
        assert stage["evaluation"]["games"] == 8
        assert stage["champion_arena"]["opponents"]


def test_promotion_requires_metrics_and_previous_stage() -> None:
    config = load_config(
        CONFIG_PATH, available_agents={"baseline", "candidate", "public_salem"}
    )
    stage = config.stage("stage_2")
    passed = evaluate_promotion(
        stage,
        {
            "evaluation_games": 24,
            "win_rate": 0.60,
            "mean_reward_delta": 10,
            "failure_rate": 0,
            "hard_opponent_win_rate": 0.60,
        },
    )
    blocked = evaluate_promotion(
        stage,
        {
            "evaluation_games": 24,
            "win_rate": 0.60,
            "mean_reward_delta": 10,
            "failure_rate": 0,
            "hard_opponent_win_rate": 0.60,
        },
        previous_stage_promoted=False,
    )

    assert passed.promoted
    assert not blocked.promoted
    assert "previous_stage_promoted" in blocked.reasons


def test_manifest_and_checkpoint_metadata_are_written(tmp_path: Path) -> None:
    config = load_config(
        CONFIG_PATH, available_agents={"baseline", "candidate", "public_salem"}
    )
    plan = build_plan(
        config,
        available_agents={"baseline", "candidate", "public_salem"},
        games_override=4,
    )
    manifest = build_run_manifest(
        config,
        plan,
        run_id="specialization-test",
        config_path=CONFIG_PATH,
        output_dir=tmp_path,
        created_at="2026-09-19T00:00:00+00:00",
    )
    checkpoint = build_checkpoint_metadata(config, "stage_1", plan=plan)
    manifest_path = write_run_manifest(tmp_path / "manifest.json", manifest)
    checkpoint_path = write_checkpoint_metadata(tmp_path / "checkpoint.json", checkpoint)

    assert manifest_path.exists()
    assert checkpoint_path.exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["config_sha256"] == config_fingerprint(config)
    assert json.loads(checkpoint_path.read_text(encoding="utf-8"))["ppo_implemented"] is False


def test_cli_emits_json_outputs_and_resumes(tmp_path: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_specialization.py"),
        "--config",
        str(CONFIG_PATH),
        "--output-dir",
        str(tmp_path),
        "--games",
        "4",
    ]
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    first = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    second = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))

    assert first["ppo_implemented"] is False
    assert second["resumed"] is True
    assert (tmp_path / "arena_plan.json").exists()
    assert (tmp_path / "checkpoints" / "stage_4.json").exists()
