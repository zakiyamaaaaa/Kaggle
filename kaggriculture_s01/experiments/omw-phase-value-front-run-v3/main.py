"""One More Wheat with phase-repeat sale prediction and value gating."""

from __future__ import annotations

import importlib.util
import statistics
from pathlib import Path


_V2_PATH = (
    Path(__file__).resolve().parents[1]
    / "omw-observed-value-front-run-v2"
    / "main.py"
)
_SPEC = importlib.util.spec_from_file_location("_omw_observed_value_front_run_v2", _V2_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load observed value front-run v2: {_V2_PATH}")
_V2 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_V2)
_V1 = _V2._V1


PHASE_PERIODS = (24, 48, 72, 96)
PHASE_TOLERANCE = 1
MIN_PHASE_QTY = 4

_STATE = {}
TELEMETRY = _V1.TELEMETRY
TELEMETRY.update(
    phase_predictions=0,
    value_gate_checks=0,
    value_gate_accepts=0,
    value_gate_rejects=0,
    estimated_gain=0.0,
)


def _nearby_event(events, target):
    matches = [
        (abs(tick - target), -qty, qty)
        for tick, qty in events
        if abs(tick - target) <= PHASE_TOLERANCE
    ]
    return min(matches) if matches else None


def _phase_forecast(events, step):
    """Predict a sale 1-2 turns ahead after two matching phase recurrences."""
    candidates = []
    for lead in (1, 2):
        target = step + lead
        for period in PHASE_PERIODS:
            first = _nearby_event(events, target - period)
            second = _nearby_event(events, target - 2 * period)
            if first is None or second is None:
                continue
            quantities = [first[2], second[2]]
            predicted_qty = int(statistics.median(quantities))
            if predicted_qty >= MIN_PHASE_QTY:
                # Prefer exact phase alignment, then the closest forecast and
                # shortest period (which reacts sooner to a changed route).
                candidates.append((first[0] + second[0], lead, period, target, predicted_qty))
    if not candidates:
        return None
    _, _, period, target, quantity = min(candidates)
    return target, quantity, period


def _front_run_phase_value(observation, action, state):
    step = int(observation["step"])
    if step < 96 or step >= 700:
        return action
    tape = _V1._native_tape(observation)
    if tape is None:
        return action
    market = [list(order) for order in action.get("market") or []]
    blocked = {
        order[1]
        for order in market
        if len(order) >= 2 and order[0] in ("SELL", "BUY_PRODUCT")
    }
    stock = None
    changed = False
    for item in _V1.PRODUCTS:
        prediction = _phase_forecast(state["events"][item], step)
        if prediction is None:
            continue
        predicted_step, predicted_qty, period = prediction
        key = (item, predicted_step, period)
        if key in state["predicted"]:
            continue
        state["predicted"].add(key)
        TELEMETRY["predictions"] += 1
        TELEMETRY["phase_predictions"] += 1
        if item in blocked or len(market) >= _V1.MAX_ORDERS:
            continue
        if int(observation["market"]["prices"].get(item, 0)) < _V1.MIN_PRICE:
            continue
        planned = _V2._next_planned_sale(tape, item, step)
        if planned is None:
            continue
        sale_step, planned_qty = planned
        if stock is None:
            stock = _V1._projected_stock(observation, action)
        quantity = min(
            max(0, int(stock.get(item, 0))),
            planned_qty,
            predicted_qty,
            _V1.MAX_ADVANCE_QTY,
        )
        if quantity <= 0:
            continue
        TELEMETRY["value_gate_checks"] += 1
        gain = _V2._expected_gain(
            observation,
            item,
            quantity,
            predicted_qty,
            step,
            sale_step,
        )
        if gain < _V2.MIN_EXPECTED_GAIN or gain / quantity < _V2.MIN_GAIN_PER_UNIT:
            TELEMETRY["value_gate_rejects"] += 1
            continue
        market.insert(0, ["SELL", item, quantity])
        state["advanced"][item] += quantity
        blocked.add(item)
        TELEMETRY["value_gate_accepts"] += 1
        TELEMETRY["estimated_gain"] += gain
        TELEMETRY["front_run_fires"] += 1
        TELEMETRY["front_run_units"] += quantity
        changed = True
    if not changed:
        return action
    result = dict(action)
    result["market"] = market[:_V1.MAX_ORDERS]
    return result


def agent(observation, configuration=None):
    player = int(observation["player"])
    step = int(observation["step"])
    state = _STATE.get(player)
    if state is None or step <= state["step"]:
        state = _STATE[player] = _V1._new_state()
        if step == 0:
            for key in TELEMETRY:
                TELEMETRY[key] = 0.0 if key == "estimated_gain" else 0
    state["step"] = step
    parent_action = _V1._PARENT.agent(observation, configuration)
    try:
        _V1._recover_rival_sales(observation, state)
        action = _V1._suppress_advanced(parent_action, state)
        action = _front_run_phase_value(observation, action, state)
        _V1._remember(observation, action, state)
        return action
    except Exception:
        TELEMETRY["errors"] += 1
        try:
            _V1._remember(observation, parent_action, state)
        except Exception:
            state["prev"] = None
        return parent_action


agent.telemetry = TELEMETRY
