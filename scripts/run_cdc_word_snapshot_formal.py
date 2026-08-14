#!/usr/bin/env python3
"""Bound the coherent held-bus CDC safety contract under arbitrary clocks."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCAL_YOSYS = REPOSITORY_ROOT / ".tools" / "root" / "usr" / "bin" / "yosys"
LOCAL_LIBRARY = REPOSITORY_ROOT / ".tools" / "root" / "usr" / "lib"
PREPARE = (
    "read_verilog -formal -D FORMAL -sv "
    "rtl/io/cdc_word_snapshot.sv "
    "sim/formal/cdc_word_snapshot_formal.sv; "
    "prep -top cdc_word_snapshot_formal; "
    "flatten; "
    "clk2fflogic; "
    "opt_clean"
)


def resolve_yosys(requested: str) -> Path | None:
    resolved = shutil.which(requested)
    if resolved is not None:
        return Path(resolved)
    candidate = Path(requested)
    if candidate.is_file():
        return candidate.resolve()
    if requested == "yosys" and LOCAL_YOSYS.is_file():
        return LOCAL_YOSYS
    return None


def run_yosys(yosys: Path, command: str, log_path: Path) -> str:
    environment = os.environ.copy()
    using_local_tools = yosys.resolve().is_relative_to(LOCAL_YOSYS.parent.resolve())
    if using_local_tools and LOCAL_LIBRARY.is_dir():
        existing = environment.get("LD_LIBRARY_PATH")
        environment["LD_LIBRARY_PATH"] = (
            f"{LOCAL_LIBRARY}:{existing}" if existing else str(LOCAL_LIBRARY)
        )
    completed = subprocess.run(
        [str(yosys), "-Q", "-p", command],
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    log_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode:
        print(completed.stdout, file=sys.stderr)
        raise RuntimeError(f"Yosys failed; see {log_path}")
    return completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yosys", default="yosys")
    args = parser.parse_args()

    yosys = resolve_yosys(args.yosys)
    if yosys is None:
        print("ERROR: Yosys unavailable", file=sys.stderr)
        return 2

    build = REPOSITORY_ROOT / "build" / "formal_cdc_word_snapshot"
    build.mkdir(parents=True, exist_ok=True)

    proof_command = (
        f"{PREPARE}; "
        "sat -prove-asserts -set-assumes -set-init-zero "
        "-seq 40 -verify -timeout 30"
    )
    try:
        proof = run_yosys(yosys, proof_command, build / "bounded_proof.log")
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if "SAT proof finished - no model found: SUCCESS!" not in proof:
        print("ERROR: held-bus CDC bounded proof did not pass", file=sys.stderr)
        return 1

    # Require one complete nonzero transfer and full return to idle. This keeps
    # the safety proof honest without asserting liveness when either clock may
    # legally stop forever in the arbitrary-clock environment.
    reachability_command = (
        f"{PREPARE}; "
        "sat -set-assumes -set-init-zero -seq 40 "
        "-set-at 40 accepted_count 1 -set-at 40 completed_count 1 "
        "-set-at 40 source_available 1 -set-at 40 source_snapshot_data 10 "
        "-show accepted_count -show completed_count -show source_available "
        "-show source_snapshot_valid -show source_snapshot_data"
    )
    try:
        reachability = run_yosys(
            yosys, reachability_command, build / "reachability.log"
        )
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if "SAT solving finished - model found:" not in reachability:
        print("ERROR: held-bus CDC transfer witness was not found", file=sys.stderr)
        return 1

    print(
        "PASS: held-bus CDC 9-property arbitrary-clock safety through 40 "
        "steps; nonzero capture/return-to-idle witness found"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
