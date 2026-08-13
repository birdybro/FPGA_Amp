#!/usr/bin/env python3
"""Compare fixed chord and analytical-Newton V1 behavior versus 1 kHz level."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.fixed_circuit import FixedChordV1CircuitModel  # noqa: E402
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


def fit_harmonics(
    time_s: np.ndarray, waveform: np.ndarray
) -> tuple[float, float, list[float]]:
    columns = [np.ones_like(time_s)]
    for harmonic in range(1, 11):
        angle = 2.0 * np.pi * 1_000.0 * harmonic * time_s
        columns.extend((np.sin(angle), np.cos(angle)))
    coefficient, *_ = np.linalg.lstsq(np.column_stack(columns), waveform, rcond=None)
    peak = [
        float(np.hypot(coefficient[2 * harmonic - 1], coefficient[2 * harmonic]))
        for harmonic in range(1, 11)
    ]
    thd = float(np.sqrt(np.sum(np.square(peak[1:]))) / peak[0])
    return peak[0], thd, peak


def main() -> int:
    sample_rate_hz = 768_000.0
    levels_peak_v = (
        0.0005,
        0.001,
        0.0025,
        0.005,
        0.010,
        0.020,
        0.050,
        0.100,
        0.200,
        0.500,
        1.000,
        1.100,
        1.250,
        1.500,
        2.000,
        5.000,
    )
    time_s = np.arange(int(0.030 * sample_rate_hz)) / sample_rate_hz
    selected = time_s >= 0.020
    measurements: list[dict[str, object]] = []
    for level_peak_v in levels_peak_v:
        stimulus = level_peak_v * np.sin(2.0 * np.pi * 1_000.0 * time_s)
        reference_model = V1CircuitModel(sample_rate_hz)
        reference = reference_model.process(
            stimulus, max_iterations=8, tolerance_a=1.0e-12
        )
        fixed_model = FixedChordV1CircuitModel(sample_rate_hz)
        fixed = fixed_model.process(stimulus)
        reference_h1, reference_thd, reference_harmonics = fit_harmonics(
            time_s[selected], reference[selected]
        )
        fixed_h1, fixed_thd, fixed_harmonics = fit_harmonics(
            time_s[selected], fixed[selected]
        )
        residual = fixed[selected] - reference[selected]
        reference_rms = float(np.sqrt(np.mean(np.square(reference[selected]))))
        residual_rms = float(np.sqrt(np.mean(np.square(residual))))
        measurements.append(
            {
                "input_peak_v": level_peak_v,
                "analytical": {
                    "output_fundamental_peak_v": reference_h1,
                    "gain_db": float(20.0 * np.log10(reference_h1 / level_peak_v)),
                    "thd_percent_h2_to_h10": 100.0 * reference_thd,
                    "harmonic_peak_v_h1_to_h10": reference_harmonics,
                    "nonconvergence_count": reference_model.nonconvergence_count,
                },
                "fixed": {
                    "output_fundamental_peak_v": fixed_h1,
                    "gain_db": float(20.0 * np.log10(fixed_h1 / level_peak_v)),
                    "thd_percent_h2_to_h10": 100.0 * fixed_thd,
                    "harmonic_peak_v_h1_to_h10": fixed_harmonics,
                    "max_residual_a": fixed_model.max_residual_q44_observed
                    / float(1 << 44),
                    "residual_limit_exceedance_count": fixed_model.nonconvergence_count,
                    "saturation_count": fixed_model.saturation_count,
                    "lut_clip_count": fixed_model.lut_clip_count,
                },
                "fixed_vs_analytical": {
                    "normalized_residual_db": float(
                        20.0 * np.log10(residual_rms / reference_rms)
                    ),
                    "fundamental_gain_error_db": float(
                        20.0 * np.log10(fixed_h1 / reference_h1)
                    ),
                    "max_absolute_error_v": float(np.max(np.abs(residual))),
                },
            }
        )

    small_signal_gain = float(measurements[0]["fixed"]["gain_db"])  # type: ignore[index]
    for measurement in measurements:
        fixed = measurement["fixed"]
        assert isinstance(fixed, dict)
        fixed["gain_compression_db"] = float(fixed["gain_db"]) - small_signal_gain
    compression = [
        float(entry["input_peak_v"])
        for entry in measurements
        if float(entry["fixed"]["gain_compression_db"]) <= -1.0  # type: ignore[index]
    ]
    residual_failures = [
        float(entry["input_peak_v"])
        for entry in measurements
        if int(entry["fixed"]["residual_limit_exceedance_count"]) > 0  # type: ignore[index]
    ]
    lut_clips = [
        float(entry["input_peak_v"])
        for entry in measurements
        if int(entry["fixed"]["lut_clip_count"]) > 0  # type: ignore[index]
    ]
    report = {
        "stimulus": "1 kHz sine at 768 kHz circuit input",
        "analysis_window_s": [0.020, 0.030],
        "analytical_reference": "Koren model, backward Euler, Newton to 1 pA",
        "fixed_candidate": "128x256 LUT, heterogeneous state, exactly three Q17.1 chord corrections",
        "fixed_residual_limit_a": 2.0e-6,
        "fixed_small_signal_gain_db": small_signal_gain,
        "first_tested_fixed_level_at_or_beyond_1db_compression_peak_v": (
            compression[0] if compression else None
        ),
        "first_tested_fixed_residual_failure_peak_v": (
            residual_failures[0] if residual_failures else None
        ),
        "first_tested_lut_clip_peak_v": lut_clips[0] if lut_clips else None,
        "measurements": measurements,
    }
    path = REPOSITORY_ROOT / "reference" / "results" / "fixed_level_sweep.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
