#!/usr/bin/env python3
"""Run an immutable hard-gate sweep for the Event-CNN-PPO v1 policy.

The event wrapper reads ``OMW_NET_SN_BUFFER`` and ``OMW_NET_SN_EXPOSURE`` when
it is imported by an evaluator worker.  Each grid point therefore runs the
existing evaluator in its own subprocess, with the gate values passed both as
CLI arguments and inherited environment variables.  The learned model is
loaded read-only for every setting; no training or model rewrite is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / "scripts/evaluate_event_cnn_ppo_omw.py"
WRAPPER = ROOT / "experiments/omw-event-cnn-ppo-v1/main.py"
NET_STOCK = ROOT / "experiments/omw-net-stock-sellnow-v2/main.py"
MODEL_DEFAULT = ROOT / "outputs/event_cnn_ppo_omw_v1/cf-trained/model.json"
RESULTS_ROOT = ROOT / "experiments/omw-event-cnn-ppo-v1/results"
OUTPUT_DEFAULT = RESULTS_ROOT / "hard-gate-sweep-v1"
OPPONENTS = ("omw", "peak", "triad")
POLICIES = ("learned", "fixed")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _parse_ints(value: str, label: str) -> tuple[int, ...]:
    try:
        parsed = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as exc:
        raise ValueError(f"{label} must be comma-separated integers") from exc
    if not parsed or any(item < 0 for item in parsed):
        raise ValueError(f"{label} must contain at least one nonnegative integer")
    if len(set(parsed)) != len(parsed):
        raise ValueError(f"{label} contains duplicates")
    return parsed


def _parse_floats(value: str, label: str) -> tuple[float, ...]:
    try:
        parsed = tuple(float(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as exc:
        raise ValueError(f"{label} must be comma-separated numbers") from exc
    if not parsed or any(item < 0 for item in parsed):
        raise ValueError(f"{label} must contain at least one nonnegative number")
    if len(set(parsed)) != len(parsed):
        raise ValueError(f"{label} contains duplicates")
    return parsed


def _slug(value: float) -> str:
    text = format(value, "g")
    return text.replace("-", "m").replace(".", "p")


def _setting_id(buffer: int, exposure: float) -> str:
    return f"b{buffer:02d}-e{_slug(exposure)}"


def _metrics(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten child WDL/score/margin/error summaries for easy comparison."""

    rows: list[dict[str, Any]] = []
    for policy in POLICIES:
        policy_summary = summary["policies"][policy]
        for opponent, stats in policy_summary["opponents"].items():
            rows.append(
                {
                    "policy": policy,
                    "opponent": opponent,
                    "wins": stats["wins"],
                    "draws": stats["draws"],
                    "losses": stats["losses"],
                    "wdl": [stats["wins"], stats["draws"], stats["losses"]],
                    "score": stats["score"],
                    "mean_margin": stats["mean_margin"],
                    "errors": stats["errors"],
                    "games": stats["games"],
                    "completed": stats["completed"],
                }
            )
    return rows


def _best_key(setting: dict[str, Any]) -> tuple[int, float, float, int]:
    aggregate = setting["policies"]["learned"]["aggregate"]
    score = aggregate["score"] if aggregate["score"] is not None else -1.0
    margin = aggregate["mean_margin"] if aggregate["mean_margin"] is not None else float("-inf")
    errors = int(setting["errors"])
    return (int(errors == 0), score, margin, -errors)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL_DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--seed", type=int, default=988000)
    parser.add_argument("--seeds", type=int, default=4)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--buffer-values", default="8,12,16")
    parser.add_argument("--exposure-values", default="0.5,1,2")
    args = parser.parse_args()
    args.output = args.output.resolve()

    try:
        buffers = _parse_ints(args.buffer_values, "--buffer-values")
        exposures = _parse_floats(args.exposure_values, "--exposure-values")
    except ValueError as exc:
        parser.error(str(exc))
    if args.seed < 0 or args.seeds < 1 or args.workers < 1:
        parser.error("--seed must be nonnegative; --seeds and --workers must be positive")
    if not args.model.is_file():
        parser.error(f"model does not exist: {args.model}")
    if not EVALUATOR.is_file() or not WRAPPER.is_file() or not NET_STOCK.is_file():
        parser.error("expected evaluator and wrapper sources are missing")
    if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        parser.error("use a new output directory; sweep results are immutable")

    settings = [
        {
            "id": _setting_id(buffer, exposure),
            "OMW_NET_SN_BUFFER": buffer,
            "OMW_NET_SN_EXPOSURE": exposure,
        }
        for buffer in buffers
        for exposure in exposures
    ]
    games_per_setting = len(POLICIES) * len(OPPONENTS) * args.seeds * 2
    expected_games = len(settings) * games_per_setting
    model_path = args.model.resolve()
    model_sha256 = _sha256(model_path)
    source_fingerprints = {
        str(path.resolve()): _sha256(path)
        for path in (Path(__file__), EVALUATOR, WRAPPER, NET_STOCK, model_path)
    }
    manifest: dict[str, Any] = {
        "schema": 1,
        "status": "running",
        "sweep": "event_cnn_ppo_v1_hard_gate",
        "description": (
            "Paired learned-vs-fixed games over OMW/Peak/Triad with the frozen "
            "Event-CNN-PPO v1 model and a 3x3 hard-gate grid."
        ),
        "model": {
            "path": str(model_path),
            "sha256_before": model_sha256,
            "read_only": True,
        },
        "evaluator": str(EVALUATOR.resolve()),
        "wrapper": str(WRAPPER.resolve()),
        "gate_environment": {
            "buffer": "OMW_NET_SN_BUFFER",
            "exposure": "OMW_NET_SN_EXPOSURE",
            "injection": (
                "Each grid point invokes the evaluator in a fresh subprocess; "
                "the evaluator sets these values before spawning its workers."
            ),
        },
        "buffers": list(buffers),
        "exposures": list(exposures),
        "settings": settings,
        "seed_start": args.seed,
        "seed_count": args.seeds,
        "seeds": list(range(args.seed, args.seed + args.seeds)),
        "seats": [0, 1],
        "opponents": list(OPPONENTS),
        "policies": list(POLICIES),
        "games_per_setting": games_per_setting,
        "expected_games": expected_games,
        "workers": args.workers,
        "source_fingerprints": source_fingerprints,
        "commands": [],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    settings_root = args.output / "settings"
    settings_root.mkdir()
    _write_json(args.output / "manifest.json", manifest)

    all_games: list[dict[str, Any]] = []
    setting_summaries: list[dict[str, Any]] = []
    for setting in settings:
        setting_id = setting["id"]
        setting_output = settings_root / setting_id
        buffer = setting["OMW_NET_SN_BUFFER"]
        exposure = setting["OMW_NET_SN_EXPOSURE"]
        command = [
            sys.executable,
            str(EVALUATOR),
            "--model",
            str(model_path),
            "--output",
            str(setting_output),
            "--seed",
            str(args.seed),
            "--seeds",
            str(args.seeds),
            "--workers",
            str(args.workers),
            "--policies",
            ",".join(POLICIES),
            "--opponents",
            ",".join(OPPONENTS),
            "--net-sn-buffer",
            str(buffer),
            "--net-sn-exposure",
            format(exposure, ".15g"),
        ]
        manifest["commands"].append(
            {
                "setting": setting_id,
                "argv": command,
                "shell": shlex.join(command),
            }
        )
        child_env = os.environ.copy()
        source_path = os.pathsep.join(
            part
            for part in (str(ROOT / "src"), str(ROOT), child_env.get("PYTHONPATH", ""))
            if part
        )
        child_env["PYTHONPATH"] = source_path
        child_env["OMW_NET_SN_BUFFER"] = str(buffer)
        child_env["OMW_NET_SN_EXPOSURE"] = format(exposure, ".15g")
        print(f"[{setting_id}] {shlex.join(command)}", flush=True)
        completed = subprocess.run(command, cwd=ROOT, env=child_env, check=False)
        if completed.returncode != 0:
            manifest["status"] = "failed"
            _write_json(args.output / "manifest.json", manifest)
            raise RuntimeError(f"setting {setting_id} failed with exit code {completed.returncode}")

        child_manifest = json.loads((setting_output / "manifest.json").read_text())
        child_results = json.loads((setting_output / "results.json").read_text())
        child_summary = json.loads((setting_output / "summary.json").read_text())
        games = child_results["games"]
        if child_summary["status"] != "completed" or child_summary["errors"]:
            raise RuntimeError(f"setting {setting_id} has failed games")
        if len(games) != games_per_setting or any(
            row["status"] != "completed" or bool(row["error"]) for row in games
        ):
            raise RuntimeError(f"setting {setting_id} does not have {games_per_setting} clean games")
        expected_gate = {
            key: value for key, value in setting.items() if key.startswith("OMW_")
        }
        if child_manifest["gate_parameters"] != expected_gate:
            raise RuntimeError(f"setting {setting_id} has mismatched gate metadata")
        if _sha256(model_path) != model_sha256:
            raise RuntimeError("learned model changed during sweep")

        for game in games:
            all_games.append(
                {
                    "setting": setting_id,
                    "OMW_NET_SN_BUFFER": buffer,
                    "OMW_NET_SN_EXPOSURE": exposure,
                    **game,
                }
            )
        setting_summaries.append(
            {
                "setting": setting_id,
                "OMW_NET_SN_BUFFER": buffer,
                "OMW_NET_SN_EXPOSURE": exposure,
                "games": len(games),
                "errors": child_summary["errors"],
                "status": child_summary["status"],
                "policies": child_summary["policies"],
                "paired_vs_fixed": child_summary["paired_vs_fixed"],
                "metrics": _metrics(child_summary),
            }
        )

    model_sha256_after = _sha256(model_path)
    if model_sha256_after != model_sha256:
        raise RuntimeError("learned model changed during sweep")
    manifest["status"] = "completed"
    manifest["completed_games"] = len(all_games)
    manifest["model"]["sha256_after"] = model_sha256_after
    manifest["model"]["unchanged"] = True
    summary_settings = sorted(setting_summaries, key=lambda item: item["setting"])
    best = max(summary_settings, key=_best_key)
    summary = {
        "schema": 1,
        "status": "completed",
        "errors": sum(int(item["errors"]) for item in summary_settings),
        "expected_games": expected_games,
        "completed_games": len(all_games),
        "settings": summary_settings,
        "best_setting": {
            "setting": best["setting"],
            "OMW_NET_SN_BUFFER": best["OMW_NET_SN_BUFFER"],
            "OMW_NET_SN_EXPOSURE": best["OMW_NET_SN_EXPOSURE"],
            "criterion": "learned aggregate score, then mean margin, with zero errors preferred",
            "learned_aggregate": best["policies"]["learned"]["aggregate"],
        },
    }
    manifest["summary_file"] = str((args.output / "summary.json").resolve())
    manifest["results_file"] = str((args.output / "results.json").resolve())
    _write_json(args.output / "manifest.json", manifest)
    _write_json(args.output / "results.json", {"manifest": manifest, "games": all_games})
    _write_json(args.output / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
