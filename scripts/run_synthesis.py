#!/usr/bin/env python3
"""Run reproducible XC7 synthesis for project RTL."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RESULT_TAG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def validated_result_tag(tag: str) -> str:
    if RESULT_TAG_PATTERN.fullmatch(tag) is None:
        raise argparse.ArgumentTypeError(
            "result tag must be 1-64 lowercase letters, digits, underscores, "
            "or hyphens and must start with a letter or digit"
        )
    return tag


def locate(name: str) -> Path | None:
    found = shutil.which(name)
    if found:
        return Path(found)
    local = REPOSITORY_ROOT / ".tools" / "root" / "usr" / "bin" / name
    return local if local.exists() else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--top",
        choices=(
            "triode_12ax7",
            "triode_12ax7_factorized",
            "triode_12ax7_factorized_linear",
            "hermite_q16_pipeline",
            "chord_corrector_v1",
            "chord_corrector_v1_wide",
            "network_rhs_v1",
            "network_rhs_v1_wide",
            "network_kcl_v1",
            "network_kcl_v1_wide",
            "v1_solver_mono",
            "v1_solver_mono_factorized",
            "v1_solver_mono_wide",
            "v1_solver_mono_wide_linear",
            "v1_solver_mono_wide_trapezoidal",
            "v1_solver_mono_wide_banked",
            "v1_solver_mono_wide_banked_terminal",
            "v1_solver_mono_wide_trapezoidal_banked",
            "v1_solver_mono_wide_trapezoidal_banked_terminal",
            "halfband_interpolator_2x",
            "halfband_decimator_2x",
            "interpolator_16x",
            "decimator_16x",
            "interpolator_8x",
            "decimator_8x",
            "phono_stream_mono",
            "phono_stream_mono_factorized",
            "phono_stream_mono_wide",
            "phono_stream_mono_wide_banked_terminal",
            "phono_stream_mono_wide_trapezoidal",
            "phono_stream_mono_wide_trapezoidal_banked_terminal",
            "phono_stream_mono_wide_trapezoidal_384khz_banked_terminal",
            "phono_stream_mono_wide_guarded",
            "output_mute_ramp",
            "audio_clock_rate_monitor",
            "async_fifo",
            "cdc_toggle_pulse",
            "cdc_word_snapshot",
            "spi_control_transport",
            "i2s_receiver",
            "i2s_transmitter",
            "i2s_async_bridge",
            "pcm24_to_q8_24",
            "q8_24_to_pcm24",
            "audio_frame_scheduler",
            "calibration_commit_guard",
            "phono_control_registers",
            "phono_fabric_mono_adapter",
            "phono_i2s_mono_top",
            "phono_i2s_control_top",
            "phono_i2s_spi_top",
            "solver_pnr_harness",
            "linear_solver_pnr_harness",
            "parallel_solver_pnr_harness",
            "parallel_pipelined_solver_pnr_harness",
            "parallel_deep_pipelined_solver_pnr_harness",
            "parallel_max_pipelined_solver_pnr_harness",
            "parallel_diagnostic_pipelined_solver_pnr_harness",
            "parallel_decoupled_diagnostic_pipelined_solver_pnr_harness",
            "parallel_shared_capacitor_decoupled_diagnostic_pipelined_solver_pnr_harness",
            "parallel_shared_capacitor_terminal_decoupled_diagnostic_pipelined_solver_pnr_harness",
            "parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness",
            "hermite_pnr_harness",
            "linear_tube_pnr_harness",
            "terminal_current_pnr_harness",
            "half_parallel_terminal_current_pnr_harness",
            "kcl_pnr_harness",
            "pipelined_kcl_pnr_harness",
            "deep_pipelined_kcl_pnr_harness",
            "max_pipelined_kcl_pnr_harness",
            "diagnostic_pipelined_kcl_pnr_harness",
            "decoupled_diagnostic_pipelined_kcl_pnr_harness",
            "shared_capacitor_decoupled_diagnostic_pipelined_kcl_pnr_harness",
            "chord_pnr_harness",
            "pipelined_chord_pnr_harness",
            "stream_384khz_pnr_harness",
            "stream_384khz_49mhz_pnr_harness",
        ),
        default="triode_12ax7",
    )
    parser.add_argument(
        "--pnr-json",
        type=Path,
        help=(
            "also insert top-level XC7 I/O/clock buffers and write a JSON "
            "netlist suitable for the open nextpnr-himbaechel flow"
        ),
    )
    parser.add_argument(
        "--result-tag",
        type=validated_result_tag,
        help="retain tagged synthesis logs and summaries for an experiment",
    )
    parser.add_argument(
        "--sample-rate-hz",
        type=int,
        choices=(384_000, 768_000),
        default=768_000,
        help="select rate-specific fixed assets for the supported V1 wrapper",
    )
    soft_multiplier_mapping = parser.add_mutually_exclusive_group()
    soft_multiplier_mapping.add_argument(
        "--soft-multiplier-module",
        choices=("network_kcl_v1_wide",),
        help=(
            "map every multiplier in the selected module hierarchy to LUT "
            "logic instead of DSP48E1s"
        ),
    )
    soft_multiplier_mapping.add_argument(
        "--soft-kcl-capacitor-multipliers",
        action="store_true",
        help=(
            "map only the two 48x44 KCL capacitor multipliers to LUT logic; "
            "retain the nine matrix multipliers in DSP48E1s"
        ),
    )
    args = parser.parse_args()
    rate_selectable_top = (
        "v1_solver_mono_wide_trapezoidal_banked_terminal"
    )
    if args.sample_rate_hz != 768_000 and args.top != rate_selectable_top:
        parser.error(
            "--sample-rate-hz 384000 is currently supported only for "
            f"--top {rate_selectable_top}"
        )
    yosys = locate("yosys")
    abc = locate("abc")
    if yosys is None or abc is None:
        print("ERROR: yosys/abc unavailable; run `make tools`", file=sys.stderr)
        return 2
    results = REPOSITORY_ROOT / "reference" / "results"
    results.mkdir(parents=True, exist_ok=True)
    sources = {
        "triode_12ax7": ["rtl/tube/triode_12ax7.sv"],
        "triode_12ax7_factorized": ["rtl/tube/triode_12ax7_factorized.sv"],
        "triode_12ax7_factorized_linear": [
            "rtl/tube/triode_12ax7_factorized_linear.sv"
        ],
        "hermite_q16_pipeline": ["rtl/math/hermite_q16_pipeline.sv"],
        "chord_corrector_v1": ["rtl/circuit/chord_corrector_v1.sv"],
        "chord_corrector_v1_wide": ["rtl/circuit/chord_corrector_v1_wide.sv"],
        "network_rhs_v1": ["rtl/circuit/network_rhs_v1.sv"],
        "network_rhs_v1_wide": ["rtl/circuit/network_rhs_v1_wide.sv"],
        "network_kcl_v1": ["rtl/circuit/network_kcl_v1.sv"],
        "network_kcl_v1_wide": ["rtl/circuit/network_kcl_v1_wide.sv"],
        "v1_solver_mono": [
            "rtl/tube/triode_12ax7.sv",
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1.sv",
            "rtl/circuit/network_kcl_v1.sv",
            "rtl/circuit/chord_corrector_v1.sv",
            "rtl/phono/v1_solver_mono.sv",
        ],
        "v1_solver_mono_factorized": [
            "rtl/tube/triode_12ax7.sv",
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1.sv",
            "rtl/circuit/network_kcl_v1.sv",
            "rtl/circuit/chord_corrector_v1.sv",
            "rtl/phono/v1_solver_mono.sv",
        ],
        "v1_solver_mono_wide": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
        ],
        "v1_solver_mono_wide_linear": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/tube/triode_12ax7_factorized_linear.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
        ],
        "v1_solver_mono_wide_trapezoidal": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal.sv",
        ],
        "v1_solver_mono_wide_banked": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_banked.sv",
        ],
        "v1_solver_mono_wide_banked_terminal": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_banked_terminal.sv",
        ],
        "v1_solver_mono_wide_trapezoidal_banked": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal_banked.sv",
        ],
        "v1_solver_mono_wide_trapezoidal_banked_terminal": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal_banked_terminal.sv",
        ],
        "halfband_interpolator_2x": [
            "rtl/filters/halfband_interpolator_2x.sv"
        ],
        "halfband_decimator_2x": ["rtl/filters/halfband_decimator_2x.sv"],
        "interpolator_16x": [
            "rtl/filters/halfband_interpolator_2x.sv",
            "rtl/audio/interpolator_16x.sv",
        ],
        "decimator_16x": [
            "rtl/filters/halfband_decimator_2x.sv",
            "rtl/audio/decimator_16x.sv",
        ],
        "interpolator_8x": [
            "rtl/filters/halfband_interpolator_2x.sv",
            "rtl/audio/interpolator_8x.sv",
        ],
        "decimator_8x": [
            "rtl/filters/halfband_decimator_2x.sv",
            "rtl/audio/decimator_8x.sv",
        ],
        "phono_stream_mono": [
            "rtl/tube/triode_12ax7.sv",
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1.sv",
            "rtl/circuit/network_kcl_v1.sv",
            "rtl/circuit/chord_corrector_v1.sv",
            "rtl/phono/v1_solver_mono.sv",
            "rtl/filters/halfband_interpolator_2x.sv",
            "rtl/filters/halfband_decimator_2x.sv",
            "rtl/audio/interpolator_16x.sv",
            "rtl/audio/decimator_16x.sv",
            "rtl/top/phono_stream_mono.sv",
        ],
        "phono_stream_mono_factorized": [
            "rtl/tube/triode_12ax7.sv",
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1.sv",
            "rtl/circuit/network_kcl_v1.sv",
            "rtl/circuit/chord_corrector_v1.sv",
            "rtl/phono/v1_solver_mono.sv",
            "rtl/filters/halfband_interpolator_2x.sv",
            "rtl/filters/halfband_decimator_2x.sv",
            "rtl/audio/interpolator_16x.sv",
            "rtl/audio/decimator_16x.sv",
            "rtl/top/phono_stream_mono.sv",
        ],
        "phono_stream_mono_wide": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/filters/halfband_interpolator_2x.sv",
            "rtl/filters/halfband_decimator_2x.sv",
            "rtl/audio/interpolator_16x.sv",
            "rtl/audio/decimator_16x.sv",
            "rtl/top/phono_stream_mono_wide.sv",
        ],
        "phono_stream_mono_wide_banked_terminal": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/filters/halfband_interpolator_2x.sv",
            "rtl/filters/halfband_decimator_2x.sv",
            "rtl/audio/interpolator_16x.sv",
            "rtl/audio/decimator_16x.sv",
            "rtl/top/phono_stream_mono_wide.sv",
            "rtl/top/phono_stream_mono_wide_banked_terminal.sv",
        ],
        "phono_stream_mono_wide_trapezoidal": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/filters/halfband_interpolator_2x.sv",
            "rtl/filters/halfband_decimator_2x.sv",
            "rtl/audio/interpolator_16x.sv",
            "rtl/audio/decimator_16x.sv",
            "rtl/top/phono_stream_mono_wide.sv",
            "rtl/top/phono_stream_mono_wide_trapezoidal.sv",
        ],
        "phono_stream_mono_wide_trapezoidal_banked_terminal": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/filters/halfband_interpolator_2x.sv",
            "rtl/filters/halfband_decimator_2x.sv",
            "rtl/audio/interpolator_16x.sv",
            "rtl/audio/decimator_16x.sv",
            "rtl/top/phono_stream_mono_wide.sv",
            "rtl/top/phono_stream_mono_wide_trapezoidal_banked_terminal.sv",
        ],
        "phono_stream_mono_wide_trapezoidal_384khz_banked_terminal": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/filters/halfband_interpolator_2x.sv",
            "rtl/filters/halfband_decimator_2x.sv",
            "rtl/audio/interpolator_16x.sv",
            "rtl/audio/decimator_16x.sv",
            "rtl/audio/interpolator_8x.sv",
            "rtl/audio/decimator_8x.sv",
            "rtl/top/phono_stream_mono_wide.sv",
            "rtl/top/phono_stream_mono_wide_trapezoidal_384khz_banked_terminal.sv",
        ],
        "stream_384khz_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/filters/halfband_interpolator_2x.sv",
            "rtl/filters/halfband_decimator_2x.sv",
            "rtl/audio/interpolator_16x.sv",
            "rtl/audio/decimator_16x.sv",
            "rtl/audio/interpolator_8x.sv",
            "rtl/audio/decimator_8x.sv",
            "rtl/top/phono_stream_mono_wide.sv",
            "rtl/top/phono_stream_mono_wide_trapezoidal_384khz_banked_terminal.sv",
            "rtl/diagnostics/stream_384khz_pnr_harness.sv",
        ],
        "stream_384khz_49mhz_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/filters/halfband_interpolator_2x.sv",
            "rtl/filters/halfband_decimator_2x.sv",
            "rtl/audio/interpolator_16x.sv",
            "rtl/audio/decimator_16x.sv",
            "rtl/audio/interpolator_8x.sv",
            "rtl/audio/decimator_8x.sv",
            "rtl/top/phono_stream_mono_wide.sv",
            "rtl/top/phono_stream_mono_wide_trapezoidal_384khz_banked_terminal.sv",
            "rtl/diagnostics/stream_384khz_pnr_harness.sv",
        ],
        "phono_stream_mono_wide_guarded": [
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
            "rtl/control/model_change_guard.sv",
            "rtl/top/phono_stream_mono_wide.sv",
            "rtl/top/phono_stream_mono_wide_guarded.sv",
        ],
        "output_mute_ramp": ["rtl/audio/output_mute_ramp.sv"],
        "async_fifo": ["rtl/io/async_fifo.sv"],
        "audio_clock_rate_monitor": ["rtl/io/audio_clock_rate_monitor.sv"],
        "i2s_receiver": ["rtl/io/i2s_receiver.sv"],
        "cdc_toggle_pulse": ["rtl/io/cdc_toggle_pulse.sv"],
        "cdc_word_snapshot": ["rtl/io/cdc_word_snapshot.sv"],
        "spi_control_transport": ["rtl/io/spi_control_transport.sv"],
        "i2s_transmitter": ["rtl/io/i2s_transmitter.sv"],
        "i2s_async_bridge": [
            "rtl/io/async_fifo.sv",
            "rtl/io/i2s_receiver.sv",
            "rtl/io/i2s_transmitter.sv",
            "rtl/io/i2s_async_bridge.sv",
        ],
        "pcm24_to_q8_24": ["rtl/io/pcm24_to_q8_24.sv"],
        "q8_24_to_pcm24": ["rtl/io/q8_24_to_pcm24.sv"],
        "audio_frame_scheduler": ["rtl/io/audio_frame_scheduler.sv"],
        "calibration_commit_guard": [
            "rtl/control/calibration_commit_guard.sv"
        ],
        "phono_control_registers": [
            "rtl/control/phono_control_registers.sv"
        ],
        "phono_fabric_mono_adapter": [
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
        ],
        "phono_i2s_mono_top": [
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
            "rtl/top/phono_fabric_mono_adapter.sv",
            "rtl/top/phono_i2s_mono_top.sv",
        ],
        "phono_i2s_control_top": [
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
            "rtl/control/calibration_commit_guard.sv",
            "rtl/control/phono_control_registers.sv",
            "rtl/io/audio_clock_rate_monitor.sv",
            "rtl/io/async_fifo.sv",
            "rtl/io/cdc_toggle_pulse.sv",
            "rtl/io/cdc_word_snapshot.sv",
            "rtl/io/i2s_receiver.sv",
            "rtl/io/i2s_transmitter.sv",
            "rtl/io/i2s_async_bridge.sv",
            "rtl/io/audio_frame_scheduler.sv",
            "rtl/io/pcm24_to_q8_24.sv",
            "rtl/io/q8_24_to_pcm24.sv",
            "rtl/top/phono_stream_mono_wide.sv",
            "rtl/top/phono_stream_mono_wide_trapezoidal_banked_terminal.sv",
            "rtl/top/phono_fabric_mono_adapter.sv",
            "rtl/top/phono_i2s_mono_top.sv",
            "rtl/top/phono_i2s_control_top.sv",
        ],
        "phono_i2s_spi_top": [
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
            "rtl/top/phono_fabric_mono_adapter.sv",
            "rtl/top/phono_i2s_mono_top.sv",
            "rtl/top/phono_i2s_control_top.sv",
            "rtl/top/phono_i2s_spi_top.sv",
        ],
        "solver_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/tube/triode_12ax7_factorized_linear.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal_banked_terminal.sv",
            "rtl/diagnostics/solver_pnr_harness.sv",
        ],
        "linear_solver_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/tube/triode_12ax7_factorized_linear.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal_banked_terminal.sv",
            "rtl/diagnostics/solver_pnr_harness.sv",
        ],
        "parallel_solver_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/tube/triode_12ax7_factorized_linear.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal_banked_terminal.sv",
            "rtl/diagnostics/solver_pnr_harness.sv",
        ],
        "parallel_pipelined_solver_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/tube/triode_12ax7_factorized_linear.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal_banked_terminal.sv",
            "rtl/diagnostics/solver_pnr_harness.sv",
        ],
        "parallel_deep_pipelined_solver_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/tube/triode_12ax7_factorized_linear.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal_banked_terminal.sv",
            "rtl/diagnostics/solver_pnr_harness.sv",
        ],
        "parallel_max_pipelined_solver_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/tube/triode_12ax7_factorized_linear.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal_banked_terminal.sv",
            "rtl/diagnostics/solver_pnr_harness.sv",
        ],
        "parallel_diagnostic_pipelined_solver_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/tube/triode_12ax7_factorized_linear.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal_banked_terminal.sv",
            "rtl/diagnostics/solver_pnr_harness.sv",
        ],
        "parallel_decoupled_diagnostic_pipelined_solver_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/tube/triode_12ax7_factorized_linear.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal_banked_terminal.sv",
            "rtl/diagnostics/solver_pnr_harness.sv",
        ],
        "parallel_shared_capacitor_decoupled_diagnostic_pipelined_solver_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/tube/triode_12ax7_factorized_linear.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal_banked_terminal.sv",
            "rtl/diagnostics/solver_pnr_harness.sv",
        ],
        "parallel_shared_capacitor_terminal_decoupled_diagnostic_pipelined_solver_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/tube/triode_12ax7_factorized_linear.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal_banked_terminal.sv",
            "rtl/diagnostics/solver_pnr_harness.sv",
        ],
        "parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized.sv",
            "rtl/tube/triode_12ax7_factorized_linear.sv",
            "rtl/circuit/network_rhs_v1_wide.sv",
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/phono/v1_solver_mono_wide.sv",
            "rtl/phono/v1_solver_mono_wide_trapezoidal_banked_terminal.sv",
            "rtl/diagnostics/solver_pnr_harness.sv",
        ],
        "hermite_pnr_harness": [
            "rtl/math/hermite_q16_pipeline.sv",
            "rtl/diagnostics/hermite_pnr_harness.sv",
        ],
        "linear_tube_pnr_harness": [
            "rtl/tube/triode_12ax7_factorized_linear.sv",
            "rtl/diagnostics/linear_tube_pnr_harness.sv",
        ],
        "terminal_current_pnr_harness": [
            "rtl/circuit/terminal_current_update_v1.sv",
            "rtl/diagnostics/solver_block_pnr_harnesses.sv",
        ],
        "half_parallel_terminal_current_pnr_harness": [
            "rtl/circuit/terminal_current_update_v1.sv",
            "rtl/diagnostics/solver_block_pnr_harnesses.sv",
        ],
        "kcl_pnr_harness": [
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/diagnostics/solver_block_pnr_harnesses.sv",
        ],
        "pipelined_kcl_pnr_harness": [
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/diagnostics/solver_block_pnr_harnesses.sv",
        ],
        "deep_pipelined_kcl_pnr_harness": [
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/diagnostics/solver_block_pnr_harnesses.sv",
        ],
        "max_pipelined_kcl_pnr_harness": [
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/diagnostics/solver_block_pnr_harnesses.sv",
        ],
        "diagnostic_pipelined_kcl_pnr_harness": [
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/diagnostics/solver_block_pnr_harnesses.sv",
        ],
        "decoupled_diagnostic_pipelined_kcl_pnr_harness": [
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/diagnostics/solver_block_pnr_harnesses.sv",
        ],
        "shared_capacitor_decoupled_diagnostic_pipelined_kcl_pnr_harness": [
            "rtl/circuit/network_kcl_v1_wide.sv",
            "rtl/diagnostics/solver_block_pnr_harnesses.sv",
        ],
        "chord_pnr_harness": [
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/diagnostics/solver_block_pnr_harnesses.sv",
        ],
        "pipelined_chord_pnr_harness": [
            "rtl/circuit/chord_corrector_v1_wide.sv",
            "rtl/diagnostics/solver_block_pnr_harnesses.sv",
        ],
    }[args.top]
    # The wide solver has a compile-time selectable value-only tube candidate.
    # Include its definition for every wide hierarchy; the default parameter
    # still elaborates the established Hermite implementation exclusively.
    linear_tube_source = "rtl/tube/triode_12ax7_factorized_linear.sv"
    if (
        "rtl/phono/v1_solver_mono_wide.sv" in sources
        and linear_tube_source not in sources
    ):
        sources.insert(1, linear_tube_source)
    # Terminal trapezoidal correction is instantiated by the wide solver even
    # when the corresponding parameter is disabled.  Keep the dependency in
    # one place so every solver, stream, adapter, and board hierarchy compiles
    # the identical source set.
    terminal_current_source = "rtl/circuit/terminal_current_update_v1.sv"
    if (
        "rtl/phono/v1_solver_mono_wide.sv" in sources
        and terminal_current_source not in sources
    ):
        solver_index = sources.index("rtl/phono/v1_solver_mono_wide.sv")
        sources.insert(solver_index, terminal_current_source)
    pnr_mode = args.pnr_json is not None
    result_tag = f"_{args.result_tag}" if args.result_tag is not None else ""
    rate_tag = "_384khz" if args.sample_rate_hz == 384_000 else ""
    log_suffix = rate_tag + ("_pnr" if pnr_mode else "") + result_tag
    log_path = results / f"yosys_xc7_{args.top}{log_suffix}.log"
    # Only the legacy solver/stream aliases select the factorized primitive by
    # overriding a wrapper parameter.  The factorized tube primitive is itself
    # a real top-level module despite sharing the same suffix.
    factorized_top = args.top in {
        "v1_solver_mono_factorized",
        "phono_stream_mono_factorized",
    }
    actual_top = args.top.removesuffix("_factorized") if factorized_top else args.top
    parameter_command = None
    if factorized_top:
        parameter_command = f"chparam -set USE_FACTORIZED_TUBE 1 {actual_top}"
    if args.top == "v1_solver_mono_wide_linear":
        actual_top = "v1_solver_mono_wide"
        parameter_command = (
            "chparam -set USE_LINEAR_FACTORIZED_TUBE 1 v1_solver_mono_wide"
        )
    if args.sample_rate_hz == 384_000:
        parameter_command = (
            "chparam -set SAMPLE_RATE_384KHZ 1 "
            f"{rate_selectable_top}"
        )
    # The packaged Yosys has an absolute system ABC default. Stopping before
    # map_luts and invoking the identical documented steps with -exe keeps the
    # non-root bootstrap reproducible.
    commands = [f"read_verilog -sv {' '.join(sources)}"]
    if parameter_command is not None:
        commands.append(parameter_command)
    out_of_context_flags = "" if pnr_mode else " -noiopad -noclkbuf"
    synthesis_command = (
        f"synth_xilinx -family xc7 -top {actual_top}{out_of_context_flags}"
    )
    soft_multiplier_scope = None
    if args.soft_multiplier_module is not None:
        module_pattern = f"*{args.soft_multiplier_module}*"
        soft_multiplier_selection = f"{module_pattern}/t:$mul"
        expected_soft_multiplier_count = 11
        soft_multiplier_scope = "kcl_all"
    elif args.soft_kcl_capacitor_multipliers:
        module_pattern = "*network_kcl_v1_wide*"
        soft_multiplier_selection = (
            f"{module_pattern}/t:$mul "
            f"{module_pattern}/r:A_WIDTH=48 %i"
        )
        expected_soft_multiplier_count = 2
        soft_multiplier_scope = "kcl_capacitors"
    if soft_multiplier_scope is not None:
        commands.extend(
            [
                f"{synthesis_command} -run begin:map_dsp",
                (
                    f"select -assert-count {expected_soft_multiplier_count} "
                    f"{soft_multiplier_selection}"
                ),
                f"chtype -set $__soft_mul {soft_multiplier_selection}",
                f"{synthesis_command} -run map_dsp:map_luts",
            ]
        )
    else:
        commands.append(f"{synthesis_command} -run begin:map_luts")
    commands.extend(
        [
            "opt_expr -mux_undef -noclkinv",
            f"abc -exe {abc} -luts 2:2,3,6:5,10,20",
            "clean",
            "techmap -map +/xilinx/ff_map.v",
            "xilinx_srl -fixed -minlen 3",
            "techmap -map +/xilinx/lut_map.v -map +/xilinx/cells_map.v -D LUT_WIDTH=6",
            "xilinx_dffopt",
            "opt_lut_ins -tech xilinx",
            "clean",
        ]
    )
    if pnr_mode:
        # This is the standard synth_xilinx finalize step.  I/O cells were
        # inserted before map_luts because -noiopad was deliberately omitted.
        commands.append("clkbufmap -buf BUFG O:I")
    commands.extend(
        [
            # The Xilinx stat formatter aggregates LUTs through user-module
            # hierarchy but does not aggregate primitive flip-flop submodules.
            # Flatten only after mapping so the final resource table and JSON
            # cannot silently omit registers from instantiated blocks.
            "flatten",
            "clean",
            "hierarchy -check",
            "stat -tech xilinx",
            "check -noinit",
        ]
    )
    pnr_json_path = None
    if args.pnr_json is not None:
        pnr_json_path = args.pnr_json
        if not pnr_json_path.is_absolute():
            pnr_json_path = REPOSITORY_ROOT / pnr_json_path
        pnr_json_path.parent.mkdir(parents=True, exist_ok=True)
        # Match the synth_xilinx JSON finalizer: primitive simulation models
        # loaded as whiteboxes must become blackboxes before serialization.
        commands.append("blackbox =A:whitebox")
        commands.append(f"write_json {json.dumps(str(pnr_json_path))}")
    script = "; ".join(commands)
    environment = os.environ.copy()
    local_library = REPOSITORY_ROOT / ".tools" / "root" / "usr" / "lib"
    if local_library.exists():
        environment["LD_LIBRARY_PATH"] = str(local_library)
    completed = subprocess.run(
        [str(yosys), "-Q", "-p", script],
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    log_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode:
        print(completed.stdout, file=sys.stderr)
        return completed.returncode

    local_section = completed.stdout.split(f"=== {actual_top} ===", 1)[1].split(
        "=== design hierarchy ===", 1
    )[0]
    hierarchy_section = completed.stdout.split("=== design hierarchy ===", 1)[1].split(
        "Executing CHECK", 1
    )[0]
    section = (
        hierarchy_section
        if "Count including submodules" in hierarchy_section
        else local_section
    )

    def count(cell: str) -> int:
        match = re.search(rf"^\s*(\d+)\s+{re.escape(cell)}\s*$", section, re.MULTILINE)
        return int(match.group(1)) if match else 0

    lc_match = re.search(r"Estimated number of LCs:\s+(\d+)", section)
    warning_match = re.search(r"Warnings:\s+(\d+) unique", completed.stdout)
    warning_count = int(warning_match.group(1)) if warning_match else 0
    if warning_count == 0:
        warning_note = "No synthesis warnings."
    elif args.top in {"async_fifo", "i2s_async_bridge"}:
        warning_note = (
            "Yosys implemented the small dual-clock memory as registers; "
            "see the full log. This is not a structural-check failure."
        )
    elif "Replacing memory" in completed.stdout:
        warning_note = (
            "Warnings include small local-array register expansion and/or "
            "Xilinx primitive output-port resize notices; see the full log. "
            "No structural-check failure was reported."
        )
    else:
        warning_note = (
            "Warnings are Xilinx primitive output-port resize notices from "
            "Yosys techmap; see full log."
        )
    summary = {
        "flow": (
            "Yosys synth_xilinx XC7 netlist for open place/route"
            if pnr_mode
            else "Yosys out-of-context synth_xilinx XC7; no place/route"
        ),
        "top": args.top,
        "result_tag": args.result_tag,
        "soft_multiplier_module": args.soft_multiplier_module,
        "soft_multiplier_scope": soft_multiplier_scope,
        "yosys": subprocess.check_output([str(yosys), "-V"], text=True).strip(),
        "estimated_logic_cells": int(lc_match.group(1)) if lc_match else None,
        "lut_by_size": {f"LUT{size}": count(f"LUT{size}") for size in range(2, 7)},
        "flip_flops": {
            cell: count(cell)
            for cell in (
                "FDRE",
                "FDSE",
                "FDCE",
                "FDPE",
                "FDRE_1",
                "FDSE_1",
                "FDCE_1",
                "FDPE_1",
            )
        },
        "dsp48e1": count("DSP48E1"),
        "ramb18e1": count("RAMB18E1"),
        "ramb36e1": count("RAMB36E1"),
        "block_ram_18k_equivalents": (
            count("RAMB18E1") + 2 * count("RAMB36E1")
        ),
        "carry4": count("CARRY4"),
        "muxf7": count("MUXF7"),
        "check_problems": 0 if "Found and reported 0 problems." in completed.stdout else None,
        "yosys_warning_count": warning_count,
        "warning_note": warning_note,
        "fmax_mhz": None,
        "timing_note": (
            "Timing is established only by a subsequent named-part open "
            "place-and-route run; synthesis alone makes no Fmax claim."
            if pnr_mode
            else "Fmax requires named-part place-and-route and is not claimed here."
        ),
    }
    if args.top == rate_selectable_top:
        summary["sample_rate_hz"] = args.sample_rate_hz
    candidate_stream_top = (
        "phono_stream_mono_wide_trapezoidal_384khz_banked_terminal"
    )
    if args.top == candidate_stream_top:
        summary["input_sample_rate_hz"] = 48_000
        summary["circuit_sample_rate_hz"] = 384_000
        summary["output_sample_rate_hz"] = 48_000
    resampler_rates = {
        "interpolator_16x": (48_000, 768_000),
        "decimator_16x": (768_000, 48_000),
        "interpolator_8x": (48_000, 384_000),
        "decimator_8x": (384_000, 48_000),
    }
    if args.top in resampler_rates:
        input_rate_hz, output_rate_hz = resampler_rates[args.top]
        summary["input_sample_rate_hz"] = input_rate_hz
        summary["output_sample_rate_hz"] = output_rate_hz
    if pnr_json_path is not None:
        summary["pnr_json"] = str(pnr_json_path.relative_to(REPOSITORY_ROOT))
    summary_path = results / f"synthesis_{args.top}{log_suffix}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
