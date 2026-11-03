from __future__ import annotations

import csv
import json
from pathlib import Path

from kaggriculture_agent.champion_arena import (
    Candidate,
    ChampionArenaConfig,
    ArchetypeSlot,
    build_champion_schedule,
    evaluate_candidate,
    matchup_score,
    mean_matchup_score,
    run_champion_arena,
)
from kaggriculture_agent.local_arena import GameResult, GameSpec


def _result(
    game_id: str,
    player_0: str,
    player_1: str,
    reward_0: float | None,
    reward_1: float | None,
    status: str = "completed",
) -> GameResult:
    return GameResult(
        game_id=game_id,
        seed=7,
        player_0=player_0,
        player_1=player_1,
        reward_0=reward_0,
        reward_1=reward_1,
        winner=(
            "draw"
            if reward_0 is None or reward_1 is None or reward_0 == reward_1
            else player_0
            if reward_0 > reward_1
            else player_1
        ),
        steps=1,
        elapsed_seconds=0.0,
        status=status,
        error="" if status == "completed" else "failed",
        agent_a="baseline",
        agent_b="candidate",
    )


def test_schedule_is_paired_and_only_contains_candidate_matchups() -> None:
    schedule = build_champion_schedule(
        ["candidate"], ["baseline", "candidate_two"], 2, 1000, True
    )

    assert len(schedule) == 8
    assert len({spec.game_id for spec in schedule}) == len(schedule)
    for index in range(0, len(schedule), 2):
        direct, swapped = schedule[index : index + 2]
        assert direct.seed == swapped.seed
        assert (direct.player_0, direct.player_1) == (swapped.player_1, swapped.player_0)
        assert {direct.agent_a, direct.agent_b} == {swapped.agent_a, swapped.agent_b}
        assert "candidate" in {direct.agent_a, direct.agent_b}


def test_mean_score_is_from_candidate_perspective() -> None:
    win = _result("win", "candidate", "baseline", 2, 1)
    draw = _result("draw", "baseline", "candidate", 4, 4)
    loss = _result("loss", "baseline", "candidate", 9, 2)

    assert matchup_score("candidate", win) == 1.0
    assert matchup_score("candidate", draw) == 0.5
    assert matchup_score("candidate", loss) == 0.0
    assert mean_matchup_score("candidate", [win, draw, loss]) == 0.5


def test_failed_game_blocks_promotion() -> None:
    schedule = [
        GameSpec("one", 7, "candidate", "baseline", "baseline", "candidate"),
        GameSpec("two", 7, "baseline", "candidate", "baseline", "candidate"),
    ]
    results = {
        "one": _result("one", "candidate", "baseline", 2, 1),
        "two": _result("two", "baseline", "candidate", None, None, "failed"),
    }

    evaluation = evaluate_candidate(
        Candidate("candidate", "general"),
        schedule,
        results,
        ["baseline"],
        incumbent="baseline",
    )

    assert evaluation.completed_games == 1
    assert evaluation.failed_games == 1
    assert evaluation.mean_matchup_score == 1.0
    assert evaluation.eligible is False


def test_persistent_resume_uses_schedule_ids(tmp_path: Path, monkeypatch) -> None:
    config = ChampionArenaConfig(
        slots=(ArchetypeSlot("general", "baseline"),),
        candidates=(Candidate("candidate", "general"),),
        games_per_matchup=1,
        seed=100,
        swap_seats=True,
        workers=1,
        output=tmp_path,
    )

    calls: list[str] = []

    def fake_run_games(specs, workers):
        for spec in specs:
            calls.append(spec.game_id)
            candidate_is_zero = spec.player_0 == "candidate"
            yield _result(
                spec.game_id,
                spec.player_0,
                spec.player_1,
                2 if candidate_is_zero else 1,
                1 if candidate_is_zero else 2,
            )

    monkeypatch.setattr("kaggriculture_agent.champion_arena.run_games", fake_run_games)
    first = run_champion_arena(config)
    with (tmp_path / "promotion_report.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    # After promotion, the candidate is now the only champion and there is no
    # self-match to schedule.  A changed config/state must therefore be a
    # deterministic no-op rather than an attempt to construct a one-agent
    # schedule.
    second = run_champion_arena(config)

    assert first["executed_games"] == 2
    assert second["executed_games"] == 0
    assert second["reused_games"] == 0
    assert len(calls) == 2
    assert json.loads((tmp_path / "state.json").read_text())['generation'] == 1
    assert rows[0]["promoted"] == "True"
    assert rows[0]["new_champion"] == "candidate"
