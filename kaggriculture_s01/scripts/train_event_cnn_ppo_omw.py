#!/usr/bin/env python3
"""Train event-driven CNN + PPO decisions for OMW sell-now opportunities."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

from kaggriculture_agent import registry
from kaggriculture_agent.cnn_ppo import CHANNELS, SCALARS
from kaggriculture_agent.event_cnn_ppo import (
    ACTIONS,
    EVENT_SCHEMA_V1,
    encode_event,
    event_feature_names,
    normalize_event_schema,
)
from kaggriculture_agent.local_arena import GameSpec, play_game


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "experiments/omw-event-cnn-ppo-v1/main.py"
CONTROL = ROOT / "references/kaggle-scan-2026-09-21/extracted/one-more-wheat/main.py"
ELIGIBLE_ITEMS = (
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"
)


def load(path: Path, label: str):
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
    def __init__(self, rng, filters=8, hidden=24, feature_schema=EVENT_SCHEMA_V1):
        self.feature_schema = normalize_event_schema(feature_schema)
        self.event_features = event_feature_names(self.feature_schema)
        scalar_count = len(SCALARS) + len(self.event_features)
        self.params = {
            "cw": rng.normal(0, 0.08, (filters, len(CHANNELS), 3, 3)),
            "cb": np.zeros(filters),
            "hw": rng.normal(0, 0.1, (hidden, filters + scalar_count)),
            "hb": np.zeros(hidden),
            "pw": rng.normal(0, 0.06, (len(ACTIONS), hidden)),
            "pb": np.asarray([0.0, 0.0, 0.15]),
            "vw": rng.normal(0, 0.06, hidden),
            "vb": np.zeros(1),
        }
        self.m = {key: np.zeros_like(value) for key, value in self.params.items()}
        self.v = {key: np.zeros_like(value) for key, value in self.params.items()}
        self.t = 0

    def forward(self, images, scalars):
        ps = patches(images)
        z = np.einsum("bhwcij,fcij->bhwf", ps, self.params["cw"]) + self.params["cb"]
        pooled = np.maximum(z, 0).mean(axis=(1, 2))
        shared = np.concatenate([pooled, scalars], axis=1)
        hidden = np.tanh(shared @ self.params["hw"].T + self.params["hb"])
        logits = hidden @ self.params["pw"].T + self.params["pb"]
        logits -= logits.max(axis=1, keepdims=True)
        probs = np.exp(np.clip(logits, -40, 40))
        probs /= probs.sum(axis=1, keepdims=True)
        values = hidden @ self.params["vw"] + self.params["vb"][0]
        return probs, values, (ps, z, shared, hidden)

    def update(
        self, images, scalars, actions, old_probs, returns, advantages, lr, clip, entropy=0.03
    ):
        probs, values, (ps, z, shared, hidden) = self.forward(images, scalars)
        chosen = probs[np.arange(len(actions)), actions]
        ratio = chosen / np.maximum(old_probs, 1e-8)
        active = ((advantages >= 0) & (ratio <= 1 + clip)) | (
            (advantages < 0) & (ratio >= 1 - clip)
        )
        coeff = -(advantages * ratio * active) / len(actions)
        onehot = np.eye(len(ACTIONS))[actions]
        dlogits = coeff[:, None] * (onehot - probs)
        log_probs = np.log(np.maximum(probs, 1e-8))
        mean_log_prob = (probs * log_probs).sum(axis=1, keepdims=True)
        dlogits += entropy * probs * (log_probs - mean_log_prob) / len(actions)
        dvalues = 0.5 * (values - returns) / len(actions)
        grads = {
            "pw": dlogits.T @ hidden,
            "pb": dlogits.sum(axis=0),
            "vw": hidden.T @ dvalues,
            "vb": np.asarray([dvalues.sum()]),
        }
        dhidden = dlogits @ self.params["pw"] + dvalues[:, None] * self.params["vw"]
        dz_hidden = dhidden * (1 - hidden * hidden)
        grads["hw"] = dz_hidden.T @ shared
        grads["hb"] = dz_hidden.sum(axis=0)
        dpool = (dz_hidden @ self.params["hw"])[:, : self.params["cw"].shape[0]]
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

    def bc_update(self, images, scalars, actions, lr):
        probs, _, (ps, z, shared, hidden) = self.forward(images, scalars)
        onehot = np.eye(len(ACTIONS))[actions]
        dlogits = (probs - onehot) / len(actions)
        grads = {
            "pw": dlogits.T @ hidden,
            "pb": dlogits.sum(axis=0),
            "vw": np.zeros_like(self.params["vw"]),
            "vb": np.zeros_like(self.params["vb"]),
        }
        dhidden = dlogits @ self.params["pw"]
        dz_hidden = dhidden * (1 - hidden * hidden)
        grads["hw"] = dz_hidden.T @ shared
        grads["hb"] = dz_hidden.sum(axis=0)
        dpool = (dz_hidden @ self.params["hw"])[:, : self.params["cw"].shape[0]]
        dz = (z > 0) * dpool[:, None, None, :] / 64.0
        grads["cw"] = np.einsum("bhwf,bhwcij->fcij", dz, ps)
        grads["cb"] = dz.sum(axis=(0, 1, 2))
        self.t += 1
        for key, grad in grads.items():
            self.m[key] = 0.9 * self.m[key] + 0.1 * grad
            self.v[key] = 0.999 * self.v[key] + 0.001 * grad * grad
            mhat = self.m[key] / (1 - 0.9**self.t)
            vhat = self.v[key] / (1 - 0.999**self.t)
            self.params[key] -= lr * mhat / (np.sqrt(vhat) + 1e-8)

    def artifact(self, training):
        p = self.params
        artifact = {
            "schema": self.feature_schema,
            "architecture": "event_conv3x3_relu_gap_mlp_actor_critic",
            "actions": list(ACTIONS),
            "channels": list(CHANNELS),
            "scalars": list(SCALARS) + list(self.event_features),
            "conv": {"weights": p["cw"].tolist(), "bias": p["cb"].tolist()},
            "hidden": {"weights": p["hw"].tolist(), "bias": p["hb"].tolist()},
            "policy": {"weights": p["pw"].tolist(), "bias": p["pb"].tolist()},
            "value": {"weights": p["vw"].tolist(), "bias": float(p["vb"][0])},
            "training": training,
        }
        if self.feature_schema != EVENT_SCHEMA_V1:
            artifact["feature_schema"] = self.feature_schema
            artifact["event_features"] = list(self.event_features)
        return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=973100)
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--games-per-epoch", type=int, default=16)
    parser.add_argument("--lr", type=float, default=0.006)
    parser.add_argument("--counterfactuals", type=Path)
    parser.add_argument(
        "--items",
        default=",".join(ELIGIBLE_ITEMS),
        help="comma-separated items controlled by the learned policy",
    )
    parser.add_argument(
        "--feature-schema",
        "--schema",
        default="v1",
        help="event encoder schema (1/v1 or 2/v2) used for training and rows",
    )
    args = parser.parse_args()
    feature_schema = normalize_event_schema(args.feature_schema)
    items = tuple(part.strip().upper() for part in args.items.split(",") if part.strip())
    if not items or any(item not in ELIGIBLE_ITEMS for item in items):
        parser.error(f"--items must use {', '.join(ELIGIBLE_ITEMS)}")
    if len(set(items)) != len(items):
        parser.error("duplicate --items")
    args.output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    net = Network(rng, feature_schema=feature_schema)
    bc_report = None
    if args.counterfactuals:
        counterfactuals = json.loads(args.counterfactuals.read_text())
        recorded_schema = counterfactuals.get("feature_schema", EVENT_SCHEMA_V1)
        if normalize_event_schema(recorded_schema) != feature_schema:
            raise ValueError(
                "counterfactual feature schema does not match training schema: "
                f"{recorded_schema!r} != {feature_schema!r}"
            )
        examples = counterfactuals["examples"]
        recorded_items = tuple(counterfactuals.get("items", ELIGIBLE_ITEMS))
        if recorded_items != items:
            raise ValueError(
                "counterfactual items do not match training items: "
                f"{recorded_items!r} != {items!r}"
            )
        bc_images = np.asarray([row["image"] for row in examples])
        bc_scalars = np.asarray([row["scalars"] for row in examples])
        bc_actions = np.asarray([row["label"] for row in examples])
        for _ in range(250):
            net.bc_update(bc_images, bc_scalars, bc_actions, 0.004)
        bc_probs, _, _ = net.forward(bc_images, bc_scalars)
        bc_report = {
            "examples": len(examples),
            "accuracy": float((bc_probs.argmax(axis=1) == bc_actions).mean()),
            "label_counts": {name: int((bc_actions == index).sum())
                             for index, name in enumerate(ACTIONS)},
        }
        bc_training = {
            "method": "event_driven_counterfactual_behavior_cloning",
            "opponent": None,
            "items": list(items),
            "seed": args.seed,
            "games": 0,
            "history": [],
            "counterfactual_behavior_cloning": bc_report,
            "feature_schema": feature_schema,
        }
        (args.output / "bc_model.json").write_text(
            json.dumps(net.artifact(bc_training), indent=2) + "\n"
        )
        print(json.dumps({"behavior_cloning": bc_report}), flush=True)
    learner = load(WRAPPER, "_event_ppo_learner")
    opponent = load(CONTROL, "_event_ppo_opponent")
    registry.AGENTS["_event_ppo_learner"] = learner.agent
    registry.AGENTS["_event_ppo_opponent"] = opponent.agent
    history = []
    for epoch in range(args.epochs):
        all_rows, game_ranges, margins = [], [], []
        action_counts = np.zeros(len(ACTIONS), dtype=int)
        wins = draws = 0
        current_rows = []

        def decide(observation, item, quantity, net_batch, recovery, exposure, first_sale, rival_stock):
            if item not in items:
                return 2
            image, scalars = encode_event(
                observation,
                item,
                quantity,
                net_batch,
                recovery,
                exposure,
                first_sale,
                rival_stock,
                schema=feature_schema,
            )
            probs, value, _ = net.forward(
                np.asarray(image, dtype=np.float64)[None],
                np.asarray(scalars, dtype=np.float64)[None],
            )
            sample = probs[0]
            action = int(rng.choice(len(ACTIONS), p=sample))
            action_counts[action] += 1
            current_rows.append(
                {"image": image, "scalars": scalars, "action": action,
                 "old_prob": float(probs[0, action]), "value": float(value[0])}
            )
            return action

        learner._OR3_DECIDER = decide
        for game in range(args.games_per_epoch):
            current_rows = []
            seat = game % 2
            players = (
                ("_event_ppo_learner", "_event_ppo_opponent")
                if seat == 0 else ("_event_ppo_opponent", "_event_ppo_learner")
            )
            result = play_game(
                GameSpec(f"event-ppo-{epoch}-{game}", args.seed + epoch * 1000 + game,
                         *players, "event_cnn_ppo", "omw")
            )
            if result.status != "completed":
                raise RuntimeError(result.error)
            own, rival = (
                (result.reward_0, result.reward_1)
                if seat == 0 else (result.reward_1, result.reward_0)
            )
            terminal = (1.0 if own > rival else -1.0 if own < rival else 0.0) + 0.25 * np.tanh(
                (own - rival) / 2000.0
            )
            start = len(all_rows)
            all_rows.extend(current_rows)
            game_ranges.append((start, len(all_rows), float(terminal)))
            margins.append(own - rival)
            wins += own > rival
            draws += own == rival
        returns = np.zeros(len(all_rows))
        for start, end, terminal in game_ranges:
            for index in range(end - 1, start - 1, -1):
                returns[index] = terminal * (0.995 ** (end - 1 - index))
        if not all_rows:
            raise RuntimeError("training produced no eligible sell events")
        values = np.asarray([row["value"] for row in all_rows])
        advantages = returns - values
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        images = np.asarray([row["image"] for row in all_rows])
        scalars = np.asarray([row["scalars"] for row in all_rows])
        actions = np.asarray([row["action"] for row in all_rows])
        old_probs = np.asarray([row["old_prob"] for row in all_rows])
        for _ in range(6):
            net.update(images, scalars, actions, old_probs, returns, advantages, args.lr, 0.2)
        item = {
            "epoch": epoch + 1,
            "games": args.games_per_epoch,
            "events": len(all_rows),
            "win_rate": wins / args.games_per_epoch,
            "score": (wins + 0.5 * draws) / args.games_per_epoch,
            "mean_margin": float(np.mean(margins)),
            "action_counts": {ACTIONS[i]: int(action_counts[i]) for i in range(len(ACTIONS))},
        }
        history.append(item)
        print(json.dumps(item), flush=True)
    training = {
        "method": "event_driven_cnn_clipped_ppo",
        "feature_schema": feature_schema,
        "opponent": "one_more_wheat",
        "items": list(items),
        "seed": args.seed,
        "games": args.epochs * args.games_per_epoch,
        "history": history,
        "counterfactual_behavior_cloning": bc_report,
    }
    model = net.artifact(training)
    (args.output / "model.json").write_text(json.dumps(model, indent=2) + "\n")
    (args.output / "training_report.json").write_text(json.dumps(training, indent=2) + "\n")


if __name__ == "__main__":
    main()
