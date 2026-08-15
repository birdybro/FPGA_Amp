#!/usr/bin/env python3
"""Generate, lint, and simulate the wide branch-current KCL engine."""

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
    parser.add_argument("--pipelined-finish", action="store_true")
    parser.add_argument("--pipelined-columns", action="store_true")
    parser.add_argument("--pipelined-accumulator", action="store_true")
    parser.add_argument("--pipelined-capacitor-current", action="store_true")
    parser.add_argument("--pipelined-maximum", action="store_true")
    parser.add_argument("--decoupled-maximum", action="store_true")
    parser.add_argument("--serial-maximum", action="store_true")
    parser.add_argument("--shared-capacitor-multiplier", action="store_true")
    args = parser.parse_args()
    if args.pipelined_accumulator and not args.pipelined_columns:
        parser.error("--pipelined-accumulator requires --pipelined-columns")
    if args.pipelined_capacitor_current and not args.pipelined_columns:
        parser.error("--pipelined-capacitor-current requires --pipelined-columns")
    if (args.pipelined_maximum and not args.pipelined_finish
            and not args.decoupled_maximum):
        parser.error(
            "--pipelined-maximum without --pipelined-finish requires "
            "--decoupled-maximum"
        )
    if args.decoupled_maximum and not args.pipelined_maximum:
        parser.error("--decoupled-maximum requires --pipelined-maximum")
    if args.serial_maximum and (
        args.pipelined_maximum or args.decoupled_maximum
    ):
        parser.error("--serial-maximum is exclusive with pipelined maximum modes")
    if args.shared_capacitor_multiplier and not args.pipelined_columns:
        parser.error(
            "--shared-capacitor-multiplier requires --pipelined-columns"
        )
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    subprocess.run(
        [sys.executable, "scripts/generate_wide_network_vectors.py"],
        cwd=ROOT,
        check=True,
    )
    tests = [
        (
            "network_rhs_v1_wide_tb",
            "build/verilator_network_rhs_wide",
            [
                "rtl/circuit/network_rhs_v1_wide.sv",
                "sim/unit/network_rhs_v1_wide_tb.sv",
            ],
        ),
        (
            "network_kcl_v1_wide_tb",
            "build/verilator_network_kcl_wide",
            [
                "rtl/circuit/network_kcl_v1_wide.sv",
                "sim/unit/network_kcl_v1_wide_tb.sv",
            ],
        ),
    ]
    for top, build_relative, sources in tests:
        parameter_args = []
        if top == "network_kcl_v1_wide_tb":
            if args.pipelined_finish:
                parameter_args.append("-GPIPELINED_FINISH=1")
            if args.pipelined_columns:
                parameter_args.append("-GPIPELINED_COLUMNS=1")
            if args.pipelined_accumulator:
                parameter_args.append("-GPIPELINED_ACCUMULATOR=1")
            if args.pipelined_capacitor_current:
                parameter_args.append("-GPIPELINED_CAPACITOR_CURRENT=1")
            if args.pipelined_maximum:
                parameter_args.append("-GPIPELINED_MAXIMUM=1")
            if args.decoupled_maximum:
                parameter_args.append("-GDECOUPLED_MAXIMUM=1")
            if args.serial_maximum:
                parameter_args.append("-GSERIAL_MAXIMUM=1")
            if args.shared_capacitor_multiplier:
                parameter_args.append("-GSHARED_CAPACITOR_MULTIPLIER=1")
        subprocess.run(
            [
                verilator,
                "--lint-only",
                "--timing",
                "-Wall",
                "-Wno-fatal",
                "-sv",
                *parameter_args,
                *sources,
            ],
            cwd=ROOT,
            check=True,
        )
        build = ROOT / (
            build_relative
            + ("_pipelined_finish" if args.pipelined_finish else "")
            + ("_pipelined_columns" if args.pipelined_columns else "")
            + ("_pipelined_accumulator" if args.pipelined_accumulator else "")
            + (
                "_pipelined_capacitor_current"
                if args.pipelined_capacitor_current
                else ""
            )
            + ("_pipelined_maximum" if args.pipelined_maximum else "")
            + ("_decoupled_maximum" if args.decoupled_maximum else "")
            + ("_serial_maximum" if args.serial_maximum else "")
            + (
                "_shared_capacitor_multiplier"
                if args.shared_capacitor_multiplier
                else ""
            )
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
        subprocess.run([str(build / f"V{top}")], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
