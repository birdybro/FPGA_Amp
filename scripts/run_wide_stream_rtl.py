#!/usr/bin/env python3
"""Generate, lint, build, and verify the complete wide mono phono stream."""

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
    parser.add_argument("--skip-generate", action="store_true")
    parser.add_argument("--vectors-file")
    parser.add_argument("--vector-count", type=int)
    parser.add_argument("--capture-file")
    parser.add_argument("--trapezoidal", action="store_true")
    parser.add_argument("--banked", action="store_true")
    parser.add_argument("--terminal-correction", action="store_true")
    parser.add_argument(
        "--sample-rate-hz", type=int, choices=(384_000, 768_000), default=768_000
    )
    parser.add_argument(
        "--run-only",
        action="store_true",
        help="reuse an already built simulator for another vector file",
    )
    args = parser.parse_args()
    if args.terminal_correction and not args.banked:
        parser.error("terminal correction requires --banked")
    if args.sample_rate_hz == 384_000 and not (
        args.trapezoidal and args.banked and args.terminal_correction
    ):
        parser.error(
            "384 kHz stream verification requires --trapezoidal --banked "
            "--terminal-correction"
        )
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    generators = [
        [sys.executable, "scripts/generate_wide_network_vectors.py"],
        [sys.executable, "scripts/generate_wide_chord_vectors.py"],
        [sys.executable, "scripts/generate_factorized_tube.py"],
        [sys.executable, "scripts/generate_wide_solver_vectors.py"],
        [sys.executable, "scripts/generate_halfband_rtl_vectors.py"],
        [sys.executable, "scripts/generate_stream_vectors.py", "--wide"],
    ]
    if args.trapezoidal:
        generators.insert(
            1,
            [sys.executable, "scripts/generate_trapezoidal_network_vectors.py"],
        )
        generators[2].append("--trapezoidal")
        generators[4].append("--trapezoidal")
        generators[-1].append("--trapezoidal")
    if args.banked:
        next(
            command
            for command in generators
            if command[1].endswith("generate_wide_chord_vectors.py")
        ).append("--banked")
        next(
            command
            for command in generators
            if command[1].endswith("generate_wide_solver_vectors.py")
        ).append("--banked")
        generators[-1].append("--banked")
    if args.terminal_correction:
        next(
            command
            for command in generators
            if command[1].endswith("generate_wide_solver_vectors.py")
        ).append("--terminal-correction")
        generators[-1].append("--terminal-correction")
    if args.sample_rate_hz != 768_000:
        rate_arguments = ["--sample-rate-hz", str(args.sample_rate_hz)]
        for command in generators:
            if command[1].endswith(
                (
                    "generate_trapezoidal_network_vectors.py",
                    "generate_wide_chord_vectors.py",
                    "generate_wide_solver_vectors.py",
                    "generate_stream_vectors.py",
                )
            ):
                command.extend(rate_arguments)
    if not args.skip_generate:
        for command in generators:
            subprocess.run(command, cwd=ROOT, check=True)
    if (args.vectors_file is None) != (args.vector_count is None):
        parser.error("--vectors-file and --vector-count must be provided together")
    if args.vector_count is not None and not 0 < args.vector_count <= 8192:
        parser.error("--vector-count must be within 1..8192")
    sources = [
        "rtl/tube/triode_12ax7_factorized.sv",
        "rtl/circuit/network_rhs_v1_wide.sv",
        "rtl/circuit/network_kcl_v1_wide.sv",
        "rtl/circuit/chord_corrector_v1_wide.sv",
        "rtl/circuit/terminal_current_update_v1.sv",
        "rtl/phono/v1_solver_mono_wide.sv",
        "rtl/filters/halfband_interpolator_2x.sv",
        "rtl/filters/halfband_decimator_2x.sv",
        "rtl/audio/interpolator_16x.sv",
        "rtl/audio/decimator_16x.sv",
        "rtl/audio/interpolator_8x.sv",
        "rtl/audio/decimator_8x.sv",
        "rtl/top/phono_stream_mono_wide.sv",
        "sim/integration/phono_stream_mono_wide_tb.sv",
    ]
    if args.trapezoidal:
        sources.append(
            "sim/integration/phono_stream_mono_wide_trapezoidal_tb.sv"
        )
    top = "phono_stream_mono_wide_tb"
    if args.trapezoidal and not args.banked:
        top = "phono_stream_mono_wide_trapezoidal_tb"
    parameter_args: list[str] = []
    if args.trapezoidal and args.banked:
        parameter_args.append("-GTRAPEZOIDAL=1")
    if args.banked:
        parameter_args.append("-GBANKED=1")
    if args.terminal_correction:
        parameter_args.append("-GTERMINAL_CORRECTION=1")
    if args.sample_rate_hz == 384_000:
        parameter_args.append("-GSAMPLE_RATE_384KHZ=1")
    build = ROOT / "build" / (
        "verilator_phono_stream_wide"
        + ("_trapezoidal" if args.trapezoidal else "")
        + ("_384khz" if args.sample_rate_hz == 384_000 else "")
        + ("_banked" if args.banked else "")
        + ("_terminal" if args.terminal_correction else "")
    )
    if not args.run_only:
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
    if args.run_only and not Path(simulation[0]).is_file():
        parser.error("--run-only requested before the simulator was built")
    if args.vectors_file:
        simulation.extend(
            (
                f"+VECTORS={args.vectors_file}",
                f"+VECTOR_COUNT={args.vector_count}",
            )
        )
    if args.capture_file:
        simulation.append(f"+CAPTURE={args.capture_file}")
    subprocess.run(simulation, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
