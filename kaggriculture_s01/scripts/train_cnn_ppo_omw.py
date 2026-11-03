#!/usr/bin/env python3
"""Train a small NumPy CNN + PPO router directly against One More Wheat."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

from kaggriculture_agent import registry
from kaggriculture_agent.cnn_ppo import CHANNELS, SCALARS, THRESHOLDS, encode_observation
from kaggriculture_agent.local_arena import GameSpec, play_game


ROOT = Path(__file__).resolve().parents[1]
ADAPTIVE = ROOT / "experiments/omw-net-stock-sellnow-v2/main.py"
CONTROL = ROOT / "references/kaggle-scan-2026-09-21/extracted/one-more-wheat/main.py"


def load_module(path: Path, label: str):
    spec = importlib.util.spec_from_file_location(label, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


def patches(images):
    return np.lib.stride_tricks.sliding_window_view(images, (3, 3), axis=(1, 2))


class Network:
    def __init__(self, rng, filters=8, hidden=16):
        self.params = {
            "cw": rng.normal(0, 0.08, (filters, len(CHANNELS), 3, 3)),
            "cb": np.zeros(filters),
            "hw": rng.normal(0, 0.12, (hidden, filters + len(SCALARS))),
            "hb": np.zeros(hidden),
            "pw": rng.normal(0, 0.08, (len(THRESHOLDS), hidden)),
            "pb": np.asarray([-0.5, -0.2, 0.0, 0.8, 0.0, -0.2]),
            "vw": rng.normal(0, 0.08, hidden),
            "vb": np.zeros(1),
        }
        self.m = {key: np.zeros_like(value) for key, value in self.params.items()}
        self.v = {key: np.zeros_like(value) for key, value in self.params.items()}
        self.t = 0

    def forward(self, images, scalars):
        ps = patches(images)
        z = np.einsum("bhwcij,fcij->bhwf", ps, self.params["cw"]) + self.params["cb"]
        relu = np.maximum(z, 0)
        pooled = relu.mean(axis=(1, 2))
        shared = np.concatenate([pooled, scalars], axis=1)
        hidden = np.tanh(shared @ self.params["hw"].T + self.params["hb"])
        logits = hidden @ self.params["pw"].T + self.params["pb"]
        logits -= logits.max(axis=1, keepdims=True)
        probs = np.exp(np.clip(logits, -40, 40))
        probs /= probs.sum(axis=1, keepdims=True)
        values = hidden @ self.params["vw"] + self.params["vb"][0]
        return probs, values, (ps, z, shared, hidden)

    def update(self, images, scalars, actions, old_probs, returns, advantages, lr, clip):
        probs, values, cache = self.forward(images, scalars)
        ps, z, shared, hidden = cache
        chosen = probs[np.arange(len(actions)), actions]
        ratio = chosen / np.maximum(old_probs, 1e-8)
        active = ((advantages >= 0) & (ratio <= 1 + clip)) | (
            (advantages < 0) & (ratio >= 1 - clip)
        )
        coeff = -(advantages * ratio * active) / len(actions)
        onehot = np.eye(len(THRESHOLDS))[actions]
        dlogits = coeff[:, None] * (onehot - probs)
        dvalues = 0.5 * (values - returns) / len(actions)
        grads = {}
        grads["pw"] = dlogits.T @ hidden
        grads["pb"] = dlogits.sum(axis=0)
        grads["vw"] = hidden.T @ dvalues
        grads["vb"] = np.asarray([dvalues.sum()])
        dh = dlogits @ self.params["pw"] + dvalues[:, None] * self.params["vw"]
        dz_hidden = dh * (1 - hidden * hidden)
        grads["hw"] = dz_hidden.T @ shared
        grads["hb"] = dz_hidden.sum(axis=0)
        dshared = dz_hidden @ self.params["hw"]
        dpool = dshared[:, : self.params["cw"].shape[0]]
        dz = (z > 0) * dpool[:, None, None, :] / 64.0
        grads["cw"] = np.einsum("bhwf,bhwcij->fcij", dz, ps)
        grads["cb"] = dz.sum(axis=(0, 1, 2))
        self.t += 1
        for key, grad in grads.items():
            grad = np.clip(grad, -2.0, 2.0)
            self.m[key] = 0.9 * self.m[key] + 0.1 * grad
            self.v[key] = 0.999 * self.v[key] + 0.001 * grad * grad
            mhat = self.m[key] / (1 - 0.9**self.t)
            vhat = self.v[key] / (1 - 0.999**self.t)
            self.params[key] -= lr * mhat / (np.sqrt(vhat) + 1e-8)

    def artifact(self, training):
        p = self.params
        return {
            "schema": 1,
            "architecture": "conv3x3_relu_gap_mlp_actor_critic",
            "thresholds": list(THRESHOLDS),
            "channels": list(CHANNELS),
            "scalars": list(SCALARS),
            "conv": {"weights": p["cw"].tolist(), "bias": p["cb"].tolist()},
            "hidden": {"weights": p["hw"].tolist(), "bias": p["hb"].tolist()},
            "policy": {"weights": p["pw"].tolist(), "bias": p["pb"].tolist()},
            "value": {"weights": p["vw"].tolist(), "bias": float(p["vb"][0])},
            "training": training,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=972100)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--games-per-epoch", type=int, default=16)
    parser.add_argument("--lr", type=float, default=0.008)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    net = Network(rng)
    adaptive = load_module(ADAPTIVE, "_cnn_ppo_adaptive")
    control = load_module(CONTROL, "_cnn_ppo_control")
    registry.AGENTS["_cnn_ppo_opponent"] = control.agent
    history = []
    for epoch in range(args.epochs):
        rows, margins, wins = [], [], 0
        state = {"step": -1, "day": -1, "margin": 0.0}

        def learner(obs):
            step, day = int(obs["step"]), int(obs["day"])
            if step <= state["step"]:
                state.update(step=-1, day=-1, margin=0.0)
            if day != state["day"]:
                image, scalar = encode_observation(obs)
                images = np.asarray(image, dtype=np.float64)[None]
                scalars = np.asarray(scalar, dtype=np.float64)[None]
                probs, value, _ = net.forward(images, scalars)
                sample = probs[0] ** (1 / 0.8)
                sample /= sample.sum()
                action = int(rng.choice(len(THRESHOLDS), p=sample))
                player = int(obs["player"])
                farms = obs["farms"]
                margin = float(farms[player]["money"]) - float(farms[1 - player]["money"])
                if rows and rows[-1].get("open"):
                    rows[-1]["reward"] += 0.05 * float(np.tanh((margin - state["margin"]) / 5000))
                    rows[-1]["open"] = False
                rows.append(
                    {"image": image, "scalars": scalar, "action": action,
                     "old_prob": float(probs[0, action]), "value": float(value[0]),
                     "reward": 0.0, "open": True}
                )
                state.update(day=day, margin=margin, action=action)
            state["step"] = step
            adaptive._OR2_SN_K = THRESHOLDS[state["action"]]
            return adaptive._GENERATED_AGENT(obs)

        registry.AGENTS["_cnn_ppo_learner"] = learner
        game_ranges = []
        for game in range(args.games_per_epoch):
            start = len(rows)
            seat = game % 2
            players = (
                ("_cnn_ppo_learner", "_cnn_ppo_opponent")
                if seat == 0 else ("_cnn_ppo_opponent", "_cnn_ppo_learner")
            )
            result = play_game(GameSpec(f"cnn-ppo-{epoch}-{game}", args.seed + epoch * 1000 + game, *players, "cnn", "omw"))
            if result.status != "completed":
                raise RuntimeError(result.error)
            own, rival = (result.reward_0, result.reward_1) if seat == 0 else (result.reward_1, result.reward_0)
            terminal = (1.0 if own > rival else -1.0 if own < rival else 0.0) + 0.25 * np.tanh((own - rival) / 2000)
            rows[-1]["reward"] += float(terminal)
            rows[-1]["open"] = False
            game_ranges.append((start, len(rows)))
            margins.append(own - rival)
            wins += own > rival
        returns = np.zeros(len(rows))
        for start, end in game_ranges:
            running = 0.0
            for index in range(end - 1, start - 1, -1):
                running = rows[index]["reward"] + 0.99 * running
                returns[index] = running
        advantages = returns - np.asarray([row["value"] for row in rows])
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        images = np.asarray([row["image"] for row in rows])
        scalars = np.asarray([row["scalars"] for row in rows])
        actions = np.asarray([row["action"] for row in rows])
        old = np.asarray([row["old_prob"] for row in rows])
        for _ in range(6):
            net.update(images, scalars, actions, old, returns, advantages, args.lr, 0.2)
        counts = {str(THRESHOLDS[i]): int((actions == i).sum()) for i in range(len(THRESHOLDS))}
        item = {"epoch": epoch + 1, "games": args.games_per_epoch, "win_rate": wins / args.games_per_epoch,
                "mean_margin": float(np.mean(margins)), "action_counts": counts}
        history.append(item)
        print(json.dumps(item), flush=True)
    training = {"method": "cnn_clipped_ppo", "opponent": "one_more_wheat", "seed": args.seed,
                "games": args.epochs * args.games_per_epoch, "history": history}
    model = net.artifact(training)
    (args.output / "model.json").write_text(json.dumps(model, indent=2) + "\n")
    (args.output / "training_report.json").write_text(json.dumps(training, indent=2) + "\n")


if __name__ == "__main__":
    main()
