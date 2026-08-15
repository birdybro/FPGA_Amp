#!/usr/bin/env python3
"""Lint and verify the DAC relay/XSMT output sequence."""

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
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    sources = [
        "rtl/io/dac_line_output_sequencer.sv",
        "sim/unit/dac_line_output_sequencer_tb.sv",
    ]
    subprocess.run(
        [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
        cwd=ROOT,
        check=True,
    )
    build = ROOT / "build" / "verilator_dac_line_output_sequencer"
    subprocess.run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "dac_line_output_sequencer_tb",
            "--Mdir",
            str(build),
            *sources,
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [str(build / "Vdac_line_output_sequencer_tb")],
        cwd=ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
