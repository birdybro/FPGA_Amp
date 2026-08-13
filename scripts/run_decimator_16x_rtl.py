#!/usr/bin/env python3
"""Build and run the complete 16x decimator with optional capture vectors."""

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
    parser.add_argument("--input-count", type=int)
    parser.add_argument("--output-count", type=int)
    parser.add_argument("--capture-file")
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    custom = (args.vectors_file, args.input_count, args.output_count)
    if any(value is not None for value in custom) and not all(
        value is not None for value in custom
    ):
        parser.error(
            "--vectors-file, --input-count, and --output-count are required together"
        )
    if args.input_count is not None and not 0 < args.input_count <= 131072:
        parser.error("--input-count must be within 1..131072")
    if args.output_count is not None and not 0 < args.output_count <= 8192:
        parser.error("--output-count must be within 1..8192")
    if not args.skip_generate:
        subprocess.run(
            [sys.executable, "scripts/generate_halfband_rtl_vectors.py"],
            cwd=ROOT,
            check=True,
        )
    sources = [
        "rtl/filters/halfband_decimator_2x.sv",
        "rtl/audio/decimator_16x.sv",
        "sim/integration/decimator_16x_tb.sv",
    ]
    subprocess.run(
        [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
        cwd=ROOT,
        check=True,
    )
    build = ROOT / "build" / "verilator_decimator_16x"
    subprocess.run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "decimator_16x_tb",
            "--Mdir",
            str(build),
            *sources,
        ],
        cwd=ROOT,
        check=True,
    )
    simulation = [str(build / "Vdecimator_16x_tb")]
    if args.vectors_file:
        simulation.extend(
            (
                f"+VECTORS={args.vectors_file}",
                f"+INPUT_COUNT={args.input_count}",
                f"+OUTPUT_COUNT={args.output_count}",
            )
        )
    if args.capture_file:
        simulation.append(f"+CAPTURE={args.capture_file}")
    subprocess.run(simulation, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
