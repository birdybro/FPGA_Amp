#!/usr/bin/env python3
"""Generate, lint, build, and run the integrated wide V1 solver."""

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
    parser.add_argument("--lint-only", action="store_true")
    parser.add_argument("--skip-generate", action="store_true")
    parser.add_argument("--vectors-file")
    parser.add_argument("--capture-file")
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    if not args.skip_generate:
        for generator in (
            "scripts/generate_wide_network_vectors.py",
            "scripts/generate_wide_chord_vectors.py",
            "scripts/generate_factorized_tube.py",
            "scripts/generate_wide_solver_vectors.py",
        ):
            subprocess.run([sys.executable, generator], cwd=ROOT, check=True)
    sources = [
        "rtl/tube/triode_12ax7_factorized.sv",
        "rtl/circuit/network_rhs_v1_wide.sv",
        "rtl/circuit/network_kcl_v1_wide.sv",
        "rtl/circuit/chord_corrector_v1_wide.sv",
        "rtl/phono/v1_solver_mono_wide.sv",
        "sim/integration/v1_solver_mono_wide_tb.sv",
    ]
    subprocess.run(
        [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
        cwd=ROOT,
        check=True,
    )
    if args.lint_only:
        return 0
    build = ROOT / "build" / "verilator_v1_solver_wide"
    subprocess.run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "v1_solver_mono_wide_tb",
            "--Mdir",
            str(build),
            *sources,
        ],
        cwd=ROOT,
        check=True,
    )
    simulation = [str(build / "Vv1_solver_mono_wide_tb")]
    if args.vectors_file:
        simulation.append(f"+VECTORS={args.vectors_file}")
    if args.capture_file:
        simulation.append(f"+CAPTURE={args.capture_file}")
    subprocess.run(simulation, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
