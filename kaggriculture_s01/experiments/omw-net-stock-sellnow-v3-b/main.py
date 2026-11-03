"""OMW net-stock sell-now candidate B.

Candidate B adds an execution-confirmed ledger to candidate A. Every
accelerated quantity is recorded with its future suppression plan. On the
next observation the private shed confirms how many units actually left; any
unexecuted remainder is refunded from the future debt buckets before the
parent suppression layer runs.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


_V2_PATH = (
    Path(__file__).resolve().parents[1]
    / "omw-net-stock-sellnow-v2"
    / "main.py"
)
_SPEC = importlib.util.spec_from_file_location("_omw_net_stock_sellnow_v2_for_b", _V2_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load OMW net-stock v2: %s" % _V2_PATH)
_V2 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_V2)

RIVAL_STOCK_THRESHOLD = _V2.RIVAL_STOCK_THRESHOLD
NET_STOCK_BUFFER = _V2.NET_STOCK_BUFFER
MIN_EXPOSURE = _V2.MIN_EXPOSURE


_source = _V2._source

_A_HELPERS = (
    "\n\n# OMW net-stock sell-now candidates A/B/C: unknown-shop boundary guard.\n"
    "_OR2_UNKNOWN_SHOP_UNLOCK_PERIOD = 3 * 24\n"
    "_OR2_UNKNOWN_SHOP_UNLOCK_REPORT_KEY = \"or2_unlock_blocked\"\n\n"
    "def _or2_crosses_unknown_shop_unlock(shops, start_step, horizon_end, unlock_period=72):\n"
    "    \"\"\"Return whether [start_step, horizon_end] crosses an unknown shop unlock.\"\"\"\n"
    "    try:\n"
    "        start = int(start_step)\n"
    "        end = int(horizon_end)\n"
    "        period = int(unlock_period)\n"
    "    except (TypeError, ValueError):\n"
    "        return False\n"
    "    if period <= 0 or end <= start:\n"
    "        return False\n"
    "    # The engine unlocks with replacement, so eight instances can contain\n"
    "    # duplicate shop names while still exhausting future unlocks.\n"
    "    known_count = len(tuple(shops or ()))\n"
    "    if known_count >= len(_OR2_SHOPS):\n"
    "        return False\n"
    "    next_boundary = ((start // period) + 1) * period\n"
    "    return next_boundary <= end\n\n"
    "_OR2_REPORT.setdefault(_OR2_UNKNOWN_SHOP_UNLOCK_REPORT_KEY, 0)\n"
)

_B_HELPERS = (
    "\n# OMW net-stock sell-now candidate B: execution-confirmed ledger.\n"
    "_OR2_REPORT.update({\n"
    "    \"or2_accel_confirmed\": 0,\n"
    "    \"or2_accel_refunded\": 0,\n"
    "    \"or2_debt_corrections\": 0,\n"
    "    \"or2_debt_errors\": 0,\n"
    "})\n\n"
    "def _or2_refund_accelerated_debt(debts, item, plan, quantity):\n"
    "    \"\"\"Remove an unexecuted acceleration from its booked due-step debts.\"\"\"\n"
    "    remaining = max(0, int(quantity))\n"
    "    for due_step, booked in plan or ():\n"
    "        if remaining <= 0:\n"
    "            break\n"
    "        bucket = debts.get(int(due_step), {})\n"
    "        owed = max(0, int(bucket.get(item, 0)))\n"
    "        refund = min(owed, remaining, max(0, int(booked)))\n"
    "        if refund <= 0:\n"
    "            continue\n"
    "        bucket[item] = owed - refund\n"
    "        remaining -= refund\n"
    "        if bucket.get(item, 0) <= 0:\n"
    "            bucket.pop(item, None)\n"
    "        if not bucket:\n"
    "            debts.pop(int(due_step), None)\n"
    "    return max(0, remaining)\n\n"
    "def _or2_reconcile_pending(observation):\n"
    "    \"\"\"Confirm or refund pending acceleration before parent suppression runs.\"\"\"\n"
    "    step = int(observation.get(\"step\", -1))\n"
    "    seat = int(observation.get(\"player\", 0))\n"
    "    state = _OR2_STATE.get(seat)\n"
    "    if not state:\n"
    "        return\n"
    "    pending = list(state.get(\"or2_pending_accelerations\") or [])\n"
    "    if not pending:\n"
    "        return\n"
    "    native = _IMPL.chassis.players.get(seat)\n"
    "    debts = native[\"sell_state\"].setdefault(\"r36_debts\", {}) if native else {}\n"
    "    current_private = observation.get(\"private\") or {}\n"
    "    current_shed = current_private.get(\"shed\") or {}\n"
    "    exact_next = all(step == int(entry.get(\"source_step\", -2)) + 1 for entry in pending)\n"
    "    observed = {}\n"
    "    if exact_next:\n"
    "        for entry in pending:\n"
    "            item = entry.get(\"item\")\n"
    "            previous = int((entry.get(\"projected\") or {}).get(item, 0))\n"
    "            if item not in current_shed:\n"
    "                exact_next = False\n"
    "                break\n"
    "            current = int(current_shed.get(item, 0))\n"
    "            observed[item] = max(observed.get(item, 0), max(0, previous - current))\n"
    "    for entry in pending:\n"
    "        item = entry.get(\"item\")\n"
    "        requested = max(0, int(entry.get(\"qty\", 0)))\n"
    "        confirmed = min(requested, observed.get(item, 0)) if exact_next else 0\n"
    "        observed[item] = max(0, observed.get(item, 0) - confirmed)\n"
    "        refund = requested - confirmed\n"
    "        if refund:\n"
    "            _or2_refund_accelerated_debt(debts, item, entry.get(\"plan\"), refund)\n"
    "            _OR2_REPORT[\"or2_accel_refunded\"] = _OR2_REPORT.get(\"or2_accel_refunded\", 0) + refund\n"
    "            _OR2_REPORT[\"or2_debt_corrections\"] = _OR2_REPORT.get(\"or2_debt_corrections\", 0) + 1\n"
    "        if confirmed:\n"
    "            _OR2_REPORT[\"or2_accel_confirmed\"] = _OR2_REPORT.get(\"or2_accel_confirmed\", 0) + confirmed\n"
    "    state[\"or2_pending_accelerations\"] = []\n"
)

_report_marker = (
    '_OR2_REPORT = {"or2_reordered": 0, "or2_changed_vs_v39": 0, '
    '"or2_rival_harvest": 0, "or2_rival_sold": 0,\n'
    '               "or2_errors": 0}\n'
)
if _source.count(_report_marker) != 1:
    raise RuntimeError("unexpected One More Wheat OR2 report definition")
_source = _source.replace(_report_marker, _report_marker + _A_HELPERS + _B_HELPERS, 1)

_old_guard_point = (
    '                    if take > 0:\n'
    '                        first_sale = plan[0][0]\n'
    '                        shops = list((observation.get("town") or {}).get("unlocked_shops") or [])\n'
    '                        recovery = sum(_or2_draw(shops, s).get(item, 0)\n'
    '                                       for s in range(step, first_sale))\n'
)
_new_guard_point = (
    '                    if take > 0:\n'
    '                        shops = list((observation.get("town") or {}).get("unlocked_shops") or [])\n'
    '                        horizon_end = min(694, step + _OR2_SN_H)\n'
    '                        if _or2_crosses_unknown_shop_unlock(\n'
    '                                shops, step, horizon_end, _OR2_UNKNOWN_SHOP_UNLOCK_PERIOD):\n'
    '                            _OR2_REPORT[_OR2_UNKNOWN_SHOP_UNLOCK_REPORT_KEY] = (\n'
    '                                _OR2_REPORT.get(_OR2_UNKNOWN_SHOP_UNLOCK_REPORT_KEY, 0) + take\n'
    '                            )\n'
    '                            continue\n'
    '                        first_sale = plan[0][0]\n'
    '                        recovery = sum(_or2_draw(shops, s).get(item, 0)\n'
    '                                       for s in range(step, first_sale))\n'
)
if _source.count(_old_guard_point) != 1:
    raise RuntimeError("unexpected v2 net-stock sell-now guard point")
_source = _source.replace(_old_guard_point, _new_guard_point, 1)

_old_state = (
    '            st = _OR2_STATE[seat] = {"step": -1, "stock": {i: 0 for i in _OR2_ITEMS}, "prev": None}\n'
)
if _source.count(_old_state) != 1:
    raise RuntimeError("unexpected OR2 state initialization")
_source = _source.replace(
    _old_state,
    _old_state + '            st["or2_pending_accelerations"] = []\n',
    1,
)

_old_agent_start = (
    'def agent(observation, configuration=None):\n'
    '    action = _OR2_PARENT(observation, configuration)\n'
)
_new_agent_start = (
    'def agent(observation, configuration=None):\n'
    '    try:\n'
    '        _or2_reconcile_pending(observation)\n'
    '    except Exception:\n'
    '        _OR2_REPORT["or2_debt_errors"] = _OR2_REPORT.get("or2_debt_errors", 0) + 1\n'
    '    action = _OR2_PARENT(observation, configuration)\n'
)
if _source.count(_old_agent_start) != 1:
    raise RuntimeError("unexpected OR2 agent start")
_source = _source.replace(_old_agent_start, _new_agent_start, 1)

_old_projection = (
    '            orders = [list(o) for o in (action.get("market") or [])]\n'
    '            proj = dict(projected_shed(action, FarmView(observation)))\n'
)
_new_projection = (
    '            orders = [list(o) for o in (action.get("market") or [])]\n'
    '            proj = dict(projected_shed(action, FarmView(observation)))\n'
    '            base_proj = dict(proj)\n'
    '            st.setdefault("or2_pending_accelerations", [])\n'
)
if _source.count(_old_projection) != 1:
    raise RuntimeError("unexpected OR2 projection setup")
_source = _source.replace(_old_projection, _new_projection, 1)

_old_trigger_tail = (
    '                        _OR2_REPORT["or2_net_triggered"] = _OR2_REPORT.get("or2_net_triggered", 0) + take\n'
    '                        action = dict(action)\n'
    '                        action["market"] = orders\n'
)
_new_trigger_tail = (
    '                        _OR2_REPORT["or2_net_triggered"] = _OR2_REPORT.get("or2_net_triggered", 0) + take\n'
    '                        st["or2_pending_accelerations"].append({\n'
    '                            "source_step": step, "item": item, "qty": take,\n'
    '                            "plan": list(plan), "projected": dict(base_proj),\n'
    '                        })\n'
    '                        action = dict(action)\n'
    '                        action["market"] = orders\n'
)
if _source.count(_old_trigger_tail) != 1:
    raise RuntimeError("unexpected OR2 trigger tail")
_source = _source.replace(_old_trigger_tail, _new_trigger_tail, 1)

exec(compile(_source, str(_V2_PATH), "exec"), globals())

_GENERATED_AGENT = agent  # noqa: F821 - provided by the inlined parent source
TELEMETRY = {}


def agent(observation, configuration=None):
    action = _GENERATED_AGENT(observation, configuration)
    TELEMETRY.clear()
    TELEMETRY.update(
        {
            "candidate": "B",
            "threshold": RIVAL_STOCK_THRESHOLD,
            "net_buffer": NET_STOCK_BUFFER,
            "min_exposure": MIN_EXPOSURE,
        }
    )
    TELEMETRY.update(_OR2_REPORT)  # noqa: F821 - provided by the inlined parent source
    return action


agent.telemetry = TELEMETRY
