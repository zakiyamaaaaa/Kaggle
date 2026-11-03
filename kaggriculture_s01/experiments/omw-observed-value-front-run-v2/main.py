"""Observation-driven front-running with an exact-price value gate.

This v2 keeps the v1 cadence detector, but advances only the next planned lot
and only when the engine's market curve estimates that selling now beats waiting
until after the predicted rival sale and intervening town demand.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path


_V1_PATH = (
    Path(__file__).resolve().parents[1]
    / "omw-observed-front-run-v1"
    / "main.py"
)
_SPEC = importlib.util.spec_from_file_location("_omw_observed_front_run_v1", _V1_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load observed front-run v1: {_V1_PATH}")
_V1 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_V1)


# Exact defaults from kaggle-environments 1.32.7, Apache-2.0.
_MARKET_PARAMS = {
    "WHEAT": {"base": 25, "I0": 10000, "T": 400, "below_func": "sqrt", "below_target": 0.8, "above_func": "log", "above_target": 0.2},
    "CARROT": {"base": 35, "I0": 10000, "T": 450, "below_func": "hinge", "below_target": 1.0, "above_func": "sqrt", "above_target": 0.7},
    "TOMATO": {"base": 60, "I0": 10000, "T": 200, "below_func": "hinge", "below_target": 0.4, "above_func": "sqrt", "above_target": 0.6},
    "STRAWBERRY": {"base": 120, "I0": 10000, "T": 100, "below_func": "sqrt", "below_target": 0.7, "above_func": "linear", "above_target": 1.6},
    "MELON": {"base": 250, "I0": 10000, "T": 300, "below_func": "log", "below_target": 0.2, "above_func": "sq", "above_target": 3.6},
    "EGG": {"base": 50, "I0": 10000, "T": 332, "below_func": "hinge", "below_target": 0.4, "above_func": "log", "above_target": 0.2},
    "MILK": {"base": 160, "I0": 10000, "T": 122, "below_func": "sqrt", "below_target": 0.6, "above_func": "linear", "above_target": 1.6},
    "WOOL": {"base": 200, "I0": 10000, "T": 105, "below_func": "log", "below_target": 0.2, "above_func": "sq", "above_target": 3.2},
    "FERTILIZER": {"base": 100, "I0": 10000, "T": 200, "below_func": "linear", "below_target": 0.4, "above_func": "linear", "above_target": 0.4},
}

MIN_EXPECTED_GAIN = 4
MIN_GAIN_PER_UNIT = 0.5
MIN_RESOLVED_FORECASTS = 2
MIN_FORECAST_HIT_RATE = 0.75

_STATE = {}
TELEMETRY = _V1.TELEMETRY
TELEMETRY.update(
    value_gate_checks=0,
    value_gate_accepts=0,
    value_gate_rejects=0,
    estimated_gain=0.0,
    forecast_hits=0,
    forecast_misses=0,
    confidence_rejects=0,
)


def _new_state():
    state = _V1._new_state()
    state["pending_forecasts"] = []
    state["forecast_stats"] = {
        item: {"hits": 0, "misses": 0} for item in _V1.PRODUCTS
    }
    return state


def _settle_forecasts(state, step):
    """Score forecasts only after the predicted public sale tick is observable."""
    remaining = []
    for forecast in state["pending_forecasts"]:
        item, predicted_step, predicted_qty = forecast
        if predicted_step > step - 1:
            remaining.append(forecast)
            continue
        actual = max(
            (
                qty
                for event_step, qty in state["events"][item]
                if abs(event_step - predicted_step) <= 1
            ),
            default=0,
        )
        stats = state["forecast_stats"][item]
        if actual >= max(_V1.MASS_SALE_QTY, predicted_qty // 2):
            stats["hits"] += 1
            TELEMETRY["forecast_hits"] += 1
        else:
            stats["misses"] += 1
            TELEMETRY["forecast_misses"] += 1
    state["pending_forecasts"] = remaining


def _forecast_is_trusted(state, item):
    stats = state["forecast_stats"][item]
    resolved = stats["hits"] + stats["misses"]
    return (
        resolved >= MIN_RESOLVED_FORECASTS
        and stats["hits"] / resolved >= MIN_FORECAST_HIT_RATE
    )


def _shape(func, x, threshold=None):
    x = max(0.0, float(x))
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "log10":
        return math.log10(1.0 + x)
    if func == "hinge":
        if not threshold or threshold <= 0:
            return x
        u = x / threshold
        return u + 8.0 * max(0.0, u - 1.0) ** 2
    return x


def _params(observation):
    params = {item: dict(values) for item, values in _MARKET_PARAMS.items()}
    for item, patch in (observation["market"].get("params") or {}).items():
        if item in params:
            params[item].update(patch)
    return params


def _market_price(item, inventory, params):
    p = params[item]
    base, midpoint, threshold = p["base"], p["I0"], p["T"]
    if inventory < midpoint:
        func = p["below_func"]
        amp = p["below_target"] * base / _shape(func, threshold, threshold)
        price = base + amp * _shape(func, midpoint - inventory, threshold)
    else:
        func = p["above_func"]
        amp = p["above_target"] * base / _shape(func, threshold, threshold)
        price = base - amp * _shape(func, inventory - midpoint, threshold)
    return max(1, int(round(price)))


def _sale_revenue(item, inventory, quantity, params):
    return sum(_market_price(item, inventory + offset, params) for offset in range(quantity))


def _next_planned_sale(tape, item, step):
    if tape is None:
        return None
    for turn in range(step + 1, min(len(tape), step + _V1.OWN_PLAN_HORIZON + 1)):
        quantity = sum(
            min(_V1.MAX_ADVANCE_QTY, max(0, int(order[2])))
            for order in (tape[turn] or {}).get("market") or []
            if len(order) >= 3 and order[0] == "SELL" and order[1] == item
        )
        if quantity > 0:
            return turn, quantity
    return None


def _demand_before_sale(observation, item, step, sale_step):
    shops = list(observation["town"]["unlocked_shops"])
    return sum(
        _V1._town_draw(shops, turn).get(item, 0)
        for turn in range(step, sale_step)
    )


def _expected_gain(observation, item, quantity, predicted_qty, step, sale_step):
    params = _params(observation)
    inventory = int(observation["market"]["inventory"].get(item, 0))
    demand = _demand_before_sale(observation, item, step, sale_step)
    later_inventory = max(0, inventory + int(predicted_qty) - demand)
    now = _sale_revenue(item, inventory, quantity, params)
    later = _sale_revenue(item, later_inventory, quantity, params)
    return now - later


def _front_run_value(observation, action, state):
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
        prediction = _V1._forecast(state["events"][item], step)
        if prediction is None:
            continue
        predicted_step, predicted_qty = prediction
        key = (item, predicted_step)
        if key in state["predicted"]:
            continue
        state["predicted"].add(key)
        state["pending_forecasts"].append((item, predicted_step, predicted_qty))
        TELEMETRY["predictions"] += 1
        if item in blocked or len(market) >= _V1.MAX_ORDERS:
            continue
        if int(observation["market"]["prices"].get(item, 0)) < _V1.MIN_PRICE:
            continue
        planned = _next_planned_sale(tape, item, step)
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
        if not _forecast_is_trusted(state, item):
            TELEMETRY["confidence_rejects"] += 1
            continue
        TELEMETRY["value_gate_checks"] += 1
        gain = _expected_gain(
            observation,
            item,
            quantity,
            predicted_qty,
            step,
            sale_step,
        )
        if gain < MIN_EXPECTED_GAIN or gain / quantity < MIN_GAIN_PER_UNIT:
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
        state = _STATE[player] = _new_state()
        if step == 0:
            for key in TELEMETRY:
                TELEMETRY[key] = 0.0 if key == "estimated_gain" else 0
    state["step"] = step
    parent_action = _V1._PARENT.agent(observation, configuration)
    try:
        _V1._recover_rival_sales(observation, state)
        _settle_forecasts(state, step)
        action = _V1._suppress_advanced(parent_action, state)
        action = _front_run_value(observation, action, state)
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
