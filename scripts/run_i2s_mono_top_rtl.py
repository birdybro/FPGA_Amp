#!/usr/bin/env python3
"""Generate, lint, build, and verify the pin-facing I2S mono integration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REPORT_PREFIX = "LATENCY_REPORT "
I2S_BCLK_HZ = 3_072_000
SAMPLE_RATE_HZ = 48_000
CLOCK_MONITOR_EXPECTED_BCLK_EDGES = 1_024
CLOCK_MONITOR_EDGE_TOLERANCE = 1
CLOCK_MONITOR_LOCK_WINDOWS = 3


def _build_latency_report(
    markers: dict[str, int | float], *, internal_sample_rate_hz: int = 768_000
) -> dict[str, object]:
    if internal_sample_rate_hz == 384_000:
        fabric_hz = 49_152_000
        clock_monitor_window_fabric_clocks = 16_384
        expected_first_nonzero_output_index = 20
        expected_model_input_to_output_clocks = 265
    elif internal_sample_rate_hz == 768_000:
        fabric_hz = 98_304_000
        clock_monitor_window_fabric_clocks = 32_768
        expected_first_nonzero_output_index = 19
        # The circular-history decimator performs its center tap in a
        # dedicated cycle.  Four cascaded 2x stages therefore add four exact
        # fabric clocks relative to the pre-inference transport report.
        expected_model_input_to_output_clocks = 277
    else:
        raise ValueError("internal sample rate must be 384000 or 768000")
    if (
        int(markers["first_nonzero_output_index"])
        != expected_first_nonzero_output_index
    ):
        raise RuntimeError(
            "first quantized nonzero output changed: "
            f"{markers['first_nonzero_output_index']} != "
            f"{expected_first_nonzero_output_index}"
        )
    expected_differences = {
        "fabric_rx_to_model_input_clocks": 1,
        "model_input_to_output_clocks": expected_model_input_to_output_clocks,
        "model_output_to_calibrated_output_clocks": 2,
        "calibrated_output_to_tx_accept_clocks": 1,
        "adc_complete_to_dac_complete_bclks": 192,
        "model_frame_to_first_nonzero_bclks": (
            expected_first_nonzero_output_index * 64
        ),
    }
    measured_differences = {
        "fabric_rx_to_model_input_clocks": (
            int(markers["first_model_input_cycle"])
            - int(markers["first_fabric_rx_accept_cycle"])
        ),
        "model_input_to_output_clocks": (
            int(markers["first_model_output_cycle"])
            - int(markers["first_model_input_cycle"])
        ),
        "model_output_to_calibrated_output_clocks": (
            int(markers["first_calibrated_output_cycle"])
            - int(markers["first_model_output_cycle"])
        ),
        "calibrated_output_to_tx_accept_clocks": (
            int(markers["first_fabric_tx_accept_cycle"])
            - int(markers["first_calibrated_output_cycle"])
        ),
        "adc_complete_to_dac_complete_bclks": (
            int(markers["first_dac_model_frame_bclk"])
            - int(markers["first_adc_frame_complete_bclk"])
        ),
        "model_frame_to_first_nonzero_bclks": (
            int(markers["first_nonzero_dac_frame_bclk"])
            - int(markers["first_dac_model_frame_bclk"])
        ),
    }
    if measured_differences != expected_differences:
        raise RuntimeError(
            "pin-top latency changed: "
            f"measured={measured_differences}, expected={expected_differences}"
        )
    expected_watermarks = {
        "rx_fifo_i2s_high_water": 1,
        "rx_fifo_fabric_high_water": 1,
        "tx_fifo_fabric_high_water": 1,
        "tx_fifo_i2s_high_water": 1,
    }
    measured_watermarks = {
        name: int(markers[name]) for name in expected_watermarks
    }
    if measured_watermarks != expected_watermarks:
        raise RuntimeError(
            "locked-rate FIFO occupancy changed: "
            f"measured={measured_watermarks}, expected={expected_watermarks}"
        )
    expected_clock_monitor = {
        "audio_clock_measured_bclk_edges": CLOCK_MONITOR_EXPECTED_BCLK_EDGES,
        "audio_clock_good_windows": CLOCK_MONITOR_LOCK_WINDOWS,
        "audio_clock_measurement_count": 4,
    }
    measured_clock_monitor = {
        name: int(markers[name]) for name in expected_clock_monitor
    }
    if measured_clock_monitor != expected_clock_monitor:
        raise RuntimeError(
            "audio clock monitor changed: "
            f"measured={measured_clock_monitor}, "
            f"expected={expected_clock_monitor}"
        )

    def delta_ns(end: str, start: str) -> float:
        return float(markers[end]) - float(markers[start])

    end_to_end_ns = delta_ns(
        "first_dac_model_frame_ns", "first_adc_frame_complete_ns"
    )
    expected_end_to_end_ns = (
        measured_differences["adc_complete_to_dac_complete_bclks"]
        * 1.0e9
        / I2S_BCLK_HZ
    )
    if abs(end_to_end_ns - expected_end_to_end_ns) > 0.001:
        raise RuntimeError(
            "absolute I2S rate changed: timestamp latency "
            f"{end_to_end_ns:.9f} ns != clock-count latency "
            f"{expected_end_to_end_ns:.9f} ns"
        )
    intervals = {
        **measured_differences,
        "adc_complete_to_fabric_rx_accept_ns": delta_ns(
            "first_fabric_rx_accept_ns", "first_adc_frame_complete_ns"
        ),
        "model_input_to_output_ns": delta_ns(
            "first_model_output_ns", "first_model_input_ns"
        ),
        "fabric_tx_accept_to_fifo_read_ns": delta_ns(
            "first_tx_fifo_read_ns", "first_fabric_tx_accept_ns"
        ),
        "fifo_read_to_serial_frame_start_ns": delta_ns(
            "first_tx_serial_frame_start_ns", "first_tx_fifo_read_ns"
        ),
        "serial_frame_start_to_dac_complete_ns": delta_ns(
            "first_dac_model_frame_ns", "first_tx_serial_frame_start_ns"
        ),
        "adc_complete_to_dac_complete_simulation_ns": end_to_end_ns,
        "adc_complete_to_dac_complete_clock_derived_ns": expected_end_to_end_ns,
        "adc_complete_to_dac_complete_samples": (
            measured_differences["adc_complete_to_dac_complete_bclks"]
            * SAMPLE_RATE_HZ
            / I2S_BCLK_HZ
        ),
        "first_model_frame_to_first_nonzero_ns": delta_ns(
            "first_nonzero_dac_frame_ns", "first_dac_model_frame_ns"
        ),
    }
    return {
        "schema_version": 1,
        "scope": "RTL serial-frame transport at configured locked clocks",
        "clock_contract": {
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "i2s_bclk_hz": I2S_BCLK_HZ,
            "fabric_hz": fabric_hz,
            "sample_bits": 24,
            "slot_bits": 32,
            "rate_monitor": {
                "window_fabric_clocks": clock_monitor_window_fabric_clocks,
                "expected_bclk_edges": CLOCK_MONITOR_EXPECTED_BCLK_EDGES,
                "edge_tolerance": CLOCK_MONITOR_EDGE_TOLERANCE,
                "lock_windows": CLOCK_MONITOR_LOCK_WINDOWS,
            },
        },
        "markers": markers,
        "intervals": intervals,
        "locked_rate_fifo_high_water": measured_watermarks,
        "audio_clock_rate_monitor": measured_clock_monitor,
        "interpretation": {
            "frame_boundary_latency": (
                "From the first complete ADC PCM frame to completion of the "
                "first corresponding valid model-output DAC frame."
            ),
            "not_group_delay": (
                "Valid transport latency and first quantized nonzero index do "
                "not replace the separately measured FIR/circuit group delay."
            ),
            "excluded": (
                "ADC/DAC digital filters, converter aperture, analog filters, "
                "and board propagation are not simulated."
            ),
            "fifo_level_semantics": (
                "Each watermark is local to the named clock domain; write-side "
                "levels conservatively lag reads high and read-side levels lag "
                "writes low. They are not a coherent multi-clock snapshot."
            ),
            "clock_monitor_scope": (
                "The Gray edge-counter monitor checks BCLK frequency against "
                "fabric windows; it does not establish phase, perform rate "
                "matching, or replace placed CDC timing constraints."
            ),
        },
    }


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
            cwd=REPOSITORY_ROOT,
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
        "rtl/io/audio_clock_rate_monitor.sv",
        "rtl/io/async_fifo.sv",
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
        "sim/integration/phono_i2s_mono_top_tb.sv",
    ]
    common = [
        "--timing",
        "-Wall",
        "-Wno-fatal",
        "-sv",
        "--top-module",
        "phono_i2s_mono_top_tb",
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
    subprocess.run(
        [verilator, "--lint-only", *common],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    rate_suffix = "_384khz" if args.sample_rate_hz == 384_000 else ""
    build = (
        REPOSITORY_ROOT / "build" / f"verilator_phono_i2s_mono_top{rate_suffix}"
    )
    subprocess.run(
        [verilator, "--binary", *common, "--Mdir", str(build)],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    simulation = subprocess.run(
        [str(build / "Vphono_i2s_mono_top_tb")],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(simulation.stdout)
    sys.stderr.write(simulation.stderr)
    match = re.search(
        r"^" + REPORT_PREFIX + r"(\{.*\})$",
        simulation.stdout,
        flags=re.MULTILINE,
    )
    if match is None:
        raise RuntimeError("pin-top simulation did not emit a latency report")
    report = _build_latency_report(
        json.loads(match.group(1)), internal_sample_rate_hz=args.sample_rate_hz
    )
    report_path = (
        REPOSITORY_ROOT
        / f"model/generated/phono_i2s_mono_top{rate_suffix}_latency.json"
    )
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
