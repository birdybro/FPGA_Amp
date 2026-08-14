#!/usr/bin/env python3
"""Generate, lint, and verify the PCM24/Q8.24 calibration boundary."""

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

    subprocess.run(
        [sys.executable, "scripts/generate_calibration_vectors.py"],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    sources = [
        "rtl/io/pcm24_to_q8_24.sv",
        "rtl/io/q8_24_to_pcm24.sv",
        "sim/unit/audio_sample_calibration_tb.sv",
    ]
    subprocess.run(
        [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    build = REPOSITORY_ROOT / "build" / "verilator_audio_sample_calibration"
    subprocess.run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "audio_sample_calibration_tb",
            "--Mdir",
            str(build),
            *sources,
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    subprocess.run(
        [str(build / "Vaudio_sample_calibration_tb")],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
