#!/usr/bin/env python3
"""Generate, lint, and simulate the wide trapezoidal KCL engine."""

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
    subprocess.run(
        [sys.executable, "scripts/generate_trapezoidal_network_vectors.py"],
        cwd=ROOT,
        check=True,
    )
    top = "network_kcl_v1_wide_trapezoidal_tb"
    sources = [
        "rtl/circuit/network_kcl_v1_wide.sv",
        "sim/unit/network_kcl_v1_wide_trapezoidal_tb.sv",
    ]
    subprocess.run(
        [verilator, "--lint-only", "--timing", "-Wall", "-sv", *sources],
        cwd=ROOT,
        check=True,
    )
    build = ROOT / "build" / "verilator_network_kcl_wide_trapezoidal"
    subprocess.run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-sv",
            "--top-module",
            top,
            "--Mdir",
            str(build),
            *sources,
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run([str(build / f"V{top}")], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
