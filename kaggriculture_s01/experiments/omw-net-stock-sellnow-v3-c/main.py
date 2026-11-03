"""OMW net-stock sell-now candidate C.

Candidate C is candidate B plus order placement: an accelerated SELL is moved
to the earliest market slot that cannot violate a same-item purchase
dependency. The v2/B order cap and all unrelated order relative order remain
unchanged.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


_B_PATH = (
    Path(__file__).resolve().parents[1]
    / "omw-net-stock-sellnow-v3-b"
    / "main.py"
)
_SPEC = importlib.util.spec_from_file_location("_omw_net_stock_sellnow_v3_b_for_c", _B_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load OMW net-stock sell-now candidate B: %s" % _B_PATH)
_B = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_B)

RIVAL_STOCK_THRESHOLD = _B.RIVAL_STOCK_THRESHOLD
NET_STOCK_BUFFER = _B.NET_STOCK_BUFFER
MIN_EXPOSURE = _B.MIN_EXPOSURE


_source = _B._source

_C_HELPERS = (
    "\n# OMW net-stock sell-now candidate C: earliest safe SELL slot.\n"
    "_OR2_REPORT.setdefault(\"or2_accel_slot_moves\", 0)\n\n"
    "def _or2_move_accelerated_sells(orders, items):\n"
    "    \"\"\"Move each accelerated SELL to its earliest dependency-safe slot.\n\n"
    "    A same-item BUY_PRODUCT/BUY_ANIMAL must remain before the SELL. The v2\n"
    "    acceleration branch already abstains when such a buy is present; the\n"
    "    dependency rule keeps this helper safe for direct use and future tapes.\n"
    "    \"\"\"\n"
    "    result = [list(order) for order in (orders or [])]\n"
    "    for item in items or ():\n"
    "        index = next((i for i, order in enumerate(result)\n"
    "                      if len(order) >= 3 and order[0] == \"SELL\" and order[1] == item), None)\n"
    "        if index is None:\n"
    "            continue\n"
    "        target = 0\n"
    "        for i, order in enumerate(result[:index]):\n"
    "            if (len(order) >= 2 and order[0] in (\"BUY_PRODUCT\", \"BUY_ANIMAL\")\n"
    "                    and order[1] == item):\n"
    "                target = i + 1\n"
    "        if target == index:\n"
    "            continue\n"
    "        accelerated = result.pop(index)\n"
    "        if target > index:\n"
    "            target -= 1\n"
    "        result.insert(target, accelerated)\n"
    "    return result\n"
)

_report_update_marker = (
    '_OR2_REPORT.update({\n'
    '    "or2_accel_confirmed": 0,\n'
    '    "or2_accel_refunded": 0,\n'
    '    "or2_debt_corrections": 0,\n'
    '    "or2_debt_errors": 0,\n'
    '})\n'
)
if _source.count(_report_update_marker) != 1:
    raise RuntimeError("unexpected candidate B report definition")
_source = _source.replace(_report_update_marker, _report_update_marker + _C_HELPERS, 1)

_old_orders_setup = (
    '            orders = [list(o) for o in (action.get("market") or [])]\n'
)
if _source.count(_old_orders_setup) != 1:
    raise RuntimeError("unexpected OR2 order setup")
_source = _source.replace(
    _old_orders_setup,
    _old_orders_setup + '            or2_accelerated_items = []\n',
    1,
)

_old_trigger_item = (
    '                        st["or2_pending_accelerations"].append({\n'
    '                            "source_step": step, "item": item, "qty": take,\n'
    '                            "plan": list(plan), "projected": dict(base_proj),\n'
    '                        })\n'
)
if _source.count(_old_trigger_item) != 1:
    raise RuntimeError("unexpected candidate B trigger ledger")
_source = _source.replace(
    _old_trigger_item,
    _old_trigger_item + '                        or2_accelerated_items.append(item)\n',
    1,
)

_old_sort_tail = (
    '                    action["market"] = new\n'
    '                    orders = new\n'
    '            for o in orders[:10]:\n'
)
_new_sort_tail = (
    '                    action["market"] = new\n'
    '                    orders = new\n'
    '            if or2_accelerated_items:\n'
    '                moved = _or2_move_accelerated_sells(orders, or2_accelerated_items)\n'
    '                if moved != orders:\n'
    '                    _OR2_REPORT["or2_accel_slot_moves"] = (\n'
    '                        _OR2_REPORT.get("or2_accel_slot_moves", 0) + 1\n'
    '                    )\n'
    '                    action = dict(action)\n'
    '                    action["market"] = moved\n'
    '                    orders = moved\n'
    '            for o in orders[:10]:\n'
)
if _source.count(_old_sort_tail) != 1:
    raise RuntimeError("unexpected OR2 sort tail")
_source = _source.replace(_old_sort_tail, _new_sort_tail, 1)

exec(compile(_source, str(_B_PATH), "exec"), globals())

_GENERATED_AGENT = agent  # noqa: F821 - provided by the inlined parent source
TELEMETRY = {}


def agent(observation, configuration=None):
    action = _GENERATED_AGENT(observation, configuration)
    TELEMETRY.clear()
    TELEMETRY.update(
        {
            "candidate": "C",
            "threshold": RIVAL_STOCK_THRESHOLD,
            "net_buffer": NET_STOCK_BUFFER,
            "min_exposure": MIN_EXPOSURE,
        }
    )
    TELEMETRY.update(_OR2_REPORT)  # noqa: F821 - provided by the inlined parent source
    return action


agent.telemetry = TELEMETRY
