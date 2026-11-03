#!/usr/bin/env python3
"""Replay forecast4's OMW losses against an OMW mirror control."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

from kaggriculture_agent import registry
from kaggriculture_agent.local_arena import GameSpec, play_game_with_trajectory


ROOT = Path(__file__).resolve().parents[1]
OMW_PATH = ROOT / "references/kaggle-scan-2026-09-21/extracted/one-more-wheat/main.py"
F4_PATH = ROOT / "experiments/omw-forecast4/main.py"
SCREEN_PATH = ROOT / "experiments/omw-forecast4/screen.json"
OUTPUT_PATH = ROOT / "experiments/omw-forecast4/loss-diagnostics.json"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def action(row: dict) -> dict:
    try:
        value = json.loads(row["chosen_action_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def market_sells(rows: list[dict]) -> dict:
    quantities: Counter[str] = Counter()
    orders = 0
    feed_actions = 0
    for row in rows:
        selected = action(row)
        farmer = selected.get("farmer") or []
        commands = list(farmer) if farmer and isinstance(farmer[0], str) else [farmer]
        commands += list(selected.get("hands") or [])
        for command in commands:
            if command == "FEED" or (isinstance(command, list) and command and command[0] == "FEED"):
                feed_actions += 1
        for order in selected.get("market") or []:
            if isinstance(order, list) and len(order) >= 3 and order[0] == "SELL":
                orders += 1
                quantities[str(order[1])] += int(order[2])
    return {"orders": orders, "units": dict(quantities), "feed_actions": feed_actions}


def sell_timing(candidate_rows: list[dict], control_rows: list[dict]) -> dict:
    """Compare candidate-only sell quantities with the later control sells."""
    def orders(rows: list[dict]) -> list[dict]:
        result = []
        for row in rows:
            selected = action(row)
            for order in selected.get("market") or []:
                if not isinstance(order, list) or len(order) < 3 or order[0] != "SELL":
                    continue
                item = str(order[1])
                result.append({
                    "step": int(row["step"]),
                    "item": item,
                    "qty": int(order[2]),
                    "price": row.get(f"market_price_{item.lower()}"),
                })
        return result

    candidate = orders(candidate_rows)
    control = orders(control_rows)
    candidate_by_step = {int(row["step"]): action(row) for row in candidate_rows}
    control_by_step = {int(row["step"]): action(row) for row in control_rows}
    by_key: dict[tuple[int, str], int] = {}
    for row in control:
        key = (row["step"], row["item"])
        by_key[key] = by_key.get(key, 0) + row["qty"]
    extra = []
    for row in candidate:
        key = (row["step"], row["item"])
        same_step = by_key.get(key, 0)
        extra_qty = max(0, row["qty"] - same_step)
        if extra_qty <= 0:
            continue
        future = [
            other for other in control
            if other["item"] == row["item"] and other["step"] > row["step"]
        ][:3]
        extra.append({
            "step": row["step"], "item": row["item"], "qty": extra_qty,
            "candidate_price": row["price"],
            "candidate_market_len": len(candidate_by_step.get(row["step"], {}).get("market") or []),
            "control_market_len": len(control_by_step.get(row["step"], {}).get("market") or []),
            "next_control_sales": future,
        })
    return {"extra_sell_events": len(extra), "events": extra[:40]}


def final_features(rows: list[dict]) -> dict:
    if not rows:
        return {}
    row = rows[-1]
    keys = (
        "step", "own_money", "own_seed_total", "own_shed_total",
        "own_shed_wheat", "own_shed_milk", "own_shed_wool",
        "own_shed_strawberry", "own_shed_egg", "own_shed_melon",
        "market_inventory_milk", "market_inventory_wool",
        "market_inventory_strawberry", "market_price_milk",
        "market_price_wool", "market_price_strawberry",
    )
    return {key: row.get(key) for key in keys if key in row}


def semantic_action(action_value: dict) -> dict:
    return {
        "farmer": action_value.get("farmer") or [],
        "hands": action_value.get("hands") or [],
        "market": action_value.get("market") or [],
    }


def first_divergences(candidate_rows: list[dict], control_rows: list[dict], limit: int = 20) -> dict:
    candidate_by_step = {int(row["step"]): row for row in candidate_rows}
    control_by_step = {int(row["step"]): row for row in control_rows}
    divergent = []
    market_only = 0
    for step in sorted(set(candidate_by_step) & set(control_by_step)):
        candidate_action = semantic_action(action(candidate_by_step[step]))
        control_action = semantic_action(action(control_by_step[step]))
        if candidate_action == control_action:
            continue
        if (candidate_action["farmer"] == control_action["farmer"] and
                candidate_action["hands"] == control_action["hands"]):
            market_only += 1
        if len(divergent) < limit:
            divergent.append({
                "step": step,
                "candidate": candidate_action,
                "control": control_action,
                "candidate_money": candidate_by_step[step].get("own_money"),
                "control_money": control_by_step[step].get("own_money"),
                "candidate_prices": {
                    item: candidate_by_step[step].get(f"market_price_{item.lower()}")
                    for item in ("MILK", "WOOL", "STRAWBERRY")
                },
            })
    return {"count": sum(
        semantic_action(action(candidate_by_step[step])) != semantic_action(action(control_by_step[step]))
        for step in set(candidate_by_step) & set(control_by_step)
    ), "market_only_count": market_only, "first": divergent}


def play(candidate_module, omw_module, seed: int, seat: int, control: bool):
    registry.AGENTS["diagnostic_f4"] = candidate_module.agent
    registry.AGENTS["diagnostic_omw"] = omw_module.agent
    if control:
        players = ("diagnostic_omw", "diagnostic_omw")
    else:
        players = (("diagnostic_f4", "diagnostic_omw") if seat == 0
                   else ("diagnostic_omw", "diagnostic_f4"))
    spec = GameSpec(
        f"loss-diagnostic-{'control' if control else 'candidate'}-{seed}-{seat}",
        seed,
        players[0], players[1],
        "diagnostic_f4", "diagnostic_omw", f"loss-{seed}", seat,
    )
    result, trajectory = play_game_with_trajectory(spec)
    candidate_seat = 0 if control else seat
    own_reward = result.reward_0 if candidate_seat == 0 else result.reward_1
    other_reward = result.reward_1 if candidate_seat == 0 else result.reward_0
    rows = [row for row in trajectory if int(row["seat"]) == candidate_seat]
    return {
        "status": result.status,
        "candidate_reward": own_reward,
        "opponent_reward": other_reward,
        "margin": None if own_reward is None or other_reward is None else own_reward - other_reward,
        "sell_summary": market_sells(rows),
        "final_features": final_features(rows),
        "rows": rows,
    }


def main() -> None:
    payload = json.loads(SCREEN_PATH.read_text())
    losses = [
        (int(row["seed"]), int(row["seat"]))
        for row in payload["rows"]
        if row["policy"] == "forecast4" and row["opponent"] == "omw" and row["margin"] < 0
    ]
    candidate_module = load(F4_PATH, "diagnostic_f4_module")
    omw_module = load(OMW_PATH, "diagnostic_omw_module")
    cases = []
    for seed, seat in losses:
        before = dict(getattr(candidate_module, "_V92_P_REPORT", {}))
        candidate = play(candidate_module, omw_module, seed, seat, control=False)
        after = dict(getattr(candidate_module, "_V92_P_REPORT", {}))
        telemetry_delta = {
            key: after.get(key, 0) - before.get(key, 0)
            for key in after
            if isinstance(after.get(key), (int, float)) and isinstance(before.get(key, 0), (int, float))
        }
        control = play(candidate_module, omw_module, seed, seat, control=True)
        candidate_rows = candidate.pop("rows")
        control_rows = control.pop("rows")
        timing = sell_timing(candidate_rows, control_rows)
        cases.append({
            "seed": seed,
            "seat": seat,
            "candidate": candidate,
            "control_omw_mirror": control,
            "candidate_telemetry_delta": telemetry_delta,
            "action_divergence_vs_control": first_divergences(candidate_rows, control_rows),
            "sell_timing": timing,
        })
    result = {
        "source": str(SCREEN_PATH.relative_to(ROOT)),
        "loss_count": len(losses),
        "cases": cases,
    }
    OUTPUT_PATH.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "loss_count": len(losses),
        "output": str(OUTPUT_PATH),
        "cases": [
            {"seed": c["seed"], "seat": c["seat"],
             "candidate_margin": c["candidate"]["margin"],
             "control_margin": c["control_omw_mirror"]["margin"],
             "telemetry": c["candidate_telemetry_delta"],
             "divergence_count": c["action_divergence_vs_control"]["count"]}
            for c in result["cases"]
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
