#!/usr/bin/env python3
"""Audit the frozen economy experiment and compute series/main promotion gates."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import zipfile
from collections import defaultdict
from pathlib import Path

from evaluate_independent import bootstrap

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/strategy-cycle"


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = read(ROOT / "configs/economy_v4_protocol.json")
    selected = "economy_mix50"
    references = ["planner_cows8", "candidate"]
    ranges, counts = {}, {}
    for stage in ("smoke", "screen", "adoption", "holdout"):
        directory = BASE / f"economy-v4-{stage}"
        summary, manifest = (read(directory / f"{name}.json") for name in ("summary", "manifest"))
        with (directory / "games.csv").open() as f:
            rows = list(csv.DictReader(f))
        agents = manifest["agents"].split(",")
        opponents = manifest["opponents"].split(",")
        expected = {
            (agent, opponent, seed, seat)
            for agent in agents
            for opponent in opponents
            for seed in range(manifest["seed"], manifest["seed"] + manifest["seeds"])
            for seat in (0, 1)
        }
        actual = set()
        observed = defaultdict(list)
        for r in rows:
            agent, opponent, seed, seat = r["game_id"].split("--")
            key = agent, opponent, int(seed), int(seat)
            assert key not in actual
            actual.add(key)
            rewards = [float(r["reward_0"]), float(r["reward_1"])]
            assert all(math.isfinite(v) for v in rewards)
            own, other = rewards[int(seat)], rewards[1 - int(seat)]
            score = 1.0 if own > other else 0.5 if own == other else 0.0
            observed[agent, opponent].append((score, own, own - other))
            assert int(r["seed"]) == int(seed)
            assert (r["player_0"], r["player_1"]) == (
                (agent, opponent) if seat == "0" else (opponent, agent)
            )
            assert r["status"] == "completed" and int(r["steps"]) == 719 and not r["error"]
        assert actual == expected
        assert summary["games"] == len(rows) and summary["failed_games"] == 0
        for (agent, opponent), values in observed.items():
            reported = summary["policies"][agent]["opponents"][opponent]
            for index, metric in enumerate(("score", "cash", "cash_margin")):
                actual_mean = statistics.fmean(v[index] for v in values)
                assert math.isclose(actual_mean, reported[metric], rel_tol=1e-12, abs_tol=1e-8)
        if stage != "smoke":
            assert (manifest["seed"], manifest["seeds"]) == (
                protocol[stage]["seed_start"],
                protocol[stage]["seeds"],
            )
        ranges[stage] = {key[2] for key in actual}
        counts[stage] = len(rows)
        for path, sha in manifest["fingerprints"].items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha, path
        if stage == "holdout":
            assert opponents == protocol["holdout"]["opponents"]
            assert set(agents) == {selected, *references}
            holdout_rows = rows
    stages = list(ranges)
    for i, stage in enumerate(stages):
        for other in stages[i + 1 :]:
            assert ranges[stage].isdisjoint(ranges[other])
    screen = read(BASE / "economy-v4-screen/summary.json")["policies"]
    best = max(
        (n for n in screen if n != references[0]),
        key=lambda n: (
            statistics.fmean(v["score"] for v in screen[n]["opponents"].values()),
            statistics.fmean(v["cash"] for v in screen[n]["opponents"].values()),
        ),
    )
    assert best == selected
    scores = defaultdict(list)
    for r in holdout_rows:
        agent, opponent, seed, seat = r["game_id"].split("--")
        own, other = float(r[f"reward_{seat}"]), float(r[f"reward_{1 - int(seat)}"])
        scores[agent, opponent, int(seed)].append(
            1.0 if own > other else 0.5 if own == other else 0.0
        )
    comparison = {}
    for ref in references:
        deltas = [
            statistics.fmean(
                statistics.fmean(scores[selected, o, seed]) - statistics.fmean(scores[ref, o, seed])
                for o in protocol["holdout"]["opponents"]
            )
            for seed in sorted(ranges["holdout"])
        ]
        ci = bootstrap(deltas)
        comparison[ref] = {
            "score_delta": statistics.fmean(deltas),
            "ci95": ci,
            "gate_passed": ci[0] > 0,
        }
    adoption = read(BASE / "economy-v4-adoption/summary.json")["policies"][selected]
    promote_series = (
        adoption["score_delta_ci95"][0] > 0 and comparison[references[0]]["gate_passed"]
    )
    promote_main = promote_series and comparison[references[1]]["gate_passed"]
    bundle = ROOT / "submissions/independent-economy-v4.zip"
    manifest = read(bundle.with_suffix(".manifest.json"))
    assert manifest["policy"] == selected and manifest["submission_status"] == "not_submitted"
    assert hashlib.sha256(bundle.read_bytes()).hexdigest() == manifest["zip_sha256"]
    with zipfile.ZipFile(bundle) as z:
        assert z.namelist() == ["main.py"]
        content = z.read("main.py")
    assert hashlib.sha256(content).hexdigest() == manifest["source_sha256"]
    assert (ROOT / "src/kaggriculture_agent/planning_agent.py").read_bytes() in content
    assert manifest["verification"]["official_fast_all_steps_equal"]
    assert len(manifest["verification"]["bundle_checks"]) == 2
    assert all(
        c["status"] == "completed" and c["actions_equal"] == 719
        for c in manifest["verification"]["bundle_checks"]
    )
    for version in ("v3", "v4"):
        gap = read(BASE / f"economic-gap-{version}.json")
        assert gap["cash_gap"] == gap["reconstructed_gap"]
        initial_balances = []
        for r in gap["rows"]:
            assert r["cashflow_reconciled"] and not r["bad_statuses"]
            metrics = r["metrics"]
            revenue = sum(v for k, v in metrics.items() if k.startswith("cashflow.SELL."))
            cost = sum(
                v
                for k, v in metrics.items()
                if k.startswith("cashflow.") and not k.startswith("cashflow.SELL.")
            )
            initial_balances.append(r["rewards"][r["seat"]] - revenue + cost)
        assert set(initial_balances) == {3000.0}
        attributed = sum(v["revenue_gap"] for v in gap["revenue_attribution"].values())
        attributed -= sum(gap["opponent_extra_cost"].values())
        assert math.isclose(attributed, gap["cash_gap"], abs_tol=1e-8)

    result = {
        "selected": selected,
        "games": counts,
        "total_games": sum(counts.values()),
        "comparison": comparison,
        "promote_independent_series": promote_series,
        "promote_main": promote_main,
        "main_agent": selected if promote_main else "candidate",
        "bundle_sha256": manifest["zip_sha256"],
        "submission_status": "not_submitted",
        "limitations": protocol["caveat"],
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
