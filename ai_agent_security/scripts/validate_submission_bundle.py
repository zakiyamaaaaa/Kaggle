#!/usr/bin/env python3
"""Validate a local Kaggle kernel bundle before pushing it from CI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

COMPETITION = "ai-agent-security-multi-step-tool-attacks"
REQUIRED_METADATA_FIELDS = {
    "id",
    "title",
    "code_file",
    "language",
    "kernel_type",
    "is_private",
    "competition_sources",
}
NOTEBOOK_SUFFIXES = {".ipynb"}
SCRIPT_SUFFIXES = {".py", ".R", ".Rmd", ".sql", ".jl"}


class BundleValidationError(ValueError):
    """Raised when a Kaggle kernel bundle is not safe to submit."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BundleValidationError(f"{path} is not valid JSON: {exc}") from exc


def _resolve_bundle_dir(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def validate_bundle(bundle_dir: Path, competition: str = COMPETITION) -> dict[str, Any]:
    if not bundle_dir.exists():
        raise BundleValidationError(f"Bundle directory does not exist: {bundle_dir}")
    if not bundle_dir.is_dir():
        raise BundleValidationError(f"Bundle path is not a directory: {bundle_dir}")

    metadata_path = bundle_dir / "kernel-metadata.json"
    if not metadata_path.exists():
        raise BundleValidationError(f"Missing kernel-metadata.json in {bundle_dir}")

    metadata = _load_json(metadata_path)
    if not isinstance(metadata, dict):
        raise BundleValidationError("kernel-metadata.json must contain a JSON object")

    missing = sorted(REQUIRED_METADATA_FIELDS - metadata.keys())
    if missing:
        raise BundleValidationError(
            "kernel-metadata.json is missing required fields: " + ", ".join(missing)
        )

    kernel_id = str(metadata["id"]).strip()
    if len(kernel_id.split("/")) != 2 or any(not part for part in kernel_id.split("/")):
        raise BundleValidationError("metadata.id must be in owner/kernel-slug format")

    code_file = Path(str(metadata["code_file"]).strip())
    if not code_file.name or code_file.is_absolute() or len(code_file.parts) != 1:
        raise BundleValidationError("metadata.code_file must be a direct child filename")

    code_path = bundle_dir / code_file
    if not code_path.exists():
        raise BundleValidationError(f"metadata.code_file does not exist: {code_path}")
    if code_path.suffix not in NOTEBOOK_SUFFIXES | SCRIPT_SUFFIXES:
        raise BundleValidationError(f"Unsupported code file extension: {code_path.name}")

    competition_sources = metadata.get("competition_sources")
    if not isinstance(competition_sources, list):
        raise BundleValidationError("metadata.competition_sources must be a list")
    if competition not in competition_sources:
        raise BundleValidationError(
            f"metadata.competition_sources must include {competition!r}"
        )

    kernel_type = str(metadata["kernel_type"]).lower()
    if code_path.suffix in NOTEBOOK_SUFFIXES and kernel_type != "notebook":
        raise BundleValidationError("Notebook code_file requires kernel_type='notebook'")
    if code_path.suffix in SCRIPT_SUFFIXES and kernel_type != "script":
        raise BundleValidationError("Script code_file requires kernel_type='script'")

    if code_path.suffix == ".ipynb":
        notebook = _load_json(code_path)
        if not isinstance(notebook, dict):
            raise BundleValidationError(f"{code_path.name} must contain a JSON object")
        if "cells" not in notebook or "nbformat" not in notebook:
            raise BundleValidationError(f"{code_path.name} is missing notebook fields")
        if not isinstance(notebook["cells"], list) or not notebook["cells"]:
            raise BundleValidationError(f"{code_path.name} must contain at least one cell")

    return {
        "bundle_dir": str(bundle_dir),
        "kernel_id": kernel_id,
        "code_file": code_path.name,
        "competition": competition,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a Kaggle kernel bundle.")
    parser.add_argument("bundle_dir", help="Path to ai_agent_security/kaggle-push/<exp>.")
    parser.add_argument("--competition", default=COMPETITION)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    bundle_dir = _resolve_bundle_dir(args.bundle_dir)
    result = validate_bundle(bundle_dir, args.competition)
    print(
        "Validated Kaggle bundle: "
        f"{result['kernel_id']} ({result['code_file']}) -> {result['competition']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BundleValidationError as exc:
        print(f"validate_submission_bundle.py: {exc}")
        raise SystemExit(1)
