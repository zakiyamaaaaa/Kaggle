from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from kaggle_environments import make

from kaggriculture_agent import agent
from kaggriculture_agent.local_arena import (
    EPISODE_FIELDS,
    GAME_FIELDS,
    MATCHUP_FIELDS,
    PAIR_FIELDS,
    TRANSITION_FIELDS,
    GameSpec,
    build_schedule,
    compare_runners,
    episode_rows,
    matchup_rows,
    play_game,
    play_game_with_trajectory,
    read_parquet,
    write_parquet,
    pair_rows,
    run_games,
)
from kaggriculture_agent.registry import agent_names

ROOT = Path(__file__).resolve().parents[1]


def test_seed_reproducibility() -> None:
    spec = GameSpec("same", 7123, "baseline", "candidate", "baseline", "candidate")
    first = play_game(spec)
    second = play_game(spec)

    assert (first.reward_0, first.reward_1, first.status, first.steps) == (
        second.reward_0,
        second.reward_1,
        second.status,
        second.steps,
    )


def test_debug_io_optimization_preserves_legacy_outcome_and_major_state() -> None:
    def legacy(debug: bool):
        env = make("kaggriculture", configuration={"seed": 7331}, debug=debug)
        env.run([agent, agent])
        trace = [
            (
                tuple(state.reward for state in step),
                tuple(str(state.status) for state in step),
                tuple(farm["money"] for farm in step[0].observation["farms"]),
                tuple(step[0].observation["town"]["unlocked_shops"]),
            )
            for step in env.steps
        ]
        return trace

    assert legacy(debug=True) == legacy(debug=False)


def test_fast_runner_matches_legacy_every_step_across_seeds() -> None:
    for seed in (1000, 1001, 7331):
        spec = GameSpec(str(seed), seed, "baseline", "candidate", "baseline", "candidate")
        legacy, fast, traces_match = compare_runners(spec)
        assert traces_match
        assert (legacy.reward_0, legacy.reward_1, legacy.status, legacy.steps) == (
            fast.reward_0,
            fast.reward_1,
            fast.status,
            fast.steps,
        )


def test_fast_runner_isolates_mutating_agent_observations(monkeypatch) -> None:
    from kaggriculture_agent import registry

    def mutating_agent(obs):
        obs["farms"][0]["money"] = -999999
        obs["market"]["inventory"]["WHEAT"] = -999999
        obs["private"]["seeds"]["CARROT"] = 999999
        return {"farmer": ["PASS"], "hands": [], "market": []}

    monkeypatch.setitem(registry.AGENTS, "mutating", mutating_agent)
    spec = GameSpec("mutating", 1441, "mutating", "baseline", "mutating", "baseline")
    legacy, fast, traces_match = compare_runners(spec)
    assert traces_match
    assert (legacy.reward_0, legacy.reward_1) == (fast.reward_0, fast.reward_1)


def test_fast_runner_matches_legacy_action_defaulting(monkeypatch) -> None:
    from kaggriculture_agent import registry

    def malformed_agent(_obs):
        return []

    monkeypatch.setitem(registry.AGENTS, "malformed", malformed_agent)
    spec = GameSpec("malformed", 1442, "malformed", "baseline", "malformed", "baseline")
    legacy, fast, traces_match = compare_runners(spec)
    assert traces_match
    assert legacy.status == fast.status == "completed"


def test_seat_swap_uses_paired_seed() -> None:
    schedule = build_schedule(["baseline", "candidate"], 3, 1000, True)

    assert len(schedule) == 6
    for index in range(0, len(schedule), 2):
        direct, swapped = schedule[index : index + 2]
        assert direct.seed == swapped.seed
        assert (direct.player_0, direct.player_1) == (swapped.player_1, swapped.player_0)


def test_32_seeds_with_seat_swap_are_64_games_and_32_pairs() -> None:
    schedule = build_schedule(["baseline", "candidate"], 32, 1000, True)

    assert len(schedule) == 64
    assert len({spec.pair_id for spec in schedule}) == 32
    assert all(
        len([item for item in schedule if item.seed == seed]) == 2 for seed in range(1000, 1032)
    )


def test_trajectory_rows_are_reproducible_and_compact() -> None:
    spec = GameSpec("trajectory", 817, "baseline", "candidate", "baseline", "candidate")
    first_result, first_rows = play_game_with_trajectory(spec)
    second_result, second_rows = play_game_with_trajectory(spec)

    assert first_result.status == second_result.status == "completed"
    assert first_rows == second_rows
    assert len(first_rows) == first_result.steps * 2
    assert set(TRANSITION_FIELDS).issubset(first_rows[0])
    assert "farms" not in first_rows[0]
    assert "market_price_wheat" in first_rows[0]
    assert "own_shed_fertilizer" in first_rows[0]
    assert first_rows[0]["split"] == first_rows[0]["evaluation_stage"] == "development"
    assert first_rows[0]["chosen_action_json"].startswith("{")


def test_trajectory_parquet_schemas_and_summary_counts(tmp_path: Path) -> None:
    spec = GameSpec("trajectory-schema", 818, "baseline", "candidate", "baseline", "candidate")
    result, transitions = play_game_with_trajectory(spec)
    output = tmp_path / "trajectory"
    output.mkdir()
    write_parquet(output / "transitions.parquet", TRANSITION_FIELDS, transitions)
    write_parquet(output / "episodes.parquet", EPISODE_FIELDS, episode_rows([result], [spec]))
    write_parquet(output / "pairs.parquet", PAIR_FIELDS, pair_rows([result], [spec]))

    import pyarrow.parquet as pq

    transition_table = pq.read_table(output / "transitions.parquet")
    assert transition_table.column_names == list(TRANSITION_FIELDS)
    assert transition_table.num_rows == result.steps * 2
    assert pq.read_table(output / "episodes.parquet").num_rows == 1
    assert pq.read_table(output / "pairs.parquet").num_rows == 1
    assert read_parquet(output / "transitions.parquet") == transitions


def test_schedule_ids_and_seed_assignments_are_unique() -> None:
    schedule = build_schedule(["baseline", "candidate"], 5, 2000, False)

    assert len({spec.game_id for spec in schedule}) == len(schedule)
    assert len({spec.seed for spec in schedule}) == len(schedule)


def test_worker_count_does_not_change_game_set() -> None:
    schedule = build_schedule(["baseline", "candidate"], 2, 3000, False)
    serial = list(run_games(schedule, workers=1))
    parallel = list(run_games(schedule, workers=2))

    serial_outcomes = {
        (item.game_id, item.seed, item.reward_0, item.reward_1, item.status, item.steps)
        for item in serial
    }
    parallel_outcomes = {
        (item.game_id, item.seed, item.reward_0, item.reward_1, item.status, item.steps)
        for item in parallel
    }
    assert serial_outcomes == parallel_outcomes


def test_failed_agent_is_recorded_without_exception(monkeypatch) -> None:
    from kaggriculture_agent import registry

    def broken_agent(_obs):
        raise RuntimeError("expected test failure")

    monkeypatch.setitem(registry.AGENTS, "broken", broken_agent)
    result = play_game(GameSpec("bad", 9, "broken", "baseline", "broken", "baseline"))

    assert result.status == "failed"
    assert "ERROR" in result.error


def test_matchup_and_game_csv_schemas(tmp_path: Path) -> None:
    result = play_game(GameSpec("schema", 811, "baseline", "candidate", "baseline", "candidate"))
    assert tuple(result.csv_row()) == GAME_FIELDS
    assert tuple(matchup_rows([result])[0]) == MATCHUP_FIELDS

    game_path = tmp_path / "games.csv"
    with game_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=GAME_FIELDS)
        writer.writeheader()
        writer.writerow(result.csv_row())
    assert tuple(next(csv.reader(game_path.open(encoding="utf-8")))) == GAME_FIELDS


def test_resume_skips_completed_games(tmp_path: Path) -> None:
    output = tmp_path / "arena"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_arena.py"),
        "--agents",
        "baseline,candidate",
        "--games-per-pair",
        "1",
        "--workers",
        "1",
        "--seed",
        "901",
        "--output",
        str(output),
    ]
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    before = (output / "games.csv").read_text(encoding="utf-8")
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))

    assert summary["executed_games"] == 0
    assert summary["reused_games"] == 1
    assert (output / "games.csv").read_text(encoding="utf-8") == before


def test_existing_agent_interface_regression() -> None:
    action = agent({})
    assert action == {"farmer": ["PASS"], "hands": [], "market": []}


def test_public_salem_reference_is_registered_and_runs() -> None:
    assert "public_salem" in agent_names()
    result = play_game(
        GameSpec("public", 812, "public_salem", "baseline", "public_salem", "baseline")
    )
    assert result.status == "completed"
    assert result.reward_0 is not None
    assert result.steps == 719


def test_hybrid_weed_liquidation_variants_keep_agent_interface() -> None:
    from kaggriculture_agent.registry import get_agent

    for name in (
        "salem_liquidate_29_weed_4",
        "salem_liquidate_29_weed_10",
        "salem_liquidate_29_weed_11",
        "salem_liquidate_29_weed_12",
        "salem_liquidate_29_weed_13",
        "salem_liquidate_29_weed_14",
        "salem_liquidate_29_weed_16",
        "salem_liquidate_29_weed_20",
        "salem_liquidate_29_weed_24",
        "salem_liquidate_29_weed_32",
        "salem_liquidate_29_front_carrot",
        "salem_liquidate_29_front_tomato",
        "salem_liquidate_29_front_egg",
        "salem_liquidate_29_front_scarcity",
        "salem_liquidate_28_hour_12",
        "salem_liquidate_28_hour_18",
        "salem_liquidate_28_hour_20",
        "salem_liquidate_28_hour_22",
        "salem_early_wheat",
        "salem_early_fertilizer",
        "salem_early_melon",
        "salem_early_milk",
        "salem_early_milk_6",
        "salem_early_milk_9",
        "salem_early_milk_15",
        "salem_early_milk_18",
        "salem_early_milk_day_27",
        "salem_early_milk_day_26",
        "salem_early_milk_fraction_25",
        "salem_early_milk_fraction_50",
        "salem_early_milk_fraction_75",
        "salem_early_milk_price_50",
        "salem_early_milk_price_100",
        "salem_early_milk_price_150",
        "salem_early_milk_price_200",
        "salem_early_strawberry",
        "salem_early_strawberry_18",
        "salem_early_strawberry_20",
        "salem_early_strawberry_22",
        "salem_early_wool",
        "salem_early_milk_strawberry",
        "salem_early_milk_wool",
        "salem_early_milk_melon",
        "salem_early_milk_strawberry_wool",
    ):
        action = get_agent(name)({})
        assert set(action) == {"farmer", "hands", "market"}
        assert all(isinstance(action[field], list) for field in action)
