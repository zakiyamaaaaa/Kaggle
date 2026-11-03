"""One More Wheat with a hook for per-item sell-now decisions."""

from __future__ import annotations

import runpy
from pathlib import Path


_PARENT = Path(__file__).resolve().parents[1] / "omw-net-stock-sellnow-v2" / "main.py"
_namespace = runpy.run_path(str(_PARENT))
_source = _namespace["_source"]
NET_STOCK_BUFFER = _namespace["NET_STOCK_BUFFER"]
MIN_EXPOSURE = _namespace["MIN_EXPOSURE"]

_start_marker = "                        if net_batch < "
_end_marker = '                        action["market"] = orders\n'
if _source.count(_start_marker) != 1:
    raise RuntimeError("unexpected net-stock decision block")
_start = _source.index(_start_marker)
_end_marker_position = _source.find(_end_marker, _start)
if _end_marker_position < 0:
    raise RuntimeError("unexpected net-stock decision block")
_end = _end_marker_position + len(_end_marker)

_new = f'''                        if net_batch < {NET_STOCK_BUFFER} or exposure < {MIN_EXPOSURE!r}:
                            _OR2_REPORT["or2_net_blocked"] = _OR2_REPORT.get("or2_net_blocked", 0) + take
                            continue
                        choice = int(_OR3_DECIDER(observation, item, take, net_batch, recovery,
                                                  exposure, first_sale, rival_stock))
                        target = 0 if choice <= 0 else ((take + 1) // 2 if choice == 1 else take)
                        if target <= 0:
                            _OR2_REPORT["or3_skipped"] = _OR2_REPORT.get("or3_skipped", 0) + take
                            continue
                        chosen, remaining = [], target
                        for due, q in plan:
                            selected = min(q, remaining)
                            if selected > 0:
                                chosen.append((due, selected))
                                remaining -= selected
                            if remaining <= 0:
                                break
                        for due, q in chosen:
                            debts.setdefault(due, {{}})[item] = debts.get(due, {{}}).get(item, 0) + q
                        for o in orders:
                            if len(o) >= 3 and o[0] == "SELL" and o[1] == item:
                                o[2] = int(o[2]) + target
                                break
                        else:
                            orders.append(["SELL", item, target])
                        _OR2_REPORT["or2_sellnow"] = _OR2_REPORT.get("or2_sellnow", 0) + target
                        _OR2_REPORT["or2_net_triggered"] = _OR2_REPORT.get("or2_net_triggered", 0) + target
                        _OR2_REPORT["or3_half"] = _OR2_REPORT.get("or3_half", 0) + (choice == 1)
                        _OR2_REPORT["or3_full"] = _OR2_REPORT.get("or3_full", 0) + (choice >= 2)
                        action = dict(action)
                        action["market"] = orders
'''

_source = _source[:_start] + _new + _source[_end:]


def _default_decider(*_args):
    return 2


_source = _source.replace(
    "_OR2_PARENT = agent\ndel agent\n",
    "_OR3_DECIDER = globals().get('_OR3_DECIDER', lambda *args: 2)\n_OR2_PARENT = agent\ndel agent\n",
    1,
)
_OR3_DECIDER = _default_decider
exec(compile(_source, str(_PARENT), "exec"), globals())
