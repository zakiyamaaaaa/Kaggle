#!/usr/bin/env python3
"""BC-warm a macro policy from top replays, then refine it with local PPO."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from kaggriculture_agent import registry
from kaggriculture_agent.local_arena import GameSpec, play_game
from kaggriculture_agent.macro_rl import (
    ACTIONS,
    FEATURE_NAMES,
    _farm_counts,
    features,
    make_macro_agent,
    probabilities,
)
from kaggriculture_agent.planning_agent import PLANS, agent_for_plan


def expert_label(now, future):
    player = int(now.get("player", 0))
    a = _farm_counts(now["farms"][player])
    b = _farm_counts(future["farms"][player])
    land = len(future["farms"][player].get("unlocked_quadrants", []))
    if b["FERTILIZED"] > a["FERTILIZED"]:
        return ACTIONS.index("economy_fert50")
    if b["COW"] >= 5 and b["COW"] > b["SHEEP"] + b["GOOSE"]:
        return ACTIONS.index("planner_cows8")
    if b["SHEEP"] >= 5 and b["SHEEP"] > b["COW"] + b["GOOSE"]:
        return ACTIONS.index("planner_sheep8")
    if land >= 3:
        return ACTIONS.index("economy_mix75")
    if land >= 2:
        return ACTIONS.index("economy_mix50")
    return ACTIONS.index("economy_mix25")


def replay_examples(paths):
    xs, ys, sources = [], [], []
    for path in paths:
        replay = json.loads(path.read_text())
        steps = replay["steps"]
        for player in (0, 1):
            for step in range(0, 648, 72):
                now = steps[step][player]["observation"]
                future = steps[min(step + 72, 719)][player]["observation"]
                xs.append(features(now))
                ys.append(expert_label(now, future))
                sources.append(path.name)
    return np.asarray(xs), np.asarray(ys), sources


def softmax(logits):
    logits = logits - logits.max(axis=1, keepdims=True)
    values = np.exp(np.clip(logits, -40, 40))
    return values / values.sum(axis=1, keepdims=True)


def bc_train(x, y, rng, epochs=500, lr=0.08):
    w = rng.normal(0, 0.02, (len(ACTIONS), x.shape[1]))
    b = np.zeros(len(ACTIONS))
    for _ in range(epochs):
        p = softmax(x @ w.T + b)
        target = np.eye(len(ACTIONS))[y]
        grad = (p - target) / len(x)
        w -= lr * (grad.T @ x + 0.002 * w)
        b -= lr * grad.sum(axis=0)
    accuracy = float((softmax(x @ w.T + b).argmax(axis=1) == y).mean())
    return w, b, accuracy


def rollout(model, opponent, seed, seat, rng, temperature):
    records = []
    alias = "_macro_ppo_learner"
    state = {"step": -1, "phase": -1, "action": 0, "margin": 0.0}

    def learner(obs):
        step, phase = int(obs["step"]), int(obs["step"]) // 72
        if step <= state["step"]:
            state.update(step=-1, phase=-1, action=0, margin=0.0)
            records.clear()
        if phase != state["phase"]:
            x = features(obs)
            player = int(obs["player"])
            farms = obs["farms"]
            margin = float(farms[player]["money"]) - float(farms[1 - player]["money"])
            if records:
                records[-1]["reward"] += 0.15 * float(
                    np.tanh((margin - state["margin"]) / 10_000.0)
                )
            probs = np.asarray(probabilities(model, x))
            if temperature != 1.0:
                probs = probs ** (1.0 / temperature)
                probs /= probs.sum()
            action = int(rng.choice(len(ACTIONS), p=probs))
            records.append(
                {"x": x, "action": action, "old_prob": float(probs[action]), "reward": 0.0}
            )
            state.update(phase=phase, action=action, margin=margin)
        state["step"] = step
        plan = ACTIONS[state["action"]]
        return agent_for_plan(obs, PLANS[plan], "macro-ppo-executor")

    registry.AGENTS[alias] = learner
    players = (alias, opponent) if seat == 0 else (opponent, alias)
    result = play_game(GameSpec(f"ppo-{seed}-{seat}", seed, *players, alias, opponent))
    if result.status != "completed":
        raise RuntimeError(result.error)
    own, other = (result.reward_0, result.reward_1) if seat == 0 else (result.reward_1, result.reward_0)
    terminal = (1.0 if own > other else -1.0 if own < other else 0.0) + 0.25 * np.tanh(
        (own - other) / 20_000.0
    )
    records[-1]["reward"] += float(terminal)
    return records, float(own), float(other)


def ppo_update(w, b, rows, lr=0.025, clip=0.2, epochs=8):
    x = np.asarray([r["x"] for r in rows])
    actions = np.asarray([r["action"] for r in rows])
    old = np.asarray([r["old_prob"] for r in rows])
    adv = np.asarray([r["reward"] for r in rows])
    adv = (adv - adv.mean()) / (adv.std() + 1e-8)
    for _ in range(epochs):
        p = softmax(x @ w.T + b)
        chosen = p[np.arange(len(rows)), actions]
        ratio = chosen / np.maximum(old, 1e-8)
        active = ((adv >= 0) & (ratio <= 1 + clip)) | ((adv < 0) & (ratio >= 1 - clip))
        coeff = -(adv * ratio * active) / len(rows)
        onehot = np.eye(len(ACTIONS))[actions]
        grad_logits = coeff[:, None] * (onehot - p)
        w -= lr * (grad_logits.T @ x + 0.001 * w)
        b -= lr * grad_logits.sum(axis=0)
    return w, b


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replays", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=741743)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--games-per-epoch", type=int, default=48)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    paths = sorted(args.replays.glob("*-replay.json"))
    if not paths:
        parser.error("no replay files found")
    rng = np.random.default_rng(args.seed)
    x, y, sources = replay_examples(paths)
    w, b, bc_accuracy = bc_train(x, y, rng)
    history = []
    bank_model = {"weights": w.tolist(), "bias": b.tolist()}
    for epoch in range(args.epochs):
        rows, margins, wins = [], [], 0
        model = {"weights": w.tolist(), "bias": b.tolist()}
        registry.AGENTS["_macro_ppo_self"] = make_macro_agent(model, f"ppo-self-{epoch}")
        registry.AGENTS["_macro_ppo_bank"] = make_macro_agent(bank_model, f"ppo-bank-{epoch}")
        opponents = ("_macro_ppo_self", "_macro_ppo_self", "candidate", "_macro_ppo_bank")
        for game in range(args.games_per_epoch):
            opponent = opponents[game % len(opponents)]
            seat = game % 2
            trajectory, own, other = rollout(
                model, opponent, args.seed + epoch * 10_000 + game, seat, rng, 0.8
            )
            rows.extend(trajectory)
            margins.append(own - other)
            wins += own > other
        w, b = ppo_update(w, b, rows)
        item = {
            "epoch": epoch + 1,
            "games": args.games_per_epoch,
            "decisions": len(rows),
            "win_rate": wins / args.games_per_epoch,
            "mean_margin": float(np.mean(margins)),
        }
        history.append(item)
        print(json.dumps(item), flush=True)
        bank_model = model
    counts = {action: int((y == index).sum()) for index, action in enumerate(ACTIONS)}
    artifact = {
        "schema": 1,
        "actions": list(ACTIONS),
        "feature_names": list(FEATURE_NAMES),
        "weights": w.tolist(),
        "bias": b.tolist(),
        "training": {
            "method": "behavior_cloning_then_clipped_ppo",
            "replays": sorted(set(sources)),
            "bc_examples": len(x),
            "bc_label_counts": counts,
            "bc_training_accuracy": bc_accuracy,
            "ppo_games": args.epochs * args.games_per_epoch,
            "opponent_mix": {"self_play": 0.5, "active_candidate": 0.25, "policy_bank": 0.25},
            "temperature": 0.8,
            "history": history,
        },
    }
    (args.output / "model.json").write_text(json.dumps(artifact, indent=2) + "\n")
    (args.output / "training_report.json").write_text(json.dumps(artifact["training"], indent=2) + "\n")
    print(json.dumps({"output": str(args.output / "model.json"), **artifact["training"]}, indent=2))


if __name__ == "__main__":
    main()
