"""Persistent promotion arena for the registered Kaggriculture agents.

The local arena is intentionally a small, stateless match runner.  This module
adds the stateful part needed to keep one incumbent for each strategy slot and
to promote a candidate only after it has beaten the current pool of
incumbents.  Games are still created and executed by :mod:`local_arena`; in
particular, schedule ids remain the single source of truth for resuming a run.

The on-disk format is deliberately boring:

``state.json``
    Sorted JSON containing the current champion per slot and promotion history.
``games.csv``
    The normal local-arena game rows.  Completed rows whose complete
    ``GameSpec`` matches the new schedule are safe to reuse.
``promotion_report.csv``
    One deterministic row per candidate evaluated in the current generation.

Both the state and report are written through a temporary file followed by
``os.replace``.  That matters when a long arena is interrupted while another
process is reading its results.
"""

from __future__ import annotations

import csv
import json
import math
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from kaggriculture_agent.local_arena import (
    GAME_FIELDS,
    GameResult,
    GameSpec,
    build_schedule,
    run_games,
)

SCHEMA_VERSION = 1
DEFAULT_GAMES_PER_MATCHUP = 2
DEFAULT_SEED = 1000
DEFAULT_SWAP_SEATS = True
DEFAULT_WORKERS = 1
DEFAULT_PROMOTION_THRESHOLD = 0.5

PROMOTION_FIELDS = (
    "generation",
    "slot",
    "candidate",
    "incumbent",
    "opponents",
    "scheduled_games",
    "completed_games",
    "failed_games",
    "mean_matchup_score",
    "eligible",
    "promoted",
    "new_champion",
)


@dataclass(frozen=True)
class ArchetypeSlot:
    """A named slot and its current incumbent."""

    name: str
    champion: str


@dataclass(frozen=True)
class Candidate:
    """A candidate and the slot it may replace."""

    name: str
    slot: str


@dataclass(frozen=True)
class ChampionArenaConfig:
    """Validated configuration for one champion-arena invocation."""

    slots: tuple[ArchetypeSlot, ...]
    candidates: tuple[Candidate, ...]
    games_per_matchup: int = DEFAULT_GAMES_PER_MATCHUP
    seed: int = DEFAULT_SEED
    swap_seats: bool = DEFAULT_SWAP_SEATS
    workers: int = DEFAULT_WORKERS
    output: Path = Path("outputs/champion_arena")
    promotion_threshold: float = DEFAULT_PROMOTION_THRESHOLD

    def __post_init__(self) -> None:
        if not self.slots:
            raise ValueError("at least one champion slot is required")
        slot_names = [slot.name for slot in self.slots]
        if len(slot_names) != len(set(slot_names)):
            raise ValueError("slot names must be unique")
        if any(not slot.name or not slot.champion for slot in self.slots):
            raise ValueError("slot names and champions must be non-empty")
        candidate_names = [candidate.name for candidate in self.candidates]
        if len(candidate_names) != len(set(candidate_names)):
            raise ValueError("candidate names must be unique")
        unknown_slots = sorted(
            {candidate.slot for candidate in self.candidates} - set(slot_names)
        )
        if unknown_slots:
            raise ValueError(
                "candidate(s) refer to unknown slot(s): " + ", ".join(unknown_slots)
            )
        if self.games_per_matchup < 1:
            raise ValueError("games_per_matchup must be positive")
        if self.workers < 1:
            raise ValueError("workers must be positive")
        if not math.isfinite(self.promotion_threshold) or not (
            0.0 <= self.promotion_threshold <= 1.0
        ):
            raise ValueError("promotion_threshold must be between 0 and 1")

    @property
    def slot_map(self) -> dict[str, str]:
        return {slot.name: slot.champion for slot in self.slots}

    def with_overrides(
        self,
        *,
        games_per_matchup: int | None = None,
        seed: int | None = None,
        swap_seats: bool | None = None,
        workers: int | None = None,
        output: Path | None = None,
    ) -> "ChampionArenaConfig":
        """Return a copy with command-line overrides applied."""

        return replace(
            self,
            games_per_matchup=(
                self.games_per_matchup
                if games_per_matchup is None
                else games_per_matchup
            ),
            seed=self.seed if seed is None else seed,
            swap_seats=self.swap_seats if swap_seats is None else swap_seats,
            workers=self.workers if workers is None else workers,
            output=self.output if output is None else output,
        )


# A shorter name is useful for callers that think of a slot as a schema-level
# archetype.  Keep the descriptive class above as the canonical API.
SlotConfig = ArchetypeSlot
CandidateConfig = Candidate


@dataclass(frozen=True)
class CandidateEvaluation:
    """Outcome of evaluating one candidate against all current champions."""

    generation: int
    slot: str
    candidate: str
    incumbent: str
    opponents: tuple[str, ...]
    scheduled_games: int
    completed_games: int
    failed_games: int
    mean_matchup_score: float
    eligible: bool
    promoted: bool = False
    new_champion: str = ""

    def csv_row(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "slot": self.slot,
            "candidate": self.candidate,
            "incumbent": self.incumbent,
            "opponents": "|".join(self.opponents),
            "scheduled_games": self.scheduled_games,
            "completed_games": self.completed_games,
            "failed_games": self.failed_games,
            "mean_matchup_score": self.mean_matchup_score,
            "eligible": self.eligible,
            "promoted": self.promoted,
            "new_champion": self.new_champion,
        }


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"expected a boolean, got {value!r}")


def _as_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc


def _slot_entries(raw_slots: Any) -> list[tuple[str, Any]]:
    if isinstance(raw_slots, Mapping):
        return [(str(name), value) for name, value in raw_slots.items()]
    if isinstance(raw_slots, list):
        entries: list[tuple[str, Any]] = []
        for entry in raw_slots:
            if not isinstance(entry, Mapping):
                raise ValueError("slot list entries must be objects")
            name = entry.get("name", entry.get("slot", entry.get("archetype")))
            if not name:
                raise ValueError("slot entries require a name")
            entries.append((str(name), entry))
        return entries
    raise ValueError("slots/archetypes must be an object or list")


def _parse_slot(name: str, raw: Any) -> tuple[ArchetypeSlot, list[str]]:
    if isinstance(raw, str):
        return ArchetypeSlot(name, raw), []
    if not isinstance(raw, Mapping):
        raise ValueError(f"slot {name!r} must be a champion name or object")
    champion = raw.get("champion", raw.get("incumbent", raw.get("agent")))
    if not isinstance(champion, str) or not champion:
        raise ValueError(f"slot {name!r} requires a champion")
    candidates = raw.get("candidates", [])
    if isinstance(candidates, str):
        candidates = [candidates]
    if not isinstance(candidates, list) or any(not isinstance(item, str) for item in candidates):
        raise ValueError(f"slot {name!r} candidates must be a list of names")
    return ArchetypeSlot(name, champion), list(candidates)


def _parse_candidates(
    raw_candidates: Any,
    slot_names: Sequence[str],
    candidate_slots: Mapping[str, Any] | None,
) -> list[Candidate]:
    """Parse the deliberately permissive candidate config forms.

    The documented form is a list of ``{"name": ..., "slot": ...}``
    objects.  A list of strings is also accepted when there is one slot, and
    a mapping of candidate name to slot is convenient for small experiments.
    """

    slot_lookup = {str(name): str(name) for name in slot_names}
    result: list[Candidate] = []
    if raw_candidates is None:
        raw_candidates = []
    if isinstance(raw_candidates, Mapping):
        items = list(raw_candidates.items())
        for name, value in items:
            if isinstance(value, Mapping):
                slot = value.get("slot", value.get("archetype"))
            else:
                slot = value
            if slot is None and candidate_slots is not None:
                slot = candidate_slots.get(str(name))
            if slot is None:
                if len(slot_names) != 1:
                    raise ValueError(f"candidate {name!r} requires a slot")
                slot = slot_names[0]
            result.append(Candidate(str(name), str(slot)))
    elif isinstance(raw_candidates, list):
        for item in raw_candidates:
            if isinstance(item, str):
                name = item
                slot = None
            elif isinstance(item, Mapping):
                name = item.get("name", item.get("agent", item.get("candidate")))
                slot = item.get("slot", item.get("archetype"))
            else:
                raise ValueError("candidate list entries must be names or objects")
            if not isinstance(name, str) or not name:
                raise ValueError("candidate entries require a name")
            if slot is None and candidate_slots is not None:
                slot = candidate_slots.get(name)
            if slot is None:
                if len(slot_names) != 1:
                    raise ValueError(f"candidate {name!r} requires a slot")
                slot = slot_names[0]
            result.append(Candidate(name, str(slot)))
    elif raw_candidates:
        raise ValueError("candidates must be a list, object, or omitted")
    del slot_lookup  # Kept above only to make the accepted slot names explicit.
    return result


def config_from_mapping(
    payload: Mapping[str, Any],
    *,
    base_dir: Path | None = None,
) -> ChampionArenaConfig:
    """Build a :class:`ChampionArenaConfig` from a JSON-compatible mapping."""

    raw_slots = payload.get("slots", payload.get("archetypes"))
    if raw_slots is None:
        raise ValueError("config requires a slots or archetypes object")
    slots: list[ArchetypeSlot] = []
    embedded_candidates: list[Candidate] = []
    entries = _slot_entries(raw_slots)
    for name, raw in entries:
        slot, candidate_names = _parse_slot(name, raw)
        slots.append(slot)
        embedded_candidates.extend(Candidate(candidate, name) for candidate in candidate_names)

    raw_candidate_slots = payload.get("candidate_slots")
    if raw_candidate_slots is not None and not isinstance(raw_candidate_slots, Mapping):
        raise ValueError("candidate_slots must be an object")
    candidates = embedded_candidates + _parse_candidates(
        payload.get("candidates"),
        [slot.name for slot in slots],
        raw_candidate_slots,
    )
    # Embedded and top-level declarations may intentionally overlap; retain
    # the first declaration but reject conflicting slot assignments.
    unique_candidates: list[Candidate] = []
    by_name: dict[str, Candidate] = {}
    for candidate in candidates:
        previous = by_name.get(candidate.name)
        if previous is not None:
            if previous.slot != candidate.slot:
                raise ValueError(
                    f"candidate {candidate.name!r} is assigned to both "
                    f"{previous.slot!r} and {candidate.slot!r}"
                )
            continue
        by_name[candidate.name] = candidate
        unique_candidates.append(candidate)

    output_raw = payload.get("output", "outputs/champion_arena")
    output = Path(str(output_raw))
    if base_dir is not None and not output.is_absolute():
        output = (base_dir / output).resolve()

    return ChampionArenaConfig(
        slots=tuple(slots),
        candidates=tuple(unique_candidates),
        games_per_matchup=_as_int(
            payload.get("games_per_matchup", payload.get("games_per_pair", DEFAULT_GAMES_PER_MATCHUP)),
            "games_per_matchup",
        ),
        seed=_as_int(payload.get("seed", DEFAULT_SEED), "seed"),
        swap_seats=_as_bool(payload.get("swap_seats"), default=DEFAULT_SWAP_SEATS),
        workers=_as_int(payload.get("workers", DEFAULT_WORKERS), "workers"),
        output=output,
        promotion_threshold=float(
            payload.get("promotion_threshold", DEFAULT_PROMOTION_THRESHOLD)
        ),
    )


def load_config(path: Path) -> ChampionArenaConfig:
    """Read and validate a champion-arena JSON config."""

    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, Mapping):
        raise ValueError("champion arena config must be a JSON object")
    return config_from_mapping(payload, base_dir=path.parent)


def build_champion_schedule(
    candidates: Iterable[str],
    champions: Iterable[str],
    games_per_matchup: int,
    seed: int,
    swap_seats: bool = True,
) -> list[GameSpec]:
    """Build only candidate-vs-champion games from the stable local schedule.

    ``build_schedule`` creates a complete round-robin.  Filtering its output
    keeps the exact same deterministic game-id and seed scheme while avoiding
    unnecessary candidate-vs-candidate and champion-vs-champion games.
    """

    candidate_names = tuple(dict.fromkeys(str(name) for name in candidates))
    champion_names = tuple(dict.fromkeys(str(name) for name in champions))
    if not candidate_names or not champion_names:
        return []
    all_agents = sorted(set(candidate_names) | set(champion_names))
    if len(all_agents) < 2:
        # A candidate that is already the only current champion has no
        # meaningful opponent.  Keep the invocation a safe no-op instead of
        # asking local_arena.build_schedule to construct a one-agent round.
        return []
    full_schedule = build_schedule(all_agents, games_per_matchup, seed, swap_seats)
    candidate_set = set(candidate_names)
    champion_set = set(champion_names)
    return [
        spec
        for spec in full_schedule
        if (
            spec.agent_a in candidate_set
            and spec.agent_b in champion_set
        )
        or (
            spec.agent_b in candidate_set
            and spec.agent_a in champion_set
        )
    ]


# A concise alias is useful in notebooks and keeps the public vocabulary close
# to ``local_arena.build_schedule``.
build_schedule_for_champions = build_champion_schedule


def matchup_score(candidate: str, result: GameResult) -> float | None:
    """Return candidate's 1/0.5/0 score, or ``None`` for a failed game."""

    if result.status != "completed" or result.reward_0 is None or result.reward_1 is None:
        return None
    if result.player_0 == candidate:
        candidate_reward, opponent_reward = result.reward_0, result.reward_1
    elif result.player_1 == candidate:
        candidate_reward, opponent_reward = result.reward_1, result.reward_0
    else:
        return None
    if candidate_reward > opponent_reward:
        return 1.0
    if candidate_reward < opponent_reward:
        return 0.0
    return 0.5


def mean_matchup_score(candidate: str, results: Iterable[GameResult]) -> float:
    """Compute the candidate's mean win/draw/loss score over completed games."""

    scores = [
        score
        for result in results
        if (score := matchup_score(candidate, result)) is not None
    ]
    return sum(scores) / len(scores) if scores else 0.0


def evaluate_candidate(
    candidate: Candidate | str,
    schedule: Sequence[GameSpec],
    results: Mapping[str, GameResult] | Iterable[GameResult],
    champions: Iterable[str],
    *,
    generation: int = 0,
    incumbent: str = "",
    promotion_threshold: float = DEFAULT_PROMOTION_THRESHOLD,
) -> CandidateEvaluation:
    """Evaluate one candidate and mark it eligible only with no failed games."""

    if isinstance(candidate, str):
        candidate_name = candidate
        slot = ""
    else:
        candidate_name = candidate.name
        slot = candidate.slot
    if isinstance(results, Mapping):
        result_by_id = dict(results)
    else:
        result_by_id = {result.game_id: result for result in results}
    champion_set = set(champions)
    candidate_specs = [
        spec
        for spec in schedule
        if candidate_name in {spec.agent_a, spec.agent_b}
        and ({spec.agent_a, spec.agent_b} & champion_set)
    ]
    candidate_results = [
        result_by_id[spec.game_id]
        for spec in candidate_specs
        if spec.game_id in result_by_id
    ]
    completed = sum(matchup_score(candidate_name, result) is not None for result in candidate_results)
    scheduled_games = len(candidate_specs)
    failed_games = scheduled_games - completed
    score = mean_matchup_score(candidate_name, candidate_results)
    opponents = tuple(
        sorted(
            {
                spec.agent_b if spec.agent_a == candidate_name else spec.agent_a
                for spec in candidate_specs
                if (spec.agent_b if spec.agent_a == candidate_name else spec.agent_a)
                in champion_set
            }
        )
    )
    eligible = scheduled_games > 0 and failed_games == 0
    # The promotion threshold is intentionally strict: an all-draw candidate
    # (score 0.5) does not displace a champion by default.
    eligible = eligible and score > promotion_threshold
    return CandidateEvaluation(
        generation=generation,
        slot=slot,
        candidate=candidate_name,
        incumbent=incumbent,
        opponents=opponents,
        scheduled_games=scheduled_games,
        completed_games=completed,
        failed_games=failed_games,
        mean_matchup_score=round(score, 12),
        eligible=eligible,
    )


def _initial_state(config: ChampionArenaConfig) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generation": 0,
        "slots": config.slot_map,
        "champions": config.slot_map,
        "history": [],
    }


def _state_champions(raw: Mapping[str, Any], config: ChampionArenaConfig) -> dict[str, str]:
    slots_raw = raw.get("slots", raw.get("champions"))
    if not isinstance(slots_raw, Mapping):
        raise ValueError("state.json requires a slots object")
    champions: dict[str, str] = {}
    for slot in config.slots:
        value = slots_raw.get(slot.name)
        if isinstance(value, Mapping):
            value = value.get("champion", value.get("incumbent"))
        if not isinstance(value, str) or not value:
            raise ValueError(f"state.json has no champion for slot {slot.name!r}")
        champions[slot.name] = value
    unknown = set(slots_raw) - set(champions)
    if unknown:
        raise ValueError("state.json contains unknown slot(s): " + ", ".join(sorted(unknown)))
    return champions


def load_state(path: Path, config: ChampionArenaConfig) -> dict[str, Any]:
    """Load state or create a deterministic initial state when absent."""

    if not path.exists():
        return _initial_state(config)
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, Mapping):
        raise ValueError("state.json must be an object")
    champions = _state_champions(raw, config)
    try:
        generation = int(raw.get("generation", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("state generation must be an integer") from exc
    if generation < 0:
        raise ValueError("state generation cannot be negative")
    history = raw.get("history", [])
    if not isinstance(history, list):
        raise ValueError("state history must be a list")
    return {
        "schema_version": int(raw.get("schema_version", SCHEMA_VERSION)),
        "generation": generation,
        "slots": champions,
        "champions": champions,
        "history": history,
    }


def _atomic_write(path: Path, writer: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_state(path: Path, state: Mapping[str, Any]) -> None:
    """Atomically write canonical, sorted JSON state."""

    payload = dict(state)
    slots = payload.get("slots", {})
    if isinstance(slots, Mapping):
        canonical_slots = {str(key): slots[key] for key in sorted(slots)}
        payload["slots"] = canonical_slots
        payload["champions"] = canonical_slots
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("generation", 0)
    payload.setdefault("history", [])

    def dump(handle: Any) -> None:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")

    _atomic_write(path, dump)


def _read_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return {
            str(row["game_id"]): dict(row)
            for row in reader
            if row.get("game_id")
        }


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _row_matches_spec(row: Mapping[str, str], spec: GameSpec) -> bool:
    if row.get("status") != "completed":
        return False
    if row.get("game_id") != spec.game_id:
        return False
    if _to_int(row.get("seed")) != spec.seed:
        return False
    for field, expected in (
        ("player_0", spec.player_0),
        ("player_1", spec.player_1),
        ("agent_a", spec.agent_a),
        ("agent_b", spec.agent_b),
    ):
        actual = row.get(field)
        if actual not in (None, "", expected):
            return False
    return _to_float(row.get("reward_0")) is not None and _to_float(row.get("reward_1")) is not None


def _result_from_row(row: Mapping[str, str], spec: GameSpec) -> GameResult | None:
    if not _row_matches_spec(row, spec):
        return None
    reward_0 = _to_float(row.get("reward_0"))
    reward_1 = _to_float(row.get("reward_1"))
    if reward_0 is None or reward_1 is None:
        return None
    return GameResult(
        game_id=spec.game_id,
        seed=spec.seed,
        player_0=spec.player_0,
        player_1=spec.player_1,
        reward_0=reward_0,
        reward_1=reward_1,
        winner=row.get("winner", ""),
        steps=_to_int(row.get("steps")) or 0,
        elapsed_seconds=_to_float(row.get("elapsed_seconds")) or 0.0,
        status="completed",
        error="",
        agent_a=spec.agent_a,
        agent_b=spec.agent_b,
    )


def _write_games(path: Path, schedule: Sequence[GameSpec], results: Mapping[str, GameResult]) -> None:
    def write(handle: Any) -> None:
        writer = csv.DictWriter(handle, fieldnames=GAME_FIELDS)
        writer.writeheader()
        writer.writerows(
            results[spec.game_id].csv_row()
            for spec in schedule
            if spec.game_id in results
        )

    _atomic_write(path, write)


def write_promotion_report(path: Path, evaluations: Iterable[CandidateEvaluation]) -> None:
    """Atomically write a stable CSV report in candidate declaration order."""

    rows = list(evaluations)

    def write(handle: Any) -> None:
        writer = csv.DictWriter(handle, fieldnames=PROMOTION_FIELDS)
        writer.writeheader()
        writer.writerows(evaluation.csv_row() for evaluation in rows)

    _atomic_write(path, write)


def _apply_promotions(
    state: Mapping[str, Any],
    evaluations: Sequence[CandidateEvaluation],
) -> tuple[dict[str, Any], list[CandidateEvaluation], list[dict[str, str]]]:
    champions = dict(state["slots"])
    updated = list(evaluations)
    promotions: list[dict[str, str]] = []
    for slot in sorted({evaluation.slot for evaluation in evaluations}):
        choices = [
            evaluation
            for evaluation in evaluations
            if (
                evaluation.slot == slot
                and evaluation.eligible
                and evaluation.candidate != champions[slot]
            )
        ]
        if not choices:
            continue
        winner = sorted(choices, key=lambda item: (-item.mean_matchup_score, item.candidate))[0]
        incumbent = champions[slot]
        champions[slot] = winner.candidate
        promotions.append(
            {
                "slot": slot,
                "from": incumbent,
                "to": winner.candidate,
                "mean_matchup_score": str(winner.mean_matchup_score),
            }
        )
        updated = [
            replace(
                evaluation,
                promoted=evaluation is winner,
                new_champion=winner.candidate,
            )
            if evaluation.slot == slot
            else evaluation
            for evaluation in updated
        ]
    return {**state, "slots": champions, "champions": champions}, updated, promotions


def run_champion_arena(
    config: ChampionArenaConfig,
    *,
    output: Path | None = None,
    state_path: Path | None = None,
    games_path: Path | None = None,
    report_path: Path | None = None,
    resume: bool = True,
    dry_run: bool = False,
    smoke: bool = False,
    games_per_matchup: int | None = None,
    workers: int | None = None,
) -> dict[str, Any]:
    """Run one persistent champion-arena generation.

    A candidate is eligible only when every scheduled game against every
    current champion completed.  Eligible candidates with a mean score above
    ``promotion_threshold`` are promoted; when multiple candidates target one
    slot, the highest score wins with a lexical tie-break.
    """

    effective_games = 1 if smoke else games_per_matchup
    effective_workers = 1 if smoke else workers
    config = config.with_overrides(
        games_per_matchup=effective_games,
        workers=effective_workers,
        output=output,
    )
    output_dir = config.output
    state_path = state_path or output_dir / "state.json"
    games_path = games_path or output_dir / "games.csv"
    report_path = report_path or output_dir / "promotion_report.csv"

    state = load_state(state_path, config)
    champions = list(state["slots"].values())
    candidate_names = [candidate.name for candidate in config.candidates]
    schedule = build_champion_schedule(
        candidate_names,
        champions,
        config.games_per_matchup,
        config.seed,
        config.swap_seats,
    )
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generation": state["generation"],
        "scheduled_games": len(schedule),
        "games_per_matchup": config.games_per_matchup,
        "seed": config.seed,
        "swap_seats": config.swap_seats,
        "workers": config.workers,
        "dry_run": dry_run,
        "smoke": smoke,
        "reused_games": 0,
        "executed_games": 0,
        "completed_games": 0,
        "failed_games": 0,
        "promotions": [],
    }
    if dry_run:
        summary["champions"] = dict(state["slots"])
        return summary

    output_dir.mkdir(parents=True, exist_ok=True)
    existing_rows = _read_rows(games_path) if resume else {}
    reusable: dict[str, GameResult] = {}
    for spec in schedule:
        if spec.game_id in existing_rows:
            result = _result_from_row(existing_rows[spec.game_id], spec)
            if result is not None:
                reusable[spec.game_id] = result
    pending = [spec for spec in schedule if spec.game_id not in reusable]
    result_by_id = dict(reusable)
    checkpoint_every = max(1, config.workers * 2)
    new_results: list[GameResult] = []
    for result in run_games(pending, config.workers):
        new_results.append(result)
        result_by_id[result.game_id] = result
        if len(new_results) % checkpoint_every == 0:
            _write_games(games_path, schedule, result_by_id)
    # A worker failure should never accidentally turn an incomplete candidate
    # into a promotion.  The normal runner yields one result per spec, but a
    # defensive synthetic failure handles an interrupted/short iterator too.
    for spec in schedule:
        if spec.game_id not in result_by_id:
            result_by_id[spec.game_id] = GameResult(
                game_id=spec.game_id,
                seed=spec.seed,
                player_0=spec.player_0,
                player_1=spec.player_1,
                reward_0=None,
                reward_1=None,
                winner="",
                steps=0,
                elapsed_seconds=0.0,
                status="failed",
                error="missing result",
                agent_a=spec.agent_a,
                agent_b=spec.agent_b,
            )
    _write_games(games_path, schedule, result_by_id)

    evaluations = [
        evaluate_candidate(
            candidate,
            schedule,
            result_by_id,
            champions,
            generation=state["generation"],
            incumbent=state["slots"][candidate.slot],
            promotion_threshold=config.promotion_threshold,
        )
        for candidate in config.candidates
    ]
    updated_state, evaluations, promotions = _apply_promotions(state, evaluations)
    if promotions:
        updated_state["generation"] = state["generation"] + 1
        updated_state["history"] = [
            *state.get("history", []),
            {
                "generation": updated_state["generation"],
                "promotions": promotions,
            },
        ]
    else:
        updated_state["generation"] = state["generation"]
        updated_state["history"] = state.get("history", [])
    write_promotion_report(report_path, evaluations)
    write_state(state_path, updated_state)

    summary.update(
        {
            "generation": updated_state["generation"],
            "reused_games": len(reusable),
            "executed_games": len(new_results),
            "completed_games": sum(
                result.status == "completed" for result in result_by_id.values()
            ),
            "failed_games": sum(
                result.status != "completed" for result in result_by_id.values()
            ),
            "promotions": promotions,
            "champions": dict(updated_state["slots"]),
            "state_path": str(state_path),
            "games_path": str(games_path),
            "report_path": str(report_path),
        }
    )
    return summary


__all__ = [
    "ArchetypeSlot",
    "Candidate",
    "CandidateConfig",
    "CandidateEvaluation",
    "ChampionArenaConfig",
    "PROMOTION_FIELDS",
    "SlotConfig",
    "build_champion_schedule",
    "build_schedule_for_champions",
    "config_from_mapping",
    "evaluate_candidate",
    "load_config",
    "load_state",
    "matchup_score",
    "mean_matchup_score",
    "run_champion_arena",
    "write_promotion_report",
    "write_state",
]
