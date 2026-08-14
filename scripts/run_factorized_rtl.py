#!/usr/bin/env python3
"""Generate, lint, compile, and verify the factorized 12AX7 RTL."""

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
    parser.add_argument("--linear", action="store_true")
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print(f"ERROR: Verilator not found: {args.verilator}", file=sys.stderr)
        return 2

    rtl = (
        "rtl/tube/triode_12ax7_factorized_linear.sv"
        if args.linear
        else "rtl/tube/triode_12ax7_factorized.sv"
    )
    tb = "sim/unit/triode_12ax7_factorized_tb.sv"
    generator = [
        sys.executable,
        "scripts/generate_factorized_tube.py",
        "--vectors",
        str(args.vectors),
    ]
    defines = ["-DLINEAR_FACTORIZED"] if args.linear else []
    if args.linear:
        generator.append("--linear")
    run(generator)
    run(
        [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv"]
        + defines
        + [rtl, tb]
    )
    if args.lint_only:
        return 0

    output_dir = REPOSITORY_ROOT / "build" / (
        "verilator_triode_factorized_linear"
        if args.linear
        else "verilator_triode_factorized"
    )
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
            "triode_12ax7_factorized_tb",
            "--Mdir",
            str(output_dir),
            *defines,
            rtl,
            tb,
        ]
    )
    run(
        [
            str(output_dir / "Vtriode_12ax7_factorized_tb"),
            "+VECTORS="
            + (
                "sim/vectors/generated/triode_factorized_linear_random.txt"
                if args.linear
                else "sim/vectors/generated/triode_factorized_random.txt"
            ),
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
