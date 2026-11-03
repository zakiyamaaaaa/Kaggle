"""Deterministic, process-safe local Kaggriculture match execution."""

from __future__ import annotations

import csv
import copy
import hashlib
import json
import math
import os
import platform
import statistics
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any, Iterable, Iterator

from kaggle_environments import make
from kaggle_environments.errors import DeadlineExceeded
from kaggle_environments.utils import structify

from kaggriculture_agent.registry import get_agent

GAME_FIELDS = (
    "game_id",
    "seed",
    "player_0",
    "player_1",
    "reward_0",
    "reward_1",
    "winner",
    "steps",
    "elapsed_seconds",
    "status",
    "error",
)

# Trajectory files intentionally use a small, scalar schema.  The complete
# Kaggriculture observation contains nested tile, market, and inventory
# structures which are useful to policies but very expensive (and brittle) to
# persist as replay blobs.  Keep these names in one place so the writer and
# tests cannot silently drift apart.
TRAJECTORY_METADATA_FIELDS = (
    "split",
    "evaluation_stage",
    "pair_id",
    "game_id",
    "seed",
    "seat",
    "player",
    "policy",
    "opponent",
    "step",
    "day",
    "hour",
)
TRAJECTORY_FEATURE_FIELDS = (
    "own_money",
    "opponent_money",
    "own_farmer_x",
    "own_farmer_y",
    "opponent_farmer_x",
    "opponent_farmer_y",
    "own_hands_count",
    "opponent_hands_count",
    "own_open_tile_count",
    "opponent_open_tile_count",
    "own_locked_tile_count",
    "opponent_locked_tile_count",
    "own_planted_tile_count",
    "opponent_planted_tile_count",
    "own_watered_tile_count",
    "opponent_watered_tile_count",
    "own_unlocked_quadrant_count",
    "opponent_unlocked_quadrant_count",
    "own_hires_today",
    "opponent_hires_today",
    "own_seed_total",
    "opponent_seed_total",
    "own_shed_total",
    "opponent_shed_total",
    "own_inventory_total",
    "opponent_inventory_total",
    "market_inventory_total",
    "market_mean_price",
    "market_min_price",
    "market_max_price",
    "town_unlocked_shop_count",
    "own_seed_wheat",
    "own_seed_fertilizer",
    "own_seed_melon",
    "own_seed_milk",
    "own_seed_strawberry",
    "own_seed_wool",
    "own_shed_wheat",
    "own_shed_fertilizer",
    "own_shed_melon",
    "own_shed_milk",
    "own_shed_strawberry",
    "own_shed_wool",
    "market_inventory_wheat",
    "market_inventory_fertilizer",
    "market_inventory_melon",
    "market_inventory_milk",
    "market_inventory_strawberry",
    "market_inventory_wool",
    "market_price_wheat",
    "market_price_fertilizer",
    "market_price_melon",
    "market_price_milk",
    "market_price_strawberry",
    "market_price_wool",
)
TRANSITION_FIELDS = TRAJECTORY_METADATA_FIELDS + (
    "chosen_action_json",
    "final_reward",
    "opponent_final_reward",
    "reward_difference",
    "win",
) + TRAJECTORY_FEATURE_FIELDS

# One episode row represents one game.  Player-specific final outcomes are
# retained alongside the canonical player-0/player-1 columns so this table is
# useful without joining back to games.csv.
EPISODE_FIELDS = (
    "split",
    "evaluation_stage",
    "pair_id",
    "game_id",
    "seed",
    "player_0",
    "player_1",
    "policy_0",
    "policy_1",
    "opponent_0",
    "opponent_1",
    "final_reward_0",
    "final_reward_1",
    "reward_difference",
    "winner",
    "win_0",
    "win_1",
    "steps",
    "status",
)

PAIR_FIELDS = (
    "split",
    "evaluation_stage",
    "pair_id",
    "seed",
    "agent_a",
    "agent_b",
    "games",
    "game_id_seat_0",
    "game_id_seat_1",
    "reward_a_seat_0",
    "reward_b_seat_0",
    "reward_a_seat_1",
    "reward_b_seat_1",
    "reward_difference_seat_0",
    "reward_difference_seat_1",
    "wins_a",
    "wins_b",
    "draws",
    "paired_win_rate_a",
    "paired_reward_difference_a",
    "status",
)
MATCHUP_FIELDS = (
    "agent_a",
    "agent_b",
    "games",
    "wins_a",
    "wins_b",
    "draws",
    "win_rate_a",
    "mean_reward_a",
    "mean_reward_b",
    "mean_reward_difference",
)


@dataclass(frozen=True)
class GameSpec:
    game_id: str
    seed: int
    player_0: str
    player_1: str
    agent_a: str
    agent_b: str
    # ``pair_id`` is shared by the direct and seat-swapped games.  Defaults
    # keep hand-written GameSpec instances used by existing callers valid.
    pair_id: str = ""
    seat: int = 0


@dataclass
class GameResult:
    game_id: str
    seed: int
    player_0: str
    player_1: str
    reward_0: float | None
    reward_1: float | None
    winner: str
    steps: int
    elapsed_seconds: float
    status: str
    error: str
    agent_seconds: float = 0.0
    engine_seconds: float = 0.0
    environment_setup_seconds: float = 0.0
    decisions: int = 0
    agent_a: str = ""
    agent_b: str = ""

    def csv_row(self) -> dict[str, Any]:
        row = asdict(self)
        return {key: row[key] for key in GAME_FIELDS}


class _TimedAgent:
    def __init__(self, fn: Any) -> None:
        self.fn = fn
        self.seconds = 0.0
        self.calls = 0

    def __call__(self, obs: dict, _configuration: Any = None) -> dict[str, list]:
        started = time.perf_counter()
        try:
            return self.fn(obs)
        finally:
            self.seconds += time.perf_counter() - started
            self.calls += 1


_SHARED_OBSERVATION_FIELDS = ("step", "farms", "market", "town", "day", "hour")
_DEFAULT_ACTION = {"farmer": ["PASS"], "hands": [], "market": []}
_MARKET_FEATURE_ITEMS = ("WHEAT", "FERTILIZER", "MELON", "MILK", "STRAWBERRY", "WOOL")


def _value(obj: Any, key: str, default: Any = None) -> Any:
    """Read a dict-like Kaggle Struct without depending on its concrete type."""

    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return obj[key]
    except (KeyError, IndexError, TypeError):
        return getattr(obj, key, default)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _count_farm_tiles(farm: Any) -> tuple[int, int, int, int]:
    """Return open, locked, planted, and watered tile counts."""

    open_tiles = locked_tiles = planted_tiles = watered_tiles = 0
    for row in _value(farm, "tiles", []) or []:
        for tile in row or []:
            if tile == "LOCKED":
                locked_tiles += 1
                continue
            open_tiles += 1
            if isinstance(tile, dict) or hasattr(tile, "get"):
                planted_tiles += 1
                if bool(_value(tile, "watered_today", False)):
                    watered_tiles += 1
    return open_tiles, locked_tiles, planted_tiles, watered_tiles


def _inventory_total(value: Any) -> int:
    if not value:
        return 0
    if isinstance(value, dict):
        values = value.values()
    else:
        try:
            values = value.values()
        except AttributeError:
            return 0
    return sum(int(_number(item)) for item in values)


def _inventory_item(value: Any, item: str) -> int:
    return int(_number(_value(value, item, 0)))


def _farm_features(farm: Any, private: Any) -> dict[str, int | float]:
    open_tiles, locked_tiles, planted_tiles, watered_tiles = _count_farm_tiles(farm)
    farmer = _value(farm, "farmer", []) or []
    own_x = int(_number(farmer[0])) if len(farmer) > 0 else 0
    own_y = int(_number(farmer[1])) if len(farmer) > 1 else 0
    hands = _value(farm, "hands", []) or []
    quadrants = _value(farm, "unlocked_quadrants", []) or []
    inventories = _value(private, "inventories", []) or []
    return {
        "money": _number(_value(farm, "money", 0.0)),
        "farmer_x": own_x,
        "farmer_y": own_y,
        "hands_count": len(hands),
        "open_tile_count": open_tiles,
        "locked_tile_count": locked_tiles,
        "planted_tile_count": planted_tiles,
        "watered_tile_count": watered_tiles,
        "unlocked_quadrant_count": len(quadrants),
        "hires_today": int(_number(_value(farm, "hires_today", 0))),
        "seed_total": _inventory_total(_value(private, "seeds", {})),
        "shed_total": _inventory_total(_value(private, "shed", {})),
        "inventory_total": sum(_inventory_total(item) for item in inventories),
    }


def _trajectory_features(observation: Any, seat: int) -> dict[str, int | float]:
    """Extract fixed-length scalar features from one player observation."""

    farms = _value(observation, "farms", []) or []
    privates = [None, None]
    own_private = _value(observation, "private", {}) or {}
    if 0 <= seat < len(privates):
        privates[seat] = own_private
    # The opponent's private inventory is intentionally not present in the
    # observation.  Keep those feature slots fixed-length and use zero rather
    # than leaking hidden state into the trajectory dataset.
    own = _farm_features(farms[seat] if seat < len(farms) else {}, own_private)
    other_seat = 1 - seat
    opponent = _farm_features(farms[other_seat] if other_seat < len(farms) else {}, {})
    market = _value(observation, "market", {}) or {}
    market_inventory = _value(market, "inventory", {}) or {}
    prices = [_number(value) for value in (_value(market, "prices", {}) or {}).values()]
    features: dict[str, int | float] = {
        "own_money": own["money"],
        "opponent_money": opponent["money"],
        "own_farmer_x": own["farmer_x"],
        "own_farmer_y": own["farmer_y"],
        "opponent_farmer_x": opponent["farmer_x"],
        "opponent_farmer_y": opponent["farmer_y"],
        "own_hands_count": own["hands_count"],
        "opponent_hands_count": opponent["hands_count"],
        "own_open_tile_count": own["open_tile_count"],
        "opponent_open_tile_count": opponent["open_tile_count"],
        "own_locked_tile_count": own["locked_tile_count"],
        "opponent_locked_tile_count": opponent["locked_tile_count"],
        "own_planted_tile_count": own["planted_tile_count"],
        "opponent_planted_tile_count": opponent["planted_tile_count"],
        "own_watered_tile_count": own["watered_tile_count"],
        "opponent_watered_tile_count": opponent["watered_tile_count"],
        "own_unlocked_quadrant_count": own["unlocked_quadrant_count"],
        "opponent_unlocked_quadrant_count": opponent["unlocked_quadrant_count"],
        "own_hires_today": own["hires_today"],
        "opponent_hires_today": opponent["hires_today"],
        "own_seed_total": own["seed_total"],
        "opponent_seed_total": opponent["seed_total"],
        "own_shed_total": own["shed_total"],
        "opponent_shed_total": opponent["shed_total"],
        "own_inventory_total": own["inventory_total"],
        "opponent_inventory_total": opponent["inventory_total"],
        "market_inventory_total": _inventory_total(market_inventory),
        "market_mean_price": statistics.fmean(prices) if prices else 0.0,
        "market_min_price": min(prices) if prices else 0.0,
        "market_max_price": max(prices) if prices else 0.0,
        "town_unlocked_shop_count": len(_value(_value(observation, "town", {}), "unlocked_shops", []) or []),
    }
    own_seeds = _value(own_private, "seeds", {}) or {}
    own_shed = _value(own_private, "shed", {}) or {}
    market_prices = _value(market, "prices", {}) or {}
    for item in _MARKET_FEATURE_ITEMS:
        suffix = item.lower()
        features[f"own_seed_{suffix}"] = _inventory_item(own_seeds, item)
        features[f"own_shed_{suffix}"] = _inventory_item(own_shed, item)
        features[f"market_inventory_{suffix}"] = _inventory_item(market_inventory, item)
        features[f"market_price_{suffix}"] = _number(_value(market_prices, item, 0.0))
    return features


def _action_json(action: Any) -> str:
    """Serialize only the selected action, never the full observation."""

    if isinstance(action, BaseException):
        return "null"
    try:
        return json.dumps(action, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return json.dumps(str(action), separators=(",", ":"))


def _trajectory_row(
    spec: GameSpec,
    observation: Any,
    seat: int,
    action: Any,
) -> dict[str, Any]:
    policy = spec.player_0 if seat == 0 else spec.player_1
    opponent = spec.player_1 if seat == 0 else spec.player_0
    pair_id = spec.pair_id or f"{_slug(spec.agent_a)}-vs-{_slug(spec.agent_b)}-seed-{spec.seed}"
    row = {
        "split": "development",
        "evaluation_stage": "development",
        "pair_id": pair_id,
        "game_id": spec.game_id,
        "seed": spec.seed,
        "seat": seat,
        "player": policy,
        "policy": policy,
        "opponent": opponent,
        "step": int(_number(_value(observation, "step", 0))),
        "day": int(_number(_value(observation, "day", 0))),
        "hour": int(_number(_value(observation, "hour", 0))),
        "chosen_action_json": _action_json(action),
    }
    row.update(_trajectory_features(observation, seat))
    return row


def _decorate_trajectory(result: GameResult, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rewards = (result.reward_0, result.reward_1)
    for row in rows:
        seat = int(row["seat"])
        own_reward = rewards[seat]
        opponent_reward = rewards[1 - seat]
        row["final_reward"] = own_reward
        row["opponent_final_reward"] = opponent_reward
        if own_reward is None or opponent_reward is None:
            row["reward_difference"] = None
            row["win"] = None
        else:
            row["reward_difference"] = float(own_reward) - float(opponent_reward)
            row["win"] = bool(own_reward > opponent_reward)
    return rows


def _agent_observation(env: Any, player: int) -> Any:
    """Reproduce Kaggle's per-player shared observation without schema traversal."""

    player_observation = env.state[player].observation
    observation = {
        field: copy.deepcopy(value)
        for field, value in player_observation.items()
        if field not in _SHARED_OBSERVATION_FIELDS
    }
    shared = env.state[0].observation
    for field in _SHARED_OBSERVATION_FIELDS:
        if field in shared:
            observation[field] = copy.deepcopy(shared[field])
    return structify(observation)


def _major_state(env: Any) -> tuple[Any, ...]:
    observation = env.state[0].observation
    return (
        int(observation.step),
        tuple(str(state.status) for state in env.state),
        tuple(state.reward for state in env.state),
        copy.deepcopy(observation.farms),
        copy.deepcopy(observation.market),
        copy.deepcopy(observation.town),
    )


def _run_fast(
    env: Any,
    wrappers: list[_TimedAgent],
    capture_trace: bool = False,
    trajectory_spec: GameSpec | None = None,
) -> tuple:
    """Run Kaggriculture while bypassing generic runner/schema/history overhead."""

    bad_statuses: set[str] = set()
    trace: list[tuple[Any, ...]] = [_major_state(env)] if capture_trace else []
    trajectory: list[dict[str, Any]] = []
    step = 0
    while not env.done:
        actions: list[Any] = []
        durations: list[float] = []
        observations: list[Any | None] = []
        for player, wrapper in enumerate(wrappers):
            state = env.state[player]
            if str(state.status) != "ACTIVE":
                actions.append(None)
                durations.append(0.0)
                observations.append(None)
                continue
            observation = _agent_observation(env, player)
            observations.append(observation)
            started = time.perf_counter()
            try:
                action = wrapper(observation)
            except Exception as exc:
                action = exc
            duration = round(time.perf_counter() - started, 6)
            if duration - env.configuration.actTimeout > observation.remainingOverageTime:
                action = DeadlineExceeded()
            actions.append(action)
            durations.append(duration)

        action_state = []
        for player, action in enumerate(actions):
            next_state = {**env.state[player], "action": None}
            if isinstance(action, DeadlineExceeded):
                next_state["status"] = "TIMEOUT"
            elif isinstance(action, BaseException):
                next_state["status"] = "ERROR"
            else:
                # Kaggriculture's action schema only requires an object and
                # defaults non-objects to a PASS action. Nested illegal ops are
                # intentionally silent no-ops in the official interpreter.
                next_state["action"] = copy.deepcopy(action if isinstance(action, dict) else _DEFAULT_ACTION)
            action_state.append(next_state)

            if trajectory_spec is not None and observations[player] is not None:
                # Record the normalized action that reaches the interpreter,
                # not a malformed object an agent may have returned.
                normalized_action = next_state.get("action")
                trajectory.append(
                    _trajectory_row(trajectory_spec, observations[player], player, normalized_action)
                )

        env.state = structify(env.interpreter(structify(action_state), env))
        step += 1
        env.state[0].observation.step = step
        for player, state in enumerate(env.state):
            consumed = max(0.0, durations[player] - env.configuration.actTimeout)
            state.observation.remainingOverageTime -= consumed
            current_status = str(state.status)
            if current_status in {"ERROR", "INVALID", "TIMEOUT"}:
                bad_statuses.add(current_status)
                state.reward = None
        if step >= env.configuration.episodeSteps - 1:
            for state in env.state:
                if str(state.status) in {"ACTIVE", "INACTIVE"}:
                    state.status = "DONE"
        if capture_trace:
            trace.append(_major_state(env))
    return env.state, bad_statuses, trace, trajectory


def _winner(player_0: str, player_1: str, rewards: list[float | None]) -> str:
    if rewards[0] is None or rewards[1] is None or rewards[0] == rewards[1]:
        return "draw"
    return player_0 if rewards[0] > rewards[1] else player_1


def _play_game(
    spec: GameSpec,
    *,
    fast: bool,
    capture_trace: bool = False,
    capture_trajectory: bool = False,
) -> tuple[GameResult, list]:
    """Play one isolated game. Safe to call inside a process worker."""

    started = time.perf_counter()
    wrappers = [_TimedAgent(get_agent(spec.player_0)), _TimedAgent(get_agent(spec.player_1))]
    try:
        # A fresh environment per game prevents mutable state and RNG leakage.
        env = make("kaggriculture", configuration={"seed": spec.seed}, debug=False)
        setup_seconds = time.perf_counter() - started
        if fast:
            final, bad_statuses, trace, trajectory = _run_fast(
                env,
                wrappers,
                capture_trace,
                spec if capture_trajectory else None,
            )
            step_count = int(final[0].observation.step)
        else:
            env.run(wrappers)
            final = env.steps[-1]
            bad_statuses = {
                str(state.status)
                for step_state in env.steps
                for state in step_state
                if str(state.status) in {"ERROR", "INVALID", "TIMEOUT"}
            }
            trace = [_major_state_from_step(step_state) for step_state in env.steps] if capture_trace else []
            trajectory = []
            step_count = max(0, len(env.steps) - 1)
        rewards = [state.reward for state in final]
        statuses = [str(state.status) for state in final]
        bad_statuses = sorted(bad_statuses)
        status = "completed" if statuses == ["DONE", "DONE"] and not bad_statuses else "failed"
        error = "" if status == "completed" else ",".join(bad_statuses or statuses)
        elapsed = time.perf_counter() - started
        agent_seconds = sum(wrapper.seconds for wrapper in wrappers)
        result = GameResult(
            game_id=spec.game_id,
            seed=spec.seed,
            player_0=spec.player_0,
            player_1=spec.player_1,
            reward_0=rewards[0],
            reward_1=rewards[1],
            winner=_winner(spec.player_0, spec.player_1, rewards),
            steps=step_count,
            elapsed_seconds=elapsed,
            status=status,
            error=error,
            agent_seconds=agent_seconds,
            engine_seconds=max(0.0, elapsed - agent_seconds),
            environment_setup_seconds=setup_seconds,
            decisions=sum(wrapper.calls for wrapper in wrappers),
            agent_a=spec.agent_a,
            agent_b=spec.agent_b,
        )
        if capture_trajectory:
            trajectory = _decorate_trajectory(result, trajectory)
        return result, trajectory if capture_trajectory else trace
    except Exception as exc:  # keep a worker failure from aborting the arena
        elapsed = time.perf_counter() - started
        agent_seconds = sum(wrapper.seconds for wrapper in wrappers)
        result = GameResult(
            game_id=spec.game_id,
            seed=spec.seed,
            player_0=spec.player_0,
            player_1=spec.player_1,
            reward_0=None,
            reward_1=None,
            winner="",
            steps=0,
            elapsed_seconds=elapsed,
            status="failed",
            error=f"{type(exc).__name__}: {exc}"[:2000],
            agent_seconds=agent_seconds,
            engine_seconds=max(0.0, elapsed - agent_seconds),
            decisions=sum(wrapper.calls for wrapper in wrappers),
            agent_a=spec.agent_a,
            agent_b=spec.agent_b,
        )
        return result, []


def _major_state_from_step(step_state: Any) -> tuple[Any, ...]:
    observation = step_state[0].observation
    return (
        int(observation.step),
        tuple(str(state.status) for state in step_state),
        tuple(state.reward for state in step_state),
        copy.deepcopy(observation.farms),
        copy.deepcopy(observation.market),
        copy.deepcopy(observation.town),
    )


def play_game(spec: GameSpec) -> GameResult:
    """Play one isolated game with the optimized compatible runner."""

    use_legacy = os.environ.get("KAGGRICULTURE_LEGACY_RUNNER") == "1"
    return _play_game(spec, fast=not use_legacy)[0]


def play_game_with_trajectory(spec: GameSpec) -> tuple[GameResult, list[dict[str, Any]]]:
    """Play one fast game and return compact trajectory rows to the caller.

    This worker deliberately returns Python rows instead of writing files.  It
    keeps all filesystem coordination in the parent process and makes serial
    and process-pool collection use exactly the same code path.
    """

    result, rows = _play_game(spec, fast=True, capture_trajectory=True)
    return result, rows


def play_game_legacy(spec: GameSpec) -> GameResult:
    """Reference runner used for compatibility checks."""

    return _play_game(spec, fast=False)[0]


def compare_runners(spec: GameSpec) -> tuple[GameResult, GameResult, bool]:
    """Run both paths and compare all captured major per-step state."""

    legacy, legacy_trace = _play_game(spec, fast=False, capture_trace=True)
    fast, fast_trace = _play_game(spec, fast=True, capture_trace=True)
    return legacy, fast, legacy_trace == fast_trace


def _slug(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in value)


def build_schedule(
    agents: list[str], games_per_pair: int, seed: int, swap_seats: bool
) -> list[GameSpec]:
    """Build a stable schedule with unique ids and seeds per unswapped game."""

    if len(agents) < 2:
        raise ValueError("at least two agents are required")
    if games_per_pair < 1:
        raise ValueError("games_per_pair must be positive")
    schedule: list[GameSpec] = []
    pair_index = 0
    for left in range(len(agents)):
        for right in range(left + 1, len(agents)):
            agent_a, agent_b = agents[left], agents[right]
            for game_index in range(games_per_pair):
                game_seed = seed + pair_index * games_per_pair + game_index
                pair_id = (
                    f"{_slug(agent_a)}-vs-{_slug(agent_b)}-"
                    f"{game_index:06d}-seed-{game_seed}"
                )
                seats = [(agent_a, agent_b, 0)]
                if swap_seats:
                    seats.append((agent_b, agent_a, 1))
                for player_0, player_1, seat in seats:
                    raw = f"{agent_a}|{agent_b}|{game_index}|{game_seed}|{seat}"
                    digest = hashlib.blake2s(raw.encode(), digest_size=6).hexdigest()
                    game_id = (
                        f"{_slug(agent_a)}-vs-{_slug(agent_b)}-"
                        f"{game_index:06d}-s{seat}-{digest}"
                    )
                    schedule.append(
                        GameSpec(
                            game_id,
                            game_seed,
                            player_0,
                            player_1,
                            agent_a,
                            agent_b,
                            pair_id,
                            seat,
                        )
                    )
            pair_index += 1
    return schedule


def recommended_workers(requested: int | None = None) -> int:
    available = os.cpu_count() or 1
    return min(available, max(1, requested if requested is not None else available))


def _chunksize(task_count: int, workers: int) -> int:
    return max(1, math.ceil(task_count / max(1, workers * 4)))


def run_games(
    specs: list[GameSpec],
    workers: int,
    *,
    capture_trajectory: bool = False,
) -> Iterator[GameResult | tuple[GameResult, list[dict[str, Any]]]]:
    """Run games, optionally returning compact per-step rows with each result."""

    if capture_trajectory:
        yield from run_games_with_trajectories(specs, workers)
        return
    workers = recommended_workers(workers)
    if workers == 1:
        yield from map(play_game, specs)
        return
    with ProcessPoolExecutor(max_workers=workers) as executor:
        yield from executor.map(play_game, specs, chunksize=_chunksize(len(specs), workers))


def run_games_with_trajectories(
    specs: list[GameSpec], workers: int
) -> Iterator[tuple[GameResult, list[dict[str, Any]]]]:
    """Run games and return ``(GameResult, transition_rows)`` from workers."""

    workers = recommended_workers(workers)
    if workers == 1:
        yield from map(play_game_with_trajectory, specs)
        return
    with ProcessPoolExecutor(max_workers=workers) as executor:
        yield from executor.map(
            play_game_with_trajectory,
            specs,
            chunksize=_chunksize(len(specs), workers),
        )


def read_completed(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            row["game_id"]: row
            for row in csv.DictReader(handle)
            if row.get("status") == "completed"
        }


def write_games(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=GAME_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def matchup_rows(results: list[GameResult]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[GameResult]] = defaultdict(list)
    for result in results:
        if result.status == "completed":
            grouped[(result.agent_a, result.agent_b)].append(result)
    rows = []
    for (agent_a, agent_b), games in sorted(grouped.items()):
        rewards_a, rewards_b = [], []
        wins_a = wins_b = draws = 0
        for game in games:
            a_is_zero = game.player_0 == agent_a
            reward_a = float(game.reward_0 if a_is_zero else game.reward_1)
            reward_b = float(game.reward_1 if a_is_zero else game.reward_0)
            rewards_a.append(reward_a)
            rewards_b.append(reward_b)
            if reward_a > reward_b:
                wins_a += 1
            elif reward_b > reward_a:
                wins_b += 1
            else:
                draws += 1
        rows.append(
            {
                "agent_a": agent_a,
                "agent_b": agent_b,
                "games": len(games),
                "wins_a": wins_a,
                "wins_b": wins_b,
                "draws": draws,
                "win_rate_a": (wins_a + 0.5 * draws) / len(games),
                "mean_reward_a": _mean(rewards_a),
                "mean_reward_b": _mean(rewards_b),
                "mean_reward_difference": _mean(rewards_a) - _mean(rewards_b),
            }
        )
    return rows


def rating_rows(results: list[GameResult], k_factor: float = 32.0) -> list[dict[str, Any]]:
    ratings: dict[str, float] = defaultdict(lambda: 1500.0)
    games: dict[str, int] = defaultdict(int)
    for result in sorted(results, key=lambda item: item.game_id):
        if result.status != "completed":
            continue
        left, right = result.player_0, result.player_1
        expected = 1.0 / (1.0 + 10 ** ((ratings[right] - ratings[left]) / 400.0))
        actual = 0.5 if result.reward_0 == result.reward_1 else float(result.reward_0 > result.reward_1)
        delta = k_factor * (actual - expected)
        ratings[left] += delta
        ratings[right] -= delta
        games[left] += 1
        games[right] += 1
    return [
        {"agent": name, "rating": round(score, 6), "games": games[name]}
        for name, score in sorted(ratings.items(), key=lambda item: (-item[1], item[0]))
    ]


def write_csv(path: Path, fieldnames: tuple[str, ...], rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


_INTEGER_FEATURE_FIELDS = {
    field
    for field in TRAJECTORY_FEATURE_FIELDS
    if field.endswith(("_count", "_x", "_y", "_today", "_total"))
    or field.startswith(("own_seed_", "own_shed_", "market_inventory_"))
}


def _parquet_schema(fieldnames: tuple[str, ...]) -> Any:
    """Build a stable Arrow schema for one of the trajectory tables."""

    import pyarrow as pa

    types: dict[str, Any] = {}
    for field in fieldnames:
        if field in {"seed", "seat", "step", "day", "hour", "steps", "games", "wins_a", "wins_b", "draws"}:
            types[field] = pa.int64()
        elif field in _INTEGER_FEATURE_FIELDS:
            types[field] = pa.int64()
        elif field == "win" or field.startswith("win_"):
            types[field] = pa.bool_()
        elif field.startswith("final_reward") or field.startswith("reward_") or field in {
            "opponent_final_reward",
            "reward_difference",
            "paired_win_rate_a",
            "paired_reward_difference_a",
        }:
            types[field] = pa.float64()
        elif field in {
            "own_money",
            "opponent_money",
            "market_mean_price",
            "market_min_price",
            "market_max_price",
        } or field.startswith("market_price_"):
            types[field] = pa.float64()
        else:
            types[field] = pa.string()
    return pa.schema([(field, types[field]) for field in fieldnames])


def write_parquet(path: Path, fieldnames: tuple[str, ...], rows: Iterable[dict[str, Any]]) -> None:
    """Write a trajectory table from the parent process with a fixed schema."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    materialized = [{field: row.get(field) for field in fieldnames} for row in rows]
    table = pa.Table.from_pylist(materialized, schema=_parquet_schema(fieldnames))
    temporary = path.with_name(f".{path.name}.tmp")
    pq.write_table(table, temporary, compression="zstd", use_dictionary=False)
    temporary.replace(path)


def read_parquet(path: Path) -> list[dict[str, Any]]:
    """Read previously collected rows for resume-aware trajectory writes."""

    if not path.exists():
        return []
    import pyarrow.parquet as pq

    return pq.read_table(path).to_pylist()


def _spec_pair_id(spec: GameSpec) -> str:
    return spec.pair_id or f"{_slug(spec.agent_a)}-vs-{_slug(spec.agent_b)}-seed-{spec.seed}"


def episode_rows(results: list[GameResult], specs: list[GameSpec]) -> list[dict[str, Any]]:
    """Build one final-outcome row per scheduled game."""

    specs_by_id = {spec.game_id: spec for spec in specs}
    rows = []
    for result in sorted(results, key=lambda item: item.game_id):
        spec = specs_by_id.get(result.game_id)
        pair_id = _spec_pair_id(spec) if spec is not None else f"seed-{result.seed}"
        reward_difference = None
        win_0 = win_1 = None
        if result.reward_0 is not None and result.reward_1 is not None:
            reward_difference = float(result.reward_0) - float(result.reward_1)
            win_0 = bool(result.reward_0 > result.reward_1)
            win_1 = bool(result.reward_1 > result.reward_0)
        rows.append(
            {
                "split": "development",
                "evaluation_stage": "development",
                "pair_id": pair_id,
                "game_id": result.game_id,
                "seed": result.seed,
                "player_0": result.player_0,
                "player_1": result.player_1,
                "policy_0": result.player_0,
                "policy_1": result.player_1,
                "opponent_0": result.player_1,
                "opponent_1": result.player_0,
                "final_reward_0": result.reward_0,
                "final_reward_1": result.reward_1,
                "reward_difference": reward_difference,
                "winner": result.winner,
                "win_0": win_0,
                "win_1": win_1,
                "steps": result.steps,
                "status": result.status,
            }
        )
    return rows


def pair_rows(results: list[GameResult], specs: list[GameSpec]) -> list[dict[str, Any]]:
    """Build one paired-seat summary row per seed/policy pair."""

    specs_by_id = {spec.game_id: spec for spec in specs}
    grouped: dict[str, list[tuple[GameResult, GameSpec | None]]] = defaultdict(list)
    for result in results:
        spec = specs_by_id.get(result.game_id)
        pair_id = _spec_pair_id(spec) if spec is not None else f"seed-{result.seed}"
        grouped[pair_id].append((result, spec))

    rows = []
    for pair_id, games in sorted(grouped.items()):
        first_spec = next((spec for _, spec in games if spec is not None), None)
        if first_spec is None:
            first_result = games[0][0]
            agent_a, agent_b = first_result.agent_a, first_result.agent_b
            seed = first_result.seed
        else:
            agent_a, agent_b, seed = first_spec.agent_a, first_spec.agent_b, first_spec.seed
        by_seat: dict[int, tuple[GameResult, GameSpec | None]] = {}
        for result, spec in games:
            seat = spec.seat if spec is not None else int(result.player_0 != agent_a)
            by_seat.setdefault(seat, (result, spec))

        rewards_a: list[float] = []
        wins_a = wins_b = draws = 0
        seat_values: dict[int, tuple[float | None, float | None, float | None]] = {}
        game_ids: dict[int, str | None] = {0: None, 1: None}
        for seat in (0, 1):
            result_spec = by_seat.get(seat)
            if result_spec is None:
                seat_values[seat] = (None, None, None)
                continue
            result, _ = result_spec
            game_ids[seat] = result.game_id
            if result.reward_0 is None or result.reward_1 is None:
                seat_values[seat] = (None, None, None)
                continue
            if seat == 0:
                reward_a, reward_b = result.reward_0, result.reward_1
            else:
                reward_a, reward_b = result.reward_1, result.reward_0
            difference = float(reward_a) - float(reward_b)
            seat_values[seat] = (float(reward_a), float(reward_b), difference)
            rewards_a.append(float(reward_a))
            if reward_a > reward_b:
                wins_a += 1
            elif reward_b > reward_a:
                wins_b += 1
            else:
                draws += 1
        games_count = len(games)
        rows.append(
            {
                "split": "development",
                "evaluation_stage": "development",
                "pair_id": pair_id,
                "seed": seed,
                "agent_a": agent_a,
                "agent_b": agent_b,
                "games": games_count,
                "game_id_seat_0": game_ids[0],
                "game_id_seat_1": game_ids[1],
                "reward_a_seat_0": seat_values[0][0],
                "reward_b_seat_0": seat_values[0][1],
                "reward_a_seat_1": seat_values[1][0],
                "reward_b_seat_1": seat_values[1][1],
                "reward_difference_seat_0": seat_values[0][2],
                "reward_difference_seat_1": seat_values[1][2],
                "wins_a": wins_a,
                "wins_b": wins_b,
                "draws": draws,
                "paired_win_rate_a": (wins_a + 0.5 * draws) / games_count if games_count else 0.0,
                "paired_reward_difference_a": _mean(rewards_a) - _mean(
                    [
                        float(values[1])
                        for values in seat_values.values()
                        if values[1] is not None
                    ]
                ),
                "status": "completed" if all(item[0].status == "completed" for item in games) else "failed",
            }
        )
    return rows


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def system_info() -> dict[str, Any]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "os": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count() or 1,
        "kaggle_environments_version": version("kaggle-environments"),
    }


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
