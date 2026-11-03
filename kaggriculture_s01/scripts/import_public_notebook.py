#!/usr/bin/env python3
"""Extract a named %%writefile cell from a downloaded public Kaggle notebook."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def cell_source(cell: dict) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("notebook", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--filename", default="main.py")
    parser.add_argument("--source-url", required=True)
    args = parser.parse_args()

    notebook_bytes = args.notebook.read_bytes()
    notebook = json.loads(notebook_bytes)
    prefix = f"%%writefile {args.filename}"
    matches = []
    for cell in notebook.get("cells", []):
        source = cell_source(cell)
        first, separator, body = source.partition("\n")
        if first.strip() == prefix:
            if not separator:
                raise ValueError(f"Empty {prefix} cell")
            matches.append(body)
    if len(matches) != 1:
        raise ValueError(f"Expected one {prefix} cell, found {len(matches)}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / args.filename
    output_path.write_text(matches[0], encoding="utf-8")
    source_sha = hashlib.sha256(notebook_bytes).hexdigest()
    output_sha = hashlib.sha256(matches[0].encode()).hexdigest()
    provenance = (
        "# Public notebook provenance\n\n"
        f"- Source: {args.source_url}\n"
        f"- Downloaded notebook SHA-256: `{source_sha}`\n"
        f"- Extracted `{args.filename}` SHA-256: `{output_sha}`\n"
        "- Import method: exact extraction of the notebook's `%%writefile` cell; "
        "no source transformation.\n"
    )
    (args.output_dir / "SOURCE.md").write_text(provenance, encoding="utf-8")
    print(f"Extracted {output_path} ({output_sha})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
