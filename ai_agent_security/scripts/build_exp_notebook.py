#!/usr/bin/env python3
"""Build Kaggle submit notebook from an experiment attack.py."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_notebook(exp_id: str, description: str, attack_code: str) -> dict:
    attack_literal = repr(attack_code)
    return {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    f"# {exp_id}\n",
                    "\n",
                    f"{description}\n",
                    "\n",
                    f"Version description: `{exp_id}`\n",
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
                    'for candidate in glob.glob("/kaggle/input/**/kaggle_evaluation", recursive=True):\n',
                    "    dataset_root = str(Path(candidate).parent)\n",
                    "    if dataset_root not in sys.path:\n",
                    "        sys.path.insert(0, dataset_root)\n",
                    '    print(f"Dataset root: {dataset_root}")\n',
                    "    break\n",
                    "\n",
                    'print("Setup complete")\n',
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    f"attack_code = {attack_literal}\n",
                    'Path("/kaggle/working/attack.py").write_text(attack_code, encoding="utf-8")\n',
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
                    'submission_path = Path("/kaggle/working/submission.csv")\n',
                    "if not submission_path.exists():\n",
                    '    with submission_path.open("w", newline="") as f:\n',
                    "        writer = csv.writer(f)\n",
                    '        writer.writerow(["Id", "Score"])\n',
                    "        for row_id in (\n",
                    '            "gpt_oss_public",\n',
                    '            "gpt_oss_private",\n',
                    '            "gemma_public",\n',
                    '            "gemma_private",\n',
                    "        ):\n",
                    "            writer.writerow([row_id, 0.0])\n",
                    'print("submission.csv present:", submission_path.exists())\n',
                ],
            },
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def verify_notebook(notebook_path: Path, attack_code: str) -> None:
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    cell_lines = notebook["cells"][2]["source"]
    assignment = cell_lines[0]
    namespace: dict[str, str] = {}
    exec(compile(assignment, str(notebook_path), "exec"), namespace)
    if namespace["attack_code"] != attack_code:
        raise SystemExit(f"Notebook attack_code mismatch for {notebook_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("exp_id", help="e.g. exp-021-output-spec-bank")
    parser.add_argument("--exp-num", default=None, help="e.g. exp-021")
    parser.add_argument(
        "--description",
        default="Output-spec replay bank with compact Go-Explore fallback.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    attack_path = root / "experiments" / "runs" / args.exp_id / "attack.py"
    attack_code = attack_path.read_text(encoding="utf-8")
    exp_num = args.exp_num or "-".join(args.exp_id.split("-")[:2])

    notebook = build_notebook(args.exp_id, args.description, attack_code)
    outputs = [
        root / "kaggle-push" / exp_num / f"{args.exp_id}.ipynb",
        root / "experiments" / "runs" / args.exp_id / "submit.ipynb",
    ]
    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        verify_notebook(output, attack_code)
        print(f"wrote {output.relative_to(root)} (sync ok)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
