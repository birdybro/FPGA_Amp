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
    parser.add_argument("--terminal-correction", action="store_true")
    parser.add_argument("--linear-tube", action="store_true")
    parser.add_argument("--parallel-tubes", action="store_true")
    parser.add_argument("--pipelined-kcl-finish", action="store_true")
    parser.add_argument("--pipelined-kcl-columns", action="store_true")
    parser.add_argument("--pipelined-kcl-accumulator", action="store_true")
    parser.add_argument("--pipelined-kcl-capacitor-current", action="store_true")
    parser.add_argument("--pipelined-kcl-maximum", action="store_true")
    parser.add_argument("--pipelined-chord-apply", action="store_true")
    args = parser.parse_args()
    if args.pipelined_kcl_accumulator and not args.pipelined_kcl_columns:
        parser.error(
            "--pipelined-kcl-accumulator requires --pipelined-kcl-columns"
        )
    if args.pipelined_kcl_capacitor_current and not args.pipelined_kcl_columns:
        parser.error(
            "--pipelined-kcl-capacitor-current requires "
            "--pipelined-kcl-columns"
        )
    if args.pipelined_kcl_maximum and not args.pipelined_kcl_finish:
        parser.error("--pipelined-kcl-maximum requires --pipelined-kcl-finish")
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
        if args.terminal_correction:
            generators[-1].append("--terminal-correction")
        if args.linear_tube:
            generators[2 if not args.trapezoidal else 3].append("--linear")
            generators[-1].append("--linear-tube")
        for command in generators:
            subprocess.run(command, cwd=ROOT, check=True)
    sources = [
        "rtl/tube/triode_12ax7_factorized.sv",
        "rtl/tube/triode_12ax7_factorized_linear.sv",
        "rtl/circuit/network_rhs_v1_wide.sv",
        "rtl/circuit/network_kcl_v1_wide.sv",
        "rtl/circuit/chord_corrector_v1_wide.sv",
        "rtl/circuit/terminal_current_update_v1.sv",
        "rtl/phono/v1_solver_mono_wide.sv",
        "sim/integration/v1_solver_mono_wide_tb.sv",
    ]
    if args.trapezoidal and not args.terminal_correction:
        sources.append("sim/integration/v1_solver_mono_wide_trapezoidal_tb.sv")
    top = (
        "v1_solver_mono_wide_trapezoidal_tb"
        if args.trapezoidal and not args.terminal_correction
        else "v1_solver_mono_wide_tb"
    )
    parameter_args = ["-GBANKED=1"] if args.banked else []
    if args.trapezoidal and args.terminal_correction:
        parameter_args.append("-GTRAPEZOIDAL=1")
    if args.terminal_correction:
        parameter_args.append("-GTERMINAL_CORRECTION=1")
    if args.linear_tube:
        parameter_args.append("-GLINEAR_TUBE=1")
    if args.parallel_tubes:
        parameter_args.append("-GPARALLEL_TUBES=1")
    if args.pipelined_kcl_finish:
        parameter_args.append("-GPIPELINED_KCL_FINISH=1")
    if args.pipelined_kcl_columns:
        parameter_args.append("-GPIPELINED_KCL_COLUMNS=1")
    if args.pipelined_kcl_accumulator:
        parameter_args.append("-GPIPELINED_KCL_ACCUMULATOR=1")
    if args.pipelined_kcl_capacitor_current:
        parameter_args.append("-GPIPELINED_KCL_CAPACITOR_CURRENT=1")
    if args.pipelined_kcl_maximum:
        parameter_args.append("-GPIPELINED_KCL_MAXIMUM=1")
    if args.pipelined_chord_apply:
        parameter_args.append("-GPIPELINED_CHORD_APPLY=1")
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
        + ("_terminal" if args.terminal_correction else "")
        + ("_linear" if args.linear_tube else "")
        + ("_parallel_tubes" if args.parallel_tubes else "")
        + ("_pipelined_kcl" if args.pipelined_kcl_finish else "")
        + ("_pipelined_columns" if args.pipelined_kcl_columns else "")
        + (
            "_pipelined_accumulator"
            if args.pipelined_kcl_accumulator
            else ""
        )
        + (
            "_pipelined_capacitor_current"
            if args.pipelined_kcl_capacitor_current
            else ""
        )
        + ("_pipelined_maximum" if args.pipelined_kcl_maximum else "")
        + ("_pipelined_chord" if args.pipelined_chord_apply else "")
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
    elif args.linear_tube:
        vector_suffix = (
            ("_trapezoidal" if args.trapezoidal else "")
            + ("_banked" if args.banked else "")
            + ("_terminal" if args.terminal_correction else "")
            + "_linear"
        )
        simulation.append(
            "+VECTORS=sim/vectors/generated/"
            f"v1_solver_wide_factorized_stream{vector_suffix}.txt"
        )
    if args.capture_file:
        simulation.append(f"+CAPTURE={args.capture_file}")
    subprocess.run(simulation, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
