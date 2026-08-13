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
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    subprocess.run([sys.executable, "scripts/generate_wide_chord_vectors.py"], cwd=ROOT, check=True)
    sources = [
        "rtl/circuit/chord_corrector_v1_wide.sv",
        "sim/unit/chord_corrector_v1_wide_tb.sv",
    ]
    subprocess.run(
        [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
        cwd=ROOT,
        check=True,
    )
    build = ROOT / "build" / "verilator_chord_wide"
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
            *sources,
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run([str(build / "Vchord_corrector_v1_wide_tb")], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
