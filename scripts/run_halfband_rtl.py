#!/usr/bin/env python3
"""Generate, lint, and verify the serial half-band RTL primitives."""

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
        [sys.executable, "scripts/generate_halfband_rtl_vectors.py"],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    tests = (
        ("halfband_interpolator_2x", "halfband_interpolator_2x_tb"),
        ("halfband_decimator_2x", "halfband_decimator_2x_tb"),
    )
    for module, top in tests:
        sources = [f"rtl/filters/{module}.sv", f"sim/unit/{top}.sv"]
        subprocess.run(
            [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
            cwd=REPOSITORY_ROOT,
            check=True,
        )
        build = REPOSITORY_ROOT / "build" / f"verilator_{module}"
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
                *sources,
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
        )
        subprocess.run([str(build / f"V{top}")], cwd=REPOSITORY_ROOT, check=True)
    integrations = (
        ("interpolator_16x", "interpolator_16x_tb"),
        ("decimator_16x", "decimator_16x_tb"),
    )
    for module, top in integrations:
        primitive = (
            "rtl/filters/halfband_interpolator_2x.sv"
            if module == "interpolator_16x"
            else "rtl/filters/halfband_decimator_2x.sv"
        )
        sources = [primitive, f"rtl/audio/{module}.sv", f"sim/integration/{top}.sv"]
        subprocess.run(
            [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
            cwd=REPOSITORY_ROOT,
            check=True,
        )
        build = REPOSITORY_ROOT / "build" / f"verilator_{module}"
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
                *sources,
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
        )
        subprocess.run([str(build / f"V{top}")], cwd=REPOSITORY_ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
