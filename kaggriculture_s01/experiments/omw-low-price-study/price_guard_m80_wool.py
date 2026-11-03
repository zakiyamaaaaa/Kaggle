"""OMW price guard wrapper: WOOL only, base price minus 80 or below."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments/omw-price-guard/main.py"
spec = importlib.util.spec_from_file_location("omw_price_guard_m80_wool_source", SOURCE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {SOURCE}")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module._V92_P4_PRICE_MARGIN = -80
module._V92_P4_PRICE_ITEMS = ("WOOL",)
agent = module.agent
