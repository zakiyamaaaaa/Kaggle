#!/usr/bin/env python3
"""Reconcile cash gaps into volume, execution price, and actual cost components."""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import fmean

from diagnose_policy import diagnose


def run(spec):
    return diagnose(*spec)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--agent", default="planner_cows8")
    p.add_argument("--opponent", default="candidate")
    p.add_argument("--seed", type=int, default=138000)
    p.add_argument("--seeds", type=int, default=8)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error("output exists")
    specs = [
        (agent, other, seed, seat)
        for seed in range(a.seed, a.seed + a.seeds)
        for seat in (0, 1)
        for agent, other in ((a.agent, a.opponent), (a.opponent, a.agent))
    ]
    # Re-run each paired game from the other seat to instrument both policies.
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        rows = list(pool.map(run, specs))
    means = {}
    for agent in (a.agent, a.opponent):
        selected = [r for r in rows if r["agent"] == agent]
        keys = set().union(*(r["metrics"] for r in selected))
        means[agent] = {k: fmean(r["metrics"].get(k, 0) for r in selected) for k in sorted(keys)}
        means[agent]["final_cash"] = fmean(r["rewards"][r["seat"]] for r in selected)
    own, other = means[a.agent], means[a.opponent]
    products = sorted(
        {k.split(".")[-1] for m in means.values() for k in m if k.startswith("traded.SELL.")}
    )
    attribution = {}
    for product in products:
        q0, q1 = (m.get("traded.SELL." + product, 0) for m in (own, other))
        v0, v1 = (m.get("cashflow.SELL." + product, 0) for m in (own, other))
        # A missing product has no observable sale price; assign its entire
        # difference to product/volume mix by using the observed side's price.
        p0 = v0 / q0 if q0 else v1 / q1 if q1 else 0
        p1 = v1 / q1 if q1 else p0
        attribution[product] = {
            "own_quantity": q0,
            "opponent_quantity": q1,
            "own_unit_price": v0 / q0 if q0 else None,
            "opponent_unit_price": v1 / q1 if q1 else None,
            "volume_mix_gap": (q1 - q0) * (p1 + p0) / 2,
            "price_gap": (p1 - p0) * (q1 + q0) / 2,
            "revenue_gap": v1 - v0,
        }
    costs = sorted(
        {
            k
            for m in means.values()
            for k in m
            if k.startswith("cashflow.") and not k.startswith("cashflow.SELL.")
        }
    )
    cost_advantage = {k: other.get(k, 0) - own.get(k, 0) for k in costs}
    gap = other["final_cash"] - own["final_cash"]
    reconstructed = sum(r["revenue_gap"] for r in attribution.values()) - sum(
        cost_advantage.values()
    )
    assert abs(gap - reconstructed) < 1e-6
    root = Path(__file__).resolve().parents[1]
    paths = [
        Path(__file__),
        Path(__file__).with_name("diagnose_policy.py"),
        *sorted((root / "src/kaggriculture_agent").glob("*.py")),
    ]
    result = {
        "agent": a.agent,
        "opponent": a.opponent,
        "seed_start": a.seed,
        "seeds": a.seeds,
        "unique_games": a.seeds * 2,
        "diagnostic_runs": len(rows),
        "cash_gap": gap,
        "reconstructed_gap": reconstructed,
        "means": means,
        "revenue_attribution": attribution,
        "opponent_extra_cost": cost_advantage,
        "rows": rows,
        "fingerprints": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("rows", "fingerprints", "means")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
