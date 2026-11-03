#!/usr/bin/env python3
"""Freeze the event CNN + PPO policy into a self-contained Kaggle archive."""

from __future__ import annotations

import ast
import copy
import gzip
import hashlib
import importlib.util
import io
import json
import runpy
import sys
import tarfile
from pathlib import Path

from kaggriculture_agent import registry
from kaggriculture_agent.event_cnn_ppo import make_decider
from kaggriculture_agent.local_arena import GameSpec, play_game


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments/omw-event-cnn-ppo-v1/main.py"
MODEL = ROOT / "outputs/event_cnn_ppo_omw_v1/cf-trained/model.json"
CNN_SOURCE = ROOT / "src/kaggriculture_agent/cnn_ppo.py"
EVENT_SOURCE = ROOT / "src/kaggriculture_agent/event_cnn_ppo.py"
CONTROL = ROOT / "references/kaggle-scan-2026-09-21/extracted/one-more-wheat/main.py"
OUT_DIR = ROOT / "submissions/event-cnn-ppo-omw-v1"
OUT_MAIN = OUT_DIR / "main.py"
OUT_TAR = ROOT / "submissions/event-cnn-ppo-omw-v1.tar.gz"
OUT_MANIFEST = ROOT / "submissions/event-cnn-ppo-omw-v1.manifest.json"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def selected_source(path: Path, names: set[str]) -> str:
    tree = ast.parse(path.read_text())
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            target_names = {target.id for target in targets if isinstance(target, ast.Name)}
            if target_names & names:
                selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in names:
            selected.append(node)
    missing = names - {
        node.name if isinstance(node, ast.FunctionDef) else target.id
        for node in selected
        for target in (
            [node] if isinstance(node, ast.FunctionDef)
            else (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
        if isinstance(target, (ast.Name, ast.FunctionDef))
    }
    if missing:
        raise RuntimeError(f"could not freeze definitions from {path}: {sorted(missing)}")
    return ast.unparse(ast.Module(body=selected, type_ignores=[])) + "\n"


def build() -> tuple[dict, bytes]:
    model = json.loads(MODEL.read_text())
    source = runpy.run_path(str(EXPERIMENT))["_source"]
    cnn = selected_source(
        CNN_SOURCE, {"CHANNELS", "SCALARS", "_tile_channels", "encode_observation"}
    )
    event = selected_source(
        EVENT_SOURCE,
        {
            "ITEMS",
            "ACTIONS",
            "EVENT_SCHEMA_V1",
            "EVENT_SCHEMA_V2",
            "SUPPORTED_EVENT_SCHEMAS",
            "_ITEM_FEATURES",
            "_COMMON_EVENT_FEATURES",
            "EVENT_FEATURES_V1",
            "EVENT_FEATURES_V2",
            "EVENT_FEATURES_BY_SCHEMA",
            "EVENT_FEATURES",
            "normalize_event_schema",
            "event_feature_names",
            "feature_schema_from_artifact",
            "_encode_event_v1",
            "_encode_event_v2",
            "encode_event",
            "policy_value",
            "make_decider",
        },
    )
    frozen = (
        "\nfrom math import exp, log1p, tanh\nfrom typing import Any\n"
        + cnn
        + "\n"
        + event
        + f"\nFROZEN_EVENT_MODEL = {model!r}\n"
        + "_OR3_TELEMETRY = {}\n"
        + "_OR3_DECIDER = make_decider(FROZEN_EVENT_MODEL, _OR3_TELEMETRY)\n"
    )
    marker = "_OR3_DECIDER = globals().get('_OR3_DECIDER', lambda *args: 2)\n"
    if source.count(marker) != 1:
        raise RuntimeError("unexpected event decider marker")
    source = source.replace(marker, frozen + "\n", 1)
    content = source.encode()
    compile(content, "main.py", "exec")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_MAIN.write_bytes(content)
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w") as archive:
            member = tarfile.TarInfo("main.py")
            member.size = len(content)
            member.mode = 0o644
            member.mtime = 0
            archive.addfile(member, io.BytesIO(content))
    OUT_TAR.write_bytes(buffer.getvalue())
    return model, content


def load_agent(path: Path, label: str):
    spec = importlib.util.spec_from_file_location(label, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[label] = module
    spec.loader.exec_module(module)
    return module


def verify(model: dict, seed: int = 976777) -> dict:
    development = load_agent(EXPERIMENT, "_event_submission_development")
    development._OR3_DECIDER = make_decider(model, {})
    bundled = load_agent(OUT_MAIN, "_event_submission_bundled")
    opponent = load_agent(CONTROL, "_event_submission_opponent")
    traces = {"development": [], "bundled": []}

    def recorded(fn, key):
        def agent(obs):
            action = fn(obs)
            traces[key].append(copy.deepcopy(action))
            return action

        return agent

    registry.AGENTS["_event_submission_development"] = recorded(
        development.agent, "development"
    )
    registry.AGENTS["_event_submission_bundled"] = recorded(bundled.agent, "bundled")
    registry.AGENTS["_event_submission_opponent"] = opponent.agent
    checks = []
    for seat in (0, 1):
        outcomes = []
        saved_traces = []
        for alias, key in (
            ("_event_submission_development", "development"),
            ("_event_submission_bundled", "bundled"),
        ):
            traces[key].clear()
            players = (alias, "_event_submission_opponent") if seat == 0 else (
                "_event_submission_opponent", alias
            )
            result = play_game(GameSpec(f"bundle-{seat}-{key}", seed, *players, key, "omw"))
            if result.status != "completed" or result.steps != 719:
                raise RuntimeError(f"bundle verification failed: {result}")
            outcomes.append((result.reward_0, result.reward_1, result.status))
            saved_traces.append(copy.deepcopy(traces[key]))
        if saved_traces[0] != saved_traces[1] or outcomes[0] != outcomes[1]:
            raise RuntimeError(f"development/bundle parity failed in seat {seat}")
        checks.append({"seat": seat, "rewards": list(outcomes[0][:2]), "actions": len(saved_traces[0])})
    with tarfile.open(OUT_TAR, "r:gz") as archive:
        members = archive.getnames()
        archived_main = archive.extractfile("main.py").read()
    if members != ["main.py"] or archived_main != OUT_MAIN.read_bytes():
        raise RuntimeError("archive content verification failed")
    return {"seed": seed, "seats": checks, "archive_members": members, "action_parity": True}


def main() -> None:
    model, content = build()
    verification = verify(model)
    manifest = {
        "competition": "kaggriculture",
        "policy": "event_cnn_ppo_omw_v1",
        "parent": "one_more_wheat_with_net_stock_sellnow_v2",
        "status": "built_not_submitted",
        "model_sha256": sha256_bytes(MODEL.read_bytes()),
        "main_sha256": sha256_bytes(content),
        "archive_sha256": sha256_bytes(OUT_TAR.read_bytes()),
        "archive_size_bytes": OUT_TAR.stat().st_size,
        "archive_members": ["main.py"],
        "verification": verification,
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
