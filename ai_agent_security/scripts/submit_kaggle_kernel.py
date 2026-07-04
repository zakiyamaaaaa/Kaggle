#!/usr/bin/env python3
"""Push a Kaggle kernel bundle and wait for it to finish.

For this competition, `kaggle competitions submit -k ... -v ...` submits the
kernel output CSV statically and can produce Submission Format Error. Use this
script to create a completed kernel version, then submit the notebook from the
Kaggle UI's "Submit to Competition" button.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from validate_submission_bundle import COMPETITION, validate_bundle

COMPLETED_STATUSES = {"complete", "completed", "success", "succeeded"}
FAILED_STATUSES = {"error", "failed", "failure", "canceled", "cancelled"}
RUNNING_STATUSES = {
    "queued",
    "pending",
    "preparing",
    "running",
    "executing",
    "saving",
    "unknown",
}
VERSION_PATTERN = re.compile(r"kernel version\s+(\d+)\s+successfully pushed", re.I)
STATUS_PATTERN = re.compile(r'has status "([^"]+)"', re.I)


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {cmd[0]}")
    return result


def _load_metadata(bundle_dir: Path) -> dict:
    return json.loads((bundle_dir / "kernel-metadata.json").read_text(encoding="utf-8"))


def _parse_version(output: str) -> str:
    match = VERSION_PATTERN.search(output)
    if not match:
        raise RuntimeError(
            "Could not parse kernel version from `kaggle kernels push` output."
        )
    return match.group(1)


def _parse_status(output: str) -> str:
    match = STATUS_PATTERN.search(output)
    if match:
        return match.group(1).strip().lower()
    quoted = re.findall(r'"([^"]+)"', output)
    if quoted:
        return quoted[-1].strip().lower()
    return output.strip().lower() or "unknown"


def wait_for_kernel(
    kernel_id: str,
    version: str,
    timeout_seconds: int,
    poll_seconds: int,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    kernel_ref = f"{kernel_id}/{version}"
    while True:
        result = _run(["kaggle", "kernels", "status", kernel_ref])
        status = _parse_status(result.stdout)
        print(f"Kernel {kernel_ref} status: {status}", flush=True)
        if status in COMPLETED_STATUSES:
            return
        if status in FAILED_STATUSES:
            raise RuntimeError(f"Kernel {kernel_ref} finished with status {status}")
        if status not in RUNNING_STATUSES:
            print(f"Unrecognized Kaggle status {status!r}; continuing to poll.")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for kernel {kernel_ref}")
        time.sleep(poll_seconds)


def submit_kernel(args: argparse.Namespace) -> None:
    bundle_dir = Path(args.bundle_dir)
    if not bundle_dir.is_absolute():
        bundle_dir = (Path.cwd() / bundle_dir).resolve()
    validate_bundle(bundle_dir, args.competition)
    metadata = _load_metadata(bundle_dir)
    kernel_id = metadata["id"]

    if args.dry_run:
        print(f"Dry run: would push and wait for {kernel_id} from {bundle_dir}")
        return

    push_result = _run(["kaggle", "kernels", "push", "-p", str(bundle_dir)])
    version = _parse_version(push_result.stdout + push_result.stderr)
    wait_for_kernel(
        kernel_id=kernel_id,
        version=version,
        timeout_seconds=args.timeout_minutes * 60,
        poll_seconds=args.poll_seconds,
    )

    if not args.submit_static_output:
        print()
        print(f"Kernel {kernel_id}/{version} is complete.")
        print("Submit this notebook version from Kaggle UI: Submit to Competition.")
        print(
            "Do not use `kaggle competitions submit -k ... -v ...` for this "
            "competition unless you intentionally want a static output-file submit."
        )
        return

    submit_cmd = [
        "kaggle",
        "competitions",
        "submit",
        args.competition,
        "-f",
        args.output_file,
        "-k",
        kernel_id,
        "-v",
        version,
        "-m",
        args.message,
    ]
    _run(submit_cmd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Push a Kaggle kernel bundle and wait for the completed version."
    )
    parser.add_argument("bundle_dir", help="Path to ai_agent_security/kaggle-push/<exp>.")
    parser.add_argument("--competition", default=COMPETITION)
    parser.add_argument(
        "--output-file",
        default="submission.csv",
        help=(
            "Static kernel output file name to submit only when "
            "--submit-static-output is set."
        ),
    )
    parser.add_argument("--message", required=True, help="Kaggle submission message.")
    parser.add_argument("--timeout-minutes", type=int, default=360)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--submit-static-output",
        action="store_true",
        help=(
            "Dangerous for this competition: submit the completed kernel output "
            "file statically via Kaggle API."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    submit_kernel(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"submit_kaggle_kernel.py: {exc}", file=sys.stderr)
        raise SystemExit(1)
