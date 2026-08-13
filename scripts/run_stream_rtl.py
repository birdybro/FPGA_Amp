#!/usr/bin/env python3
"""Generate, lint, build, and verify the complete mono phono stream."""

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
    parser.add_argument("--factorized", action="store_true")
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    generators = [
        "scripts/generate_tube_lut.py",
        "scripts/generate_network_vectors.py",
        "scripts/generate_chord_vectors.py",
        "scripts/generate_halfband_rtl_vectors.py",
    ]
    if args.factorized:
        generators.extend(
            (
                "scripts/generate_factorized_tube.py",
                "scripts/generate_solver_vectors.py --factorized",
                "scripts/generate_stream_vectors.py --factorized",
            )
        )
    else:
        generators.append("scripts/generate_stream_vectors.py")
    for generator in generators:
        command = [sys.executable, *generator.split()]
        subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)
    sources = [
        "rtl/tube/triode_12ax7.sv",
        "rtl/tube/triode_12ax7_factorized.sv",
        "rtl/circuit/network_rhs_v1.sv",
        "rtl/circuit/network_kcl_v1.sv",
        "rtl/circuit/chord_corrector_v1.sv",
        "rtl/phono/v1_solver_mono.sv",
        "rtl/filters/halfband_interpolator_2x.sv",
        "rtl/filters/halfband_decimator_2x.sv",
        "rtl/audio/interpolator_16x.sv",
        "rtl/audio/decimator_16x.sv",
        "rtl/top/phono_stream_mono.sv",
        "sim/integration/phono_stream_mono_tb.sv",
    ]
    subprocess.run(
        [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    build_name = (
        "verilator_phono_stream_factorized"
        if args.factorized
        else "verilator_phono_stream"
    )
    build = REPOSITORY_ROOT / "build" / build_name
    parameter_args = ["-GUSE_FACTORIZED=1"] if args.factorized else []
    subprocess.run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "phono_stream_mono_tb",
            "--Mdir",
            str(build),
            *parameter_args,
            *sources,
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    subprocess.run([str(build / "Vphono_stream_mono_tb")], cwd=REPOSITORY_ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
