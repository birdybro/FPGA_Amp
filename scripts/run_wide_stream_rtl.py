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
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    generators = (
        "scripts/generate_wide_network_vectors.py",
        "scripts/generate_wide_chord_vectors.py",
        "scripts/generate_factorized_tube.py",
        "scripts/generate_wide_solver_vectors.py",
        "scripts/generate_halfband_rtl_vectors.py",
        "scripts/generate_stream_vectors.py --wide",
    )
    if not args.skip_generate:
        for generator in generators:
            subprocess.run([sys.executable, *generator.split()], cwd=ROOT, check=True)
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
    subprocess.run(
        [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
        cwd=ROOT,
        check=True,
    )
    build = ROOT / "build" / "verilator_phono_stream_wide"
    subprocess.run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "phono_stream_mono_wide_tb",
            "--Mdir",
            str(build),
            *sources,
        ],
        cwd=ROOT,
        check=True,
    )
    simulation = [str(build / "Vphono_stream_mono_wide_tb")]
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
