#!/usr/bin/env python3
"""Build deterministic single-file candidate submission archives."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "submissions" / "public-salem-2900" / "main.py"
DEFAULT_OUTPUT = ROOT / "submissions" / "candidate-front-run-v2.zip"
EXPECTED_SOURCE_SHA256 = "3b1cb91feb451b44d075d853f9211be216aea7f85df09d91fa232e4e9dff8fe9"
ORIGINAL = "_FR_ITEMS = ('MELON', 'MILK', 'STRAWBERRY', 'WOOL')"
REPLACEMENT = "_FR_ITEMS = ('MELON', 'MILK', 'STRAWBERRY', 'WOOL', 'WHEAT', 'FERTILIZER')"
AGENT_MARKER = "\ndef agent(obs):\n"
RETURN_MARKER = "        return _align_hands(act, obs)\n"
LIQUIDATION_HELPER = """
def _liquidate_final_day(action, obs):
    if int(_get(obs, "day", 0) or 0) < 29:
        return action
    shed = _get(_get(obs, "private", {}) or {}, "shed", {}) or {}
    non_sell = [list(order) for order in action.get("market", []) if order[0] != "SELL"]
    sell_by_item = {}
    for order in action.get("market", []):
        if len(order) >= 3 and order[0] == "SELL":
            item = str(order[1])
            sell_by_item[item] = max(sell_by_item.get(item, 0), int(order[2]))
    for item, quantity in shed.items():
        amount = max(0, int(quantity or 0))
        if amount:
            item = str(item)
            sell_by_item[item] = max(sell_by_item.get(item, 0), amount)
    sells = [["SELL", item, quantity] for item, quantity in sorted(sell_by_item.items())]
    return {**action, "market": (non_sell + sells)[:10]}
"""

EARLY_MILK_HELPER = """
def _liquidate_early_milk(action, obs):
    day = int(_get(obs, "day", 0) or 0)
    hour = int(_get(obs, "hour", 0) or 0)
    if day < 28 or (day == 28 and hour < 12):
        return action
    shed = _get(_get(obs, "private", {}) or {}, "shed", {}) or {}
    non_sell = [list(order) for order in action.get("market", []) if order[0] != "SELL"]
    sell_by_item = {}
    for order in action.get("market", []):
        if len(order) >= 3 and order[0] == "SELL":
            item = str(order[1])
            sell_by_item[item] = max(sell_by_item.get(item, 0), int(order[2]))
    force_items = {"MILK"} if day == 28 else None
    for item, quantity in shed.items():
        item = str(item)
        if force_items is not None and item not in force_items:
            continue
        amount = max(0, int(quantity or 0))
        if amount:
            sell_by_item[item] = max(sell_by_item.get(item, 0), amount)
    sells = [["SELL", item, quantity] for item, quantity in sorted(sell_by_item.items())]
    return {**action, "market": (non_sell + sells)[:10]}
"""


def build(output: Path, variant: str = "front-run-v2") -> tuple[str, str]:
    source = SOURCE.read_bytes()
    source_sha = hashlib.sha256(source).hexdigest()
    if source_sha != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(f"unexpected reference source SHA-256: {source_sha}")
    text = source.decode("utf-8")
    if text.count(ORIGINAL) != 1:
        raise RuntimeError("expected exactly one front-run item declaration")
    candidate_text = text.replace(ORIGINAL, REPLACEMENT)
    if variant == "liquidate-v3":
        if candidate_text.count(AGENT_MARKER) != 1 or candidate_text.count(RETURN_MARKER) != 1:
            raise RuntimeError("candidate source markers changed")
        candidate_text = candidate_text.replace(
            AGENT_MARKER, f"\n{LIQUIDATION_HELPER}\ndef agent(obs):\n"
        )
        candidate_text = candidate_text.replace(
            RETURN_MARKER,
            "        return _align_hands(_liquidate_final_day(act, obs), obs)\n",
        )
    elif variant == "early-milk-v1":
        if candidate_text.count(AGENT_MARKER) != 1 or candidate_text.count(RETURN_MARKER) != 1:
            raise RuntimeError("candidate source markers changed")
        candidate_text = candidate_text.replace(
            AGENT_MARKER, f"\n{EARLY_MILK_HELPER}\ndef agent(obs):\n"
        )
        candidate_text = candidate_text.replace(
            RETURN_MARKER,
            "        return _align_hands(_liquidate_early_milk(act, obs), obs)\n",
        )
    elif variant != "front-run-v2":
        raise ValueError(f"unknown variant: {variant}")
    candidate = candidate_text.encode("utf-8")
    candidate_sha = hashlib.sha256(candidate).hexdigest()

    output.parent.mkdir(parents=True, exist_ok=True)
    member = zipfile.ZipInfo("main.py", date_time=(2026, 9, 19, 0, 0, 0))
    member.compress_type = zipfile.ZIP_DEFLATED
    member.external_attr = 0o644 << 16
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(member, candidate)
    return candidate_sha, hashlib.sha256(output.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--variant",
        choices=("front-run-v2", "liquidate-v3", "early-milk-v1"),
        default="front-run-v2",
    )
    args = parser.parse_args()
    candidate_sha, zip_sha = build(args.output, args.variant)
    print(f"output={args.output.resolve()}")
    print(f"candidate_sha256={candidate_sha}")
    print(f"zip_sha256={zip_sha}")


if __name__ == "__main__":
    main()
