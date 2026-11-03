"""Enable One More Wheat's dormant ORDERPRI2 observed-stock sell-now layer."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


_PARENT_PATH = (
    Path(__file__).resolve().parents[2]
    / "references"
    / "kaggle-scan-2026-09-21"
    / "extracted"
    / "one-more-wheat"
    / "main.py"
)
_SPEC = importlib.util.spec_from_file_location("_omw_rival_stock_sellnow_parent", _PARENT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load One More Wheat parent: {_PARENT_PATH}")
_PARENT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PARENT)


RIVAL_STOCK_THRESHOLD = int(os.environ.get("OMW_OR2_SN_K", "12"))
if RIVAL_STOCK_THRESHOLD <= 0:
    raise ValueError("OMW_OR2_SN_K must be positive")

# ORDERPRI2 already maintains a conservative public-state estimate of rival
# sellable stock from visible harvests minus recovered market sales.  Its
# sell-now branch is shipped disabled at zero; enabling K leaves all other One
# More Wheat behavior and its existing debt/suppression ledger unchanged.
_PARENT._OR2_SN_K = RIVAL_STOCK_THRESHOLD
TELEMETRY = {"threshold": RIVAL_STOCK_THRESHOLD}
_GATE_DIAGNOSTICS = {
    "risk_turns": 0,
    "risk_drop_ge_1": 0,
    "risk_drop_ge_2": 0,
    "risk_drop_ge_4": 0,
    "risk_drop_ge_8": 0,
    "risk_max_drop": 0.0,
}


def _observe_price_risk(observation):
    """Measure the one-unit price damage implied by the tracked rival stock."""
    if int(observation.get("step", 0)) == 0:
        for key in _GATE_DIAGNOSTICS:
            _GATE_DIAGNOSTICS[key] = 0.0 if key == "risk_max_drop" else 0
    seat = int(observation["player"])
    state = _PARENT._OR2_STATE.get(seat)
    if not state:
        return
    drops = []
    for item in _PARENT._OR2_SN_ITEMS:
        batch = int(state["stock"].get(item, 0))
        if batch >= RIVAL_STOCK_THRESHOLD:
            drops.append(_PARENT._or2_exposure(observation, item, 1, batch))
    if not drops:
        return
    worst = max(drops)
    _GATE_DIAGNOSTICS["risk_turns"] += 1
    _GATE_DIAGNOSTICS["risk_max_drop"] = max(_GATE_DIAGNOSTICS["risk_max_drop"], worst)
    for cutoff in (1, 2, 4, 8):
        if worst >= cutoff:
            _GATE_DIAGNOSTICS[f"risk_drop_ge_{cutoff}"] += 1


def agent(observation, configuration=None):
    _observe_price_risk(observation)
    action = _PARENT.agent(observation, configuration)
    TELEMETRY.clear()
    TELEMETRY["threshold"] = RIVAL_STOCK_THRESHOLD
    TELEMETRY.update(getattr(_PARENT, "_OR2_REPORT", {}))
    TELEMETRY.update(_GATE_DIAGNOSTICS)
    return action


agent.telemetry = TELEMETRY
