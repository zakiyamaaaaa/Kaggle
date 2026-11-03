"""Population-based evaluation built on the deterministic local Arena."""

from __future__ import annotations

import hashlib
import inspect
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from kaggriculture_agent.local_arena import (
    MATCHUP_FIELDS,
    GameResult,
    GameSpec,
    build_schedule,
    dump_json,
    matchup_rows,
    percentile,
    read_completed,
    recommended_workers,
    run_games,
    system_info,
    write_csv,
    write_games,
)
from kaggriculture_agent.population import PopulationConfig, population_fingerprint
from kaggriculture_agent.rating import estimate_ratings
from kaggriculture_agent.registry import get_agent

RATING_FIELDS = (
    "agent",
    "mu",
    "sigma",
    "lcb",
    "interval_low",
    "interval_high",
    "games",
    "errors",
)
PROFILE_FIELDS = (
    "opponent",
    "family",
    "archetype",
    "configured_weight",
    "density",
    "density_weight",
    "effective_weight",
    "paired_seeds",
    "candidate_score_rate",
)


@dataclass(frozen=True)
class PopulationGate:
    candidate: str
    reference: str
    completed_fraction: float
    errors: int
    lcb_margin: float
    family_balanced_score: float
    passed: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate,
            "reference": self.reference,
            "completed_fraction": self.completed_fraction,
            "errors": self.errors,
            "lcb_margin": self.lcb_margin,
            "family_balanced_score": self.family_balanced_score,
            "passed": self.passed,
            "reasons": list(self.reasons),
        }


def build_population_schedule(
    candidate: str,
    config: PopulationConfig,
    tier_name: str,
) -> list[GameSpec]:
    """Create deterministic candidate-vs-population paired games."""

    tier = config.tier(tier_name)
    opponents = [member.agent for member in config.members if member.agent != candidate]
    if not opponents:
        raise ValueError("population contains no opponent distinct from the candidate")
    # Reuse the exact same seed block for every opponent.  This is intentional:
    # it makes the per-seed outcome profiles comparable across policies while
    # build_schedule still provides stable, pair-specific ids.
    schedule: list[GameSpec] = []
    for opponent in opponents:
        schedule.extend(
            build_schedule(
                [candidate, opponent], tier.seeds, tier.seed_start, swap_seats=True
            )
        )
    return schedule


def _score(candidate: str, result: GameResult) -> float | None:
    if result.status != "completed" or result.reward_0 is None or result.reward_1 is None:
        return None
    if result.player_0 == candidate:
        own, other = result.reward_0, result.reward_1
    elif result.player_1 == candidate:
        own, other = result.reward_1, result.reward_0
    else:
        return None
    return 1.0 if own > other else 0.0 if own < other else 0.5


def outcome_profiles(
    candidate: str,
    config: PopulationConfig,
    results: Sequence[GameResult],
    *,
    bandwidth: float = 0.25,
) -> list[dict[str, Any]]:
    """Estimate inverse-density weights from paired outcome profiles.

    Each opponent is represented by its candidate score for every shared seed.
    Similar vectors have high kernel density and therefore receive less weight.
    Missing/failed seeds are ignored pairwise instead of being imputed.
    """

    if not math.isfinite(bandwidth) or bandwidth <= 0:
        raise ValueError("bandwidth must be finite and positive")
    member_by_agent = {member.agent: member for member in config.members}
    values: dict[str, dict[int, list[float]]] = {
        agent: {} for agent in member_by_agent if agent != candidate
    }
    for result in results:
        opponent = (
            result.player_1
            if result.player_0 == candidate
            else result.player_0
            if result.player_1 == candidate
            else None
        )
        score = _score(candidate, result)
        if opponent in values and score is not None:
            values[opponent].setdefault(result.seed, []).append(score)
    profiles = {
        opponent: {seed: sum(scores) / len(scores) for seed, scores in by_seed.items()}
        for opponent, by_seed in values.items()
    }
    densities: dict[str, float] = {}
    for left, left_values in profiles.items():
        density = 0.0
        for right_values in profiles.values():
            overlap = set(left_values) & set(right_values)
            if not overlap:
                continue
            distance = sum(abs(left_values[s] - right_values[s]) for s in overlap) / len(overlap)
            density += math.exp(-((distance / bandwidth) ** 2) / 2.0)
        densities[left] = density or 1.0
    inverse = {name: 1.0 / density for name, density in densities.items()}
    mean_inverse = sum(inverse.values()) / len(inverse) if inverse else 1.0

    rows = []
    for opponent in sorted(profiles):
        member = member_by_agent[opponent]
        scores = list(profiles[opponent].values())
        density_weight = inverse[opponent] / mean_inverse
        rows.append(
            {
                "opponent": opponent,
                "family": member.family,
                "archetype": member.archetype,
                "configured_weight": member.weight,
                "density": densities[opponent],
                "density_weight": density_weight,
                "effective_weight": member.weight * density_weight,
                "paired_seeds": len(scores),
                "candidate_score_rate": sum(scores) / len(scores) if scores else None,
            }
        )
    return rows


def evaluate_gate(
    candidate: str,
    reference: str,
    schedule: Sequence[GameSpec],
    results: Sequence[GameResult],
    rating_result: Mapping[str, Any],
    profiles: Sequence[Mapping[str, Any]],
    *,
    min_lcb_margin: float = 0.0,
) -> PopulationGate:
    completed = sum(result.status == "completed" for result in results)
    completed_fraction = completed / len(schedule) if schedule else 0.0
    ratings = {row["agent"]: row for row in rating_result.get("ratings", [])}
    candidate_rating = ratings.get(candidate)
    reference_rating = ratings.get(reference)
    lcb_margin = float("-inf")
    covariance_order = rating_result.get("covariance_order", [])
    covariance = rating_result.get("covariance", [])
    if (
        candidate_rating is not None
        and reference_rating is not None
        and candidate in covariance_order
        and reference in covariance_order
    ):
        candidate_index = covariance_order.index(candidate)
        reference_index = covariance_order.index(reference)
        difference_variance = (
            float(covariance[candidate_index][candidate_index])
            + float(covariance[reference_index][reference_index])
            - 2.0 * float(covariance[candidate_index][reference_index])
        )
        difference_sigma = math.sqrt(max(0.0, difference_variance))
        difference_mu = float(candidate_rating["mu"]) - float(reference_rating["mu"])
        lcb_margin = difference_mu - 2.0 * difference_sigma
    errors = int(candidate_rating["errors"]) if candidate_rating is not None else 0
    weighted = [
        (float(row["candidate_score_rate"]), float(row["effective_weight"]))
        for row in profiles
        if row["candidate_score_rate"] is not None
    ]
    weight_sum = sum(weight for _, weight in weighted)
    balanced_score = (
        sum(score * weight for score, weight in weighted) / weight_sum if weight_sum else 0.0
    )
    reasons = []
    if completed_fraction != 1.0:
        reasons.append("incomplete_games")
    if errors:
        reasons.append("candidate_errors")
    if not math.isfinite(lcb_margin) or lcb_margin <= min_lcb_margin:
        reasons.append("lcb_margin")
    return PopulationGate(
        candidate=candidate,
        reference=reference,
        completed_fraction=completed_fraction,
        errors=errors,
        lcb_margin=lcb_margin,
        family_balanced_score=balanced_score,
        passed=not reasons,
        reasons=tuple(reasons),
    )


def _result_from_row(row: Mapping[str, str], spec: GameSpec) -> GameResult:
    return GameResult(
        game_id=spec.game_id,
        seed=spec.seed,
        player_0=spec.player_0,
        player_1=spec.player_1,
        reward_0=float(row["reward_0"]),
        reward_1=float(row["reward_1"]),
        winner=row["winner"],
        steps=int(row["steps"]),
        elapsed_seconds=float(row["elapsed_seconds"]),
        status=row["status"],
        error=row.get("error", ""),
        agent_a=spec.agent_a,
        agent_b=spec.agent_b,
    )


def _agent_source_manifest(names: Iterable[str]) -> dict[str, dict[str, str]]:
    root = Path(__file__).resolve().parents[2]
    manifest: dict[str, dict[str, str]] = {}
    for name in sorted(set(names)):
        source_name = inspect.getsourcefile(get_agent(name))
        if source_name is None:
            raise ValueError(f"cannot identify source file for agent {name!r}")
        source = Path(source_name).resolve()
        try:
            display_path = str(source.relative_to(root))
        except ValueError:
            display_path = str(source)
        manifest[name] = {
            "source": display_path,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    return manifest


def run_population_arena(
    candidate: str,
    config: PopulationConfig,
    tier_name: str,
    output: Path,
    *,
    workers: int | None = None,
    resume: bool = True,
    reference: str | None = None,
    min_lcb_margin: float = 0.0,
) -> dict[str, Any]:
    """Run/resume a population evaluation and write all parent-side outputs."""

    schedule = build_population_schedule(candidate, config, tier_name)
    output.mkdir(parents=True, exist_ok=True)
    games_path = output / "games.csv"
    completed = read_completed(games_path) if resume else {}
    pending = [spec for spec in schedule if spec.game_id not in completed]
    worker_count = recommended_workers(workers)
    started = time.perf_counter()
    new_results: list[GameResult] = []
    saved: dict[str, dict[str, Any]] = dict(completed)
    checkpoint_every = max(1, worker_count * 2)
    for result in run_games(pending, worker_count):
        assert isinstance(result, GameResult)
        new_results.append(result)
        saved[result.game_id] = result.csv_row()
        if len(new_results) % checkpoint_every == 0:
            write_games(
                games_path,
                [saved[spec.game_id] for spec in schedule if spec.game_id in saved],
            )
    elapsed = time.perf_counter() - started
    new_by_id = {result.game_id: result for result in new_results}
    results: list[GameResult] = []
    for spec in schedule:
        if spec.game_id in new_by_id:
            results.append(new_by_id[spec.game_id])
        elif spec.game_id in completed:
            results.append(_result_from_row(completed[spec.game_id], spec))
    write_games(games_path, [result.csv_row() for result in results])
    write_csv(output / "matchups.csv", MATCHUP_FIELDS, matchup_rows(results))

    rating_error = ""
    try:
        rating = estimate_ratings(results)
    except ValueError as exc:
        rating_error = str(exc)
        rating = {
            "format": "kaggriculture-bayesian-bt-v1",
            "error": rating_error,
            "ratings": [],
            "matchups": [],
        }
    write_csv(output / "ratings.csv", RATING_FIELDS, rating["ratings"])
    dump_json(output / "ratings-bt.json", rating)
    profiles = outcome_profiles(candidate, config, results)
    write_csv(output / "profiles.csv", PROFILE_FIELDS, profiles)

    if reference is None:
        incumbents = [member.agent for member in config.members if member.role == "incumbent"]
        if not incumbents:
            raise ValueError("population has no incumbent reference")
        reference = incumbents[0]
    gate = evaluate_gate(
        candidate,
        reference,
        schedule,
        results,
        rating,
        profiles,
        min_lcb_margin=min_lcb_margin,
    )
    summary = {
        "format": "kaggriculture-population-arena-v1",
        "population_fingerprint": population_fingerprint(config),
        "candidate": candidate,
        "reference": reference,
        "tier": tier_name,
        "seeds": config.tier(tier_name).seeds,
        "seed_start": config.tier(tier_name).seed_start,
        "scheduled_games": len(schedule),
        "completed_games": sum(result.status == "completed" for result in results),
        "failed_games": sum(result.status != "completed" for result in results),
        "executed_games": len(new_results),
        "reused_games": len(results) - len(new_results),
        "workers": worker_count,
        "elapsed_seconds": elapsed,
        "games_per_second": len(new_results) / elapsed if elapsed else 0.0,
        "rating_error": rating_error,
        "gate": gate.to_dict(),
    }
    dump_json(output / "summary.json", summary)
    dump_json(output / "gate.json", gate.to_dict())
    dump_json(
        output / "manifest.json",
        {
            "format": "kaggriculture-population-manifest-v1",
            "population_fingerprint": population_fingerprint(config),
            "population": config.to_dict(),
            "candidate": candidate,
            "tier": tier_name,
            "agents": _agent_source_manifest(
                [candidate, *(member.agent for member in config.members)]
            ),
            "system": system_info(),
        },
    )
    game_times = [result.elapsed_seconds for result in new_results]
    decisions = sum(result.decisions for result in new_results)
    agent_seconds = sum(result.agent_seconds for result in new_results)
    engine_seconds = sum(result.engine_seconds for result in new_results)
    benchmark_path = output / "benchmark.json"
    if new_results or not benchmark_path.exists():
        dump_json(
            benchmark_path,
            {
            "games": len(new_results),
            "completed_games": sum(result.status == "completed" for result in new_results),
            "failed_games": sum(result.status != "completed" for result in new_results),
            "total_seconds": elapsed,
            "games_per_second": len(new_results) / elapsed if elapsed else 0.0,
            "decisions_per_second": decisions / elapsed if elapsed else 0.0,
            "mean_game_seconds": sum(game_times) / len(game_times) if game_times else 0.0,
            "p50_game_seconds": percentile(game_times, 0.50),
            "p95_game_seconds": percentile(game_times, 0.95),
            "agent_seconds": agent_seconds,
            "engine_seconds": engine_seconds,
            "agent_time_fraction": agent_seconds / (agent_seconds + engine_seconds)
            if agent_seconds + engine_seconds
            else 0.0,
            "engine_time_fraction": engine_seconds / (agent_seconds + engine_seconds)
            if agent_seconds + engine_seconds
            else 0.0,
            "worker_count": worker_count,
            "seed_start": config.tier(tier_name).seed_start,
            "seed_end": config.tier(tier_name).seed_start + config.tier(tier_name).seeds - 1,
                **system_info(),
            },
        )
    return summary


__all__ = [
    "PROFILE_FIELDS",
    "RATING_FIELDS",
    "PopulationGate",
    "build_population_schedule",
    "evaluate_gate",
    "outcome_profiles",
    "run_population_arena",
]
