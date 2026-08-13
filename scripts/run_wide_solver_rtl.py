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
    parser.add_argument("--trapezoidal", action="store_true")
    parser.add_argument("--banked", action="store_true")
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    if not args.skip_generate:
        generators = [
            [sys.executable, "scripts/generate_wide_network_vectors.py"],
            [sys.executable, "scripts/generate_wide_chord_vectors.py"],
            [sys.executable, "scripts/generate_factorized_tube.py"],
            [sys.executable, "scripts/generate_wide_solver_vectors.py"],
        ]
        if args.trapezoidal:
            generators.insert(
                1,
                [sys.executable, "scripts/generate_trapezoidal_network_vectors.py"],
            )
            generators[2].append("--trapezoidal")
            generators[-1].append("--trapezoidal")
        if args.banked:
            generators[1 if not args.trapezoidal else 2].append("--banked")
            generators[-1].append("--banked")
        for command in generators:
            subprocess.run(command, cwd=ROOT, check=True)
    sources = [
        "rtl/tube/triode_12ax7_factorized.sv",
        "rtl/circuit/network_rhs_v1_wide.sv",
        "rtl/circuit/network_kcl_v1_wide.sv",
        "rtl/circuit/chord_corrector_v1_wide.sv",
        "rtl/phono/v1_solver_mono_wide.sv",
        "sim/integration/v1_solver_mono_wide_tb.sv",
    ]
    if args.trapezoidal:
        sources.append("sim/integration/v1_solver_mono_wide_trapezoidal_tb.sv")
    top = (
        "v1_solver_mono_wide_trapezoidal_tb"
        if args.trapezoidal
        else "v1_solver_mono_wide_tb"
    )
    parameter_args = ["-GBANKED=1"] if args.banked else []
    subprocess.run(
        [
            verilator,
            "--lint-only",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            top,
            *parameter_args,
            *sources,
        ],
        cwd=ROOT,
        check=True,
    )
    if args.lint_only:
        return 0
    build = ROOT / "build" / (
        "verilator_v1_solver_wide"
        + ("_trapezoidal" if args.trapezoidal else "")
        + ("_banked" if args.banked else "")
    )
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
            *parameter_args,
            *sources,
        ],
        cwd=ROOT,
        check=True,
    )
    simulation = [str(build / f"V{top}")]
    if args.vectors_file:
        simulation.append(f"+VECTORS={args.vectors_file}")
    if args.capture_file:
        simulation.append(f"+CAPTURE={args.capture_file}")
    subprocess.run(simulation, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
