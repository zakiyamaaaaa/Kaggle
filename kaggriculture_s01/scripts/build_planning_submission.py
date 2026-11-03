#!/usr/bin/env python3
"""Freeze and verify a standard-library-only planning policy without submitting."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import zipfile
from pathlib import Path

from kaggriculture_agent.local_arena import GameSpec, compare_runners, play_game
from kaggriculture_agent.planning_agent import PLANS
from kaggriculture_agent import registry

ROOT = Path(__file__).resolve().parents[1]


def build(policy: str, output: Path):
    if policy not in PLANS:
        raise ValueError(f"unknown policy: {policy}")
    if output.exists():
        raise FileExistsError("frozen submission already exists")
    source = (ROOT / "src/kaggriculture_agent/planning_agent.py").read_text()
    content = (
        source + f"\n# Frozen Kaggle entry point.\nagent = make_agent({policy!r})\n"
    ).encode()
    compile(content, "main.py", "exec")
    member = zipfile.ZipInfo("main.py", date_time=(2026, 9, 20, 0, 0, 0))
    member.compress_type = zipfile.ZIP_DEFLATED
    member.external_attr = 0o644 << 16
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(member, content)
    return content


def verify(policy, content, seed):
    traces = {"original": [], "bundle": []}
    original = registry.AGENTS[policy]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "main.py"
        path.write_bytes(content)
        spec = importlib.util.spec_from_file_location("_frozen_planning_policy", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        def wrap(fn, key):
            def recorded(obs):
                result = fn(obs)
                traces[key].append(copy.deepcopy(result))
                return result

            return recorded

        registry.AGENTS["_original_planner_check"] = wrap(original, "original")
        registry.AGENTS["_frozen_planner_check"] = wrap(module.agent, "bundle")
        checks = []
        for seat in (0, 1):
            traces["original"].clear()
            traces["bundle"].clear()
            results = []
            for name in ("_original_planner_check", "_frozen_planner_check"):
                players = (name, "candidate") if seat == 0 else ("candidate", name)
                game = GameSpec(f"check-{name}-{seat}", seed, *players, name, "candidate")
                results.append(play_game(game))
            assert traces["original"] == traces["bundle"]
            a, b = results
            assert (a.reward_0, a.reward_1, a.status, a.steps) == (
                b.reward_0,
                b.reward_1,
                b.status,
                b.steps,
            )
            assert a.status == "completed" and a.steps == 719
            checks.append(
                {
                    "seat": seat,
                    "actions_equal": len(traces["original"]),
                    "rewards": [a.reward_0, a.reward_1],
                    "status": a.status,
                }
            )
        game = GameSpec(
            "runner-check",
            seed,
            "_frozen_planner_check",
            "candidate",
            "_frozen_planner_check",
            "candidate",
        )
        legacy, fast, same = compare_runners(game)
        assert same and legacy.status == fast.status == "completed"
        assert (legacy.reward_0, legacy.reward_1) == (fast.reward_0, fast.reward_1)
        return {"seed": seed, "bundle_checks": checks, "official_fast_all_steps_equal": same}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--policy", required=True, choices=sorted(PLANS))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--verify-seed", type=int, default=135001)
    a = p.parse_args()
    content = build(a.policy, a.output)
    checks = verify(a.policy, content, a.verify_seed)
    manifest = {
        "policy": a.policy,
        "submission_status": "not_submitted",
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "zip_sha256": hashlib.sha256(a.output.read_bytes()).hexdigest(),
        "verification": checks,
    }
    a.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
