#!/usr/bin/env python3
"""Detect whether a push changed exactly one Kaggle submission bundle."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[2]
KAGGLE_PUSH_PARTS = ("ai_agent_security", "kaggle-push")
SUBMISSION_FILENAMES = {"kernel-metadata.json"}
SUBMISSION_SUFFIXES = {".ipynb", ".py", ".R", ".Rmd", ".sql", ".jl"}
ZERO_SHA = "0" * 40


def _run_git(args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _event_payload() -> dict:
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        return {}
    path = Path(event_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _default_base_head() -> tuple[str | None, str]:
    payload = _event_payload()
    head = (
        os.getenv("GITHUB_SHA")
        or payload.get("after")
        or _run_git(["rev-parse", "HEAD"])[0]
    )
    base = os.getenv("GITHUB_BEFORE") or payload.get("before")
    if base == ZERO_SHA:
        base = None
    return base, head


def _changed_files(base: str | None, head: str) -> list[str]:
    if base:
        try:
            return _run_git(["diff", "--name-only", base, head, "--"])
        except subprocess.CalledProcessError:
            print(
                f"Could not diff {base}..{head}; falling back to the head commit.",
                file=sys.stderr,
            )
    return _run_git(["diff-tree", "--no-commit-id", "--name-only", "-r", head])


def _submission_dir_for_path(path_text: str) -> str | None:
    path = Path(path_text)
    parts = path.parts
    if len(parts) != 4:
        return None
    if parts[:2] != KAGGLE_PUSH_PARTS:
        return None
    filename = parts[3]
    if filename in SUBMISSION_FILENAMES or Path(filename).suffix in SUBMISSION_SUFFIXES:
        return str(Path(*parts[:3]))
    return None


def _bundle_from_exp_id(exp_id: str) -> str:
    clean_exp_id = exp_id.strip().strip("/")
    if not clean_exp_id:
        raise ValueError("exp_id must not be empty")
    if "/" in clean_exp_id:
        raise ValueError("exp_id must be a single kaggle-push directory name")
    return str(Path("ai_agent_security", "kaggle-push", clean_exp_id))


def _write_github_outputs(values: dict[str, str]) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as f:
        for key, value in values.items():
            if "\n" in value:
                marker = f"{key}_EOF"
                f.write(f"{key}<<{marker}\n{value}\n{marker}\n")
            else:
                f.write(f"{key}={value}\n")


def detect(args: argparse.Namespace) -> dict[str, str]:
    if args.exp_id:
        submit_dir = _bundle_from_exp_id(args.exp_id)
        changed_files: list[str] = []
    else:
        base, head = args.base, args.head
        if not head:
            default_base, default_head = _default_base_head()
            base = base or default_base
            head = default_head
        changed_files = _changed_files(base, head)
        submit_dirs = sorted(
            {
                submit_dir
                for path in changed_files
                if (submit_dir := _submission_dir_for_path(path))
            }
        )
        if len(submit_dirs) > 1:
            joined = "\n".join(f"- {path}" for path in submit_dirs)
            raise RuntimeError(
                "Multiple Kaggle submission bundles changed in one push.\n"
                "Submit one experiment per push, or run the workflow manually with exp_id.\n"
                f"{joined}"
            )
        submit_dir = submit_dirs[0] if submit_dirs else ""

    exp_id = Path(submit_dir).name if submit_dir else ""
    values = {
        "should_submit": "true" if submit_dir else "false",
        "submit_dir": submit_dir,
        "exp_id": exp_id,
        "changed_files": "\n".join(changed_files),
    }
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect changed ai_agent_security/kaggle-push/<exp>/ bundles."
    )
    parser.add_argument("--base", help="Base git SHA for change detection.")
    parser.add_argument("--head", help="Head git SHA for change detection.")
    parser.add_argument(
        "--exp-id",
        help="Force a specific ai_agent_security/kaggle-push/<exp-id> bundle.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    values = detect(args)
    _write_github_outputs(values)

    print(f"should_submit={values['should_submit']}")
    if values["submit_dir"]:
        print(f"submit_dir={values['submit_dir']}")
        print(f"exp_id={values['exp_id']}")
    elif values["changed_files"]:
        print("No Kaggle submission bundle changes detected.")
    else:
        print("No changed files detected.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"detect_submission_changes.py: {exc}", file=sys.stderr)
        raise SystemExit(1)
