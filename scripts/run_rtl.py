#!/usr/bin/env python3
"""Generate tube vectors, lint, compile, and run the Verilator testbench."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verilator", default="verilator")
    parser.add_argument("--lint-only", action="store_true")
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print(f"ERROR: Verilator not found: {args.verilator}", file=sys.stderr)
        return 2

    rtl = "rtl/tube/triode_12ax7.sv"
    tb = "sim/unit/triode_12ax7_tb.sv"
    lint = [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", rtl, tb]
    run(lint)
    if args.lint_only:
        return 0

    run([sys.executable, "scripts/generate_tube_lut.py", "--vectors", "4096"])
    output_dir = REPOSITORY_ROOT / "build" / "verilator_triode"
    output_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "triode_12ax7_tb",
            "--Mdir",
            str(output_dir),
            rtl,
            tb,
        ]
    )
    executable = output_dir / "Vtriode_12ax7_tb"
    run([str(executable), "+VECTORS=sim/vectors/generated/triode_random.txt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

