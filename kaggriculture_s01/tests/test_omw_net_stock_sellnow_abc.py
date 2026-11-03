from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(candidate: str):
    path = ROOT / ("experiments/omw-net-stock-sellnow-v3-" + candidate) / "main.py"
    spec = importlib.util.spec_from_file_location("omw_net_stock_sellnow_v3_" + candidate, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_a_blocks_only_unknown_unlock_crossings():
    module = _load("a")
    assert module._or2_crosses_unknown_shop_unlock([], 71, 95)
    assert not module._or2_crosses_unknown_shop_unlock([], 72, 95)
    assert not module._or2_crosses_unknown_shop_unlock([], 71, 71)
    # Unlocks are with replacement: eight duplicate instances exhaust the
    # configured eight-instance town even though only one name is present.
    assert not module._or2_crosses_unknown_shop_unlock(["YARN_STORE"] * 8, 71, 95)
    assert module._source.count("or2_unlock_blocked") == 1


def test_candidate_b_refunds_partial_acceleration_debt():
    module = _load("b")
    debts = {10: {"MILK": 3}, 11: {"MILK": 2}}
    remaining = module._or2_refund_accelerated_debt(
        debts, "MILK", [(10, 2), (11, 3)], 4
    )
    assert remaining == 0
    assert debts == {10: {"MILK": 1}}


def test_candidate_b_confirms_executed_units_and_refunds_remainder():
    module = _load("b")
    old_players = module._IMPL.chassis.players
    module._IMPL.chassis.players = {
        0: {"sell_state": {"r36_debts": {10: {"MILK": 4}}}}
    }
    module._OR2_STATE[0] = {
        "or2_pending_accelerations": [
            {
                "source_step": 5,
                "item": "MILK",
                "qty": 4,
                "plan": [(10, 4)],
                "projected": {"MILK": 10},
            }
        ]
    }
    try:
        module._or2_reconcile_pending(
            {
                "step": 6,
                "player": 0,
                "private": {"shed": {"MILK": 7}},
            }
        )
    finally:
        module._IMPL.chassis.players = old_players
    assert module._OR2_STATE[0]["or2_pending_accelerations"] == []
    assert module._OR2_REPORT["or2_accel_confirmed"] == 3
    assert module._OR2_REPORT["or2_accel_refunded"] == 1


def test_candidate_b_refunds_all_when_execution_observation_is_not_adjacent():
    module = _load("b")
    old_players = module._IMPL.chassis.players
    module._IMPL.chassis.players = {
        0: {"sell_state": {"r36_debts": {10: {"MILK": 4}}}}
    }
    module._OR2_STATE[0] = {
        "or2_pending_accelerations": [
            {
                "source_step": 5,
                "item": "MILK",
                "qty": 4,
                "plan": [(10, 4)],
                "projected": {"MILK": 10},
            }
        ]
    }
    try:
        module._or2_reconcile_pending(
            {"step": 8, "player": 0, "private": {"shed": {"MILK": 6}}}
        )
    finally:
        module._IMPL.chassis.players = old_players
    assert module._OR2_REPORT["or2_accel_confirmed"] == 0
    assert module._OR2_REPORT["or2_accel_refunded"] == 4


def test_candidate_c_moves_accelerated_sell_to_earliest_safe_slot():
    module = _load("c")
    orders = [
        ["BUY_SEED", "WHEAT", 1],
        ["HIRE", "HAND", 1],
        ["SELL", "MILK", 3],
        ["SELL", "WOOL", 2],
    ]
    assert module._or2_move_accelerated_sells(orders, ["MILK"]) == [
        ["SELL", "MILK", 3],
        ["BUY_SEED", "WHEAT", 1],
        ["HIRE", "HAND", 1],
        ["SELL", "WOOL", 2],
    ]
    # A same-item buy is the dependency barrier and remains before the sell.
    assert module._or2_move_accelerated_sells(
        [["BUY_PRODUCT", "MILK", 1], ["BUY_SEED", "WHEAT", 1], ["SELL", "MILK", 3]],
        ["MILK"],
    ) == [
        ["BUY_PRODUCT", "MILK", 1],
        ["SELL", "MILK", 3],
        ["BUY_SEED", "WHEAT", 1],
    ]


def test_candidate_c_slot_move_is_after_or2_reorder_block():
    module = _load("c")
    source = module._source
    reorder = source.index('if movable and step >= 1:')
    move = source.index('if or2_accelerated_items:', reorder)
    consume = source.index('for o in orders[:10]:', move)
    assert reorder < move < consume
