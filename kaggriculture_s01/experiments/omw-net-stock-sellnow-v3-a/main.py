"""OMW net-stock sell-now candidate A.

Candidate A keeps the v2 policy unchanged except when the 24-turn sell-now
look-ahead crosses a shop-unlock boundary whose future shop is not observable
yet. In that case it abstains from acceleration, because the v2 demand
recovery estimate would otherwise use an incomplete shop list.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


_V2_PATH = (
    Path(__file__).resolve().parents[1]
    / "omw-net-stock-sellnow-v2"
    / "main.py"
)
_SPEC = importlib.util.spec_from_file_location("_omw_net_stock_sellnow_v2_for_a", _V2_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("cannot load OMW net-stock v2: %s" % _V2_PATH)
_V2 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_V2)

RIVAL_STOCK_THRESHOLD = _V2.RIVAL_STOCK_THRESHOLD
NET_STOCK_BUFFER = _V2.NET_STOCK_BUFFER
MIN_EXPOSURE = _V2.MIN_EXPOSURE


_source = _V2._source

# Inserted into the self-contained source before the generated parent agent.
_HELPERS = (
    "\n\n# OMW net-stock sell-now candidate A: unknown-shop boundary guard.\n"
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

_report_marker = (
    '_OR2_REPORT = {"or2_reordered": 0, "or2_changed_vs_v39": 0, '
    '"or2_rival_harvest": 0, "or2_rival_sold": 0,\n'
    '               "or2_errors": 0}\n'
)
if _source.count(_report_marker) != 1:
    raise RuntimeError("unexpected One More Wheat OR2 report definition")
_source = _source.replace(_report_marker, _report_marker + _HELPERS, 1)

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

exec(compile(_source, str(_V2_PATH), "exec"), globals())

_GENERATED_AGENT = agent  # noqa: F821 - provided by the inlined parent source
TELEMETRY = {}


def agent(observation, configuration=None):
    action = _GENERATED_AGENT(observation, configuration)
    TELEMETRY.clear()
    TELEMETRY.update(
        {
            "candidate": "A",
            "threshold": RIVAL_STOCK_THRESHOLD,
            "net_buffer": NET_STOCK_BUFFER,
            "min_exposure": MIN_EXPOSURE,
        }
    )
    TELEMETRY.update(_OR2_REPORT)  # noqa: F821 - provided by the inlined parent source
    return action


agent.telemetry = TELEMETRY
