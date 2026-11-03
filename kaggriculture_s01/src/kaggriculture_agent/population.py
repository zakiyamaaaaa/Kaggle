"""Validated, reproducible opponent-population configuration."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class PopulationConfigError(ValueError):
    """Raised when a population cannot be used reproducibly."""


@dataclass(frozen=True)
class PopulationMember:
    name: str
    agent: str
    family: str
    archetype: str
    role: str
    weight: float
    frozen: bool
    artifact: Path | None = None
    sha256: str | None = None

    def to_dict(self, *, base_dir: Path | None = None) -> dict[str, Any]:
        artifact: str | None = None
        if self.artifact is not None:
            if base_dir is not None:
                artifact = os.path.relpath(self.artifact, base_dir)
            else:
                artifact = str(self.artifact)
        return {
            "agent": self.agent,
            "family": self.family,
            "archetype": self.archetype,
            "role": self.role,
            "weight": self.weight,
            "frozen": self.frozen,
            "artifact": artifact,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class EvaluationTier:
    name: str
    seeds: int
    seed_start: int

    @property
    def games_per_matchup(self) -> int:
        return self.seeds * 2


@dataclass(frozen=True)
class PopulationConfig:
    version: int
    members: tuple[PopulationMember, ...]
    tiers: tuple[EvaluationTier, ...]
    source: Path

    def member(self, name: str) -> PopulationMember:
        try:
            return next(member for member in self.members if member.name == name)
        except StopIteration as exc:
            raise PopulationConfigError(f"unknown population member: {name}") from exc

    def tier(self, name: str) -> EvaluationTier:
        try:
            return next(tier for tier in self.tiers if tier.name == name)
        except StopIteration as exc:
            raise PopulationConfigError(f"unknown evaluation tier: {name}") from exc

    def agents(self, *, roles: set[str] | None = None) -> tuple[str, ...]:
        return tuple(
            member.agent
            for member in self.members
            if roles is None or member.role in roles
        )

    def to_dict(self) -> dict[str, Any]:
        base_dir = self.source.parent
        return {
            "version": self.version,
            "members": {
                member.name: member.to_dict(base_dir=base_dir) for member in self.members
            },
            "evaluation_tiers": {
                tier.name: {"seeds": tier.seeds, "seed_start": tier.seed_start}
                for tier in self.tiers
            },
        }


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise PopulationConfigError(f"{label} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise PopulationConfigError(f"{label} must be a positive integer") from exc
    if result < 1 or (isinstance(value, float) and value != result):
        raise PopulationConfigError(f"{label} must be a positive integer")
    return result


def _member_from_mapping(name: str, raw: Any, base_dir: Path) -> PopulationMember:
    if not isinstance(raw, Mapping):
        raise PopulationConfigError(f"members.{name} must be an object")
    agent = raw.get("agent", name)
    family = raw.get("family")
    archetype = raw.get("archetype")
    role = raw.get("role")
    if not all(isinstance(value, str) and value for value in (name, agent, family, archetype, role)):
        raise PopulationConfigError(
            f"members.{name} requires non-empty agent, family, archetype, and role"
        )
    try:
        weight = float(raw.get("weight", 1.0))
    except (TypeError, ValueError) as exc:
        raise PopulationConfigError(f"members.{name}.weight must be positive") from exc
    if not math.isfinite(weight) or weight <= 0:
        raise PopulationConfigError(f"members.{name}.weight must be positive")
    frozen = raw.get("frozen", False)
    if not isinstance(frozen, bool):
        raise PopulationConfigError(f"members.{name}.frozen must be boolean")
    artifact_raw = raw.get("artifact")
    artifact = None if artifact_raw is None else (base_dir / str(artifact_raw)).resolve()
    digest = raw.get("sha256")
    if digest is not None:
        digest = str(digest).lower()
    if frozen and (artifact is None or digest is None):
        raise PopulationConfigError(
            f"frozen member {name!r} requires artifact and sha256"
        )
    if digest is not None and (len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
        raise PopulationConfigError(f"members.{name}.sha256 is invalid")
    return PopulationMember(
        name=name,
        agent=agent,
        family=family,
        archetype=archetype,
        role=role,
        weight=weight,
        frozen=frozen,
        artifact=artifact,
        sha256=digest,
    )


def load_population(
    path: Path,
    *,
    available_agents: set[str] | None = None,
    verify: bool = True,
) -> PopulationConfig:
    """Load a population and optionally verify registry names and artifacts."""

    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, Mapping):
        raise PopulationConfigError("population config must be an object")
    version = _positive_int(raw.get("version", 1), "version")
    raw_members = raw.get("members")
    if not isinstance(raw_members, Mapping) or len(raw_members) < 2:
        raise PopulationConfigError("members must contain at least two entries")
    members = tuple(
        _member_from_mapping(str(name), value, path.parent)
        for name, value in raw_members.items()
    )
    agent_names = [member.agent for member in members]
    if len(agent_names) != len(set(agent_names)):
        raise PopulationConfigError("population registry agent names must be unique")
    if available_agents is not None:
        unknown = sorted(set(agent_names) - available_agents)
        if unknown:
            raise PopulationConfigError("unknown registry agents: " + ", ".join(unknown))

    raw_tiers = raw.get("evaluation_tiers")
    if not isinstance(raw_tiers, Mapping) or not raw_tiers:
        raise PopulationConfigError("evaluation_tiers must be a non-empty object")
    tiers: list[EvaluationTier] = []
    seed_ranges: list[tuple[int, int, str]] = []
    for name, value in raw_tiers.items():
        if not isinstance(value, Mapping):
            raise PopulationConfigError(f"evaluation_tiers.{name} must be an object")
        seeds = _positive_int(value.get("seeds"), f"evaluation_tiers.{name}.seeds")
        seed_start = _positive_int(
            value.get("seed_start"), f"evaluation_tiers.{name}.seed_start"
        )
        tiers.append(EvaluationTier(str(name), seeds, seed_start))
        seed_ranges.append((seed_start, seed_start + seeds - 1, str(name)))
    for index, (start, end, name) in enumerate(seed_ranges):
        for other_start, other_end, other_name in seed_ranges[index + 1 :]:
            if max(start, other_start) <= min(end, other_end):
                raise PopulationConfigError(
                    f"evaluation tier seed ranges overlap: {name} and {other_name}"
                )

    config = PopulationConfig(version, members, tuple(tiers), path.resolve())
    if verify:
        verify_artifacts(config)
    return config


def verify_artifacts(config: PopulationConfig) -> None:
    """Fail closed when any frozen member's bytes differ from its manifest."""

    for member in config.members:
        if not member.frozen:
            continue
        assert member.artifact is not None and member.sha256 is not None
        if not member.artifact.is_file():
            raise PopulationConfigError(
                f"frozen artifact for {member.name!r} is missing: {member.artifact}"
            )
        actual = hashlib.sha256(member.artifact.read_bytes()).hexdigest()
        if actual != member.sha256:
            raise PopulationConfigError(
                f"frozen artifact hash mismatch for {member.name!r}: "
                f"expected {member.sha256}, got {actual}"
            )


def population_fingerprint(config: PopulationConfig) -> str:
    """Return a stable identifier for the complete evaluation contract."""

    payload = json.dumps(
        config.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "EvaluationTier",
    "PopulationConfig",
    "PopulationConfigError",
    "PopulationMember",
    "load_population",
    "population_fingerprint",
    "verify_artifacts",
]
