#!/usr/bin/env python3
"""Lint and verify the atomic converter-calibration control boundary."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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
        "sim/unit/calibration_commit_guard_tb.sv",
    ]
    common = [
        "--timing",
        "-Wall",
        "-Wno-fatal",
        "-sv",
        "--top-module",
        "calibration_commit_guard_tb",
        *sources,
    ]
    subprocess.run(
        [verilator, "--lint-only", *common], cwd=REPOSITORY_ROOT, check=True
    )
    build = REPOSITORY_ROOT / "build" / "verilator_calibration_commit_guard"
    subprocess.run(
        [verilator, "--binary", *common, "--Mdir", str(build)],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    subprocess.run(
        [str(build / "Vcalibration_commit_guard_tb")],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
