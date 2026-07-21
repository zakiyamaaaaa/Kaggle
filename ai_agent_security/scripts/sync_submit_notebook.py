#!/usr/bin/env python3
"""Embed experiments/runs/<exp>/attack.py into submit and kaggle-push notebooks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "experiments" / "runs"
KAGGLE_PUSH_DIR = ROOT / "kaggle-push"


def _escape_attack_code(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")


def _build_notebook(exp_slug: str, attack_code: str) -> dict:
    escaped = _escape_attack_code(attack_code)
    return {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    f"# {exp_slug}\n",
                    "\n",
                    "Timeout-safe direct replay bank (no Go-Explore).\n",
                    "\n",
                    f"Version description: `{exp_slug}`\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "import sys, glob\n",
                    "from pathlib import Path\n",
                    "\n",
                    "sys.argv = [sys.argv[0]]\n",
                    "\n",
                    "for candidate in glob.glob(\"/kaggle/input/**/kaggle_evaluation\", recursive=True):\n",
                    "    dataset_root = str(Path(candidate).parent)\n",
                    "    if dataset_root not in sys.path:\n",
                    "        sys.path.insert(0, dataset_root)\n",
                    "    print(f\"Dataset root: {dataset_root}\")\n",
                    "    break\n",
                    "\n",
                    "print(\"Setup complete\")\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "from pathlib import Path\n",
                    "\n",
                    f"attack_code = '{escaped}'\n",
                    "Path(\"/kaggle/working/attack.py\").write_text(attack_code, encoding=\"utf-8\")\n",
                    "print(\"attack.py written\")\n",
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "import csv\n",
                    "from pathlib import Path\n",
                    "import kaggle_evaluation.jed_attack_134815.jed_attack_inference_server as server\n",
                    "\n",
                    "server.JEDAttackInferenceServer().serve()\n",
                    "\n",
                    "submission_path = Path(\"/kaggle/working/submission.csv\")\n",
                    "if not submission_path.exists():\n",
                    "    with submission_path.open(\"w\", newline=\"\") as f:\n",
                    "        writer = csv.writer(f)\n",
                    "        writer.writerow([\"Id\", \"Score\"])\n",
                    "        for row_id in (\n",
                    "            \"gpt_oss_public\",\n",
                    "            \"gpt_oss_private\",\n",
                    "            \"gemma_public\",\n",
                    "            \"gemma_private\",\n",
                    "        ):\n",
                    "            writer.writerow([row_id, 0.0])\n",
                    "print(\"submission.csv present:\", submission_path.exists())\n",
                ],
            },
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.11.0",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _write_notebook(path: Path, notebook: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notebook, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sync_notebooks(exp_dir_name: str) -> dict[str, Path]:
    run_dir = RUNS_DIR / exp_dir_name
    attack_path = run_dir / "attack.py"
    if not attack_path.exists():
        raise FileNotFoundError(f"Missing attack.py: {attack_path}")

    match = re.match(r"(exp-\d+)", exp_dir_name)
    if not match:
        raise ValueError(f"Expected exp-<NNN>-* directory name, got: {exp_dir_name!r}")
    exp_num = match.group(1)
    attack_code = attack_path.read_text(encoding="utf-8")
    notebook = _build_notebook(exp_dir_name, attack_code)

    submit_path = run_dir / "submit.ipynb"
    push_dir = KAGGLE_PUSH_DIR / exp_num
    push_path = push_dir / f"{exp_dir_name}.ipynb"

    _write_notebook(submit_path, notebook)
    _write_notebook(push_path, notebook)
    return {"submit": submit_path, "kaggle_push": push_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "exp_dir_name",
        help="Experiment directory name under experiments/runs/, e.g. exp-020-timeout-safe-replay",
    )
    args = parser.parse_args(argv)

    try:
        paths = sync_notebooks(args.exp_dir_name)
    except FileNotFoundError as exc:
        print(f"sync_submit_notebook.py: {exc}", file=sys.stderr)
        return 1

    for label, path in paths.items():
        print(f"{label}: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
