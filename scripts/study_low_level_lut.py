#!/usr/bin/env python3
"""Measure ordinary-cartridge distortion versus 12AX7 LUT resolution."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.fixed import TubeLUT  # noqa: E402
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedChordV1CircuitModel,
    LUTTubeAdapter,
)
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


def fit_harmonics(time_s: np.ndarray, waveform: np.ndarray) -> tuple[float, float]:
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


def compare(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    residual = candidate - reference
    return {
        "normalized_residual_db": float(
            20.0
            * np.log10(
                np.sqrt(np.mean(np.square(residual)))
                / np.sqrt(np.mean(np.square(reference)))
            )
        ),
        "maximum_absolute_error_v": float(np.max(np.abs(residual))),
    }


def main() -> int:
    sample_rate_hz = 768_000.0
    input_peak_v = 0.005
    time_s = np.arange(int(0.030 * sample_rate_hz)) / sample_rate_hz
    selected = time_s >= 0.020
    stimulus = input_peak_v * np.sin(2.0 * np.pi * 1_000.0 * time_s)
    analytical_model = V1CircuitModel(sample_rate_hz)
    analytical = analytical_model.process(
        stimulus, max_iterations=8, tolerance_a=1.0e-12
    )
    analytical_h1, analytical_thd = fit_harmonics(
        time_s[selected], analytical[selected]
    )

    resolutions = []
    for grid_points, plate_points in (
        (128, 256),
        (256, 256),
        (512, 256),
        (256, 512),
    ):
        lut = TubeLUT(grid_points=grid_points, plate_points=plate_points)
        lut.generate()
        lut_float_model = V1CircuitModel(
            sample_rate_hz,
            tube=LUTTubeAdapter(lut),  # type: ignore[arg-type]
            dc_tolerance_a=1.1e-9,
        )
        lut_float = lut_float_model.process(
            stimulus, max_iterations=8, tolerance_a=2.0e-9
        )
        fixed_model = FixedChordV1CircuitModel(sample_rate_hz, tube_lut=lut)
        fixed = fixed_model.process(stimulus)
        lut_h1, lut_thd = fit_harmonics(time_s[selected], lut_float[selected])
        fixed_h1, fixed_thd = fit_harmonics(time_s[selected], fixed[selected])
        resolutions.append(
            {
                "grid_points": grid_points,
                "plate_points": plate_points,
                "plate_storage_bits": grid_points * plate_points * 32,
                "raw_ramb18_equivalents": float(
                    grid_points * plate_points * 32 / 18_432
                ),
                "lut_float": {
                    "fundamental_peak_v": lut_h1,
                    "thd_percent_h2_to_h10": 100.0 * lut_thd,
                    **compare(analytical[selected], lut_float[selected]),
                },
                "fixed": {
                    "fundamental_peak_v": fixed_h1,
                    "thd_percent_h2_to_h10": 100.0 * fixed_thd,
                    **compare(analytical[selected], fixed[selected]),
                    "max_residual_a": fixed_model.max_residual_q44_observed
                    / float(1 << 44),
                    "saturation_count": fixed_model.saturation_count,
                    "lut_clip_count": fixed_model.lut_clip_count,
                },
                "fixed_vs_lut_float": compare(
                    lut_float[selected], fixed[selected]
                ),
            }
        )
    report = {
        "stimulus": "5 mV peak, 1 kHz sine",
        "analysis_window_s": [0.020, 0.030],
        "analytical": {
            "fundamental_peak_v": analytical_h1,
            "thd_percent_h2_to_h10": 100.0 * analytical_thd,
        },
        "architectural_note": "raw RAMB18 equivalents exclude aspect-ratio and packing overhead",
        "resolutions": resolutions,
    }
    result_path = REPOSITORY_ROOT / "reference" / "results" / "low_level_lut_study.json"
    result_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary_path = REPOSITORY_ROOT / "model" / "generated" / "low_level_lut_summary.json"
    summary_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
