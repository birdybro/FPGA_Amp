#!/usr/bin/env python3
"""Verify the bidirectional I2S/fabric asynchronous bridge."""

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
        "rtl/io/i2s_async_bridge.sv",
        "sim/integration/i2s_async_bridge_tb.sv",
    ]
    subprocess.run(
        [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
        cwd=ROOT,
        check=True,
    )
    build = ROOT / "build" / "verilator_i2s_async_bridge"
    subprocess.run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "i2s_async_bridge_tb",
            "--Mdir",
            str(build),
            *sources,
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run([str(build / "Vi2s_async_bridge_tb")], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
