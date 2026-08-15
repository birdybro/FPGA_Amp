#!/usr/bin/env python3
"""Generate, lint, and simulate the 40-bit wide-state chord candidate."""

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
    parser.add_argument("--pipelined-apply", action="store_true")
    parser.add_argument("--trapezoidal", action="store_true")
    parser.add_argument("--banked", action="store_true")
    parser.add_argument(
        "--sample-rate-hz", type=int, choices=(384_000, 768_000), default=768_000
    )
    args = parser.parse_args()
    if args.sample_rate_hz == 384_000 and not (args.trapezoidal and args.banked):
        parser.error("384 kHz chord verification requires --trapezoidal --banked")
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    generator = [sys.executable, "scripts/generate_wide_chord_vectors.py"]
    if args.trapezoidal:
        generator.append("--trapezoidal")
    if args.banked:
        generator.append("--banked")
    if args.sample_rate_hz != 768_000:
        generator.extend(("--sample-rate-hz", str(args.sample_rate_hz)))
    subprocess.run(generator, cwd=ROOT, check=True)
    sources = [
        "rtl/circuit/chord_corrector_v1_wide.sv",
        "sim/unit/chord_corrector_v1_wide_tb.sv",
    ]
    parameter_args = ["-GPIPELINED_APPLY=1"] if args.pipelined_apply else []
    if args.trapezoidal:
        parameter_args.append("-GTRAPEZOIDAL=1")
    if args.banked:
        parameter_args.append("-GBANKED=1")
    if args.sample_rate_hz == 384_000:
        parameter_args.append("-GSAMPLE_RATE_384KHZ=1")
    subprocess.run(
        [
            verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal",
            "-sv", *parameter_args, *sources,
        ],
        cwd=ROOT,
        check=True,
    )
    build = ROOT / "build" / (
        "verilator_chord_wide"
        + ("_trapezoidal" if args.trapezoidal else "")
        + ("_384khz" if args.sample_rate_hz == 384_000 else "")
        + ("_banked" if args.banked else "")
        + ("_pipelined_apply" if args.pipelined_apply else "")
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
            "chord_corrector_v1_wide_tb",
            "--Mdir",
            str(build),
            *parameter_args,
            *sources,
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run([str(build / "Vchord_corrector_v1_wide_tb")], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
