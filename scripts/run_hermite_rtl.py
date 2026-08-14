#!/usr/bin/env python3
"""Generate, lint, compile, and verify the iterative Hermite RTL kernel."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verilator", default="verilator")
    parser.add_argument("--lint-only", action="store_true")
    parser.add_argument("--vectors", type=int, default=4096)
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print(f"ERROR: Verilator not found: {args.verilator}", file=sys.stderr)
        return 2

    rtl = "rtl/math/hermite_q16_pipeline.sv"
    tb = "sim/unit/hermite_q16_pipeline_tb.sv"
    run([sys.executable, "scripts/generate_hermite_vectors.py", "--vectors", str(args.vectors)])
    run([verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", rtl, tb])
    if args.lint_only:
        return 0

    output_dir = REPOSITORY_ROOT / "build" / "verilator_hermite_q16_pipeline"
    output_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "hermite_q16_pipeline_tb",
            "--Mdir",
            str(output_dir),
            rtl,
            tb,
        ]
    )
    run(
        [
            str(output_dir / "Vhermite_q16_pipeline_tb"),
            "+VECTORS=sim/vectors/generated/hermite_q16_random.txt",
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
