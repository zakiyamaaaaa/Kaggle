#!/usr/bin/env python3
"""Build a deterministic standalone archive for the independent worker policy."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "kaggriculture_agent" / "independent_agent.py"
DEFAULT_OUTPUT = ROOT / "submissions" / "independent-workers-v1.zip"


def build(output: Path) -> tuple[str, str]:
    source = SOURCE.read_text(encoding="utf-8")
    standalone = (source + "\n# Kaggle submission entry point.\nagent = agent_workers\n").encode()
    source_sha = hashlib.sha256(standalone).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    member = zipfile.ZipInfo("main.py", date_time=(2026, 9, 19, 0, 0, 0))
    member.compress_type = zipfile.ZIP_DEFLATED
    member.external_attr = 0o644 << 16
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(member, standalone)
    return source_sha, hashlib.sha256(output.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source_sha, zip_sha = build(args.output)
    print(f"output={args.output.resolve()}")
    print(f"source_sha256={source_sha}")
    print(f"zip_sha256={zip_sha}")


if __name__ == "__main__":
    main()
