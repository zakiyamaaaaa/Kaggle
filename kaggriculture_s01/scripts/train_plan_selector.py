#!/usr/bin/env python3
"""Collect common-prefix counterfactual plans and evaluate a seed-held-out selector.

Every branch replays the same policy until switch_step. Only observation-visible
features are recorded. Simulator seeds and opponent IDs are grouping metadata,
never model inputs. This is an offline pilot, not automatic policy promotion.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

from kaggriculture_agent.local_arena import GameSpec, play_game
from kaggriculture_agent.planning_agent import PLANS, agent_for_plan
from kaggriculture_agent import registry


def features(obs):
    p = int(obs["player"])
    own, other = obs["farms"][p], obs["farms"][1 - p]
    result = {
        "day": obs["day"],
        "hour": obs["hour"],
        "cash": own["money"],
        "other_cash": other["money"],
        "hands": len(own["hands"]),
    }
    for label, farm in [("own", own), ("other", other)]:
        for row in farm["tiles"]:
            for tile in row:
                if isinstance(tile, dict):
                    item = tile.get("crop", tile.get("animal", tile.get("kind", "empty")))
                    key = f"{label}_{item}"
                    result[key] = result.get(key, 0) + 1
    for item, price in obs.get("market", {}).get("prices", {}).items():
        result["price_" + item] = price
    for item, quantity in obs.get("market", {}).get("inventory", {}).items():
        result["market_" + item] = quantity
    for item, quantity in obs.get("private", {}).get("shed", {}).items():
        result["shed_" + item] = quantity
    for shop in obs.get("town", {}).get("unlocked_shops", []):
        key = "shop_" + shop
        result[key] = result.get(key, 0) + 1
    return result


def run_branch(job):
    prefix, choice, opponent, seed, seat, switch = job
    captured = {}
    alias = "_plan_selector_branch"

    def policy(obs):
        nonlocal captured
        if int(obs["step"]) < switch:
            return agent_for_plan(obs, PLANS[prefix], "selector-prefix")
        if not captured:
            captured = features(obs)
        return agent_for_plan(obs, PLANS[choice], "selector-" + choice)

    registry.AGENTS[alias] = policy
    pair = f"{choice}-{opponent}-{seed}-{seat}"
    players = (alias, opponent) if seat == 0 else (opponent, alias)
    spec = GameSpec(pair, seed, *players, alias, opponent)
    result = play_game(spec)
    if result.status != "completed":
        raise RuntimeError(result.error)
    own, other = (
        (result.reward_0, result.reward_1) if seat == 0 else (result.reward_1, result.reward_0)
    )
    return {
        "plan": choice,
        "opponent": opponent,
        "seed": seed,
        "seat": seat,
        "features": captured,
        "cash": own,
        "margin": own - other,
        "score": 1.0 if own > other else 0.0 if own < other else 0.5,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prefix", required=True)
    p.add_argument("--choices", required=True)
    p.add_argument("--opponents", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--seeds", type=int, default=32)
    p.add_argument("--switch-step", type=int, default=72)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--target", choices=("score", "margin"), default="score")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    choices, opponents = a.choices.split(","), a.opponents.split(",")
    if any(c not in PLANS for c in [a.prefix, *choices]) or a.seeds < 8:
        p.error("unknown plan or fewer than eight seeds")
    a.output.mkdir(parents=True, exist_ok=True)
    if any(a.output.iterdir()):
        p.error("use a new output directory")
    jobs = [
        (a.prefix, choice, opponent, seed, seat, a.switch_step)
        for seed in range(a.seed, a.seed + a.seeds)
        for opponent in opponents
        for seat in (0, 1)
        for choice in choices
    ]
    rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=a.workers) as pool:
        for r in pool.map(run_branch, jobs, chunksize=2):
            rows.append(r)
            if len(rows) % 64 == 0:
                print(f"{len(rows)}/{len(jobs)} branches", flush=True)
    (a.output / "branches.json").write_text(json.dumps(rows, indent=2) + "\n")
    groups = {}
    for r in rows:
        key = (r["seed"], r["opponent"], r["seat"])
        groups.setdefault(key, []).append(r)
    assert all(len(g) == len(choices) for g in groups.values())
    assert all(all(r["features"] == g[0]["features"] for r in g) for g in groups.values()), (
        "prefix mismatch"
    )
    validation_seeds = [s for s in range(a.seed, a.seed + a.seeds) if (s - a.seed) % 4 == 3]
    train = [r for r in rows if r["seed"] not in validation_seeds]
    validation = [g for key, g in groups.items() if key[0] in validation_seeds]
    columns = sorted({k for r in train for k in r["features"]})

    def vector(r):
        return [r["features"].get(k, 0) for k in columns] + [int(r["plan"] == c) for c in choices]

    model = GradientBoostingRegressor(
        n_estimators=60,
        max_depth=2,
        min_samples_leaf=6,
        loss="huber" if a.target == "margin" else "squared_error",
        random_state=20260920,
    )
    model.fit(np.array([vector(r) for r in train]), np.array([r[a.target] for r in train]))
    train_means = {
        c: {
            "score": float(np.mean([r["score"] for r in train if r["plan"] == c])),
            "margin": float(np.mean([r["margin"] for r in train if r["plan"] == c])),
        }
        for c in choices
    }
    fixed = max(choices, key=lambda c: (train_means[c]["score"], train_means[c]["margin"]))
    records = []
    for g in validation:
        predictions = model.predict(np.array([vector(r) for r in g]))
        chosen = g[int(np.argmax(predictions))]
        control = next(r for r in g if r["plan"] == fixed)
        records.append(
            {
                "seed": chosen["seed"],
                "seat": chosen["seat"],
                "opponent": chosen["opponent"],
                "selected": chosen["plan"],
                "score_delta": chosen["score"] - control["score"],
                "margin_delta": chosen["margin"] - control["margin"],
                "cash_delta": chosen["cash"] - control["cash"],
            }
        )
    per_seed = [
        float(np.mean([r["score_delta"] for r in records if r["seed"] == s]))
        for s in validation_seeds
    ]
    rng = np.random.default_rng(20260920)
    samples = rng.choice(per_seed, size=(2000, len(per_seed)), replace=True).mean(axis=1)
    metrics = {
        "prefix": a.prefix,
        "choices": choices,
        "opponents": opponents,
        "switch_step": a.switch_step,
        "branch_games": len(rows),
        "failed_games": 0,
        "train_seeds": a.seeds - len(validation_seeds),
        "validation_seeds": validation_seeds,
        "validation_decisions": len(records),
        "target": a.target,
        "fixed_selected_on_training_only": fixed,
        "training_plan_means": train_means,
        "validation_score_delta": float(np.mean(per_seed)),
        "validation_score_delta_ci95": np.quantile(samples, [0.025, 0.975]).tolist(),
        "validation_margin_delta": float(np.mean([r["margin_delta"] for r in records])),
        "validation_cash_delta": float(np.mean([r["cash_delta"] for r in records])),
        "status": "pilot_only_requires_independent_128_seed_adoption_and_new_opponent_family",
    }
    (a.output / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (a.output / "validation_choices.json").write_text(json.dumps(records, indent=2) + "\n")
    joblib.dump(
        {"model": model, "features": columns, "plans": choices}, a.output / "selector.joblib"
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
