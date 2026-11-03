"""One More Wheat with a funding-order invariant market overlay.

The frozen OMW policy remains the parent.  This overlay only moves existing
SELL orders across funding-sensitive fixed-price orders when the move makes
cash available earlier in the same market queue.  BUY_PRODUCT orders and
same-item wash sales stay fixed because their slot can be semantically
important.
"""

from __future__ import annotations

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

MIN_STEP = int(os.environ.get("OMW_FOI_FROM", "216"))
if MIN_STEP < 0:
    raise ValueError("OMW_FOI_FROM must be non-negative")

_source = _PARENT_PATH.read_text()
_source += r'''

# EXP-OMW-FOI-001: funding-order invariant adapted from the public V57 design.
# Fixed-price orders may keep their parent slot or move later, never earlier.
# Only SELL orders that are not a same-item BUY_PRODUCT wash are movable.
_FOI_FIXED = ("HIRE", "BUY_SEED", "BUY_ANIMAL", "BUY_LAND")
_FOI_FROM = __OMW_FOI_MIN_STEP__
_FOI_REPORT = {
    "foi_turns": 0,
    "foi_moved_sells": 0,
    "foi_blocked_candidates": 0,
    "foi_errors": 0,
}


def _foi_sales_first(orders):
    """Return a funding-safe sales-first candidate, if one exists.

    This is the deterministic member of the same candidate family used by
    V57: eligible SELLs fill the earlier slots, while fixed orders retain
    their relative order.  The explicit position check is the invariant and
    protects against a future change to the candidate construction.
    """
    original = [list(order) if isinstance(order, (list, tuple)) else order
                for order in orders]
    if len(original) < 2:
        return original, False

    bought = {
        order[1]
        for order in original
        if order and len(order) > 1 and order[0] == "BUY_PRODUCT"
    }
    slots = []
    sells = []
    fixed = []
    for index, order in enumerate(original):
        if not order:
            continue
        if order[0] in _FOI_FIXED:
            slots.append(index)
            fixed.append(order)
        elif order[0] == "SELL" and len(order) > 1 and order[1] not in bought:
            slots.append(index)
            sells.append(order)

    if not sells or not fixed:
        return original, False
    if not any(
        sell_index > fixed_index
        for sell_index, order in enumerate(original)
        if order and order[0] == "SELL" and len(order) > 1
        and order[1] not in bought
        for fixed_index, fixed_order in enumerate(original)
        if fixed_order and fixed_order[0] in _FOI_FIXED
    ):
        return original, False

    candidate = list(original)
    sale_slots = slots[:len(sells)]
    fixed_slots = slots[len(sells):]
    for index, order in zip(sale_slots, sells):
        candidate[index] = order
    for index, order in zip(fixed_slots, fixed):
        candidate[index] = order

    original_fixed = [
        index for index in slots
        if original[index] and original[index][0] in _FOI_FIXED
    ]
    candidate_fixed = [
        index for index in slots
        if candidate[index] and candidate[index][0] in _FOI_FIXED
    ]
    if len(candidate_fixed) != len(original_fixed) or any(
        new < old for new, old in zip(candidate_fixed, original_fixed)
    ):
        _FOI_REPORT["foi_blocked_candidates"] += 1
        return original, False
    if candidate == original:
        return original, False
    return candidate, True


_FOI_PARENT = agent


def _foi_agent(observation, configuration=None):
    action = None
    try:
        if int(observation.get("step", 0)) == 0:
            _FOI_REPORT.update(
                foi_turns=0,
                foi_moved_sells=0,
                foi_blocked_candidates=0,
                foi_errors=0,
            )
        action = _FOI_PARENT(observation, configuration)
        if int(observation.get("step", 0)) < _FOI_FROM:
            return action
        market = action.get("market") or []
        candidate, changed = _foi_sales_first(market)
        if changed:
            _FOI_REPORT["foi_turns"] += 1
            _FOI_REPORT["foi_moved_sells"] += sum(
                1 for before, after in zip(market, candidate) if before != after
                and after and after[0] == "SELL"
            )
            action = dict(action, market=candidate)
        return action
    except Exception:
        _FOI_REPORT["foi_errors"] += 1
        return action if action is not None else _FOI_PARENT(observation, configuration)


_FOI_TELEMETRY = {}


def _foi_telemetry_agent(observation, configuration=None):
    result = _foi_agent(observation, configuration)
    _FOI_TELEMETRY.clear()
    parent_telemetry = getattr(_FOI_PARENT, "telemetry", {})
    if isinstance(parent_telemetry, dict):
        _FOI_TELEMETRY.update(parent_telemetry)
    _FOI_TELEMETRY.update(_FOI_REPORT)
    return result


_foi_telemetry_agent.telemetry = _FOI_TELEMETRY
agent = _foi_telemetry_agent
kaggle_submission_agent = agent
'''.replace("__OMW_FOI_MIN_STEP__", str(MIN_STEP))
