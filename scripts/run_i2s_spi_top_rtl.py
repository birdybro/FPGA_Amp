#!/usr/bin/env python3
"""Generate, lint, and verify the complete SPI-controlled I2S hierarchy."""

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
    parser.add_argument("--skip-generate", action="store_true")
    parser.add_argument(
        "--sample-rate-hz", type=int, choices=(384_000, 768_000), default=768_000
    )
    args = parser.parse_args()
    verilator = shutil.which(args.verilator)
    if verilator is None:
        print("ERROR: verilator unavailable", file=sys.stderr)
        return 2
    if not args.skip_generate:
        subprocess.run(
            [
                sys.executable,
                "scripts/run_mono_adapter_rtl.py",
                "--verilator",
                verilator,
                "--sample-rate-hz",
                str(args.sample_rate_hz),
            ],
            cwd=ROOT,
            check=True,
        )

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
        "rtl/audio/interpolator_8x.sv",
        "rtl/audio/decimator_8x.sv",
        "rtl/audio/output_mute_ramp.sv",
        "rtl/control/calibration_commit_guard.sv",
        "rtl/control/phono_control_registers.sv",
        "rtl/io/audio_clock_rate_monitor.sv",
        "rtl/io/async_fifo.sv",
        "rtl/io/cdc_toggle_pulse.sv",
        "rtl/io/cdc_word_snapshot.sv",
        "rtl/io/spi_control_transport.sv",
        "rtl/io/i2s_receiver.sv",
        "rtl/io/i2s_transmitter.sv",
        "rtl/io/i2s_async_bridge.sv",
        "rtl/io/audio_frame_scheduler.sv",
        "rtl/io/pcm24_to_q8_24.sv",
        "rtl/io/q8_24_to_pcm24.sv",
        "rtl/top/phono_stream_mono_wide.sv",
        "rtl/top/phono_stream_mono_wide_trapezoidal_banked_terminal.sv",
        "rtl/top/phono_stream_mono_wide_trapezoidal_384khz_banked_terminal.sv",
        "rtl/top/phono_fabric_mono_adapter.sv",
        "rtl/top/phono_i2s_mono_top.sv",
        "rtl/top/phono_i2s_control_top.sv",
        "rtl/top/phono_i2s_spi_top.sv",
        "sim/integration/phono_i2s_spi_top_tb.sv",
    ]
    common = [
        "--timing", "-Wall", "-Wno-fatal", "-sv",
        "--top-module", "phono_i2s_spi_top_tb",
        *(
            [
                "-GMODEL_SAMPLE_RATE_HZ=384000",
                "-GFABRIC_CLOCKS_PER_48K_INPUT=1024",
            ]
            if args.sample_rate_hz == 384_000
            else []
        ),
        *sources,
    ]
    subprocess.run([verilator, "--lint-only", *common], cwd=ROOT, check=True)
    rate_suffix = "_384khz" if args.sample_rate_hz == 384_000 else ""
    build = ROOT / "build" / f"verilator_phono_i2s_spi_top{rate_suffix}"
    subprocess.run(
        [verilator, "--binary", *common, "--Mdir", str(build)],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [str(build / "Vphono_i2s_spi_top_tb")], cwd=ROOT, check=True
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
