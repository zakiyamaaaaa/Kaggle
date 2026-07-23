"""Build controlled ablations of the public ROGII 6.213 notebook.

The source notebook is kept byte-identical in its reproduction directory.
This generator changes only the first control cell and Kaggle metadata, then
records hashes so every ablation can be traced back to the public source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Variant:
    name: str
    slug: str
    title: str
    profile: str
    disable_generic_overlays: bool = False


VARIANTS = (
    Variant(
        name="no_modelpkg",
        slug="rogii-new-strategy-6-213-no-modelpkg",
        title="ROGII New Strategy 6.213 No Modelpkg",
        profile="vp_balanced_final",
    ),
    Variant(
        name="contact_anchor",
        slug="rogii-new-strategy-6-213-contact-anchor",
        title="ROGII New Strategy 6.213 Contact Anchor",
        profile="contact_gated_anchor",
    ),
    Variant(
        name="generic_core",
        slug="rogii-new-strategy-6-213-generic-core",
        title="ROGII New Strategy 6.213 Generic Core",
        profile="contact_gated_anchor",
        disable_generic_overlays=True,
    ),
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_text(cell: dict) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def set_source(cell: dict, value: str) -> None:
    if isinstance(cell.get("source"), list):
        cell["source"] = value.splitlines(keepends=True)
    else:
        cell["source"] = value


def build_variant(
    source_notebook: Path,
    source_metadata: Path,
    output_root: Path,
    owner: str,
    variant: Variant,
) -> dict:
    notebook_bytes = source_notebook.read_bytes()
    notebook = json.loads(notebook_bytes)
    metadata = json.loads(source_metadata.read_text(encoding="utf-8"))
    control_cell = None
    for cell in notebook.get("cells", []):
        text = source_text(cell)
        if cell.get("cell_type") == "code" and "SUBMISSION_PROFILE = " in text:
            control_cell = cell
            break
    if control_cell is None:
        raise RuntimeError("Could not find the submission control cell")

    control = source_text(control_cell)
    old = "SUBMISSION_PROFILE = 'vp_balanced_modelpkg_005'"
    new = f"SUBMISSION_PROFILE = '{variant.profile}'"
    if control.count(old) != 1:
        raise RuntimeError(f"Expected one default profile assignment, found {control.count(old)}")
    control = control.replace(old, new, 1)
    overlay_marker = "_profile = PROFILE_PRESETS[SUBMISSION_PROFILE]\n"
    if variant.disable_generic_overlays:
        override = (
            "_profile = dict(\n"
            "    _profile,\n"
            "    run_guarded_overlap_override=False,\n"
            "    run_visible_prefix_calibration=False,\n"
            "    run_bimodal_detector=False,\n"
            "    run_vp_bimodal_guard=False,\n"
            "    run_model_package_correction=False,\n"
            ")\n"
        )
        if control.count(overlay_marker) != 1:
            raise RuntimeError("Could not place the generic-core overlay override")
        control = control.replace(overlay_marker, overlay_marker + override, 1)
    set_source(control_cell, control)

    metadata.pop("id_no", None)
    metadata["id"] = f"{owner}/{variant.slug}"
    metadata["title"] = variant.title
    metadata["is_private"] = True
    notebook_name = f"{variant.slug}.ipynb"
    metadata["code_file"] = notebook_name

    output_dir = output_root / variant.name
    output_dir.mkdir(parents=True, exist_ok=True)
    notebook_output = output_dir / notebook_name
    metadata_output = output_dir / "kernel-metadata.json"
    rendered_notebook = json.dumps(notebook, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    notebook_output.write_bytes(rendered_notebook)
    metadata_output.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "name": variant.name,
        "profile": variant.profile,
        "disable_generic_overlays": variant.disable_generic_overlays,
        "source_notebook": str(source_notebook),
        "source_sha256": sha256_bytes(notebook_bytes),
        "notebook": str(notebook_output),
        "notebook_sha256": sha256_bytes(rendered_notebook),
        "metadata": str(metadata_output),
        "kaggle_id": metadata["id"],
        "dataset_sources": metadata.get("dataset_sources", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--owner", default="zacky21")
    args = parser.parse_args()
    notebooks = sorted(args.source_dir.glob("*.ipynb"))
    if len(notebooks) != 1:
        raise RuntimeError(f"Expected one source notebook, found {notebooks}")
    source_metadata = args.source_dir / "kernel-metadata.json"
    if not source_metadata.exists():
        raise FileNotFoundError(source_metadata)
    records = [
        build_variant(
            notebooks[0],
            source_metadata,
            args.output_root,
            args.owner,
            variant,
        )
        for variant in VARIANTS
    ]
    manifest = {
        "source_sha256": sha256_bytes(notebooks[0].read_bytes()),
        "variants": records,
    }
    manifest_path = args.output_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
