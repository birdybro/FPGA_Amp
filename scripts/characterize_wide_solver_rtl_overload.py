#!/usr/bin/env python3
"""Capture wide-solver RTL through grid conduction, clipping, and recovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from characterize_overload_recovery import (  # noqa: E402
    burst_metrics,
    run_analytical,
    sustained_recovery_s,
)
from wide_solver_rtl_capture import capture_wide_solver_rtl  # noqa: E402


SAMPLE_RATE_HZ = 768_000.0
FREQUENCY_HZ = 1_000.0
NOMINAL_PEAK_V = 0.005
BURST_START_S = 0.010
BURST_END_S = 0.015
DURATION_S = 0.100
LEVELS_PEAK_V = (0.020, 0.500, 1.000, 1.500)


def input_trajectory_q24(level_peak_v: float) -> np.ndarray:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    amplitude = np.full(time_s.size, NOMINAL_PEAK_V)
    amplitude[(time_s >= BURST_START_S) & (time_s < BURST_END_S)] = level_peak_v
    return np.rint(
        amplitude * np.sin(2.0 * np.pi * FREQUENCY_HZ * time_s) * (1 << 24)
    ).astype(np.int64)


def level_tag(level_peak_v: float) -> str:
    return f"{level_peak_v:g}".replace(".", "p")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verilator", default="verilator")
    args = parser.parse_args()
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    burst_mask = (time_s >= BURST_START_S) & (time_s < BURST_END_S)
    post_index = int(round(BURST_END_S * SAMPLE_RATE_HZ))
    final_window = time_s >= DURATION_S - 0.010

    control_q24 = input_trajectory_q24(NOMINAL_PEAK_V)
    control_stimulus = control_q24.astype(np.float64) / float(1 << 24)
    analytical_control, _, _ = run_analytical(control_stimulus)
    control_capture = capture_wide_solver_rtl(
        control_q24, "wide_solver_rtl_overload_control", args.verilator
    )
    rtl_control = control_capture.rtl_output_q32.astype(np.float64) / float(1 << 32)
    nominal_output_rms = float(
        np.sqrt(np.mean(np.square(analytical_control[final_window])))
    )
    thresholds = {
        "ten_percent_nominal_output_rms": 0.10 * nominal_output_rms,
        "one_percent_nominal_output_rms": 0.01 * nominal_output_rms,
        "one_millivolt_rms": 0.001,
    }

    measurements: list[dict[str, object]] = []
    for level_peak_v in LEVELS_PEAK_V:
        input_q24 = input_trajectory_q24(level_peak_v)
        stimulus = input_q24.astype(np.float64) / float(1 << 24)
        analytical, analytical_grid, analytical_failures = run_analytical(stimulus)
        capture = capture_wide_solver_rtl(
            input_q24,
            f"wide_solver_rtl_overload_{level_tag(level_peak_v)}v",
            args.verilator,
        )
        rtl = capture.rtl_output_q32.astype(np.float64) / float(1 << 32)
        fixed = capture.fixed_model
        analytical_recovery = analytical - analytical_control
        rtl_recovery = rtl - rtl_control
        rtl_vs_analytical = rtl - analytical
        post = slice(post_index, None)
        measurement = {
            "burst_input_peak_v": level_peak_v,
            "rtl_fixed_bit_exact": True,
            "analytical": {
                "burst_output": burst_metrics(analytical, burst_mask),
                "maximum_grid_current_a": analytical_grid.tolist(),
                "nonconvergence_count": analytical_failures,
                "peak_post_burst_deviation_v": float(
                    np.max(np.abs(analytical_recovery[post]))
                ),
                "recovery_s": {
                    name: sustained_recovery_s(
                        analytical_recovery, threshold, post_index
                    )
                    for name, threshold in thresholds.items()
                },
            },
            "captured_rtl": {
                "burst_output": burst_metrics(rtl, burst_mask),
                "maximum_grid_current_a": capture.maximum_grid_current_a.tolist(),
                "peak_post_burst_deviation_v": float(
                    np.max(np.abs(rtl_recovery[post]))
                ),
                "recovery_s": {
                    name: sustained_recovery_s(rtl_recovery, threshold, post_index)
                    for name, threshold in thresholds.items()
                },
                "maximum_residual_a": fixed.max_residual_q44_observed
                / float(1 << 44),
                "residual_limit_exceedance_count": fixed.nonconvergence_count,
                "saturation_count": fixed.saturation_count,
                "range_clip_count": fixed.lut_clip_count,
                "correction_scale_fallback_count": (
                    fixed.correction_scale_fallback_count
                ),
                "minimum_correction_residual_fractional_bits": (
                    fixed.minimum_correction_residual_fractional_bits
                ),
            },
            "rtl_vs_analytical": {
                "post_burst_residual_rms_v": float(
                    np.sqrt(np.mean(np.square(rtl_vs_analytical[post])))
                ),
                "post_burst_residual_mean_v": float(
                    np.mean(rtl_vs_analytical[post])
                ),
                "final_10ms_residual_rms_v": float(
                    np.sqrt(np.mean(np.square(rtl_vs_analytical[final_window])))
                ),
                "maximum_post_burst_absolute_error_v": float(
                    np.max(np.abs(rtl_vs_analytical[post]))
                ),
            },
        }
        measurements.append(measurement)
        print(
            f"{level_peak_v:5.3f} V peak: residual failures "
            f"{fixed.nonconvergence_count}, range clips {fixed.lut_clip_count}, "
            f"fallbacks {fixed.correction_scale_fallback_count}",
            flush=True,
        )

    report = {
        "model": "12ax7_passive_riaa_v1",
        "implementation": "captured SystemVerilog wide factorized solver",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "stimulus": {
            "frequency_hz": FREQUENCY_HZ,
            "nominal_peak_v": NOMINAL_PEAK_V,
            "burst_start_s": BURST_START_S,
            "burst_end_s": BURST_END_S,
            "duration_s": DURATION_S,
            "post_burst_observation_s": DURATION_S - BURST_END_S,
            "burst_levels_peak_v": list(LEVELS_PEAK_V),
            "quantized_input": "Q8.24",
        },
        "nominal_analytical_output_rms_v": nominal_output_rms,
        "recovery_thresholds_v_rms": thresholds,
        "recovery_definition": (
            "last 1 ms sliding-RMS threshold crossing relative to a nominal "
            "undisturbed trajectory"
        ),
        "control_rtl_fixed_bit_exact": True,
        "measurements": measurements,
    }

    if any(
        int(measurement["captured_rtl"]["saturation_count"]) != 0
        for measurement in measurements
    ):
        raise RuntimeError("adaptive wide solver saturated during overload sweep")
    for measurement in measurements[:2]:
        rtl = measurement["captured_rtl"]
        if int(rtl["residual_limit_exceedance_count"]) or int(
            rtl["range_clip_count"]
        ):
            raise RuntimeError("solver must remain converged and in range through 0.5 V")
    one_volt = measurements[2]["captured_rtl"]
    severe = measurements[3]["captured_rtl"]
    if int(one_volt["residual_limit_exceedance_count"]) == 0:
        raise RuntimeError("expected the characterized 1.0 V residual failure")
    if int(severe["range_clip_count"]) == 0 or int(
        severe["correction_scale_fallback_count"]
    ) == 0:
        raise RuntimeError("expected characterized 1.5 V range clips and fallbacks")

    summary = ROOT / "model" / "generated" / "wide_solver_rtl_overload_summary.json"
    summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result = ROOT / "reference" / "results" / "wide_solver_rtl_overload.json"
    result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
