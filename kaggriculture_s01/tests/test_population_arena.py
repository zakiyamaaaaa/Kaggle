from __future__ import annotations

import csv
import json
from pathlib import Path

from kaggriculture_agent.local_arena import GameResult
from kaggriculture_agent.population import load_population
from kaggriculture_agent.population_arena import (
    PROFILE_FIELDS,
    RATING_FIELDS,
    build_population_schedule,
    outcome_profiles,
    run_population_arena,
)
from kaggriculture_agent.registry import agent_names

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "population.json"


def _result(spec, candidate_wins: bool = True) -> GameResult:
    candidate = "candidate"
    candidate_zero = spec.player_0 == candidate
    own, other = ((2.0, 1.0) if candidate_wins else (1.0, 2.0))
    reward_0, reward_1 = (own, other) if candidate_zero else (other, own)
    return GameResult(
        game_id=spec.game_id,
        seed=spec.seed,
        player_0=spec.player_0,
        player_1=spec.player_1,
        reward_0=reward_0,
        reward_1=reward_1,
        winner=candidate if candidate_wins else (spec.player_1 if candidate_zero else spec.player_0),
        steps=719,
        elapsed_seconds=0.01,
        status="completed",
        error="",
        agent_a=spec.agent_a,
        agent_b=spec.agent_b,
    )


def test_population_schedule_uses_tier_seeds_and_swaps_seats() -> None:
    config = load_population(CONFIG, available_agents=set(agent_names()))
    schedule = build_population_schedule("candidate", config, "development")

    opponents = len(config.members)
    assert len(schedule) == opponents * 32 * 2
    assert len({spec.game_id for spec in schedule}) == len(schedule)
    grouped = {}
    for spec in schedule:
        grouped.setdefault(spec.pair_id, []).append(spec)
    assert all(len(pair) == 2 for pair in grouped.values())
    assert all(pair[0].seed == pair[1].seed for pair in grouped.values())
    assert all(pair[0].player_0 == pair[1].player_1 for pair in grouped.values())
    assert {spec.seed for spec in schedule} == set(range(30000, 30032))


def test_outcome_density_deweights_duplicate_profiles() -> None:
    config = load_population(CONFIG, available_agents=set(agent_names()))
    schedule = build_population_schedule("candidate", config, "development")
    results = []
    for spec in schedule:
        opponent = spec.player_1 if spec.player_0 == "candidate" else spec.player_0
        # Salem variants share one profile while independent policies receive
        # a different alternating profile. This makes the density comparison deterministic.
        wins = opponent.startswith("salem") or opponent == "public_salem"
        if opponent.startswith("independent"):
            wins = spec.seed % 2 == 0
        results.append(_result(spec, wins))
    profiles = outcome_profiles("candidate", config, results)

    assert {row["opponent"] for row in profiles} == {member.agent for member in config.members}
    assert all(row["paired_seeds"] == 32 for row in profiles)
    assert abs(sum(row["density_weight"] for row in profiles) - len(profiles)) < 1e-9
    salem = next(row for row in profiles if row["opponent"] == "public_salem")
    baseline = next(row for row in profiles if row["opponent"] == "baseline")
    assert salem["density"] > baseline["density"]
    assert salem["density_weight"] < baseline["density_weight"]


def test_population_run_writes_outputs_and_resumes(tmp_path: Path, monkeypatch) -> None:
    config = load_population(CONFIG, available_agents=set(agent_names()))
    calls = []

    def fake_run_games(specs, workers):
        del workers
        for spec in specs:
            calls.append(spec.game_id)
            yield _result(spec)

    monkeypatch.setattr("kaggriculture_agent.population_arena.run_games", fake_run_games)
    first = run_population_arena(
        "candidate", config, "development", tmp_path, workers=1
    )
    first_calls = len(calls)
    second = run_population_arena(
        "candidate", config, "development", tmp_path, workers=1
    )

    assert first["scheduled_games"] == len(config.members) * 64
    assert first["executed_games"] == first_calls
    assert first["gate"]["passed"] is True
    assert second["executed_games"] == 0
    assert second["reused_games"] == first["scheduled_games"]
    assert len(calls) == first_calls
    assert tuple(next(csv.reader((tmp_path / "ratings.csv").open()))) == RATING_FIELDS
    assert tuple(next(csv.reader((tmp_path / "profiles.csv").open()))) == PROFILE_FIELDS
    assert json.loads((tmp_path / "summary.json").read_text())["population_fingerprint"]
    assert (tmp_path / "benchmark.json").exists()
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["agents"]["candidate"]["sha256"]
    assert json.loads((tmp_path / "gate.json").read_text())["passed"] is True


def test_disconnected_failures_are_saved_and_fail_gate(tmp_path: Path, monkeypatch) -> None:
    config = load_population(CONFIG, available_agents=set(agent_names()))

    def failed_games(specs, workers):
        del workers
        for spec in specs:
            yield GameResult(
                spec.game_id,
                spec.seed,
                spec.player_0,
                spec.player_1,
                None,
                None,
                "",
                0,
                0.01,
                "failed",
                "synthetic failure",
                agent_a=spec.agent_a,
                agent_b=spec.agent_b,
            )

    monkeypatch.setattr("kaggriculture_agent.population_arena.run_games", failed_games)
    summary = run_population_arena(
        "candidate", config, "development", tmp_path, workers=1
    )

    assert summary["failed_games"] == summary["scheduled_games"]
    assert summary["gate"]["passed"] is False
    assert "incomplete_games" in summary["gate"]["reasons"]
    assert summary["rating_error"]
    assert len(list(csv.DictReader((tmp_path / "games.csv").open()))) == summary["scheduled_games"]
