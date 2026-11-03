#!/usr/bin/env python3
"""Build the OMW + funding-order-invariant candidate archive."""

from __future__ import annotations

import hashlib
import json
import runpy
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments/omw-funding-order-invariant-v1/main.py"
BASE = ROOT / "references/kaggle-scan-2026-09-21/extracted/one-more-wheat/main.py"
OUT_DIR = ROOT / "submissions/omw-funding-order-invariant-v1"
OUT_MAIN = OUT_DIR / "main.py"
OUT_TAR = ROOT / "submissions/omw-funding-order-invariant-v1.tar.gz"
OUT_MANIFEST = ROOT / "submissions/omw-funding-order-invariant-v1.manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    namespace = runpy.run_path(str(EXPERIMENT))
    source = namespace["_source"]
    compile(source, str(OUT_MAIN), "exec")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_MAIN.write_text(source)
    with tarfile.open(OUT_TAR, "w:gz") as archive:
        archive.add(OUT_MAIN, arcname="main.py")
    with tarfile.open(OUT_TAR) as archive:
        if archive.getnames() != ["main.py"]:
            raise RuntimeError("archive must contain exactly main.py")
        if archive.extractfile("main.py").read() != source.encode():
            raise RuntimeError("archive main.py does not match generated source")
    manifest = {
        "competition": "kaggriculture",
        "policy": "omw_funding_order_invariant_v1",
        "parent": "one_more_wheat_public_exact",
        "parameters": {"min_step": namespace["MIN_STEP"]},
        "parent_main_sha256": sha256(BASE),
        "main_sha256": sha256(OUT_MAIN),
        "archive_sha256": sha256(OUT_TAR),
        "archive_members": ["main.py"],
        "local_source": str(EXPERIMENT.relative_to(ROOT)),
        "status": "built_not_submitted",
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

