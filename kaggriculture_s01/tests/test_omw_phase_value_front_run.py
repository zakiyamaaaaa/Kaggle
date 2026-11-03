from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "omw-phase-value-front-run-v3"
    / "main.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("omw_phase_value_front_run_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase_forecast_requires_two_prior_cycles():
    module = _load()
    assert module._phase_forecast([(100, 8)], 122) is None
    assert module._phase_forecast([(100, 8), (124, 10)], 146) == (148, 9, 24)


def test_phase_forecast_accepts_one_turn_jitter():
    module = _load()
    assert module._phase_forecast([(99, 8), (125, 10)], 146) == (148, 9, 24)


def test_phase_forecast_rejects_small_sales():
    module = _load()
    assert module._phase_forecast([(100, 2), (124, 3)], 146) is None

