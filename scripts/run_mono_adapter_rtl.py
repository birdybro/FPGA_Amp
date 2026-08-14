#!/usr/bin/env python3
"""Generate, lint, build, and verify the calibrated fabric mono adapter."""

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
    parser.add_argument("--skip-generate", action="store_true")
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2

    generators = [
        [sys.executable, "scripts/generate_wide_network_vectors.py"],
        [sys.executable, "scripts/generate_trapezoidal_network_vectors.py"],
        [
            sys.executable,
            "scripts/generate_wide_chord_vectors.py",
            "--trapezoidal",
            "--banked",
        ],
        [sys.executable, "scripts/generate_factorized_tube.py"],
        [
            sys.executable,
            "scripts/generate_wide_solver_vectors.py",
            "--trapezoidal",
            "--banked",
            "--terminal-correction",
        ],
        [sys.executable, "scripts/generate_halfband_rtl_vectors.py"],
        [sys.executable, "scripts/generate_mono_adapter_vectors.py"],
    ]
    if not args.skip_generate:
        for command in generators:
            subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)

    sources = [
        "rtl/tube/triode_12ax7_factorized.sv",
        "rtl/circuit/network_rhs_v1_wide.sv",
        "rtl/circuit/network_kcl_v1_wide.sv",
        "rtl/circuit/chord_corrector_v1_wide.sv",
        "rtl/phono/v1_solver_mono_wide.sv",
        "rtl/filters/halfband_interpolator_2x.sv",
        "rtl/filters/halfband_decimator_2x.sv",
        "rtl/audio/interpolator_16x.sv",
        "rtl/audio/decimator_16x.sv",
        "rtl/audio/output_mute_ramp.sv",
        "rtl/io/audio_frame_scheduler.sv",
        "rtl/io/pcm24_to_q8_24.sv",
        "rtl/io/q8_24_to_pcm24.sv",
        "rtl/top/phono_stream_mono_wide.sv",
        "rtl/top/phono_stream_mono_wide_trapezoidal_banked_terminal.sv",
        "rtl/top/phono_fabric_mono_adapter.sv",
        "sim/integration/phono_fabric_mono_adapter_tb.sv",
    ]
    common = [
        verilator,
        "--timing",
        "-Wall",
        "-Wno-fatal",
        "-sv",
        "--top-module",
        "phono_fabric_mono_adapter_tb",
        *sources,
    ]
    subprocess.run(
        [verilator, "--lint-only", *common[1:]],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    build = REPOSITORY_ROOT / "build" / "verilator_phono_fabric_mono_adapter"
    subprocess.run(
        [
            verilator,
            "--binary",
            *common[1:],
            "--Mdir",
            str(build),
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    subprocess.run(
        [str(build / "Vphono_fabric_mono_adapter_tb")],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
