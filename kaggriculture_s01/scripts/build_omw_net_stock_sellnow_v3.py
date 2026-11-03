#!/usr/bin/env python3
"""Build the isolated OMW net-stock sell-now A/B/C candidates.

Each output archive contains only a generated main.py. The experiment
modules remain read-only wrappers around the frozen parent and v2 source; this
builder inlines their _source before packaging so the result stays stdlib-only
and does not import workspace files at Kaggle runtime.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "references/kaggle-scan-2026-09-21/extracted/one-more-wheat/main.py"
CANDIDATES = {
    "a": ROOT / "experiments/omw-net-stock-sellnow-v3-a/main.py",
    "b": ROOT / "experiments/omw-net-stock-sellnow-v3-b/main.py",
    "c": ROOT / "experiments/omw-net-stock-sellnow-v3-c/main.py",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(candidate: str, output_root: Path) -> dict:
    experiment = CANDIDATES[candidate]
    namespace = runpy.run_path(str(experiment))
    source = namespace["_source"]
    output_dir = output_root / ("omw-net-stock-sellnow-v3-" + candidate)
    output_main = output_dir / "main.py"
    output_tar = output_root / ("omw-net-stock-sellnow-v3-" + candidate + ".tar.gz")
    output_manifest = output_root / ("omw-net-stock-sellnow-v3-" + candidate + ".manifest.json")
    compile(source, str(output_main), "exec")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_main.write_text(source)
    with tarfile.open(output_tar, "w:gz") as archive:
        archive.add(output_main, arcname="main.py")
    manifest = {
        "competition": "kaggriculture",
        "policy": "omw_net_stock_sellnow_v3_" + candidate,
        "candidate": candidate.upper(),
        "parent": "one_more_wheat_public_exact",
        "derived_from": "omw_net_stock_sellnow_v2",
        "parent_main_sha256": sha256(PARENT),
        "main_sha256": sha256(output_main),
        "archive_sha256": sha256(output_tar),
        "archive_members": ["main.py"],
        "local_source": str(experiment.relative_to(ROOT)),
        "status": "built_not_submitted",
    }
    output_manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate",
        choices=sorted(CANDIDATES),
        action="append",
        dest="candidates",
        help="candidate(s) to build; defaults to A, B, and C",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "submissions",
        help="directory receiving archives and manifests",
    )
    args = parser.parse_args()
    candidates = args.candidates or sorted(CANDIDATES)
    for candidate in candidates:
        print(json.dumps(build(candidate, args.output_root), indent=2))


if __name__ == "__main__":
    main()
