#!/usr/bin/env python3
"""Characterize large-signal grid conduction, clipping, and recovery."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedChordV1CircuitModel,
    FixedWideStateV1CircuitModel,
)
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


SAMPLE_RATE_HZ = 768_000.0
FREQUENCY_HZ = 1_000.0
NOMINAL_PEAK_V = 0.005
BURST_START_S = 0.010
BURST_END_S = 0.015
DURATION_S = 0.050


def stimulus(level_peak_v: float) -> np.ndarray:
    time_s = np.arange(int(DURATION_S * SAMPLE_RATE_HZ)) / SAMPLE_RATE_HZ
    amplitude = np.full(time_s.size, NOMINAL_PEAK_V)
    burst = (time_s >= BURST_START_S) & (time_s < BURST_END_S)
    amplitude[burst] = level_peak_v
    return amplitude * np.sin(2.0 * np.pi * FREQUENCY_HZ * time_s)


def run_analytical(
    samples: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, int]:
    model = V1CircuitModel(SAMPLE_RATE_HZ)
    output = np.empty_like(samples)
    maximum_grid_current = np.zeros(2)
    for index, sample in enumerate(samples):
        output[index] = model.process_sample(
            float(sample), max_iterations=8, tolerance_a=1.0e-12
        )
        maximum_grid_current[0] = max(
            maximum_grid_current[0],
            float(model.tube.grid_current(model.nodes["g1"] - model.nodes["k1"])),
        )
        maximum_grid_current[1] = max(
            maximum_grid_current[1],
            float(model.tube.grid_current(model.nodes["g2"] - model.nodes["k2"])),
        )
    return output, maximum_grid_current, model.nonconvergence_count


def run_fixed(
    samples: np.ndarray, wide_candidate: bool = False
) -> tuple[np.ndarray, np.ndarray, FixedChordV1CircuitModel]:
    tube = FixedFactorizedKoren12AX7()
    fixed_type = (
        FixedWideStateV1CircuitModel
        if wide_candidate
        else FixedChordV1CircuitModel
    )
    model = fixed_type(SAMPLE_RATE_HZ, tube_lut=tube)
    output = np.empty_like(samples)
    maximum_grid_current_q31 = np.zeros(2, dtype=np.int64)
    for index, sample in enumerate(samples):
        output[index] = model.process_sample(
            float(sample), max_iterations=3, residual_limit_a=2.0e-6
        )
        for tube_index, (grid_name, cathode_name) in enumerate(
            (("g1", "k1"), ("g2", "k2"))
        ):
            grid = model.node[grid_name]
            cathode = model.node[cathode_name]
            vgk_q24 = model._convert_fraction(
                int(model.voltage_q[grid]),
                int(model.VOLTAGE_FRACTIONAL_BITS[grid]),
                24,
            ) - model._convert_fraction(
                int(model.voltage_q[cathode]),
                int(model.VOLTAGE_FRACTIONAL_BITS[cathode]),
                24,
            )
            _, grid_current_q31, _ = tube.evaluate_fixed(vgk_q24, 100 << 20)
            maximum_grid_current_q31[tube_index] = max(
                maximum_grid_current_q31[tube_index], grid_current_q31
            )
    return output, maximum_grid_current_q31 / (1 << 31), model


def sliding_rms(values: np.ndarray, window: int) -> np.ndarray:
    squared = np.square(values)
    cumulative = np.concatenate(([0.0], np.cumsum(squared)))
    return np.sqrt((cumulative[window:] - cumulative[:-window]) / window)


def sustained_recovery_s(
    residual: np.ndarray, threshold_v_rms: float, start_index: int
) -> float | None:
    window = int(round(0.001 * SAMPLE_RATE_HZ))
    envelope = sliding_rms(residual, window)
    first_post = max(0, start_index - window + 1)
    above = np.flatnonzero(envelope[first_post:] > threshold_v_rms)
    if above.size == 0:
        recovered_index = first_post
    else:
        recovered_index = first_post + int(above[-1]) + 1
    if recovered_index >= envelope.size:
        return None
    return max(0.0, (recovered_index + window - 1 - start_index) / SAMPLE_RATE_HZ)


def burst_metrics(output: np.ndarray, burst_mask: np.ndarray) -> dict[str, float]:
    values = output[burst_mask]
    positive = float(np.max(values))
    negative = float(np.min(values))
    return {
        "positive_peak_v": positive,
        "negative_peak_v": negative,
        "peak_to_peak_v": positive - negative,
        "absolute_peak_asymmetry_db": float(
            20.0 * np.log10(max(abs(positive), 1.0e-15) / max(abs(negative), 1.0e-15))
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wide-candidate", action="store_true")
    args = parser.parse_args()
    levels_peak_v = (0.020, 0.500, 1.000, 1.500)
    time_s = np.arange(int(DURATION_S * SAMPLE_RATE_HZ)) / SAMPLE_RATE_HZ
    burst_mask = (time_s >= BURST_START_S) & (time_s < BURST_END_S)
    post_index = int(round(BURST_END_S * SAMPLE_RATE_HZ))

    control_stimulus = stimulus(NOMINAL_PEAK_V)
    analytical_control, _, _ = run_analytical(control_stimulus)
    fixed_control, _, _ = run_fixed(control_stimulus, args.wide_candidate)
    nominal_output_rms = float(
        np.sqrt(np.mean(np.square(analytical_control[time_s >= 0.040])))
    )
    thresholds = {
        "ten_percent_nominal_output_rms": 0.10 * nominal_output_rms,
        "one_percent_nominal_output_rms": 0.01 * nominal_output_rms,
        "one_millivolt_rms": 0.001,
    }

    measurements: list[dict[str, object]] = []
    for level_peak_v in levels_peak_v:
        samples = stimulus(level_peak_v)
        analytical, analytical_grid, analytical_failures = run_analytical(samples)
        fixed, fixed_grid, fixed_model = run_fixed(samples, args.wide_candidate)
        analytical_recovery_residual = analytical - analytical_control
        fixed_recovery_residual = fixed - fixed_control
        fixed_vs_analytical = fixed - analytical
        post = slice(post_index, None)
        measurement = {
            "burst_input_peak_v": level_peak_v,
            "analytical": {
                "burst_output": burst_metrics(analytical, burst_mask),
                "maximum_grid_current_a": analytical_grid.tolist(),
                "nonconvergence_count": analytical_failures,
                "peak_post_burst_deviation_v": float(
                    np.max(np.abs(analytical_recovery_residual[post]))
                ),
                "recovery_s": {
                    name: sustained_recovery_s(
                        analytical_recovery_residual, threshold, post_index
                    )
                    for name, threshold in thresholds.items()
                },
            },
            "fixed_factorized": {
                "burst_output": burst_metrics(fixed, burst_mask),
                "maximum_grid_current_a": fixed_grid.tolist(),
                "peak_post_burst_deviation_v": float(
                    np.max(np.abs(fixed_recovery_residual[post]))
                ),
                "recovery_s": {
                    name: sustained_recovery_s(
                        fixed_recovery_residual, threshold, post_index
                    )
                    for name, threshold in thresholds.items()
                },
                "max_residual_a": fixed_model.max_residual_q44_observed
                / (1 << 44),
                "residual_limit_exceedance_count": fixed_model.nonconvergence_count,
                "saturation_count": fixed_model.saturation_count,
                "range_clip_count": fixed_model.lut_clip_count,
                "correction_scale_fallback_count": fixed_model.correction_scale_fallback_count,
                "minimum_correction_residual_fractional_bits": fixed_model.minimum_correction_residual_fractional_bits,
            },
            "fixed_vs_analytical": {
                "post_burst_residual_rms_v": float(
                    np.sqrt(np.mean(np.square(fixed_vs_analytical[post])))
                ),
                "post_burst_residual_mean_v": float(
                    np.mean(fixed_vs_analytical[post])
                ),
                "maximum_post_burst_absolute_error_v": float(
                    np.max(np.abs(fixed_vs_analytical[post]))
                ),
            },
        }
        measurements.append(measurement)
        print(
            f"{level_peak_v:5.3f} V peak: fixed residual limit failures "
            f"{fixed_model.nonconvergence_count}, grid peaks "
            f"{fixed_grid[0] * 1e6:.3f}/{fixed_grid[1] * 1e6:.3f} uA",
            flush=True,
        )

    report = {
        "model": "12ax7_passive_riaa_v1",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "fixed_implementation": (
            "40-bit Q28/Q32 nodes, Q30 branch history, staged adaptive Q30/Q34/Q40 corrections"
            if args.wide_candidate
            else "legacy 32-bit heterogeneous nodes, Q12.20 matrix/history stamp"
        ),
        "stimulus": {
            "frequency_hz": FREQUENCY_HZ,
            "nominal_peak_v": NOMINAL_PEAK_V,
            "burst_start_s": BURST_START_S,
            "burst_end_s": BURST_END_S,
            "duration_s": DURATION_S,
            "burst_levels_peak_v": list(levels_peak_v),
        },
        "nominal_analytical_output_rms_v": nominal_output_rms,
        "recovery_thresholds_v_rms": thresholds,
        "recovery_definition": "last 1 ms sliding-RMS threshold crossing relative to a nominal undisturbed trajectory",
        "measurements": measurements,
    }
    report_stem = "overload_recovery_wide" if args.wide_candidate else "overload_recovery"
    result_path = REPOSITORY_ROOT / "reference" / "results" / f"{report_stem}.json"
    result_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary_path = (
        REPOSITORY_ROOT / "model" / "generated" / f"{report_stem}_summary.json"
    )
    summary_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
