#!/usr/bin/env python3
"""Bound the asynchronous BCLK-rate monitor safety state machine."""

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
    "rtl/io/audio_clock_rate_monitor.sv "
    "sim/formal/audio_clock_rate_monitor_formal.sv; "
    "prep -top audio_clock_rate_monitor_formal; "
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

    build = REPOSITORY_ROOT / "build" / "formal_audio_clock_rate_monitor"
    build.mkdir(parents=True, exist_ok=True)

    proof_command = (
        f"{PREPARE}; "
        "sat -prove-asserts -set-assumes -set-init-zero "
        "-seq 32 -verify -timeout 30"
    )
    try:
        proof = run_yosys(yosys, proof_command, build / "bounded_proof.log")
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if "SAT proof finished - no model found: SUCCESS!" not in proof:
        print("ERROR: audio-clock monitor bounded proof did not pass", file=sys.stderr)
        return 1

    # Require the reduced monitor to acquire lock and later retain an out-of-
    # tolerance error while unlocked. This exercises both sides of the window
    # classification instead of relying on a reset-only safety trace.
    reachability_command = (
        f"{PREPARE}; "
        "sat -set-assumes -set-init-zero -seq 48 "
        "-set-at 48 ever_locked 1 -set-at 48 rate_error_sticky 1 "
        "-set-at 48 rate_locked 0 "
        "-show ever_locked -show rate_locked -show rate_error_sticky "
        "-show measured_bclk_edges -show consecutive_good_windows"
    )
    try:
        reachability = run_yosys(
            yosys, reachability_command, build / "reachability.log"
        )
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if "SAT solving finished - model found:" not in reachability:
        print("ERROR: audio-clock lock/error witness was not found", file=sys.stderr)
        return 1

    print(
        "PASS: audio-clock monitor 16-property arbitrary-clock safety through "
        "32 steps; lock-then-rate-error witness found"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
