#!/usr/bin/env python3
"""Safely extract main.py from a literal embedded tar archive in a notebook cell."""

from __future__ import annotations

import argparse
import ast
import base64
import gzip
import io
import json
import tarfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--variable", default="ARCHIVE_BYTES")
    args = parser.parse_args()
    notebook = json.loads(args.notebook.read_text())
    encoded = None
    for cell in notebook.get("cells", []):
        source = "".join(cell.get("source", []))
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == args.variable for target in node.targets):
                continue
            value = node.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and isinstance(value.func.value, ast.Name)
                and value.func.value.id == "base64"
                and value.func.attr == "b64decode"
                and len(value.args) == 1
                and isinstance(value.args[0], ast.Constant)
                and isinstance(value.args[0].value, (str, bytes))
            ):
                encoded = value.args[0].value
    if encoded is None:
        raise SystemExit(f"literal {args.variable}=base64.b64decode(...) not found")
    archive_bytes = base64.b64decode(encoded)
    if archive_bytes[:2] == b"\x1f\x8b":
        archive_bytes = gzip.decompress(archive_bytes)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        members = archive.getmembers()
        allowed = {"main.py", "LICENSE.txt", "NOTICE.txt"}
        if (
            any(member.name not in allowed or not member.isfile() for member in members)
            or sum(member.name == "main.py" for member in members) != 1
        ):
            raise SystemExit("archive may contain only regular main.py/LICENSE.txt/NOTICE.txt files")
        main_member = next(member for member in members if member.name == "main.py")
        source = archive.extractfile(main_member).read()
        ancillary = {
            member.name: archive.extractfile(member).read()
            for member in members
            if member.name in {"LICENSE.txt", "NOTICE.txt"}
        }
    compile(source, "main.py", "exec")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "main.py").write_bytes(source)
    for name, content in ancillary.items():
        (args.output / name).write_bytes(content)
    print(f"extracted {len(source)} bytes to {args.output / 'main.py'}")


if __name__ == "__main__":
    main()
