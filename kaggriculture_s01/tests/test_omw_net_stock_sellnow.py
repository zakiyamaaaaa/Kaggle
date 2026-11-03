from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "omw-net-stock-sellnow-v2"
    / "main.py"
)


def test_loads_demand_adjusted_sellnow_candidate():
    spec = importlib.util.spec_from_file_location("omw_net_stock_sellnow_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.RIVAL_STOCK_THRESHOLD == 12
    assert module.NET_STOCK_BUFFER == 12
    assert module.MIN_EXPOSURE == 1
    assert module._OR2_SN_K == 12
    assert callable(module.agent)
