#!/usr/bin/env python3
"""Evaluate a trained CNN + PPO OMW router on seat-swapped holdout seeds."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from kaggriculture_agent import registry
from kaggriculture_agent.cnn_ppo import make_router_agent
from kaggriculture_agent.local_arena import GameSpec, play_game


ROOT = Path(__file__).resolve().parents[1]
ADAPTIVE = ROOT / "experiments/omw-net-stock-sellnow-v2/main.py"
CONTROL = ROOT / "references/kaggle-scan-2026-09-21/extracted/one-more-wheat/main.py"


def load(path, label):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=982100)
    parser.add_argument("--seeds", type=int, default=32)
    args = parser.parse_args()
    model = json.loads(args.model.read_text())
    adaptive = load(ADAPTIVE, "_cnn_eval_adaptive")
    control = load(CONTROL, "_cnn_eval_control")
    registry.AGENTS["_cnn_eval"] = make_router_agent(
        model, adaptive._GENERATED_AGENT, lambda value: setattr(adaptive, "_OR2_SN_K", value)
    )
    registry.AGENTS["_cnn_eval_omw"] = control.agent
    games = []
    for seed in range(args.seed, args.seed + args.seeds):
        for seat in (0, 1):
            players = ("_cnn_eval", "_cnn_eval_omw") if seat == 0 else ("_cnn_eval_omw", "_cnn_eval")
            result = play_game(GameSpec(f"cnn-holdout-{seed}-{seat}", seed, *players, "cnn_ppo", "omw"))
            own, rival = (result.reward_0, result.reward_1) if seat == 0 else (result.reward_1, result.reward_0)
            games.append({"seed": seed, "seat": seat, "status": result.status, "reward": own,
                          "opponent_reward": rival, "margin": own - rival,
                          "win": own > rival, "draw": own == rival, "error": result.error})
    valid = [row for row in games if row["status"] == "completed"]
    wins = sum(row["win"] for row in valid)
    draws = sum(row["draw"] for row in valid)
    summary = {"games": len(games), "completed": len(valid), "errors": len(games) - len(valid),
               "wins": wins, "draws": draws, "losses": len(valid) - wins - draws,
               "score": (wins + 0.5 * draws) / len(valid),
               "mean_margin": sum(row["margin"] for row in valid) / len(valid)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"summary": summary, "games": games}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
