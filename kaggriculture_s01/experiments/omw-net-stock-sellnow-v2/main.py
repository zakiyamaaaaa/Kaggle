"""One More Wheat with demand-adjusted observed-rival sell front-running."""

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

RIVAL_STOCK_THRESHOLD = int(os.environ.get("OMW_NET_SN_K", "12"))
NET_STOCK_BUFFER = int(os.environ.get("OMW_NET_SN_BUFFER", "12"))
MIN_EXPOSURE = float(os.environ.get("OMW_NET_SN_EXPOSURE", "1"))
if RIVAL_STOCK_THRESHOLD <= 0 or NET_STOCK_BUFFER < 0 or MIN_EXPOSURE < 0:
    raise ValueError("invalid OMW net-stock sell-now parameters")

_source = _PARENT_PATH.read_text()
_source, _constant_edits = _source.replace(
    "_OR2_SN_K = 0",
    f"_OR2_SN_K = {RIVAL_STOCK_THRESHOLD}",
    1,
), _source.count("_OR2_SN_K = 0")
if _constant_edits != 1:
    raise RuntimeError("unexpected One More Wheat OR2 threshold definition")

_old = '''                    take = 0
                    for t in range(step + 1, min(694, step + _OR2_SN_H) + 1):
                        if take >= avail:
                            break
                        tape = _IMPL.chassis.routes[2 if t >= 648 else native["route"]]
                        act = tape[t] if t < len(tape) and isinstance(tape[t], dict) else {}
                        planned = sum(max(0, int(o[2])) for o in (act.get("market") or [])
                                      if len(o) >= 3 and o[0] == "SELL" and o[1] == item)
                        planned -= debts.get(t, {}).get(item, 0)
                        q = min(planned, avail - take)
                        if q > 0:
                            debts.setdefault(t, {})[item] = debts.get(t, {}).get(item, 0) + q
                            take += q
                    if take > 0:
                        for o in orders:
                            if len(o) >= 3 and o[0] == "SELL" and o[1] == item:
                                o[2] = int(o[2]) + take
                                break
                        else:
                            orders.append(["SELL", item, take])
                        _OR2_REPORT["or2_sellnow"] = _OR2_REPORT.get("or2_sellnow", 0) + take
                        action = dict(action)
                        action["market"] = orders
'''

_new = f'''                    take = 0
                    plan = []
                    for t in range(step + 1, min(694, step + _OR2_SN_H) + 1):
                        if take >= avail:
                            break
                        tape = _IMPL.chassis.routes[2 if t >= 648 else native["route"]]
                        act = tape[t] if t < len(tape) and isinstance(tape[t], dict) else {{}}
                        planned = sum(max(0, int(o[2])) for o in (act.get("market") or [])
                                      if len(o) >= 3 and o[0] == "SELL" and o[1] == item)
                        planned -= debts.get(t, {{}}).get(item, 0)
                        q = min(planned, avail - take)
                        if q > 0:
                            plan.append((t, q))
                            take += q
                    if take > 0:
                        first_sale = plan[0][0]
                        shops = list((observation.get("town") or {{}}).get("unlocked_shops") or [])
                        recovery = sum(_or2_draw(shops, s).get(item, 0)
                                       for s in range(step, first_sale))
                        rival_stock = int(st["stock"].get(item, 0))
                        net_batch = max(0, rival_stock - recovery)
                        exposure = _or2_exposure(observation, item, take, net_batch)
                        if net_batch < {NET_STOCK_BUFFER} or exposure < {MIN_EXPOSURE!r}:
                            _OR2_REPORT["or2_net_blocked"] = _OR2_REPORT.get("or2_net_blocked", 0) + take
                            continue
                        for due, q in plan:
                            debts.setdefault(due, {{}})[item] = debts.get(due, {{}}).get(item, 0) + q
                        for o in orders:
                            if len(o) >= 3 and o[0] == "SELL" and o[1] == item:
                                o[2] = int(o[2]) + take
                                break
                        else:
                            orders.append(["SELL", item, take])
                        _OR2_REPORT["or2_sellnow"] = _OR2_REPORT.get("or2_sellnow", 0) + take
                        _OR2_REPORT["or2_net_triggered"] = _OR2_REPORT.get("or2_net_triggered", 0) + take
                        action = dict(action)
                        action["market"] = orders
'''

if _source.count(_old) != 1:
    raise RuntimeError("unexpected One More Wheat OR2 sell-now body")
_source = _source.replace(_old, _new, 1)
exec(compile(_source, str(_PARENT_PATH), "exec"), globals())

_GENERATED_AGENT = agent
TELEMETRY = {}


def agent(observation, configuration=None):
    action = _GENERATED_AGENT(observation, configuration)
    TELEMETRY.clear()
    TELEMETRY.update(
        {
            "threshold": RIVAL_STOCK_THRESHOLD,
            "net_buffer": NET_STOCK_BUFFER,
            "min_exposure": MIN_EXPOSURE,
        }
    )
    TELEMETRY.update(_OR2_REPORT)
    return action


agent.telemetry = TELEMETRY
