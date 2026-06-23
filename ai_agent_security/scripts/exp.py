#!/usr/bin/env python3
"""Experiment tracker: link local attack.py versions to Kaggle leaderboard scores."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = ROOT / "experiments"
RUNS_DIR = EXPERIMENTS_DIR / "runs"
REGISTRY_PATH = EXPERIMENTS_DIR / "registry.csv"
RESULTS_PATH = EXPERIMENTS_DIR / "results.csv"
COMPETITION = "ai-agent-security-multi-step-tool-attacks"

REGISTRY_FIELDS = [
    "exp_id",
    "name",
    "created_at",
    "kaggle_tag",
    "notes",
    "attack_path",
    "git_commit",
    "attack_sha256",
]

RESULTS_FIELDS = [
    "exp_id",
    "submission_ref",
    "submitted_at",
    "description",
    "status",
    "public_score",
    "private_score",
    "file_name",
    "matched_by",
]


def _read_csv(path: Path, fields: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _next_exp_id(registry: list[dict[str, str]]) -> str:
    numbers = []
    for row in registry:
        match = re.fullmatch(r"exp-(\d+)-.*", row["exp_id"])
        if match:
            numbers.append(int(match.group(1)))
    n = max(numbers, default=0) + 1
    return f"exp-{n:03d}"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "experiment"


def cmd_new(args: argparse.Namespace) -> int:
    registry = _read_csv(REGISTRY_PATH, REGISTRY_FIELDS)
    exp_num = _next_exp_id(registry)
    slug = _slugify(args.name)
    exp_id = f"{exp_num}-{slug}"
    kaggle_tag = args.kaggle_tag or exp_id

    run_dir = RUNS_DIR / exp_id
    run_dir.mkdir(parents=True, exist_ok=False)
    attack_path = run_dir / "attack.py"

    source = Path(args.from_file) if args.from_file else ROOT / "attack.py"
    if source.exists():
        attack_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        attack_path.write_text(
            "from aicomp_sdk.attacks import AttackAlgorithmBase, AttackCandidate, AttackRunConfig\n\n\n"
            "class AttackAlgorithm(AttackAlgorithmBase):\n"
            "    def run(self, env, config: AttackRunConfig) -> list[AttackCandidate]:\n"
            "        return []\n",
            encoding="utf-8",
        )

    notes_path = run_dir / "notes.md"
    notes_path.write_text(
        f"# {exp_id}\n\n"
        f"- Name: {args.name}\n"
        f"- Kaggle tag: `{kaggle_tag}`\n\n"
        f"## Hypothesis\n\n{args.notes or '(write here)'}\n",
        encoding="utf-8",
    )

    row = {
        "exp_id": exp_id,
        "name": args.name,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kaggle_tag": kaggle_tag,
        "notes": args.notes or "",
        "attack_path": str(attack_path.relative_to(ROOT)),
        "git_commit": _git_commit(),
        "attack_sha256": _file_sha256(attack_path),
    }
    registry.append(row)
    _write_csv(REGISTRY_PATH, REGISTRY_FIELDS, registry)

    print(f"Created {exp_id}")
    print(f"  attack: {attack_path.relative_to(ROOT)}")
    print(f"  notes:  {notes_path.relative_to(ROOT)}")
    print()
    print("Next steps:")
    print("  1. Edit attack.py")
    print("  2. Copy into your Kaggle notebook and submit")
    print(f"  3. Set Kaggle version description to include: {kaggle_tag}")
    print("  4. Run: uv run python scripts/exp.py sync")
    return 0


def _fetch_submissions() -> list[dict[str, str]]:
    cmd = [
        "kaggle",
        "competitions",
        "submissions",
        "-c",
        COMPETITION,
        "-v",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    reader = csv.DictReader(result.stdout.splitlines())
    rows = []
    for row in reader:
        rows.append(
            {
                "submission_ref": row.get("ref", "").strip(),
                "submitted_at": row.get("date", "").strip(),
                "description": row.get("description", "").strip(),
                "status": row.get("status", "").strip(),
                "public_score": row.get("publicScore", "").strip(),
                "private_score": row.get("privateScore", "").strip(),
                "file_name": row.get("fileName", "").strip(),
            }
        )
    return rows


def _match_exp_id(description: str, registry: list[dict[str, str]]) -> tuple[str, str]:
    lowered = description.lower()
    tagged = [
        row for row in registry if row["kaggle_tag"].lower() in lowered
    ]
    if len(tagged) == 1:
        return tagged[0]["exp_id"], "kaggle_tag"
    if len(tagged) > 1:
        tagged.sort(key=lambda row: len(row["kaggle_tag"]), reverse=True)
        return tagged[0]["exp_id"], "kaggle_tag"

    for row in registry:
        if row["exp_id"].lower() in lowered:
            return row["exp_id"], "exp_id"
    return "", ""


def cmd_sync(_: argparse.Namespace) -> int:
    registry = _read_csv(REGISTRY_PATH, REGISTRY_FIELDS)
    submissions = _fetch_submissions()

    results: list[dict[str, str]] = []
    for submission in submissions:
        exp_id, matched_by = _match_exp_id(submission["description"], registry)
        results.append(
            {
                "exp_id": exp_id,
                "submission_ref": submission["submission_ref"],
                "submitted_at": submission["submitted_at"],
                "description": submission["description"],
                "status": submission["status"],
                "public_score": submission["public_score"],
                "private_score": submission["private_score"],
                "file_name": submission["file_name"],
                "matched_by": matched_by,
            }
        )

    _write_csv(RESULTS_PATH, RESULTS_FIELDS, results)

    matched = sum(1 for row in results if row["exp_id"])
    print(f"Synced {len(results)} submission(s) -> {RESULTS_PATH.relative_to(ROOT)}")
    print(f"Matched to local experiments: {matched}/{len(results)}")
    if matched < len(results):
        print("Tip: include exp_id (e.g. exp-002-foo) in the Kaggle version description.")
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    registry = _read_csv(REGISTRY_PATH, REGISTRY_FIELDS)
    results = _read_csv(RESULTS_PATH, RESULTS_FIELDS)

    best_by_exp: dict[str, dict[str, str]] = {}
    for row in results:
        exp_id = row["exp_id"]
        if not exp_id:
            continue
        score_text = row["public_score"] or row["private_score"]
        if not score_text:
            continue
        score = float(score_text)
        current = best_by_exp.get(exp_id)
        if current is None or score > float(current["score"]):
            best_by_exp[exp_id] = {"score": score_text, "submitted_at": row["submitted_at"]}

    if not registry:
        print("No experiments yet. Run: uv run python scripts/exp.py new --name baseline")
        return 0

    print(f"{'exp_id':<24} {'best_score':>10}  name")
    print("-" * 60)
    for row in registry:
        best = best_by_exp.get(row["exp_id"])
        score = best["score"] if best else "-"
        print(f"{row['exp_id']:<24} {score:>10}  {row['name']}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    registry = _read_csv(REGISTRY_PATH, REGISTRY_FIELDS)
    results = _read_csv(RESULTS_PATH, RESULTS_FIELDS)
    row = next((r for r in registry if r["exp_id"] == args.exp_id), None)
    if row is None:
        print(f"Unknown experiment: {args.exp_id}", file=sys.stderr)
        return 1

    print(json.dumps(row, indent=2, ensure_ascii=False))
    exp_results = [r for r in results if r["exp_id"] == args.exp_id]
    if exp_results:
        print("\nSubmissions:")
        for result in exp_results:
            print(
                f"  {result['submitted_at']}  score={result['public_score'] or '-'}  "
                f"{result['description']}"
            )
    else:
        print("\nNo synced submissions yet.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Track Kaggle experiments and leaderboard scores.")
    sub = parser.add_subparsers(dest="command", required=True)

    new_parser = sub.add_parser("new", help="Create a new experiment folder and registry entry.")
    new_parser.add_argument("--name", required=True, help="Short experiment name.")
    new_parser.add_argument("--notes", default="", help="Hypothesis or change summary.")
    new_parser.add_argument(
        "--from-file",
        help="Copy attack.py from this path (default: ./attack.py if present).",
    )
    new_parser.add_argument(
        "--kaggle-tag",
        help="String to put in Kaggle submission description for auto-matching.",
    )
    new_parser.set_defaults(func=cmd_new)

    sync_parser = sub.add_parser("sync", help="Pull Kaggle submissions and update results.csv.")
    sync_parser.set_defaults(func=cmd_sync)

    list_parser = sub.add_parser("list", help="List experiments and best synced scores.")
    list_parser.set_defaults(func=cmd_list)

    show_parser = sub.add_parser("show", help="Show one experiment and its submissions.")
    show_parser.add_argument("exp_id")
    show_parser.set_defaults(func=cmd_show)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
