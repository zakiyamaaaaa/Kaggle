from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "omw-observed-value-front-run-v2"
    / "main.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("omw_observed_value_front_run_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_price_falls_as_premium_inventory_rises():
    module = _load()
    params = module._MARKET_PARAMS
    assert module._market_price("WOOL", 10000, params) > module._market_price("WOOL", 10020, params)


def test_value_gate_rewards_beating_a_large_sale():
    module = _load()
    observation = {
        "market": {"inventory": {"WOOL": 10000}, "prices": {"WOOL": 200}, "params": {}},
        "town": {"unlocked_shops": []},
    }
    assert module._expected_gain(observation, "WOOL", 8, 20, 200, 202) > 0


def test_demand_recovery_can_remove_early_sale_advantage():
    module = _load()
    observation = {
        "market": {"inventory": {"WOOL": 10000}, "prices": {"WOOL": 200}, "params": {}},
        "town": {"unlocked_shops": ["YARN_STORE"]},
    }
    short = module._expected_gain(observation, "WOOL", 8, 8, 199, 201)
    recovered = module._expected_gain(observation, "WOOL", 8, 8, 199, 224)
    assert recovered <= short


def test_forecast_must_prove_online_accuracy_before_trading():
    module = _load()
    state = module._new_state()
    assert not module._forecast_is_trusted(state, "WOOL")
    state["forecast_stats"]["WOOL"] = {"hits": 2, "misses": 0}
    assert module._forecast_is_trusted(state, "WOOL")
    state["forecast_stats"]["WOOL"] = {"hits": 2, "misses": 1}
    assert not module._forecast_is_trusted(state, "WOOL")
