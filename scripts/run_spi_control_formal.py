#!/usr/bin/env python3
"""Bound SPI transport safety and reach decoded/error paths."""

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
    "rtl/io/spi_control_transport.sv "
    "sim/formal/spi_control_transport_formal.sv; "
    "prep -top spi_control_transport_formal; "
    "flatten; "
    "async2sync; "
    "formalff -clk2ff; "
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
    try:
        completed = subprocess.run(
            [str(yosys), "-Q", "-p", command],
            cwd=REPOSITORY_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=45,
        )
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        log_path.write_text(output, encoding="utf-8")
        raise RuntimeError(f"Yosys timed out; see {log_path}") from error
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

    build = REPOSITORY_ROOT / "build" / "formal_spi_control_transport"
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
        print("ERROR: SPI transport bounded proof did not pass", file=sys.stderr)
        return 1

    # Forty synchronized request bits need a longer trace than the safety
    # bound. Reach decode plus first-response underflow and short-frame evidence
    # without weakening the arbitrary raw-pin environment.
    reachability_command = (
        f"{PREPARE}; "
        "sat -set-assumes -set-init-zero -seq 100 "
        "-set-at 100 ever_request 1 "
        "-set-at 100 response_underflow_sticky 1 "
        "-set-at 100 frame_error_sticky 1 "
        "-show ever_request -show response_underflow_sticky "
        "-show frame_error_sticky -show completed_frame_count"
    )
    try:
        reachability = run_yosys(
            yosys, reachability_command, build / "reachability.log"
        )
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if "SAT solving finished - model found:" not in reachability:
        print("ERROR: SPI request/error witness was not found", file=sys.stderr)
        return 1

    print(
        "PASS: SPI transport 11-property arbitrary-pin safety through 32 "
        "steps; 100-step request/short/underflow witness found"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
