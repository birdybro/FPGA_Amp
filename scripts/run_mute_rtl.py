#!/usr/bin/env python3
"""Lint and verify the standalone output safety ramp."""

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
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    sources = [
        "rtl/audio/output_mute_ramp.sv",
        "sim/unit/output_mute_ramp_tb.sv",
    ]
    subprocess.run(
        [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    build = REPOSITORY_ROOT / "build" / "verilator_output_mute_ramp"
    subprocess.run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "output_mute_ramp_tb",
            "--Mdir",
            str(build),
            *sources,
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    subprocess.run(
        [str(build / "Voutput_mute_ramp_tb")], cwd=REPOSITORY_ROOT, check=True
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
