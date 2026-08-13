#!/usr/bin/env python3
"""Generate, lint, build, and run fixed V1 network RTL tests."""

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
    subprocess.run(
        [sys.executable, "scripts/generate_network_vectors.py"],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    tests = (
        (
            "network_rhs_v1_tb",
            "build/verilator_network_rhs",
            ["rtl/circuit/network_rhs_v1.sv", "sim/unit/network_rhs_v1_tb.sv"],
        ),
        (
            "network_kcl_v1_tb",
            "build/verilator_network_kcl",
            ["rtl/circuit/network_kcl_v1.sv", "sim/unit/network_kcl_v1_tb.sv"],
        ),
    )
    for top, build_relative, sources in tests:
        subprocess.run(
            [
                verilator,
                "--lint-only",
                "--timing",
                "-Wall",
                "-Wno-fatal",
                "-sv",
                *sources,
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
        )
        build = REPOSITORY_ROOT / build_relative
        subprocess.run(
            [
                verilator,
                "--binary",
                "--timing",
                "-Wall",
                "-Wno-fatal",
                "-sv",
                "--top-module",
                top,
                "--Mdir",
                str(build),
                *sources,
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
        )
        subprocess.run([str(build / f"V{top}")], cwd=REPOSITORY_ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
