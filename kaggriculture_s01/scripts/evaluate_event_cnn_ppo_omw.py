#!/usr/bin/env python3
"""Evaluate event CNN + PPO against the frozen six-opponent OMW-002 panel.

The learned policy and the fixed OMW-002 full-action policy are evaluated on
the complete panel.  ``always_skip``, ``half``, and ``full`` are optional
action ablations and default to the three most relevant market-race
opponents.  Games are run in isolated worker processes so the script remains
reusable while preserving the event wrapper's per-game state.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import random
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from kaggriculture_agent import registry
from kaggriculture_agent.event_cnn_ppo import ACTIONS, make_decider
from kaggriculture_agent.local_arena import GameSpec, play_game


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "experiments/omw-event-cnn-ppo-v1/main.py"
MODEL_DEFAULT = ROOT / "outputs/event_cnn_ppo_omw_v1/cf-trained/model.json"
PANEL_SOURCES = {
    "omw": ROOT / "references/kaggle-scan-2026-09-21/extracted/one-more-wheat/main.py",
    "peak": ROOT / "references/kaggle-scan-2026-09-21/extracted/peak2950/main.py",
    "triad": ROOT / "references/kaggle-scan-2026-09-21/extracted/triad-counter/main.py",
}
PANEL = ("omw", "peak", "triad", "salem", "early_milk", "baseline")
ELIGIBLE_ITEMS = (
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"
)
ABLATION_POLICIES = ("always_skip", "half", "full")
POLICIES = ("learned", "fixed", *ABLATION_POLICIES)
ABLATION_PANEL = ("omw", "peak", "triad")

_WORKER_MODEL: dict[str, Any] | None = None
_WORKER_EVENT: Any = None
_WORKER_ITEMS: frozenset[str] = frozenset(ELIGIBLE_ITEMS)


def load(path: Path, label: str) -> Any:
    """Load a standalone Kaggle agent source under an isolated module name."""

    spec = importlib.util.spec_from_file_location(label, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


def _source_fingerprints(model_path: Path) -> dict[str, str]:
    paths = [
        Path(__file__).resolve(),
        WRAPPER,
        model_path.resolve(),
        ROOT / "experiments/omw-net-stock-sellnow-v2/main.py",
        ROOT / "src/kaggriculture_agent/event_cnn_ppo.py",
        ROOT / "src/kaggriculture_agent/cnn_ppo.py",
        ROOT / "src/kaggriculture_agent/local_arena.py",
        ROOT / "src/kaggriculture_agent/registry.py",
        ROOT / "submissions/public-salem-2900/main.py",
        *PANEL_SOURCES.values(),
    ]
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.is_file()
    }


def _init_worker(model: dict[str, Any], items: tuple[str, ...]) -> None:
    """Load all mutable agent modules once in a spawned worker."""

    global _WORKER_MODEL, _WORKER_EVENT, _WORKER_ITEMS
    _WORKER_MODEL = model
    _WORKER_ITEMS = frozenset(items)
    suffix = str(os.getpid())
    _WORKER_EVENT = load(WRAPPER, f"_event_panel_wrapper_{suffix}")
    opponents = {
        "omw": load(PANEL_SOURCES["omw"], f"_event_panel_omw_{suffix}").agent,
        "peak": load(PANEL_SOURCES["peak"], f"_event_panel_peak_{suffix}").agent,
        "triad": load(PANEL_SOURCES["triad"], f"_event_panel_triad_{suffix}").agent,
        # These aliases are the same fixed references used by the OMW-002
        # validation/holdout results; do not replace them with near variants.
        "salem": registry.get_agent("public_salem"),
        "early_milk": registry.get_agent("salem_early_milk"),
        "baseline": registry.get_agent("baseline"),
    }
    registry.AGENTS["_event_panel_candidate"] = _WORKER_EVENT.agent
    for name, agent in opponents.items():
        registry.AGENTS[f"_event_panel_{name}"] = agent


def _constant_decider(choice: int, telemetry: dict[str, int]):
    def decide(*_args: Any) -> int:
        name = ACTIONS[choice]
        telemetry[name] = telemetry.get(name, 0) + 1
        return choice

    return decide


def _worker_game(task: tuple[str, str, int, int]) -> dict[str, Any]:
    """Run one candidate-vs-opponent game and return JSON-safe diagnostics."""

    policy, opponent, seed, seat = task
    if _WORKER_EVENT is None or _WORKER_MODEL is None:
        raise RuntimeError("worker was not initialized")
    telemetry: dict[str, int] = {}
    if policy == "learned":
        learned_decider = make_decider(_WORKER_MODEL, telemetry)

        def item_decider(observation, item, *args):
            if item not in _WORKER_ITEMS:
                return 2
            return learned_decider(observation, item, *args)

        _WORKER_EVENT._OR3_DECIDER = item_decider
    else:
        choice = 2 if policy in {"fixed", "full"} else {"always_skip": 0, "half": 1}[policy]
        _WORKER_EVENT._OR3_DECIDER = _constant_decider(choice, telemetry)
    candidate = "_event_panel_candidate"
    rival = f"_event_panel_{opponent}"
    players = (candidate, rival) if seat == 0 else (rival, candidate)
    game_id = f"event-{policy}-{opponent}-{seed}-seat-{seat}"
    result = play_game(GameSpec(game_id, seed, *players, policy, opponent, game_id, seat))
    if seat == 0:
        own, rival_reward = result.reward_0, result.reward_1
    else:
        own, rival_reward = result.reward_1, result.reward_0
    margin = None if own is None or rival_reward is None else own - rival_reward
    win = None if margin is None else margin > 0
    draw = None if margin is None else margin == 0
    return {
        "policy": policy,
        "opponent": opponent,
        "seed": seed,
        "seat": seat,
        "status": result.status,
        "reward": own,
        "opponent_reward": rival_reward,
        "margin": margin,
        "win": win,
        "draw": draw,
        "steps": result.steps,
        "elapsed_seconds": result.elapsed_seconds,
        "decisions": result.decisions,
        "action_counts": {name: int(telemetry.get(name, 0)) for name in ACTIONS},
        "error": result.error,
    }


def _stat_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row["status"] == "completed" and row["margin"] is not None]
    wins = sum(bool(row["win"]) for row in completed)
    draws = sum(bool(row["draw"]) for row in completed)
    counts = {
        name: sum(int(row["action_counts"].get(name, 0)) for row in completed)
        for name in ACTIONS
    }
    games = len(completed)
    return {
        "games": len(rows),
        "completed": games,
        "errors": len(rows) - games,
        "wins": wins,
        "draws": draws,
        "losses": games - wins - draws,
        "score": (wins + 0.5 * draws) / games if games else None,
        "mean_margin": statistics.fmean(row["margin"] for row in completed) if completed else None,
        "mean_reward": statistics.fmean(row["reward"] for row in completed) if completed else None,
        "mean_opponent_reward": (
            statistics.fmean(row["opponent_reward"] for row in completed) if completed else None
        ),
        "action_counts": counts,
    }


def _bootstrap_ci(values: list[float], seed: int = 20260921) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    samples = sorted(
        statistics.fmean(values[rng.randrange(n)] for _ in range(n)) for _ in range(2000)
    )
    return [samples[50], samples[1949]]


def _paired_comparison(
    rows: list[dict[str, Any]], policy: str, reference: str, opponents: tuple[str, ...]
) -> dict[str, Any]:
    by_key = {
        (row["policy"], row["opponent"], row["seed"], row["seat"]): row
        for row in rows
        if row["status"] == "completed"
    }
    opponent_summary: dict[str, Any] = {}
    seed_deltas: list[float] = []
    for opponent in opponents:
        deltas: list[float] = []
        for seed in sorted({row["seed"] for row in rows if row["opponent"] == opponent}):
            seat_scores = []
            for seat in (0, 1):
                candidate = by_key.get((policy, opponent, seed, seat))
                baseline = by_key.get((reference, opponent, seed, seat))
                if candidate is None or baseline is None:
                    continue
                score = float(candidate["win"]) + 0.5 * float(candidate["draw"])
                ref_score = float(baseline["win"]) + 0.5 * float(baseline["draw"])
                seat_scores.append(score - ref_score)
            if seat_scores:
                deltas.append(statistics.fmean(seat_scores))
        if deltas:
            opponent_summary[opponent] = {
                "score_delta": statistics.fmean(deltas),
                "score_delta_ci95": _bootstrap_ci(deltas),
                "seeds": len(deltas),
            }
            seed_deltas.extend(deltas)
    return {
        "reference": reference,
        "opponents": opponent_summary,
        "score_delta": statistics.fmean(seed_deltas) if seed_deltas else None,
        "score_delta_ci95": _bootstrap_ci(seed_deltas),
        "seeds": len(seed_deltas),
    }


def _parse_csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL_DEFAULT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=983100)
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--policies", default="learned,fixed")
    parser.add_argument(
        "--items",
        default=None,
        help="comma-separated learned-policy items; defaults to model training metadata or all",
    )
    parser.add_argument("--opponents", default=",".join(PANEL))
    parser.add_argument("--ablation-opponents", default=",".join(ABLATION_PANEL))
    parser.add_argument("--include-ablations", action="store_true")
    parser.add_argument(
        "--net-sn-buffer",
        type=int,
        default=None,
        help="override OMW_NET_SN_BUFFER before loading the event wrapper",
    )
    parser.add_argument(
        "--net-sn-exposure",
        type=float,
        default=None,
        help="override OMW_NET_SN_EXPOSURE before loading the event wrapper",
    )
    args = parser.parse_args()
    net_sn_buffer = (
        args.net_sn_buffer
        if args.net_sn_buffer is not None
        else int(os.environ.get("OMW_NET_SN_BUFFER", "12"))
    )
    net_sn_exposure = (
        args.net_sn_exposure
        if args.net_sn_exposure is not None
        else float(os.environ.get("OMW_NET_SN_EXPOSURE", "1"))
    )
    if net_sn_buffer < 0 or net_sn_exposure < 0:
        parser.error("--net-sn-buffer and --net-sn-exposure must be nonnegative")
    # The wrapper reads these at module import time in each worker.  Set them
    # in the parent before ProcessPoolExecutor starts so spawned workers inherit
    # the exact gate setting for this evaluation.
    os.environ["OMW_NET_SN_BUFFER"] = str(net_sn_buffer)
    os.environ["OMW_NET_SN_EXPOSURE"] = repr(net_sn_exposure)
    policies = _parse_csv(args.policies)
    opponents = _parse_csv(args.opponents)
    ablation_opponents = _parse_csv(args.ablation_opponents)
    if not policies or any(policy not in POLICIES for policy in policies):
        parser.error(f"--policies must use {', '.join(POLICIES)}")
    if len(set(policies)) != len(policies):
        parser.error("duplicate policies")
    if not opponents or any(opponent not in PANEL for opponent in opponents):
        parser.error(f"--opponents must use {', '.join(PANEL)}")
    if len(set(opponents)) != len(opponents):
        parser.error("duplicate opponents")
    if args.include_ablations:
        for policy in ABLATION_POLICIES:
            if policy not in policies:
                policies += (policy,)
    if any(policy in ABLATION_POLICIES for policy in policies):
        if not ablation_opponents or any(opponent not in PANEL for opponent in ablation_opponents):
            parser.error(f"--ablation-opponents must use {', '.join(PANEL)}")
        if len(set(ablation_opponents)) != len(ablation_opponents):
            parser.error("duplicate ablation opponents")
    if args.seeds < 1 or args.workers < 1:
        parser.error("--seeds and --workers must be positive")
    if not args.model.is_file():
        parser.error(f"model does not exist: {args.model}")
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error("use a new output directory; results are immutable")

    full_policies = tuple(policy for policy in policies if policy not in ABLATION_POLICIES)
    tasks = []
    for policy in policies:
        task_opponents = ablation_opponents if policy in ABLATION_POLICIES else opponents
        for opponent in task_opponents:
            for seed in range(args.seed, args.seed + args.seeds):
                for seat in (0, 1):
                    tasks.append((policy, opponent, seed, seat))
    model = json.loads(args.model.read_text())
    recorded_items = model.get("training", {}).get("items", ELIGIBLE_ITEMS)
    item_source = args.items.split(",") if args.items is not None else recorded_items
    items = tuple(str(part).strip().upper() for part in item_source if str(part).strip())
    if not items or any(item not in ELIGIBLE_ITEMS for item in items):
        parser.error(f"--items must use {', '.join(ELIGIBLE_ITEMS)}")
    if len(set(items)) != len(items):
        parser.error("duplicate --items")
    manifest = {
        "schema": 1,
        "policy": "event_cnn_ppo_omw_v1",
        "reference_policy": "fixed",
        "reference_description": "event wrapper with OMW-002 full action (choice=full)",
        "model": str(args.model.resolve()),
        "seed_start": args.seed,
        "seed_count": args.seeds,
        "seats": [0, 1],
        "policies": list(policies),
        "opponents": list(opponents),
        "ablation_opponents": list(ablation_opponents),
        "games": len(tasks),
        "workers": args.workers,
        "learned_items": list(items),
        "gate_parameters": {
            "OMW_NET_SN_BUFFER": net_sn_buffer,
            "OMW_NET_SN_EXPOSURE": net_sn_exposure,
        },
        "fingerprints": _source_fingerprints(args.model),
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(
        max_workers=args.workers,
        initializer=_init_worker,
        initargs=(model, items),
    ) as pool:
        futures = [pool.submit(_worker_game, task) for task in tasks]
        for index, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if index % 32 == 0 or index == len(tasks):
                print(f"{index}/{len(tasks)} games", flush=True)
    rows.sort(key=lambda row: (row["policy"], row["opponent"], row["seed"], row["seat"]))
    (args.output / "results.json").write_text(json.dumps({"manifest": manifest, "games": rows}, indent=2) + "\n")

    summaries: dict[str, Any] = {}
    for policy in policies:
        summaries[policy] = {
            "opponents": {
                opponent: _stat_rows(
                    [row for row in rows if row["policy"] == policy and row["opponent"] == opponent]
                )
                for opponent in (ablation_opponents if policy in ABLATION_POLICIES else opponents)
            }
        }
        policy_rows = [row for row in rows if row["policy"] == policy]
        summaries[policy]["aggregate"] = _stat_rows(policy_rows)
    comparisons = {
        policy: _paired_comparison(rows, policy, "fixed", opponents)
        for policy in full_policies
        if policy != "fixed"
    }
    for policy in ABLATION_POLICIES:
        if policy in policies:
            comparisons[policy] = _paired_comparison(rows, policy, "fixed", ablation_opponents)
    failed = [row for row in rows if row["status"] != "completed"]
    summary = {
        "schema": 1,
        "manifest": manifest,
        "errors": len(failed),
        "status": "completed" if not failed else "failed",
        "policies": summaries,
        "paired_vs_fixed": comparisons,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if failed:
        raise RuntimeError(f"{len(failed)} games failed; see results.json")


if __name__ == "__main__":
    main()
