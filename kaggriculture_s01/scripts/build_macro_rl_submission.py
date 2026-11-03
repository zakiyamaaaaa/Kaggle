#!/usr/bin/env python3
"""Freeze a trained macro policy into a verified standard-library Kaggle ZIP."""

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

from kaggriculture_agent import registry
from kaggriculture_agent.local_arena import GameSpec, compare_runners, play_game
from kaggriculture_agent.macro_rl import make_macro_agent

ROOT = Path(__file__).resolve().parents[1]


def build(model_path: Path, output: Path):
    if output.exists():
        raise FileExistsError(output)
    model = json.loads(model_path.read_text())
    planning = (ROOT / "src/kaggriculture_agent/planning_agent.py").read_text()
    macro = (ROOT / "src/kaggriculture_agent/macro_rl.py").read_text()
    macro = macro.replace("from __future__ import annotations\n", "")
    macro = macro.replace("from .planning_agent import PLANS, agent_for_plan\n", "")
    content = (
        planning
        + "\n"
        + macro
        + "\n# Frozen trained model and Kaggle entry point.\n"
        + f"TRAINED_MODEL = {model!r}\n"
        + "agent = make_macro_agent(TRAINED_MODEL, 'macro-rl-submission')\n"
    ).encode()
    compile(content, "main.py", "exec")
    output.parent.mkdir(parents=True, exist_ok=True)
    member = zipfile.ZipInfo("main.py", date_time=(2026, 9, 20, 0, 0, 0))
    member.compress_type = zipfile.ZIP_DEFLATED
    member.external_attr = 0o644 << 16
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(member, content)
    return model, content


def verify(model, content, seed):
    original = make_macro_agent(model, "macro-rl-original")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "main.py"
        path.write_bytes(content)
        spec = importlib.util.spec_from_file_location("_frozen_macro_rl", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        traces = {"original": [], "bundle": []}

        def wrap(fn, key):
            def recorded(obs):
                action = fn(obs)
                traces[key].append(copy.deepcopy(action))
                return action
            return recorded

        registry.AGENTS["_macro_original_check"] = wrap(original, "original")
        registry.AGENTS["_macro_bundle_check"] = wrap(module.agent, "bundle")
        checks = []
        for seat in (0, 1):
            traces["original"].clear()
            traces["bundle"].clear()
            outcomes = []
            for name in ("_macro_original_check", "_macro_bundle_check"):
                players = (name, "candidate") if seat == 0 else ("candidate", name)
                outcomes.append(play_game(GameSpec(f"verify-{name}-{seat}", seed, *players, name, "candidate")))
            assert traces["original"] == traces["bundle"]
            left, right = outcomes
            assert (left.reward_0, left.reward_1, left.status) == (
                right.reward_0, right.reward_1, right.status
            )
            assert left.status == "completed" and left.steps == 719
            checks.append({"seat": seat, "rewards": [left.reward_0, left.reward_1]})
        game = GameSpec("runner-check", seed, "_macro_bundle_check", "candidate", "macro", "candidate")
        legacy, fast, same = compare_runners(game)
        assert same and legacy.status == fast.status == "completed"
        return {"seed": seed, "seats": checks, "official_fast_all_steps_equal": same}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-seed", type=int, default=741743)
    args = parser.parse_args()
    model, content = build(args.model, args.output)
    verification = verify(model, content, args.verify_seed)
    manifest = {
        "policy": "macro_bc_ppo_v1",
        "submission_status": "not_submitted",
        "model": model["training"],
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "zip_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "verification": verification,
    }
    manifest_path = args.output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
