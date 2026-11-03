#!/usr/bin/env python3
"""Measure actual engine effects without exposing hidden state to the policy."""

from __future__ import annotations

import argparse
import copy
import json
import time
from collections import Counter
from pathlib import Path

from kaggle_environments import make
from kaggle_environments.envs.kaggriculture import kaggriculture as engine
from kaggriculture_agent.local_arena import _run_fast, _TimedAgent
from kaggriculture_agent.registry import get_agent
from kaggriculture_agent.waste_shield import metrics as waste_shield_metrics
from kaggriculture_agent.waste_shield import reset_metrics as reset_waste_shield_metrics


def diagnose(agent: str, opponent: str, seed: int, seat: int = 0) -> dict:
    reset_waste_shield_metrics()
    env = make("kaggriculture", configuration={"seed": seed}, debug=False)
    names = [agent, opponent] if seat == 0 else [opponent, agent]
    counters = [Counter(), Counter()]
    farms, privates = [], []
    originals = {
        name: getattr(engine, name)
        for name in (
            "_apply_unit_action",
            "_commit_unit",
            "_drop_inventories_to_shed",
            "_daily_refresh_animals",
            "_daily_refresh_plants",
            "_do_hire",
            "_do_buy_land",
        )
    }
    interpreter = env.interpreter
    durations = []

    def current_interpreter(states, environment):
        nonlocal farms, privates
        farms = states[0].observation.farms
        privates = [s.observation.private for s in states]
        return interpreter(states, environment)

    def owner(value, objects):
        return next(i for i, obj in enumerate(objects) if value is obj)

    def total(private):
        return sum(private["shed"].values()) + sum(
            sum(inv.values()) for inv in private["inventories"]
        )

    def apply(farm, private, idx, action, *args, **kwargs):
        c = counters[owner(farm, farms)]
        op = action[0] if isinstance(action, list) and action else "MALFORMED"
        c[f"actions.{op}"] += 1
        before = copy.deepcopy((farm, private))
        storage = total(private)
        old_inv = dict(engine._farmer_inventory(private, idx))
        originals["_apply_unit_action"](farm, private, idx, action, *args, **kwargs)
        if op != "PASS" and (farm, private) == before:
            c[f"noops.{op}"] += 1
        if op == "DROP":
            c["overflow"] += max(0, storage - total(private))
        if op in ("HARVEST", "COLLECT_FERTILIZER"):
            inv = engine._farmer_inventory(private, idx)
            for item, quantity in inv.items():
                c[f"harvested.{item}"] += max(0, quantity - old_inv.get(item, 0))

    def commit(op, item, price, farm, private, market, *args, **kwargs):
        ok = originals["_commit_unit"](op, item, price, farm, private, market, *args, **kwargs)
        if ok:
            c = counters[owner(farm, farms)]
            c[f"traded.{op}.{item}"] += 1
            c[f"cashflow.{op}.{item}"] += price
        return ok

    def drop(private, capacity):
        c = counters[owner(private, privates)]
        before = total(private)
        originals["_drop_inventories_to_shed"](private, capacity)
        c["overflow"] += max(0, before - total(private))

    def animals(farm, day):
        c = counters[owner(farm, farms)]
        before = {
            (x, y): dict(tile)
            for y, row in enumerate(farm["tiles"])
            for x, tile in enumerate(row)
            if isinstance(tile, dict) and "animal" in tile
        }
        c["unfed_animal_days"] += sum(not t["fed_today"] for t in before.values())
        originals["_daily_refresh_animals"](farm, day)
        for (x, y), tile in before.items():
            after = farm["tiles"][y][x]
            if "animal" not in after:
                c["escaped_animals"] += 1
            else:
                product = engine.ANIMALS[tile["animal"]]["product"]
                c[f"produced.{product}"] += max(0, after["yield_units"] - tile["yield_units"])

    def plants(farm, *args):
        c = counters[owner(farm, farms)]
        before = {
            (x, y): dict(tile)
            for y, row in enumerate(farm["tiles"])
            for x, tile in enumerate(row)
            if isinstance(tile, dict) and tile.get("kind") == "PLANT"
        }
        c["unwatered_crop_days"] += sum(not t["watered_today"] for t in before.values())
        originals["_daily_refresh_plants"](farm, *args)
        for x, y in before:
            if farm["tiles"][y][x].get("kind") == "WEED":
                c["water_deadline_losses"] += 1

    def hire(farm, *args, **kwargs):
        before = farm["money"]
        originals["_do_hire"](farm, *args, **kwargs)
        counters[owner(farm, farms)]["cashflow.HIRE"] += before - farm["money"]

    def land(farm, *args, **kwargs):
        before = farm["money"]
        originals["_do_buy_land"](farm, *args, **kwargs)
        counters[owner(farm, farms)]["cashflow.BUY_LAND"] += before - farm["money"]

    engine._apply_unit_action = apply
    engine._commit_unit = commit
    engine._drop_inventories_to_shed = drop
    engine._daily_refresh_animals = animals
    engine._daily_refresh_plants = plants
    engine._do_hire = hire
    engine._do_buy_land = land
    env.interpreter = current_interpreter
    wrappers = []
    for index, name in enumerate(names):
        fn = get_agent(name)

        def timed(obs, fn=fn, index=index):
            start = time.perf_counter()
            action = fn(obs)
            if index == seat:
                durations.append(time.perf_counter() - start)
            return action

        wrappers.append(_TimedAgent(timed))
    try:
        final, bad, _, _ = _run_fast(env, wrappers)
    finally:
        for name, fn in originals.items():
            setattr(engine, name, fn)
    d = sorted(durations)
    result = {
        "agent": agent,
        "opponent": opponent,
        "seed": seed,
        "seat": seat,
        "rewards": [s.reward for s in final],
        "bad_statuses": sorted(bad),
        "metrics": dict(sorted(counters[seat].items())),
        "action_seconds_p95": d[int(0.95 * (len(d) - 1))],
        "action_seconds_max": max(d),
        "terminal_shed": dict(final[seat].observation.private.shed),
        "terminal_carried": [dict(inv) for inv in final[seat].observation.private.inventories],
    }
    c = counters[seat]
    # The shield is deliberately an executor wrapper, so its replacements are
    # not visible to the engine's no-op hook.  Preserve them beside the actual
    # effects for a direct incumbent/experiment comparison.
    c.update(waste_shield_metrics(seat))
    revenue = sum(v for k, v in c.items() if k.startswith("cashflow.SELL."))
    costs = sum(
        v for k, v in c.items() if k.startswith("cashflow.") and not k.startswith("cashflow.SELL.")
    )
    expected_cash = env.configuration.startingMoney + revenue - costs
    assert expected_cash == final[seat].reward, (expected_cash, final[seat].reward)
    result["cashflow_reconciled"] = True
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--agents", required=True)
    p.add_argument("--opponent", default="candidate")
    p.add_argument("--seed", type=int, default=130001)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    results = [
        diagnose(agent, a.opponent, a.seed, seat)
        for agent in a.agents.split(",")
        for seat in (0, 1)
    ]
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(results, indent=2) + "\n")
    for r in results:
        print(r["agent"], r["seat"], r["rewards"], r["metrics"])


if __name__ == "__main__":
    main()
