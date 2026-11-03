from __future__ import annotations

import json
from pathlib import Path

import pytest

from kaggriculture_agent.population import (
    PopulationConfigError,
    load_population,
    population_fingerprint,
)
from kaggriculture_agent.registry import agent_names

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "population.json"


def test_checked_in_population_is_valid_and_reproducible() -> None:
    first = load_population(CONFIG, available_agents=set(agent_names()))
    second = load_population(CONFIG, available_agents=set(agent_names()))

    assert population_fingerprint(first) == population_fingerprint(second)
    assert len(first.members) >= 2
    assert {member.role for member in first.members} >= {
        "anchor",
        "frozen_checkpoint",
        "specialist",
        "incumbent",
    }
    assert all(member.artifact is not None for member in first.members if member.frozen)
    assert first.to_dict()["members"]["salem_2900_frozen"]["artifact"].startswith("..")


def test_tiers_match_agreed_paired_evaluation_sizes() -> None:
    config = load_population(CONFIG, available_agents=set(agent_names()))

    assert config.tier("development").seeds == 32
    assert config.tier("development").games_per_matchup == 64
    assert config.tier("adoption").games_per_matchup == 256
    assert config.tier("final").games_per_matchup == 512


def test_unknown_registry_agent_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["members"]["safe_rule_anchor"]["agent"] = "missing_agent"
    path = tmp_path / "population.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(PopulationConfigError, match="unknown registry agents"):
        load_population(path, available_agents=set(agent_names()), verify=False)


def test_frozen_artifact_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    artifact = tmp_path / "checkpoint.zip"
    artifact.write_bytes(b"changed")
    raw = {
        "version": 1,
        "members": {
            "frozen": {
                "agent": "baseline",
                "family": "a",
                "archetype": "a",
                "role": "frozen_checkpoint",
                "frozen": True,
                "artifact": "checkpoint.zip",
                "sha256": "0" * 64,
            },
            "other": {
                "agent": "candidate",
                "family": "b",
                "archetype": "b",
                "role": "incumbent",
                "frozen": False,
            },
        },
        "evaluation_tiers": {"development": {"seeds": 1, "seed_start": 1}},
    }
    path = tmp_path / "population.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(PopulationConfigError, match="hash mismatch"):
        load_population(path, available_agents={"baseline", "candidate"})


def test_overlapping_tier_seed_ranges_are_rejected(tmp_path: Path) -> None:
    raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    raw["evaluation_tiers"] = {
        "one": {"seeds": 10, "seed_start": 100},
        "two": {"seeds": 10, "seed_start": 109},
    }
    path = tmp_path / "population.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(PopulationConfigError, match="seed ranges overlap"):
        load_population(path, verify=False)
