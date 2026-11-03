import pytest

from kaggriculture_agent.rating import aggregate_games, estimate_ratings


def _game(game_id: str, left: str, right: str, reward_left, reward_right, status="completed"):
    return {
        "game_id": game_id,
        "player_0": left,
        "player_1": right,
        "reward_0": reward_left,
        "reward_1": reward_right,
        "status": status,
    }


def test_winner_has_higher_rating_and_lcb_fields() -> None:
    result = estimate_ratings([_game(f"g{i}", "strong", "weak", 2, 1) for i in range(20)])
    by_name = {row["agent"]: row for row in result["ratings"]}
    assert by_name["strong"]["mu"] > by_name["weak"]["mu"]
    assert by_name["strong"]["lcb"] == pytest.approx(
        by_name["strong"]["mu"] - 2 * by_name["strong"]["sigma"]
    )
    assert result["outcome"].startswith("terminal")


def test_cash_margin_does_not_change_rating() -> None:
    close = [_game(f"c{i}", "a", "b", 2, 1) for i in range(8)]
    landslide = [_game(f"l{i}", "a", "b", 1_000_000, -5) for i in range(8)]
    close_mu = estimate_ratings(close)["ratings"]
    landslide_mu = estimate_ratings(landslide)["ratings"]
    assert [row["mu"] for row in close_mu] == pytest.approx(
        [row["mu"] for row in landslide_mu]
    )


def test_all_draws_produce_equal_ratings() -> None:
    result = estimate_ratings([_game(f"g{i}", "a", "b", 1, 1) for i in range(10)])
    assert [row["mu"] for row in result["ratings"]] == pytest.approx([1000, 1000])


def test_attributed_agent_error_is_a_loss_and_unknown_failure_is_excluded() -> None:
    records = [
        _game("error", "a", "b", None, 10, "failed"),
        _game("engine", "a", "b", None, None, "failed"),
    ]
    stats, _ = aggregate_games(records)
    stat = stats[("a", "b")]
    assert stat["wins"]["b"] == 1
    assert stat["errors"]["a"] == 1
    assert stat["excluded"] == 1
    assert stat["fit_games"] == 1


def test_duplicate_game_is_rejected() -> None:
    game = _game("same", "a", "b", 1, 0)
    with pytest.raises(ValueError, match="duplicate game_id"):
        estimate_ratings([game, game])


def test_disconnected_population_is_rejected() -> None:
    records = [_game("ab", "a", "b", 1, 0), _game("cd", "c", "d", 1, 0)]
    with pytest.raises(ValueError, match="disconnected"):
        estimate_ratings(records)


def test_pair_cap_limits_repeated_matchup_evidence() -> None:
    records = [_game(f"g{i}", "a", "b", 1, 0) for i in range(100)]
    uncapped = estimate_ratings(records, pair_cap=0)
    capped = estimate_ratings(records, pair_cap=10)
    uncapped_sigma = uncapped["ratings"][0]["sigma"]
    capped_sigma = capped["ratings"][0]["sigma"]
    assert capped_sigma > uncapped_sigma
