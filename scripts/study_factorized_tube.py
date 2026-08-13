#!/usr/bin/env python3
"""Characterize the factorized 1-D Koren approximation and circuit behavior."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.factorized_tube import (  # noqa: E402
    FactorizedKoren12AX7,
    FixedFactorizedKoren12AX7,
)
from fpga_amp.fixed_circuit import FixedChordV1CircuitModel  # noqa: E402
from fpga_amp.tube import Koren12AX7  # noqa: E402
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


def fit_harmonics(
    time_s: np.ndarray, waveform: np.ndarray
) -> tuple[float, float]:
    columns = [np.ones_like(time_s)]
    for harmonic in range(1, 11):
        angle = 2.0 * np.pi * 1_000.0 * harmonic * time_s
        columns.extend((np.sin(angle), np.cos(angle)))
    coefficient, *_ = np.linalg.lstsq(np.column_stack(columns), waveform, rcond=None)
    peak = np.asarray(
        [
            np.hypot(coefficient[2 * harmonic - 1], coefficient[2 * harmonic])
            for harmonic in range(1, 11)
        ]
    )
    return float(peak[0]), float(np.sqrt(np.sum(np.square(peak[1:]))) / peak[0])


def waveform_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    residual = candidate - reference
    return {
        "normalized_residual_db": float(
            20.0
            * np.log10(
                np.sqrt(np.mean(np.square(residual)))
                / np.sqrt(np.mean(np.square(reference)))
            )
        ),
        "max_absolute_error_v": float(np.max(np.abs(residual))),
    }


def main() -> int:
    analytical_tube = Koren12AX7()
    linear_factorized = FactorizedKoren12AX7(interpolation="linear")
    factorized = FactorizedKoren12AX7(interpolation="hermite")
    fixed_factorized = FixedFactorizedKoren12AX7()
    rng = np.random.default_rng(0xFAC701)
    grid_v = rng.uniform(-5.0, 1.0, 100_000)
    plate_v = rng.uniform(0.0, 400.0, 100_000)
    reference_current = analytical_tube.plate_current(grid_v, plate_v)
    factorized_current = factorized.plate_current(grid_v, plate_v)
    linear_current = linear_factorized.plate_current(grid_v, plate_v)
    current_error = factorized_current - reference_current
    fixed_current = np.empty_like(reference_current)
    for index, (grid, plate) in enumerate(zip(grid_v, plate_v, strict=True)):
        grid_q24 = int(round(grid * (1 << 24)))
        plate_q20 = int(round(plate * (1 << 20)))
        plate_q31, _, _ = fixed_factorized.evaluate_fixed(grid_q24, plate_q20)
        fixed_current[index] = plate_q31 / (1 << 31)
    quantized_reference_current = analytical_tube.plate_current(
        np.rint(grid_v * (1 << 24)) / (1 << 24),
        np.rint(plate_v * (1 << 20)) / (1 << 20),
    )
    fixed_current_error = fixed_current - quantized_reference_current
    operating = (grid_v <= 0.0) & (plate_v >= 20.0)

    sample_rate_hz = 768_000.0
    time_s = np.arange(int(0.030 * sample_rate_hz)) / sample_rate_hz
    selected = time_s >= 0.020
    circuit_measurements: list[dict[str, object]] = []
    for input_peak_v in (0.005, 0.020, 0.100, 0.500, 1.000):
        stimulus = input_peak_v * np.sin(2.0 * np.pi * 1_000.0 * time_s)
        analytical_model = V1CircuitModel(sample_rate_hz)
        analytical = analytical_model.process(
            stimulus, max_iterations=8, tolerance_a=1.0e-12
        )
        factorized_model = V1CircuitModel(
            sample_rate_hz, tube=factorized, dc_tolerance_a=1.0e-10
        )
        candidate = factorized_model.process(
            stimulus, max_iterations=8, tolerance_a=1.0e-12
        )
        fixed_model = FixedChordV1CircuitModel(
            sample_rate_hz, tube_lut=fixed_factorized
        )
        fixed_candidate = fixed_model.process(
            stimulus, max_iterations=3, residual_limit_a=2.0e-6
        )
        analytical_h1, analytical_thd = fit_harmonics(
            time_s[selected], analytical[selected]
        )
        factorized_h1, factorized_thd = fit_harmonics(
            time_s[selected], candidate[selected]
        )
        fixed_h1, fixed_thd = fit_harmonics(
            time_s[selected], fixed_candidate[selected]
        )
        fixed_metrics = waveform_metrics(
            analytical[selected], fixed_candidate[selected]
        )
        circuit_measurements.append(
            {
                "input_peak_v": input_peak_v,
                "analytical_thd_percent_h2_to_h10": 100.0 * analytical_thd,
                "factorized_thd_percent_h2_to_h10": 100.0 * factorized_thd,
                "fundamental_gain_error_db": float(
                    20.0 * np.log10(factorized_h1 / analytical_h1)
                ),
                **waveform_metrics(analytical[selected], candidate[selected]),
                "factorized_nonconvergence_count": factorized_model.nonconvergence_count,
                "fixed_factorized_thd_percent_h2_to_h10": 100.0 * fixed_thd,
                "fixed_fundamental_gain_error_db": float(
                    20.0 * np.log10(fixed_h1 / analytical_h1)
                ),
                "fixed_normalized_residual_db": fixed_metrics[
                    "normalized_residual_db"
                ],
                "fixed_max_absolute_error_v": fixed_metrics[
                    "max_absolute_error_v"
                ],
                "fixed_nonconvergence_count": fixed_model.nonconvergence_count,
                "fixed_saturation_count": fixed_model.saturation_count,
                "fixed_range_clip_count": fixed_model.lut_clip_count,
                "fixed_max_residual_a": fixed_model.max_residual_q44_observed
                / (1 << 44),
            }
        )

    report = {
        "algorithm": "Koren factorization using reciprocal-sqrt, softplus, and power value/derivative 1-D LUTs with cubic Hermite interpolation",
        "table_points": {
            "reciprocal_sqrt": factorized.reciprocal_points,
            "softplus": factorized.softplus_points,
            "power": factorized.power_points,
        },
        "floating_plate_table_bits_at_32_bits_each": factorized.raw_table_bits_q31,
        "fixed_total_table_bits_including_grid_current": fixed_factorized.raw_table_bits,
        "fixed_raw_ramb18_equivalents": fixed_factorized.raw_table_bits / 18_432.0,
        "baseline_2d_plate_table_bits": 128 * 256 * 32,
        "linear_factorized_random_current_probe": {
            "mean_absolute_error_a": float(
                np.mean(np.abs(linear_current - reference_current))
            ),
            "worst_absolute_error_a": float(
                np.max(np.abs(linear_current - reference_current))
            ),
        },
        "random_current_probe": {
            "vectors": int(grid_v.size),
            "mean_absolute_error_a": float(np.mean(np.abs(current_error))),
            "rms_error_a": float(np.sqrt(np.mean(np.square(current_error)))),
            "worst_absolute_error_a": float(np.max(np.abs(current_error))),
            "worst_operating_region_error_a": float(
                np.max(np.abs(current_error[operating]))
            ),
        },
        "fixed_random_current_probe_at_quantized_inputs": {
            "vectors": int(grid_v.size),
            "mean_absolute_error_a": float(np.mean(np.abs(fixed_current_error))),
            "rms_error_a": float(
                np.sqrt(np.mean(np.square(fixed_current_error)))
            ),
            "worst_absolute_error_a": float(np.max(np.abs(fixed_current_error))),
            "worst_operating_region_error_a": float(
                np.max(np.abs(fixed_current_error[operating]))
            ),
        },
        "circuit_analysis_window_s": [0.020, 0.030],
        "circuit_measurements": circuit_measurements,
        "status": "floating and bit-accurate Python arithmetic verified; RTL latency and equivalence not yet implemented",
    }
    result_path = REPOSITORY_ROOT / "reference" / "results" / "factorized_tube_study.json"
    result_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary_path = REPOSITORY_ROOT / "model" / "generated" / "factorized_tube_summary.json"
    summary_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
