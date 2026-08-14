#!/usr/bin/env python3
"""Lint and verify the protocol-neutral phono control register bank."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verilator", default="verilator")
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    sources = [
        "rtl/control/calibration_commit_guard.sv",
        "rtl/control/phono_control_registers.sv",
        "sim/unit/phono_control_registers_tb.sv",
    ]
    common = [
        "--timing",
        "-Wall",
        "-Wno-fatal",
        "-sv",
        "--top-module",
        "phono_control_registers_tb",
        *sources,
    ]
    subprocess.run(
        [verilator, "--lint-only", *common], cwd=ROOT, check=True
    )
    build = ROOT / "build" / "verilator_phono_control_registers"
    subprocess.run(
        [verilator, "--binary", *common, "--Mdir", str(build)],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [str(build / "Vphono_control_registers_tb")], cwd=ROOT, check=True
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
