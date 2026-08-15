#!/usr/bin/env python3
"""Lint and verify the 48 kHz/128-fS PCM4202 receive boundary."""

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
        "rtl/io/async_fifo.sv",
        "rtl/io/i2s_receiver.sv",
        "rtl/io/i2s_transmitter.sv",
        "rtl/io/pcm4202_i2s_capture.sv",
        "sim/integration/pcm4202_i2s_capture_tb.sv",
    ]
    subprocess.run(
        [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
        cwd=ROOT,
        check=True,
    )
    build = ROOT / "build" / "verilator_pcm4202_i2s_capture"
    subprocess.run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "pcm4202_i2s_capture_tb",
            "--Mdir",
            str(build),
            *sources,
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run([str(build / "Vpcm4202_i2s_capture_tb")], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
