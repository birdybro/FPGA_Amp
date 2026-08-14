#!/usr/bin/env python3
"""Bound the asynchronous FIFO safety contract with Yosys SAT."""

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
    "rtl/io/async_fifo.sv sim/formal/async_fifo_formal.sv; "
    "prep -top async_fifo_formal; "
    "flatten; "
    # Preserve independent write/read clock transitions in the implicit formal
    # clock domain and lower the edge-triggered checks for the SAT backend.
    "clk2fflogic; "
    "memory_map; "
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

    build = REPOSITORY_ROOT / "build" / "formal_async_fifo"
    build.mkdir(parents=True, exist_ok=True)

    # This is deliberately a bounded multi-clock result. The existing property
    # set is not claimed to be a complete invariant for unbounded induction.
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
        print("ERROR: 32-step bounded FIFO proof did not pass", file=sys.stderr)
        return 1

    # The assumptions must admit meaningful fault paths. Ask SAT to find one
    # trace that fills the depth-four instance and attempts both illegal sides.
    reachability_command = (
        f"{PREPARE}; "
        "sat -set-assumes -set-init-zero -seq 24 "
        "-set wr_clear_overflow 0 -set rd_clear_underflow 0 "
        "-set-at 24 wr_high_water 4 "
        "-set-at 24 wr_overflow_sticky 1 "
        "-set-at 24 rd_underflow_sticky 1 "
        "-show wr_high_water -show wr_overflow_sticky "
        "-show rd_underflow_sticky"
    )
    try:
        reachability = run_yosys(
            yosys, reachability_command, build / "reachability.log"
        )
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if "SAT solving finished - model found:" not in reachability:
        print(
            "ERROR: FIFO fault-path reachability witness was not found",
            file=sys.stderr,
        )
        return 1

    print(
        "PASS: async FIFO 13-property/32-step bounded proof; "
        "full/overflow/underflow witness found"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
