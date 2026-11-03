from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "omw-observed-front-run-v1"
    / "main.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("omw_observed_front_run_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_forecast_requires_three_consistent_large_sales():
    module = _load()
    assert module._forecast([(100, 8), (124, 10)], 146) is None
    assert module._forecast([(100, 8), (124, 10), (148, 9)], 146) is None
    assert module._forecast([(100, 8), (124, 10), (148, 9)], 170) == (172, 9)


def test_forecast_rejects_irregular_or_small_sales():
    module = _load()
    assert module._forecast([(100, 8), (124, 10), (155, 9)], 177) is None
    assert module._forecast([(100, 2), (124, 3), (148, 3)], 170) is None


def test_suppression_preserves_order_slot():
    module = _load()
    state = module._new_state()
    state["advanced"]["WOOL"] = 7
    action = {
        "farmer": ["PASS"],
        "hands": [],
        "market": [["SELL", "WOOL", 5], ["SELL", "MILK", 3]],
    }
    result = module._suppress_advanced(action, state)
    assert result["market"] == [["SELL", "WOOL", 0], ["SELL", "MILK", 3]]
    assert state["advanced"]["WOOL"] == 2

