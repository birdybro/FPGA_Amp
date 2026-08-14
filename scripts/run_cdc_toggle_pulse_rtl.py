#!/usr/bin/env python3
"""Lint and verify the unrelated-clock command-pulse crossing."""

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
        "rtl/io/cdc_toggle_pulse.sv",
        "sim/unit/cdc_toggle_pulse_tb.sv",
    ]
    common = [
        "--timing", "-Wall", "-Wno-fatal", "-sv",
        "--top-module", "cdc_toggle_pulse_tb", *sources,
    ]
    subprocess.run([verilator, "--lint-only", *common], cwd=ROOT, check=True)
    build = ROOT / "build" / "verilator_cdc_toggle_pulse"
    subprocess.run(
        [verilator, "--binary", *common, "--Mdir", str(build)],
        cwd=ROOT,
        check=True,
    )
    subprocess.run([str(build / "Vcdc_toggle_pulse_tb")], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
