"""One More Wheat with conservative observation-driven sale front-running.

This local experiment deliberately imports the frozen public One More Wheat
source instead of modifying it.  A release bundle must inline the parent before
submission.

The overlay observes only public state.  It reconstructs the rival's executed
sales from market-inventory changes, learns a repeated sale cadence per premium
product, and advances our own already-planned lot by one or two turns when a
large rival sale is predicted.  Advanced quantities are suppressed from later
parent SELL orders so this changes timing, not intended total volume.
"""

from __future__ import annotations

import importlib.util
import statistics
from pathlib import Path


_PARENT_PATH = (
    Path(__file__).resolve().parents[2]
    / "references"
    / "kaggle-scan-2026-09-21"
    / "extracted"
    / "one-more-wheat"
    / "main.py"
)
_SPEC = importlib.util.spec_from_file_location("_omw_observed_front_run_parent", _PARENT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load One More Wheat parent: {_PARENT_PATH}")
_PARENT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PARENT)


PRODUCTS = ("MILK", "WOOL", "STRAWBERRY", "MELON", "EGG")
MAX_ORDERS = 10
MIN_EVENT_QTY = 2
MASS_SALE_QTY = 4
MIN_PRICE = 4
MIN_PERIOD = 4
MAX_PERIOD = 96
PERIOD_TOLERANCE = 2
LOOKAHEAD = 2
OWN_PLAN_HORIZON = 24
MAX_ADVANCE_QTY = 100

_SHOP_ITEMS = {
    "BAKERY": ("EGG", "WHEAT"),
    "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}

_STATE = {}
TELEMETRY = {
    "rival_sale_events": 0,
    "predictions": 0,
    "front_run_fires": 0,
    "front_run_units": 0,
    "suppressed_units": 0,
    "errors": 0,
}


def _town_draw(shops, step):
    draw = dict.fromkeys(PRODUCTS, 0)
    if step % 4 == 0:
        for shop in shops:
            items = _SHOP_ITEMS.get(shop, ())
            for item in items:
                if item in draw:
                    draw[item] += 2 if len(items) == 1 else 1
    if step % 24 == 0:
        for item in draw:
            draw[item] += 1
    return draw


def _new_state():
    return {
        "step": -1,
        "prev": None,
        "events": {item: [] for item in PRODUCTS},
        "advanced": {item: 0 for item in PRODUCTS},
        "predicted": set(),
    }


def _recover_rival_sales(observation, state):
    """Recover the previous turn's rival sales from public market inventory."""
    prev = state["prev"]
    step = int(observation["step"])
    if not prev or prev["step"] != step - 1:
        return
    inventory = observation["market"]["inventory"]
    draw = _town_draw(prev["shops"], prev["step"])
    for item in PRODUCTS:
        # At the price floor, sold units may not enter market inventory, so the
        # inversion is not reliable enough to train the cadence predictor.
        if int(prev["prices"].get(item, 0)) <= 3:
            continue
        sold = (
            int(inventory.get(item, 0))
            - int(prev["inventory"].get(item, 0))
            + int(draw.get(item, 0))
            - int(prev["own"].get(item, 0))
        )
        if sold >= MIN_EVENT_QTY:
            state["events"][item].append((prev["step"], sold))
            state["events"][item] = state["events"][item][-8:]
            TELEMETRY["rival_sale_events"] += 1


def _forecast(events, step):
    """Return (predicted_step, predicted_qty) for a stable repeated cadence."""
    if len(events) < 3:
        return None
    recent = events[-5:]
    intervals = [b[0] - a[0] for a, b in zip(recent, recent[1:])]
    period = int(round(statistics.median(intervals)))
    if not MIN_PERIOD <= period <= MAX_PERIOD:
        return None
    # Require the two most recent gaps to agree.  This avoids acting on a pair
    # of unrelated liquidation events that happen to share one interval.
    if len(intervals) < 2 or any(abs(gap - period) > PERIOD_TOLERANCE for gap in intervals[-2:]):
        return None
    quantities = [qty for _, qty in recent[-3:]]
    predicted_qty = int(statistics.median(quantities))
    if predicted_qty < MASS_SALE_QTY:
        return None
    predicted_step = recent[-1][0] + period
    if not 1 <= predicted_step - step <= LOOKAHEAD:
        return None
    return predicted_step, predicted_qty


def _native_tape(observation):
    chassis = getattr(getattr(_PARENT, "_IMPL", None), "chassis", None)
    if chassis is None:
        return None
    native = chassis.players.get(int(observation["player"]))
    if not native:
        return None
    return chassis.routes.get(native.get("route"))


def _planned_sale(tape, item, step):
    if tape is None:
        return 0
    total = 0
    for turn in range(step + 1, min(len(tape), step + OWN_PLAN_HORIZON + 1)):
        action = tape[turn] or {}
        for order in action.get("market") or []:
            if len(order) >= 3 and order[0] == "SELL" and order[1] == item:
                total += min(MAX_ADVANCE_QTY, max(0, int(order[2])))
    return total


def _suppress_advanced(action, state):
    """Pay down quantities already sold early while preserving order slots."""
    market = [list(order) for order in action.get("market") or []]
    for order in market:
        if len(order) < 3 or order[0] != "SELL" or order[1] not in state["advanced"]:
            continue
        item = order[1]
        credit = state["advanced"][item]
        if credit <= 0:
            continue
        removed = min(max(0, int(order[2])), credit)
        order[2] = max(0, int(order[2]) - removed)
        state["advanced"][item] -= removed
        TELEMETRY["suppressed_units"] += removed
    result = dict(action)
    result["market"] = market
    return result


def _projected_stock(observation, action):
    view = _PARENT.FarmView(observation)
    return _PARENT.projected_shed(action, view)


def _front_run(observation, action, state):
    step = int(observation["step"])
    if step < 96 or step >= 700:
        return action
    tape = _native_tape(observation)
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
    for item in PRODUCTS:
        prediction = _forecast(state["events"][item], step)
        if prediction is None:
            continue
        predicted_step, predicted_qty = prediction
        key = (item, predicted_step)
        if key in state["predicted"]:
            continue
        TELEMETRY["predictions"] += 1
        state["predicted"].add(key)
        if item in blocked or len(market) >= MAX_ORDERS:
            continue
        if int(observation["market"]["prices"].get(item, 0)) < MIN_PRICE:
            continue
        planned = _planned_sale(tape, item, step)
        if planned <= 0:
            continue
        if stock is None:
            stock = _projected_stock(observation, action)
        qty = min(
            max(0, int(stock.get(item, 0))),
            planned,
            predicted_qty,
            MAX_ADVANCE_QTY,
        )
        if qty <= 0:
            continue
        market.insert(0, ["SELL", item, qty])
        state["advanced"][item] += qty
        blocked.add(item)
        TELEMETRY["front_run_fires"] += 1
        TELEMETRY["front_run_units"] += qty
        changed = True
    if not changed:
        return action
    result = dict(action)
    result["market"] = market[:MAX_ORDERS]
    return result


def _own_realized_sales(observation, action):
    stock = _projected_stock(observation, action)
    left = {item: max(0, int(stock.get(item, 0))) for item in PRODUCTS}
    sold = dict.fromkeys(PRODUCTS, 0)
    for order in action.get("market") or []:
        if len(order) < 3 or order[0] != "SELL" or order[1] not in sold:
            continue
        item = order[1]
        qty = min(left[item], max(0, int(order[2])))
        sold[item] += qty
        left[item] -= qty
    return sold


def _remember(observation, action, state):
    state["prev"] = {
        "step": int(observation["step"]),
        "inventory": dict(observation["market"]["inventory"]),
        "prices": dict(observation["market"]["prices"]),
        "own": _own_realized_sales(observation, action),
        "shops": list(observation["town"]["unlocked_shops"]),
    }


def agent(observation, configuration=None):
    player = int(observation["player"])
    step = int(observation["step"])
    state = _STATE.get(player)
    if state is None or step <= state["step"]:
        state = _STATE[player] = _new_state()
        if step == 0:
            for key in TELEMETRY:
                TELEMETRY[key] = 0
    state["step"] = step
    parent_action = _PARENT.agent(observation, configuration)
    try:
        _recover_rival_sales(observation, state)
        action = _suppress_advanced(parent_action, state)
        action = _front_run(observation, action, state)
        _remember(observation, action, state)
        return action
    except Exception:
        TELEMETRY["errors"] += 1
        try:
            _remember(observation, parent_action, state)
        except Exception:
            state["prev"] = None
        return parent_action


agent.telemetry = TELEMETRY

