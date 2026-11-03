from __future__ import annotations

import importlib.util
import os
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "omw-rival-stock-sellnow-v1"
    / "main.py"
)


def test_enables_parent_sellnow_threshold():
    old = os.environ.get("OMW_OR2_SN_K")
    os.environ["OMW_OR2_SN_K"] = "12"
    try:
        spec = importlib.util.spec_from_file_location("omw_rival_stock_sellnow_test", MODULE_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.RIVAL_STOCK_THRESHOLD == 12
        assert module._PARENT._OR2_SN_K == 12
        assert callable(module.agent)
    finally:
        if old is None:
            os.environ.pop("OMW_OR2_SN_K", None)
        else:
            os.environ["OMW_OR2_SN_K"] = old

