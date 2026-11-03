"""Four-stage opponent specialization planning for Kaggriculture.

The specialization loop is deliberately a planning and bookkeeping layer.  It
does not contain a learner (and in particular does not implement PPO).  It
turns a small JSON roster into deterministic, seat-balanced match assignments
that can be handed to the local Champion Arena, while keeping enough metadata
to resume a long-running experiment safely.

The four stages are intentionally ordered from broad to narrow:

``stage_1``
    A broad pool used to screen a policy against several behaviours.
``stage_2``
    The champion from each selected archetype.
``stage_3``
    The selected strategy-family representatives.
``stage_4``
    A fixed specialist evaluated against the final narrow pool.

The current repository only has two registered rule agents.  The checked-in
configuration therefore uses those agents for all four stages and records the
archetype/family labels separately.  A future registry can add more concrete
agents without changing this module or the JSON schema.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from typing import Any, Iterable, Mapping, Sequence

CONFIG_VERSION = 1
FRAMEWORK_VERSION = "0.1.0"
STAGE_IDS = ("stage_1", "stage_2", "stage_3", "stage_4")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class SpecializationConfigError(ValueError):
    """Raised when a specialization config cannot produce a safe plan."""


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SpecializationConfigError(f"{label} must be an object")
    return value


def _finite_number(value: Any, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise SpecializationConfigError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SpecializationConfigError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise SpecializationConfigError(f"{label} must be a finite number")
    if minimum is not None and number < minimum:
        raise SpecializationConfigError(f"{label} must be >= {minimum}")
    return number


def _positive_int(value: Any, label: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool):
        raise SpecializationConfigError(f"{label} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise SpecializationConfigError(f"{label} must be an integer") from exc
    if number < (0 if allow_zero else 1):
        minimum = 0 if allow_zero else 1
        raise SpecializationConfigError(f"{label} must be >= {minimum}")
    # Do not silently accept 1.5 as 1.  JSON numbers are commonly parsed as
    # floats, and a truncated game count would invalidate a run manifest.
    if isinstance(value, float) and value != number:
        raise SpecializationConfigError(f"{label} must be an integer")
    return number


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or not _IDENTIFIER.fullmatch(value):
        raise SpecializationConfigError(
            f"{label} must be a non-empty identifier (letters, digits, _, -, .)"
        )
    return value


def _json_safe(value: Any) -> Any:
    """Convert dataclass/mapping values into deterministic JSON-compatible data."""

    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_safe(item) for item in value)
    return value


@dataclass(frozen=True)
class OpponentDefinition:
    """A named pool member and the registered agent it resolves to."""

    name: str
    agent: str
    archetype: str = "unclassified"
    strategy_family: str = "rule"
    weight: float = 1.0
    hard: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, name: str, value: Any) -> "OpponentDefinition":
        name = _identifier(name, "opponent name")
        if isinstance(value, str):
            data: Mapping[str, Any] = {"agent": value}
        else:
            data = _require_mapping(value, f"opponents.{name}")
        agent = data.get("agent", data.get("registry_name", name))
        agent = _identifier(agent, f"opponents.{name}.agent")
        archetype = str(data.get("archetype", data.get("archetype_id", "unclassified")))
        family = str(data.get("strategy_family", data.get("family", "rule")))
        if not archetype or not family:
            raise SpecializationConfigError(
                f"opponents.{name}.archetype and strategy_family must be non-empty"
            )
        weight = _finite_number(data.get("weight", 1.0), f"opponents.{name}.weight", minimum=0)
        metadata = data.get("metadata", {})
        metadata = dict(_require_mapping(metadata, f"opponents.{name}.metadata"))
        return cls(
            name=name,
            agent=agent,
            archetype=archetype,
            strategy_family=family,
            weight=weight,
            hard=bool(data.get("hard", data.get("hard_opponent", False))),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "archetype": self.archetype,
            "strategy_family": self.strategy_family,
            "weight": self.weight,
            "hard": self.hard,
            "metadata": _json_safe(self.metadata),
        }


@dataclass(frozen=True)
class PromotionPrerequisites:
    """Minimum evidence required before moving to the next stage."""

    min_evaluation_games: int = 0
    min_win_rate: float = 0.5
    min_mean_reward_delta: float = 0.0
    max_failure_rate: float = 0.0
    min_hard_opponent_win_rate: float | None = None
    max_opponent_win_rate_regression: float | None = None
    require_previous_stage: bool = True

    @classmethod
    def from_mapping(cls, value: Any) -> "PromotionPrerequisites":
        data = _require_mapping(value or {}, "promotion")

        def pick(*keys: str, default: Any) -> Any:
            for key in keys:
                if key in data:
                    return data[key]
            return default

        min_games = _positive_int(
            pick("min_evaluation_games", "minimum_evaluation_games", default=0),
            "promotion.min_evaluation_games",
            allow_zero=True,
        )
        min_win = _finite_number(
            pick("min_win_rate", "minimum_win_rate", default=0.5),
            "promotion.min_win_rate",
        )
        delta = _finite_number(
            pick("min_mean_reward_delta", "minimum_mean_reward_delta", default=0.0),
            "promotion.min_mean_reward_delta",
        )
        max_failure = _finite_number(
            pick("max_failure_rate", "maximum_failure_rate", default=0.0),
            "promotion.max_failure_rate",
            minimum=0,
        )
        hard_value = pick(
            "min_hard_opponent_win_rate", "minimum_hard_opponent_win_rate", default=None
        )
        hard = None if hard_value is None else _finite_number(
            hard_value, "promotion.min_hard_opponent_win_rate"
        )
        regression_value = pick(
            "max_opponent_win_rate_regression",
            "maximum_opponent_win_rate_regression",
            default=None,
        )
        regression = (
            None
            if regression_value is None
            else _finite_number(
                regression_value, "promotion.max_opponent_win_rate_regression", minimum=0
            )
        )
        return cls(
            min_evaluation_games=min_games,
            min_win_rate=min_win,
            min_mean_reward_delta=delta,
            max_failure_rate=max_failure,
            min_hard_opponent_win_rate=hard,
            max_opponent_win_rate_regression=regression,
            require_previous_stage=bool(pick("require_previous_stage", default=True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_evaluation_games": self.min_evaluation_games,
            "min_win_rate": self.min_win_rate,
            "min_mean_reward_delta": self.min_mean_reward_delta,
            "max_failure_rate": self.max_failure_rate,
            "min_hard_opponent_win_rate": self.min_hard_opponent_win_rate,
            "max_opponent_win_rate_regression": self.max_opponent_win_rate_regression,
            "require_previous_stage": self.require_previous_stage,
        }


@dataclass(frozen=True)
class StageConfig:
    """Configuration for one specialization stage."""

    id: str
    label: str
    mode: str
    pool: tuple[str, ...]
    training_games: int
    evaluation_games: int
    seed: int
    hard_opponent_weight: float
    weights: Mapping[str, float]
    promotion: PromotionPrerequisites
    specialist_agent: str | None = None

    @property
    def opponents(self) -> tuple[str, ...]:
        """Compatibility alias used by arena/planning callers."""

        return self.pool

    @classmethod
    def from_mapping(cls, index: int, value: Any) -> "StageConfig":
        data = _require_mapping(value, f"stages[{index}]")
        stage_id = _identifier(data.get("id", f"stage_{index + 1}"), f"stages[{index}].id")
        label = str(data.get("label", data.get("name", stage_id)))
        mode = str(data.get("mode", data.get("purpose", "training")))
        if not label or not mode:
            raise SpecializationConfigError(f"stages[{index}] label and mode must be non-empty")
        pool_value = data.get("pool", data.get("opponents"))
        if not isinstance(pool_value, Sequence) or isinstance(pool_value, (str, bytes)):
            raise SpecializationConfigError(f"stages[{index}].pool must be a list")
        pool = tuple(_identifier(item, f"stages[{index}].pool") for item in pool_value)
        if len(set(pool)) != len(pool):
            raise SpecializationConfigError(f"stages[{index}].pool contains duplicate names")
        games = data.get("games", {})
        games = _require_mapping(games, f"stages[{index}].games")

        def game_count(*keys: str, default: int) -> int:
            for key in keys:
                if key in data:
                    return _positive_int(data[key], f"stages[{index}].{key}")
                if key in games:
                    return _positive_int(games[key], f"stages[{index}].games.{key}")
            return default

        training_games = game_count("training_games", "train_games", "training", "train", default=20)
        evaluation_games = game_count(
            "evaluation_games", "eval_games", "evaluation", "eval", default=training_games
        )
        seed = _positive_int(data.get("seed", 10000 + index * 10000), f"stages[{index}].seed", allow_zero=True)
        hard_weight = _finite_number(
            data.get("hard_opponent_weight", data.get("hard_weight", 1.0)),
            f"stages[{index}].hard_opponent_weight",
            minimum=0,
        )
        weights_value = data.get("weights", {})
        weights_data = _require_mapping(weights_value, f"stages[{index}].weights")
        weights = {
            _identifier(key, f"stages[{index}].weights key"): _finite_number(
                value, f"stages[{index}].weights.{key}", minimum=0
            )
            for key, value in weights_data.items()
        }
        promotion = PromotionPrerequisites.from_mapping(
            data.get("promotion", data.get("promotion_prerequisites", {}))
        )
        specialist = data.get("specialist_agent")
        if specialist is not None:
            specialist = _identifier(specialist, f"stages[{index}].specialist_agent")
        return cls(
            id=stage_id,
            label=label,
            mode=mode,
            pool=pool,
            training_games=training_games,
            evaluation_games=evaluation_games,
            seed=seed,
            hard_opponent_weight=hard_weight,
            weights=weights,
            promotion=promotion,
            specialist_agent=specialist,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "mode": self.mode,
            "pool": list(self.pool),
            "games": {"training": self.training_games, "evaluation": self.evaluation_games},
            "seed": self.seed,
            "hard_opponent_weight": self.hard_opponent_weight,
            "weights": dict(self.weights),
            "promotion": self.promotion.to_dict(),
            **({"specialist_agent": self.specialist_agent} if self.specialist_agent else {}),
        }


@dataclass(frozen=True)
class SpecializationConfig:
    """Parsed and validated four-stage specialization configuration."""

    candidate_agent: str
    opponents: Mapping[str, OpponentDefinition]
    stages: tuple[StageConfig, ...]
    evaluation: Mapping[str, Any] = field(default_factory=dict)
    version: int = CONFIG_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Any) -> "SpecializationConfig":
        data = _require_mapping(value, "specialization config")
        version = _positive_int(data.get("version", CONFIG_VERSION), "version")
        candidate = data.get("candidate_agent", data.get("learner_agent", data.get("candidate")))
        candidate = _identifier(candidate, "candidate_agent")
        roster_value = data.get("opponents", data.get("opponent_pool"))
        roster = _require_mapping(roster_value, "opponents")
        opponents = {
            _identifier(name, "opponent name"): OpponentDefinition.from_mapping(name, payload)
            for name, payload in roster.items()
        }
        if not opponents:
            raise SpecializationConfigError("opponents must contain at least one entry")
        stages_value = data.get("stages")
        if not isinstance(stages_value, Sequence) or isinstance(stages_value, (str, bytes)):
            raise SpecializationConfigError("stages must be a list of four stage objects")
        stages = tuple(StageConfig.from_mapping(index, item) for index, item in enumerate(stages_value))
        evaluation = dict(_require_mapping(data.get("evaluation", {}), "evaluation"))
        metadata = dict(_require_mapping(data.get("metadata", {}), "metadata"))
        return cls(
            candidate_agent=candidate,
            opponents=opponents,
            stages=stages,
            evaluation=evaluation,
            version=version,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "candidate_agent": self.candidate_agent,
            "opponents": {
                name: self.opponents[name].to_dict() for name in sorted(self.opponents)
            },
            "stages": [stage.to_dict() for stage in self.stages],
            "evaluation": _json_safe(self.evaluation),
            "metadata": _json_safe(self.metadata),
        }

    def stage(self, stage_id: str | int) -> StageConfig:
        if isinstance(stage_id, int):
            key = f"stage_{stage_id}"
        else:
            key = stage_id if stage_id.startswith("stage_") else f"stage_{stage_id}"
        for stage in self.stages:
            if stage.id == key:
                return stage
        raise KeyError(f"unknown specialization stage {stage_id!r}")


def validate_config(
    config: SpecializationConfig | Mapping[str, Any],
    available_agents: Iterable[str] | None = None,
) -> SpecializationConfig:
    """Validate references, four-stage ordering, pools, and promotion gates.

    ``available_agents`` is injectable for tests and for a future Champion
    Arena registry.  When omitted, the live Kaggriculture registry is used.
    The returned object is always the parsed dataclass, making this function
    convenient at CLI boundaries.
    """

    parsed = config if isinstance(config, SpecializationConfig) else SpecializationConfig.from_mapping(config)
    errors: list[str] = []
    if parsed.version != CONFIG_VERSION:
        errors.append(f"unsupported config version {parsed.version}; expected {CONFIG_VERSION}")
    if len(parsed.stages) != 4:
        errors.append(f"exactly four stages are required; found {len(parsed.stages)}")
    stage_ids = [stage.id for stage in parsed.stages]
    if len(stage_ids) != len(set(stage_ids)):
        errors.append("stage ids must be unique")
    for index, expected in enumerate(STAGE_IDS):
        if index >= len(stage_ids) or stage_ids[index] != expected:
            errors.append(f"stages must be ordered as {', '.join(STAGE_IDS)}")
            break

    if available_agents is None:
        # Import lazily so tooling can parse configs without importing the
        # Kaggle environment, while the normal validation path checks the
        # actual registry.
        from kaggriculture_agent.registry import agent_names

        known_agents = set(agent_names())
    else:
        known_agents = set(available_agents)
    if parsed.candidate_agent not in known_agents:
        errors.append(f"candidate_agent {parsed.candidate_agent!r} is not registered")
    for name, opponent in parsed.opponents.items():
        if opponent.agent not in known_agents:
            errors.append(f"opponents.{name}.agent {opponent.agent!r} is not registered")
        if opponent.weight < 0 or not math.isfinite(opponent.weight):
            errors.append(f"opponents.{name}.weight must be finite and non-negative")

    previous_pool: set[str] | None = None
    for index, stage in enumerate(parsed.stages):
        current_pool = set(stage.pool)
        missing = sorted(current_pool - set(parsed.opponents))
        if missing:
            errors.append(f"{stage.id} references unknown opponent definitions: {', '.join(missing)}")
        unknown_weights = sorted(set(stage.weights) - current_pool)
        if unknown_weights:
            errors.append(f"{stage.id} weights reference entries outside its pool: {', '.join(unknown_weights)}")
        if stage.hard_opponent_weight == 0 and not any(
            stage.weights.get(name, parsed.opponents.get(name, OpponentDefinition(name, name)).weight) > 0
            and not parsed.opponents.get(name, OpponentDefinition(name, name)).hard
            for name in stage.pool
        ):
            errors.append(f"{stage.id} has no positive effective opponent weight")
        if previous_pool is not None and not current_pool <= previous_pool:
            errors.append(f"{stage.id} must be a subset of the previous stage pool")
        previous_pool = current_pool
        if index == 3:
            specialist = stage.specialist_agent or parsed.candidate_agent
            if specialist != parsed.candidate_agent:
                errors.append(
                    f"{stage.id}.specialist_agent must equal candidate_agent {parsed.candidate_agent!r}"
                )
            if len(stage.pool) != 1:
                errors.append("stage_4 must have exactly one fixed opponent definition")
        if stage.training_games % 2 or stage.evaluation_games % 2:
            errors.append(f"{stage.id} training/evaluation game counts must be even for seat pairing")
        if not 0 <= stage.promotion.min_win_rate <= 1:
            errors.append(f"{stage.id} promotion.min_win_rate must be between 0 and 1")
        if not 0 <= stage.promotion.max_failure_rate <= 1:
            errors.append(f"{stage.id} promotion.max_failure_rate must be between 0 and 1")
        if stage.promotion.min_hard_opponent_win_rate is not None and not 0 <= stage.promotion.min_hard_opponent_win_rate <= 1:
            errors.append(f"{stage.id} promotion.min_hard_opponent_win_rate must be between 0 and 1")

    if errors:
        raise SpecializationConfigError("invalid specialization config: " + "; ".join(errors))
    return parsed


def load_config(
    path: str | Path, available_agents: Iterable[str] | None = None
) -> SpecializationConfig:
    """Load and validate a JSON specialization config."""

    config_path = Path(path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SpecializationConfigError(f"could not read config {config_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SpecializationConfigError(f"invalid JSON in {config_path}: {exc}") from exc
    return validate_config(data, available_agents)


# Explicit aliases make the public API discoverable without forcing callers to
# remember whether a config is already parsed.
load_specialization_config = load_config
validate_specialization_config = validate_config


def config_fingerprint(config: SpecializationConfig | Mapping[str, Any]) -> str:
    """Return the SHA-256 of canonical config JSON."""

    parsed = config if isinstance(config, SpecializationConfig) else SpecializationConfig.from_mapping(config)
    canonical = json.dumps(parsed.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def effective_weights(
    config: SpecializationConfig, stage: StageConfig | str | int
) -> dict[str, float]:
    """Resolve base weights and stage hard-opponent emphasis."""

    stage_config = config.stage(stage) if not isinstance(stage, StageConfig) else stage
    values: dict[str, float] = {}
    for name in stage_config.pool:
        definition = config.opponents[name]
        base = stage_config.weights.get(name, definition.weight)
        value = base * (stage_config.hard_opponent_weight if definition.hard else 1.0)
        if value < 0 or not math.isfinite(value):
            raise SpecializationConfigError(f"non-finite effective weight for {stage_config.id}.{name}")
        values[name] = value
    if not any(value > 0 for value in values.values()):
        raise SpecializationConfigError(f"{stage_config.id} has no positive effective opponent weight")
    return values


def allocate_weighted_games(
    opponents: Sequence[str],
    weights: Mapping[str, float],
    total_games: int,
    *,
    paired: bool = True,
) -> dict[str, int]:
    """Allocate an exact game count with deterministic largest remainder.

    With ``paired=True`` (the default), every opponent receives an even number
    of games so seat 0 and seat 1 can share a seed.  Ties are resolved by the
    order in ``opponents`` rather than dictionary/hash order.
    """

    if not opponents:
        raise ValueError("at least one opponent is required")
    if len(set(opponents)) != len(opponents):
        raise ValueError("opponents must be unique")
    total_games = _positive_int(total_games, "total_games")
    if paired and total_games % 2:
        raise ValueError("paired allocation requires an even total_games")
    if set(weights) != set(opponents):
        raise ValueError("weights must contain exactly one value per opponent")
    numeric = {
        name: _finite_number(weights[name], f"weights.{name}", minimum=0) for name in opponents
    }
    if sum(numeric.values()) <= 0:
        raise ValueError("at least one opponent weight must be positive")
    unit = 2 if paired else 1
    units = total_games // unit
    exact = [units * numeric[name] / sum(numeric.values()) for name in opponents]
    floors = [math.floor(value) for value in exact]
    remainder = units - sum(floors)
    ranked = sorted(
        range(len(opponents)), key=lambda index: (-(exact[index] - floors[index]), index)
    )
    for index in ranked[:remainder]:
        floors[index] += 1
    return {name: floors[index] * unit for index, name in enumerate(opponents)}


# A short alias mirrors the vocabulary used by the existing arena code and is
# useful to callers migrating from a hand-written weighted sampler.
allocate_games = allocate_weighted_games
weighted_opponent_allocation = allocate_weighted_games


def sample_opponents(
    opponents: Sequence[str],
    weights: Mapping[str, float],
    sample_count: int,
    seed: int,
    *,
    paired: bool = False,
) -> tuple[str, ...]:
    """Return a deterministic weighted sample with exact allocation counts.

    Sampling is allocation-first and shuffle-second.  This avoids the small
    run-to-run count drift of repeated floating-point ``random.choices`` while
    retaining a seeded, mixed order for rollouts.
    """

    allocation = allocate_weighted_games(opponents, weights, sample_count, paired=paired)
    sampled = [name for name in opponents for _ in range(allocation[name])]
    Random(seed).shuffle(sampled)
    return tuple(sampled)


sample_opponent_pool = sample_opponents


def _assignment_id(stage_id: str, phase: str, opponent: str, pair_index: int, seat: int) -> str:
    raw = f"{stage_id}|{phase}|{opponent}|{pair_index}|{seat}"
    digest = hashlib.blake2s(raw.encode("utf-8"), digest_size=6).hexdigest()
    return f"{stage_id}-{phase}-{opponent}-{pair_index:06d}-s{seat}-{digest}"


def build_stage_assignments(
    config: SpecializationConfig,
    stage: StageConfig | str | int,
    *,
    phase: str = "training",
    games: int | None = None,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Build deterministic seat-paired assignments for a stage phase."""

    stage_config = config.stage(stage) if not isinstance(stage, StageConfig) else stage
    if phase not in {"training", "evaluation"}:
        raise ValueError("phase must be 'training' or 'evaluation'")
    total_games = stage_config.training_games if phase == "training" else stage_config.evaluation_games
    if games is not None:
        total_games = _positive_int(games, "games")
    if total_games % 2:
        raise ValueError("stage assignments require an even game count")
    weights = effective_weights(config, stage_config)
    allocation = allocate_weighted_games(stage_config.pool, weights, total_games, paired=True)
    base_seed = stage_config.seed if seed is None else _positive_int(seed, "seed", allow_zero=True)
    # Keep training and evaluation seed ranges disjoint even when they share a
    # stage seed.  One million is far beyond the default local arena batches.
    phase_seed = base_seed + (0 if phase == "training" else 1_000_000)
    assignments: list[dict[str, Any]] = []
    pair_index = 0
    for opponent_name in stage_config.pool:
        definition = config.opponents[opponent_name]
        for local_pair in range(allocation[opponent_name] // 2):
            pair_seed = phase_seed + pair_index
            for seat in (0, 1):
                learner_first = seat == 0
                assignments.append(
                    {
                        "assignment_id": _assignment_id(
                            stage_config.id, phase, opponent_name, pair_index, seat
                        ),
                        "stage": stage_config.id,
                        "phase": phase,
                        "pair_index": pair_index,
                        "seat": seat,
                        "seed": pair_seed,
                        "learner": config.candidate_agent,
                        "learner_agent": config.candidate_agent,
                        "opponent": opponent_name,
                        "opponent_agent": definition.agent,
                        "archetype": definition.archetype,
                        "strategy_family": definition.strategy_family,
                        "hard_opponent": definition.hard,
                        "effective_weight": weights[opponent_name],
                        "player_0": config.candidate_agent if learner_first else definition.agent,
                        "player_1": definition.agent if learner_first else config.candidate_agent,
                        "swap_seats": not learner_first,
                    }
                )
            pair_index += 1
    return assignments


def build_stage_plan(
    config: SpecializationConfig,
    stage: StageConfig | str | int,
    *,
    games_override: int | None = None,
    seed_override: int | None = None,
) -> dict[str, Any]:
    """Create JSON-ready training/evaluation and Champion Arena instructions."""

    stage_config = config.stage(stage) if not isinstance(stage, StageConfig) else stage
    weights = effective_weights(config, stage_config)
    training_games = games_override or stage_config.training_games
    evaluation_games = games_override or stage_config.evaluation_games
    training = build_stage_assignments(
        config, stage_config, phase="training", games=training_games, seed=seed_override
    )
    evaluation = build_stage_assignments(
        config, stage_config, phase="evaluation", games=evaluation_games, seed=seed_override
    )
    allocation = allocate_weighted_games(stage_config.pool, weights, training_games, paired=True)
    evaluation_allocation = allocate_weighted_games(
        stage_config.pool, weights, evaluation_games, paired=True
    )
    arena_agents = sorted(
        {config.candidate_agent}
        | {config.opponents[name].agent for name in stage_config.pool}
    )
    return {
        "id": stage_config.id,
        "label": stage_config.label,
        "mode": stage_config.mode,
        "candidate_agent": config.candidate_agent,
        "pool": [
            {
                "name": name,
                "agent": config.opponents[name].agent,
                "archetype": config.opponents[name].archetype,
                "strategy_family": config.opponents[name].strategy_family,
                "hard_opponent": config.opponents[name].hard,
                "effective_weight": weights[name],
            }
            for name in stage_config.pool
        ],
        "hard_opponent_weight": stage_config.hard_opponent_weight,
        "training": {
            "games": training_games,
            "allocation": allocation,
            "assignments": training,
            "learner": config.candidate_agent,
            "learner_implementation": "registered rule agent; PPO is intentionally not implemented",
        },
        "evaluation": {
            "games": evaluation_games,
            "allocation": evaluation_allocation,
            "assignments": evaluation,
            "paired_seeds": True,
            "holdout": bool(config.evaluation.get("holdout", False)),
        },
        "champion_arena": {
            "agents": arena_agents,
            "candidate": config.candidate_agent,
            "opponents": [
                {
                    "name": name,
                    "agent": config.opponents[name].agent,
                    "games": evaluation_allocation[name],
                    "weights": weights[name],
                    "self_play": config.opponents[name].agent == config.candidate_agent,
                }
                for name in stage_config.pool
            ],
            "swap_seats": True,
            "seed": stage_config.seed,
            "schedule_source": "kaggriculture_agent.specialization",
        },
        "promotion": stage_config.promotion.to_dict(),
        "checkpoint": {
            "metadata_path": f"checkpoints/{stage_config.id}.json",
            "status": "planned",
        },
    }


def build_plan(
    config: SpecializationConfig | Mapping[str, Any],
    *,
    available_agents: Iterable[str] | None = None,
    games_override: int | None = None,
    seed_override: int | None = None,
) -> dict[str, Any]:
    """Build the complete four-stage specialization plan."""

    parsed = validate_config(config, available_agents)
    stages = [
        build_stage_plan(
            parsed, stage, games_override=games_override, seed_override=seed_override
        )
        for stage in parsed.stages
    ]
    return {
        "framework": "kaggriculture-four-stage-specialization",
        "framework_version": FRAMEWORK_VERSION,
        "config_version": parsed.version,
        "config_sha256": config_fingerprint(parsed),
        "candidate_agent": parsed.candidate_agent,
        "stage_order": list(STAGE_IDS),
        "progressive_narrowing": True,
        "ppo_implemented": False,
        "training_contract": {
            "learner": parsed.candidate_agent,
            "opponent_sampling": "deterministic largest-remainder allocation plus seeded shuffle",
            "seat_pairing": True,
            "consumer": "Champion Arena / scripts/run_arena.py",
        },
        "stages": stages,
        "evaluation": _json_safe(parsed.evaluation),
    }


@dataclass(frozen=True)
class PromotionResult:
    """Evidence-backed result of a stage promotion gate."""

    stage_id: str
    promoted: bool
    checks: Mapping[str, bool]
    reasons: tuple[str, ...]
    metrics: Mapping[str, Any]

    @property
    def eligible(self) -> bool:
        return self.promoted

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "promoted": self.promoted,
            "eligible": self.eligible,
            "checks": dict(self.checks),
            "reasons": list(self.reasons),
            "metrics": _json_safe(self.metrics),
        }


def evaluate_promotion(
    stage: StageConfig,
    metrics: Mapping[str, Any],
    *,
    previous_stage_promoted: bool = True,
) -> PromotionResult:
    """Evaluate one stage's promotion prerequisites without running training."""

    requirements = stage.promotion
    metrics = dict(metrics)

    def number(*keys: str, default: float = 0.0) -> float:
        for key in keys:
            if key in metrics and metrics[key] is not None:
                try:
                    return float(metrics[key])
                except (TypeError, ValueError):
                    return float("nan")
        return default

    game_count = number("evaluation_games", "completed_games", "games", default=0.0)
    win_rate = number("win_rate", "paired_win_rate", default=0.0)
    reward_delta = number("mean_reward_delta", "paired_reward_delta", "reward_delta", default=0.0)
    failure_rate = number("failure_rate", default=0.0)
    if "failed_games" in metrics and game_count > 0 and "failure_rate" not in metrics:
        failure_rate = number("failed_games") / game_count
    hard_rate = number("hard_opponent_win_rate", default=0.0)
    regression = number("max_opponent_win_rate_regression", default=0.0)

    checks: dict[str, bool] = {
        "previous_stage_promoted": (
            previous_stage_promoted or not requirements.require_previous_stage
        ),
        "minimum_evaluation_games": game_count >= requirements.min_evaluation_games,
        "minimum_win_rate": math.isfinite(win_rate) and win_rate >= requirements.min_win_rate,
        "minimum_mean_reward_delta": math.isfinite(reward_delta)
        and reward_delta >= requirements.min_mean_reward_delta,
        "maximum_failure_rate": math.isfinite(failure_rate)
        and failure_rate <= requirements.max_failure_rate,
    }
    if requirements.min_hard_opponent_win_rate is not None:
        checks["minimum_hard_opponent_win_rate"] = (
            math.isfinite(hard_rate) and hard_rate >= requirements.min_hard_opponent_win_rate
        )
    if requirements.max_opponent_win_rate_regression is not None:
        checks["maximum_opponent_win_rate_regression"] = (
            math.isfinite(regression)
            and regression <= requirements.max_opponent_win_rate_regression
        )
    reasons = tuple(name for name, passed in checks.items() if not passed)
    return PromotionResult(stage.id, not reasons, checks, reasons, metrics)


def meets_promotion_prerequisites(
    stage: StageConfig,
    metrics: Mapping[str, Any],
    *,
    previous_stage_promoted: bool = True,
) -> bool:
    """Boolean convenience wrapper around :func:`evaluate_promotion`."""

    return evaluate_promotion(
        stage, metrics, previous_stage_promoted=previous_stage_promoted
    ).promoted


check_promotion_prerequisites = meets_promotion_prerequisites


def build_run_manifest(
    config: SpecializationConfig | Mapping[str, Any],
    plan: Mapping[str, Any] | None = None,
    *,
    run_id: str | None = None,
    config_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create resumable run metadata for a specialization plan."""

    parsed = validate_config(config)
    if plan is None:
        plan = build_plan(parsed)
    fingerprint = config_fingerprint(parsed)
    if run_id is None:
        run_id = f"specialization-{fingerprint[:12]}"
    if not _IDENTIFIER.fullmatch(run_id):
        raise ValueError("run_id must be a simple identifier")
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    return {
        "manifest_version": 1,
        "framework": "kaggriculture-four-stage-specialization",
        "framework_version": FRAMEWORK_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "updated_at": created_at,
        "config_sha256": fingerprint,
        "config_path": str(Path(config_path).resolve()) if config_path else None,
        "output_dir": str(Path(output_dir).resolve()) if output_dir else None,
        "candidate_agent": parsed.candidate_agent,
        "ppo_implemented": False,
        "status": "planned",
        "stages": {
            stage.id: {
                "status": "planned",
                "training_games": stage.training_games,
                "evaluation_games": stage.evaluation_games,
                "checkpoint_metadata": f"checkpoints/{stage.id}.json",
                "promotion": stage.promotion.to_dict(),
            }
            for stage in parsed.stages
        },
        "checkpoints": {},
        "plan_sha256": hashlib.sha256(
            json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
                "utf-8"
            )
        ).hexdigest(),
    }


def build_checkpoint_metadata(
    config: SpecializationConfig | Mapping[str, Any],
    stage: StageConfig | str | int,
    *,
    plan: Mapping[str, Any] | None = None,
    checkpoint_path: str | Path | None = None,
    parent_checkpoint: str | Path | None = None,
    metrics: Mapping[str, Any] | None = None,
    status: str = "planned",
) -> dict[str, Any]:
    """Create metadata for a stage checkpoint; no model files are created."""

    parsed = validate_config(config)
    stage_config = parsed.stage(stage) if not isinstance(stage, StageConfig) else stage
    if plan is None:
        plan = build_plan(parsed)
    path = Path(checkpoint_path) if checkpoint_path else None
    artifact_sha256 = None
    if path is not None and path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        artifact_sha256 = digest.hexdigest()
    plan_stage = next(item for item in plan["stages"] if item["id"] == stage_config.id)
    return {
        "metadata_version": 1,
        "framework_version": FRAMEWORK_VERSION,
        "stage_id": stage_config.id,
        "stage_label": stage_config.label,
        "status": status,
        "candidate_agent": parsed.candidate_agent,
        "config_sha256": config_fingerprint(parsed),
        "plan_stage_sha256": hashlib.sha256(
            json.dumps(plan_stage, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
                "utf-8"
            )
        ).hexdigest(),
        "checkpoint_path": str(path.resolve()) if path else None,
        "checkpoint_sha256": artifact_sha256,
        "parent_checkpoint": str(Path(parent_checkpoint).resolve()) if parent_checkpoint else None,
        "metrics": _json_safe(dict(metrics or {})),
        "promotion": stage_config.promotion.to_dict(),
        "ppo_implemented": False,
    }


def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    """Write stable, human-readable JSON and return the resolved path."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(_json_safe(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination


def read_json(path: str | Path) -> dict[str, Any]:
    """Read a JSON object emitted by the planner."""

    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def write_run_manifest(path: str | Path, manifest: Mapping[str, Any]) -> Path:
    """Persist a run manifest."""

    return write_json(path, manifest)


def write_checkpoint_metadata(path: str | Path, metadata: Mapping[str, Any]) -> Path:
    """Persist checkpoint metadata without touching a checkpoint artifact."""

    return write_json(path, metadata)


__all__ = [
    "CONFIG_VERSION",
    "FRAMEWORK_VERSION",
    "STAGE_IDS",
    "OpponentDefinition",
    "PromotionPrerequisites",
    "StageConfig",
    "SpecializationConfig",
    "SpecializationConfigError",
    "PromotionResult",
    "validate_config",
    "validate_specialization_config",
    "load_config",
    "load_specialization_config",
    "config_fingerprint",
    "effective_weights",
    "allocate_weighted_games",
    "allocate_games",
    "weighted_opponent_allocation",
    "sample_opponents",
    "sample_opponent_pool",
    "build_stage_assignments",
    "build_stage_plan",
    "build_plan",
    "evaluate_promotion",
    "meets_promotion_prerequisites",
    "check_promotion_prerequisites",
    "build_run_manifest",
    "build_checkpoint_metadata",
    "write_json",
    "read_json",
    "write_run_manifest",
    "write_checkpoint_metadata",
]
