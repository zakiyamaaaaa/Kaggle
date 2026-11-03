from __future__ import annotations

import importlib.util
from pathlib import Path


EXPERIMENT = Path(__file__).resolve().parents[1] / "experiments/omw-funding-order-invariant-v1/main.py"


def load_experiment():
    spec = importlib.util.spec_from_file_location("omw_foi_experiment", EXPERIMENT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    namespace = {}
    exec(compile(module._source, str(EXPERIMENT), "exec"), namespace)
    return type("LoadedSource", (), namespace)


def test_fixed_orders_never_move_earlier():
    module = load_experiment()
    orders = [
        ["HIRE"],
        ["SELL", "MILK", 3],
        ["BUY_SEED", "WHEAT", 2],
        ["SELL", "WOOL", 2],
        ["BUY_PRODUCT", "WHEAT", 1],
        ["SELL", "WHEAT", 1],
    ]
    candidate, changed = module._foi_sales_first(orders)
    assert changed
    original_fixed = [i for i, order in enumerate(orders) if order[0] in module._FOI_FIXED]
    candidate_fixed = [i for i, order in enumerate(candidate) if order[0] in module._FOI_FIXED]
    assert len(candidate_fixed) == len(original_fixed)
    assert all(new >= old for new, old in zip(candidate_fixed, original_fixed))
    assert candidate.index(["SELL", "MILK", 3]) < candidate.index(["HIRE"])
    assert candidate.index(["SELL", "WOOL", 2]) < candidate.index(["BUY_SEED", "WHEAT", 2])


def test_same_item_wash_sale_and_buy_product_are_fixed():
    module = load_experiment()
    orders = [
        ["BUY_PRODUCT", "WHEAT", 3],
        ["SELL", "WHEAT", 3],
        ["HIRE"],
        ["SELL", "MILK", 2],
    ]
    candidate, changed = module._foi_sales_first(orders)
    assert changed
    assert candidate[0] == orders[0]
    assert candidate[1] == orders[1]
    assert candidate[2] == ["SELL", "MILK", 2]
    assert candidate[3] == ["HIRE"]
