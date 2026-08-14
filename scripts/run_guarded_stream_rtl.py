#!/usr/bin/env python3
"""Lint and verify model-change sequencing around the complete wide stream."""

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
    for generator in (
        "scripts/generate_wide_network_vectors.py",
        "scripts/generate_wide_chord_vectors.py",
        "scripts/generate_factorized_tube.py",
        "scripts/generate_halfband_rtl_vectors.py",
    ):
        subprocess.run([sys.executable, generator], cwd=ROOT, check=True)
    sources = [
        "rtl/tube/triode_12ax7_factorized.sv",
        "rtl/circuit/network_rhs_v1_wide.sv",
        "rtl/circuit/network_kcl_v1_wide.sv",
        "rtl/circuit/chord_corrector_v1_wide.sv",
        "rtl/circuit/terminal_current_update_v1.sv",
        "rtl/phono/v1_solver_mono_wide.sv",
        "rtl/filters/halfband_interpolator_2x.sv",
        "rtl/filters/halfband_decimator_2x.sv",
        "rtl/audio/interpolator_16x.sv",
        "rtl/audio/decimator_16x.sv",
        "rtl/audio/output_mute_ramp.sv",
        "rtl/control/model_change_guard.sv",
        "rtl/top/phono_stream_mono_wide.sv",
        "rtl/top/phono_stream_mono_wide_guarded.sv",
        "sim/integration/phono_stream_mono_wide_guarded_tb.sv",
    ]
    subprocess.run(
        [verilator, "--lint-only", "--timing", "-Wall", "-Wno-fatal", "-sv", *sources],
        cwd=ROOT,
        check=True,
    )
    build = ROOT / "build" / "verilator_phono_stream_mono_wide_guarded"
    subprocess.run(
        [
            verilator,
            "--binary",
            "--timing",
            "-Wall",
            "-Wno-fatal",
            "-sv",
            "--top-module",
            "phono_stream_mono_wide_guarded_tb",
            "--Mdir",
            str(build),
            *sources,
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [str(build / "Vphono_stream_mono_wide_guarded_tb")],
        cwd=ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
