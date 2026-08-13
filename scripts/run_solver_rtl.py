#!/usr/bin/env python3
"""Generate, lint, build, and run the integrated V1 mono solver."""

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
    parser.add_argument("--lint-only", action="store_true")
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
    subprocess.run(
        [sys.executable, "scripts/generate_chord_vectors.py"],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    subprocess.run(
        [sys.executable, "scripts/generate_solver_vectors.py"],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    sources = [
        "rtl/tube/triode_12ax7.sv",
        "rtl/circuit/network_rhs_v1.sv",
        "rtl/circuit/network_kcl_v1.sv",
        "rtl/circuit/chord_corrector_v1.sv",
        "rtl/phono/v1_solver_mono.sv",
        "sim/integration/v1_solver_mono_tb.sv",
    ]
    subprocess.run(
        [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    if args.lint_only:
        return 0
    build = REPOSITORY_ROOT / "build" / "verilator_v1_solver"
    subprocess.run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "v1_solver_mono_tb",
            "--Mdir",
            str(build),
            *sources,
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    subprocess.run([str(build / "Vv1_solver_mono_tb")], cwd=REPOSITORY_ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
