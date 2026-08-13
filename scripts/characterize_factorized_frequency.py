#!/usr/bin/env python3
"""Measure factorized fixed-circuit equivalence across the audio band."""

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
    FixedWideStateTrapezoidalV1CircuitModel,
)
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


def fit_harmonics(
    time_s: np.ndarray, waveform: np.ndarray, frequency_hz: float
) -> tuple[float, float, float, float]:
    columns = [np.ones_like(time_s)]
    for harmonic in range(1, 11):
        angle = 2.0 * np.pi * frequency_hz * harmonic * time_s
        columns.extend((np.sin(angle), np.cos(angle)))
    coefficient, *_ = np.linalg.lstsq(np.column_stack(columns), waveform, rcond=None)
    peak = np.asarray(
        [
            np.hypot(coefficient[2 * harmonic - 1], coefficient[2 * harmonic])
            for harmonic in range(1, 11)
        ]
    )
    phase_deg = float(np.degrees(np.arctan2(coefficient[2], coefficient[1])))
    thd = float(np.sqrt(np.sum(np.square(peak[1:]))) / peak[0])
    return float(peak[0]), phase_deg, float(coefficient[0]), thd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wide-candidate", action="store_true")
    parser.add_argument("--trapezoidal", action="store_true")
    args = parser.parse_args()
    if args.trapezoidal:
        args.wide_candidate = True
    sample_rate_hz = 768_000.0
    input_peak_v = 0.005
    frequencies_hz = (20.0, 50.0, 100.0, 1_000.0, 10_000.0, 20_000.0)
    measurements: list[dict[str, object]] = []
    for frequency_hz in frequencies_hz:
        duration_s = max(0.030, 10.0 / frequency_hz)
        analysis_duration_s = max(0.010, 5.0 / frequency_hz)
        sample_count = int(math.ceil(duration_s * sample_rate_hz))
        time_s = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
        selected = time_s >= duration_s - analysis_duration_s
        stimulus = input_peak_v * np.sin(2.0 * np.pi * frequency_hz * time_s)

        analytical_model = V1CircuitModel(
            sample_rate_hz,
            integration_method=(
                "trapezoidal" if args.trapezoidal else "backward_euler"
            ),
        )
        analytical = analytical_model.process(
            stimulus, max_iterations=8, tolerance_a=1.0e-12
        )
        if args.trapezoidal:
            fixed_type = FixedWideStateTrapezoidalV1CircuitModel
        elif args.wide_candidate:
            fixed_type = FixedWideStateV1CircuitModel
        else:
            fixed_type = FixedChordV1CircuitModel
        fixed_model = fixed_type(
            sample_rate_hz, tube_lut=FixedFactorizedKoren12AX7()
        )
        fixed = fixed_model.process(
            stimulus, max_iterations=3, residual_limit_a=2.0e-6
        )
        reference_h1, reference_phase, reference_mean, reference_thd = fit_harmonics(
            time_s[selected], analytical[selected], frequency_hz
        )
        fixed_h1, fixed_phase, fixed_mean, fixed_thd = fit_harmonics(
            time_s[selected], fixed[selected], frequency_hz
        )
        residual = fixed[selected] - analytical[selected]
        residual_mean = float(np.mean(residual))
        mean_removed = residual - residual_mean
        reference_rms = float(np.sqrt(np.mean(np.square(analytical[selected]))))
        entry = {
            "frequency_hz": frequency_hz,
            "duration_s": duration_s,
            "analysis_duration_s": analysis_duration_s,
            "samples": sample_count,
            "analytical": {
                "fundamental_peak_v": reference_h1,
                "gain_db": float(20.0 * np.log10(reference_h1 / input_peak_v)),
                "phase_deg": reference_phase,
                "mean_v": reference_mean,
                "thd_percent_h2_to_h10": 100.0 * reference_thd,
                "nonconvergence_count": analytical_model.nonconvergence_count,
            },
            "fixed_factorized": {
                "fundamental_peak_v": fixed_h1,
                "gain_db": float(20.0 * np.log10(fixed_h1 / input_peak_v)),
                "phase_deg": fixed_phase,
                "mean_v": fixed_mean,
                "thd_percent_h2_to_h10": 100.0 * fixed_thd,
                "fundamental_gain_error_db": float(
                    20.0 * np.log10(fixed_h1 / reference_h1)
                ),
                "fundamental_phase_error_deg": fixed_phase - reference_phase,
                "normalized_residual_db": float(
                    20.0
                    * np.log10(
                        np.sqrt(np.mean(np.square(residual))) / reference_rms
                    )
                ),
                "mean_removed_normalized_residual_db": float(
                    20.0
                    * np.log10(
                        np.sqrt(np.mean(np.square(mean_removed))) / reference_rms
                    )
                ),
                "residual_mean_v": residual_mean,
                "max_absolute_error_v": float(np.max(np.abs(residual))),
                "max_residual_a": fixed_model.max_residual_q44_observed
                / (1 << 44),
                "residual_limit_exceedance_count": fixed_model.nonconvergence_count,
                "saturation_count": fixed_model.saturation_count,
                "range_clip_count": fixed_model.lut_clip_count,
                "correction_scale_fallback_count": fixed_model.correction_scale_fallback_count,
                "minimum_correction_residual_fractional_bits": fixed_model.minimum_correction_residual_fractional_bits,
                "maximum_capacitor_history_current_a": [
                    value / (1 << 44)
                    for value in fixed_model.max_abs_capacitor_current_q44
                ],
            },
        }
        measurements.append(entry)
        print(
            f"{frequency_hz:8.1f} Hz: gain error "
            f"{entry['fixed_factorized']['fundamental_gain_error_db']:+.6f} dB, "  # type: ignore[index]
            f"phase error {entry['fixed_factorized']['fundamental_phase_error_deg']:+.6f} deg, "  # type: ignore[index]
            f"raw residual {entry['fixed_factorized']['normalized_residual_db']:.2f} dB",  # type: ignore[index]
            flush=True,
        )

    fixed_entries = [entry["fixed_factorized"] for entry in measurements]
    maximum_gain_error_db = max(
        abs(float(entry["fundamental_gain_error_db"])) for entry in fixed_entries
    )
    maximum_phase_error_deg = max(
        abs(float(entry["fundamental_phase_error_deg"])) for entry in fixed_entries
    )
    total_residual_limit_exceedances = sum(
        int(entry["residual_limit_exceedance_count"]) for entry in fixed_entries
    )
    total_saturations = sum(int(entry["saturation_count"]) for entry in fixed_entries)
    total_range_clips = sum(int(entry["range_clip_count"]) for entry in fixed_entries)
    if args.trapezoidal:
        gain_limit_db, phase_limit_deg = 0.0002, 0.001
    elif args.wide_candidate:
        gain_limit_db, phase_limit_deg = 0.00025, 0.0011
    else:
        gain_limit_db, phase_limit_deg = 0.01, 0.08
    acceptance_passed = (
        maximum_gain_error_db <= gain_limit_db
        and maximum_phase_error_deg <= phase_limit_deg
        and total_residual_limit_exceedances == 0
        and total_saturations == 0
        and total_range_clips == 0
    )
    report = {
        "model": "12ax7_passive_riaa_v1",
        "stimulus": "5 mV peak sine at the 768 kHz circuit input",
        "tube_implementation": "fixed factorized 1-D cubic-Hermite",
        "state_implementation": (
            "40-bit Q28/Q32 nodes, Q30 voltage/Q4.44 current trapezoidal history"
            if args.trapezoidal
            else "40-bit Q28/Q32 nodes, Q30 branch history, adaptive staged Q30/Q34/Q40 corrections"
            if args.wide_candidate
            else "legacy 32-bit heterogeneous nodes, Q12.20 matrix/history stamp"
        ),
        "integration_method": (
            "trapezoidal" if args.trapezoidal else "backward_euler"
        ),
        "frequencies_hz": list(frequencies_hz),
        "maximum_absolute_gain_error_db": maximum_gain_error_db,
        "maximum_absolute_phase_error_deg": maximum_phase_error_deg,
        "worst_raw_normalized_residual_db": max(
            float(entry["normalized_residual_db"]) for entry in fixed_entries
        ),
        "worst_mean_removed_normalized_residual_db": max(
            float(entry["mean_removed_normalized_residual_db"])
            for entry in fixed_entries
        ),
        "total_residual_limit_exceedances": total_residual_limit_exceedances,
        "total_saturations": total_saturations,
        "total_range_clips": total_range_clips,
        "acceptance": {
            "maximum_absolute_gain_error_db": gain_limit_db,
            "maximum_absolute_phase_error_deg": phase_limit_deg,
            "require_zero_residual_limit_exceedances": True,
            "require_zero_saturations": True,
            "require_zero_range_clips": True,
            "passed": acceptance_passed,
        },
        "measurements": measurements,
    }
    report_stem = (
        "factorized_frequency_trapezoidal"
        if args.trapezoidal
        else "factorized_frequency_wide"
        if args.wide_candidate
        else "factorized_frequency"
    )
    results_path = (
        REPOSITORY_ROOT / "reference" / "results" / f"{report_stem}_sweep.json"
    )
    results_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary_path = (
        REPOSITORY_ROOT / "model" / "generated" / f"{report_stem}_summary.json"
    )
    summary_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if acceptance_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
