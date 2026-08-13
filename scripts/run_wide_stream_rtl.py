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
    parser.add_argument(
        "--run-only",
        action="store_true",
        help="reuse an already built simulator for another vector file",
    )
    args = parser.parse_args()
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
        "rtl/phono/v1_solver_mono_wide.sv",
        "rtl/filters/halfband_interpolator_2x.sv",
        "rtl/filters/halfband_decimator_2x.sv",
        "rtl/audio/interpolator_16x.sv",
        "rtl/audio/decimator_16x.sv",
        "rtl/top/phono_stream_mono_wide.sv",
        "sim/integration/phono_stream_mono_wide_tb.sv",
    ]
    if args.trapezoidal:
        sources.append(
            "sim/integration/phono_stream_mono_wide_trapezoidal_tb.sv"
        )
    top = (
        "phono_stream_mono_wide_trapezoidal_tb"
        if args.trapezoidal
        else "phono_stream_mono_wide_tb"
    )
    build = ROOT / "build" / (
        "verilator_phono_stream_wide_trapezoidal"
        if args.trapezoidal
        else "verilator_phono_stream_wide"
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
