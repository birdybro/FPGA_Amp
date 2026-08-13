#!/usr/bin/env python3
"""Generate, lint, build, and run the V1 chord-corrector RTL test."""

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
    parser.add_argument("--lint-only", action="store_true")
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    sources = [
        "rtl/circuit/chord_corrector_v1.sv",
        "sim/unit/chord_corrector_v1_tb.sv",
    ]
    lint = [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources]
    subprocess.run(lint, cwd=REPOSITORY_ROOT, check=True)
    if args.lint_only:
        return 0
    subprocess.run(
        [sys.executable, "scripts/generate_chord_vectors.py"],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    build = REPOSITORY_ROOT / "build" / "verilator_chord"
    subprocess.run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "chord_corrector_v1_tb",
            "--Mdir",
            str(build),
            *sources,
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    subprocess.run(
        [
            str(build / "Vchord_corrector_v1_tb"),
            "+VECTORS=sim/vectors/generated/chord_corrector_random.txt",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
