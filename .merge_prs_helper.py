#!/usr/bin/env python3
"""Resolve registry.csv merge conflicts by unioning rows on exp_id."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def parse_registry_lines(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith("exp_id,"):
            continue
        if line.startswith("<<<<<<<") or line.startswith("=======") or line.startswith(">>>>>>>"):
            continue
        exp_id = line.split(",", 1)[0].strip()
        if exp_id:
            rows[exp_id] = line.rstrip("\n")
    return rows


def exp_sort_key(exp_id: str) -> tuple[int, str]:
    match = re.match(r"exp-(\d+)-(.*)", exp_id)
    if match:
        return int(match.group(1)), match.group(2)
    return 9999, exp_id


def resolve_registry(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "<<<<<<<" not in text:
        return
    ours, theirs = text.split("<<<<<<< HEAD", 1)[1].split("=======", 1)
    theirs = theirs.split(">>>>>>>", 1)[0]
    merged = parse_registry_lines(ours)
    merged.update(parse_registry_lines(theirs))
    lines = ["exp_id,name,created_at,kaggle_tag,notes,attack_path,git_commit,attack_sha256"]
    for exp_id in sorted(merged, key=exp_sort_key):
        lines.append(merged[exp_id])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_json_conflict(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "<<<<<<<" not in text:
        return
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("<<<<<<<"):
            i += 1
            while i < len(lines) and not lines[i].startswith("======="):
                out.append(lines[i])
                i += 1
            while i < len(lines) and not lines[i].startswith(">>>>>>>"):
                i += 1
            if i < len(lines):
                i += 1
            continue
        if line.startswith("=======") or line.startswith(">>>>>>>"):
            i += 1
            continue
        out.append(line)
        i += 1
    resolved = "\n".join(out).strip()
    if not resolved.endswith("}"):
        raise ValueError(f"Could not resolve JSON conflict in {path}")
    path.write_text(resolved + "\n", encoding="utf-8")


def main() -> int:
    root = Path(sys.argv[1])
    resolve_registry(root / "ai_agent_security/experiments/registry.csv")
    metadata = root / "ai_agent_security/kaggle-push/exp-008/kernel-metadata.json"
    if metadata.exists():
        resolve_json_conflict(metadata)
    for metadata_path in root.glob("ai_agent_security/kaggle-push/exp-*/kernel-metadata.json"):
        resolve_json_conflict(metadata_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
