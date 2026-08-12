#!/usr/bin/env python3
"""Generate and measure the 48 kHz <-> 768 kHz half-band chain."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.resampling import (  # noqa: E402
    DEFAULT_STAGES,
    decimate_16x,
    decimate_16x_fixed_q24,
    interpolation_delay_internal_samples,
    interpolate_16x,
    interpolate_16x_fixed_q24,
)


def response_metrics(coefficients: np.ndarray, input_rate_hz: int) -> dict[str, float]:
    fft_size = 1 << 20
    response = np.abs(np.fft.rfft(coefficients, fft_size))
    frequency = np.fft.rfftfreq(fft_size, 1.0 / (2 * input_rate_hz))
    response_db = 20.0 * np.log10(np.maximum(response, 1.0e-15))
    passband = response_db[frequency <= 20_000.0]
    stopband = response_db[frequency >= input_rate_hz - 20_000.0]
    return {
        "passband_min_db": float(np.min(passband)),
        "passband_max_db": float(np.max(passband)),
        "worst_image_stopband_db": float(np.max(stopband)),
    }


def tone_peak(samples: np.ndarray, sample_rate_hz: float, frequency_hz: float) -> float:
    time = np.arange(samples.size) / sample_rate_hz
    basis = np.column_stack(
        (
            np.sin(2.0 * np.pi * frequency_hz * time),
            np.cos(2.0 * np.pi * frequency_hz * time),
            np.ones_like(time),
        )
    )
    coefficient, *_ = np.linalg.lstsq(basis, samples, rcond=None)
    return float(np.hypot(coefficient[0], coefficient[1]))


def main() -> int:
    stages: list[dict[str, object]] = []
    combined_passband_min_db = 0.0
    combined_passband_max_db = 0.0
    generated: dict[str, list[float | int]] = {}
    for index, stage in enumerate(DEFAULT_STAGES, start=1):
        coefficients = stage.coefficients
        metrics = response_metrics(coefficients, stage.input_rate_hz)
        combined_passband_min_db += metrics["passband_min_db"]
        combined_passband_max_db += metrics["passband_max_db"]
        coefficient_q23 = np.rint(coefficients * (1 << 23)).astype(np.int64)
        quantized_coefficients = coefficient_q23.astype(np.float64) / (1 << 23)
        quantized_metrics = response_metrics(
            quantized_coefficients, stage.input_rate_hz
        )
        stages.append(
            {
                "stage": index,
                "input_rate_hz": stage.input_rate_hz,
                "output_rate_hz": stage.output_rate_hz,
                "taps": stage.taps,
                "nonzero_taps": stage.nonzero_taps,
                "kaiser_beta": stage.kaiser_beta,
                "coefficient_sum": float(np.sum(coefficients)),
                "q1_23_coefficient_sum": float(np.sum(coefficient_q23) / (1 << 23)),
                "q1_23_response": quantized_metrics,
                **metrics,
            }
        )
        generated[f"stage_{index}_float"] = [float(value) for value in coefficients]
        generated[f"stage_{index}_q1_23"] = [int(value) for value in coefficient_q23]

    # A cubic nonlinearity generates a 45 kHz third harmonic from a 15 kHz
    # input. At 48 kHz naive decimation aliases it to 3 kHz.
    external_rate_hz = 48_000.0
    samples = 8192
    time = np.arange(samples) / external_rate_hz
    input_signal = 0.8 * np.sin(2.0 * np.pi * 15_000.0 * time)
    internal = interpolate_16x(input_signal)
    nonlinear = internal + 0.5 * np.power(internal, 3)
    decimated = decimate_16x(nonlinear)
    roundtrip_delay = 2 * interpolation_delay_internal_samples() / 16.0
    discard = int(np.ceil(roundtrip_delay)) + 256
    measured = decimated[discard : discard + 4096]
    fundamental = tone_peak(measured, external_rate_hz, 15_000.0)
    alias = tone_peak(measured, external_rate_hz, 3_000.0)

    quantized_stage_coefficients = tuple(
        np.rint(stage.coefficients * (1 << 23)).astype(np.float64) / (1 << 23)
        for stage in DEFAULT_STAGES
    )
    internal_q23 = np.asarray(input_signal)
    for coefficients in quantized_stage_coefficients:
        stuffed = np.zeros(2 * internal_q23.size, dtype=np.float64)
        stuffed[::2] = internal_q23
        internal_q23 = np.convolve(stuffed, 2.0 * coefficients, mode="full")
    nonlinear_q23 = internal_q23 + 0.5 * np.power(internal_q23, 3)
    decimated_q23 = nonlinear_q23
    for coefficients in reversed(quantized_stage_coefficients):
        decimated_q23 = np.convolve(decimated_q23, coefficients, mode="full")[::2]
    measured_q23 = decimated_q23[discard : discard + 4096]
    fundamental_q23 = tone_peak(measured_q23, external_rate_hz, 15_000.0)
    alias_q23 = tone_peak(measured_q23, external_rate_hz, 3_000.0)

    input_q24 = np.rint(input_signal * (1 << 24)).astype(np.int64)
    internal_fixed_q24, interpolation_saturations = interpolate_16x_fixed_q24(
        input_q24
    )
    internal_fixed = internal_fixed_q24.astype(np.float64) / (1 << 24)
    # The cubic remains a test nonlinearity, not a proposed fixed implementation.
    nonlinear_fixed_q24 = np.rint(
        (internal_fixed + 0.5 * np.power(internal_fixed, 3)) * (1 << 24)
    ).astype(np.int64)
    decimated_fixed_q24, decimation_saturations = decimate_16x_fixed_q24(
        nonlinear_fixed_q24
    )
    measured_fixed = (
        decimated_fixed_q24[discard : discard + 4096].astype(np.float64) / (1 << 24)
    )
    fundamental_fixed = tone_peak(measured_fixed, external_rate_hz, 15_000.0)
    alias_fixed = tone_peak(measured_fixed, external_rate_hz, 3_000.0)

    report = {
        "external_rate_hz": 48_000,
        "internal_rate_hz": 768_000,
        "stages": stages,
        "combined_interpolator_passband_bound_db": [
            combined_passband_min_db,
            combined_passband_max_db,
        ],
        "interpolation_delay_internal_samples": interpolation_delay_internal_samples(),
        "interpolation_delay_ms": 1000.0
        * interpolation_delay_internal_samples()
        / 768_000.0,
        "roundtrip_delay_external_samples": roundtrip_delay,
        "roundtrip_delay_ms": 1000.0 * roundtrip_delay / external_rate_hz,
        "nonlinear_alias_test": {
            "input": "0.8 peak at 15 kHz",
            "nonlinearity": "y = x + 0.5*x^3",
            "generated_internal_harmonic_hz": 45_000,
            "potential_48khz_alias_hz": 3_000,
            "decimated_fundamental_peak": fundamental,
            "decimated_alias_peak": alias,
            "alias_relative_to_fundamental_db": float(20.0 * np.log10(alias / fundamental)),
            "q1_23_float_mac_alias_relative_to_fundamental_db": float(
                20.0 * np.log10(alias_q23 / fundamental_q23)
            ),
            "q8_24_sample_q1_23_mac_alias_relative_to_fundamental_db": float(
                20.0 * np.log10(alias_fixed / fundamental_fixed)
            ),
            "fixed_interpolator_saturation_count": interpolation_saturations,
            "fixed_decimator_saturation_count": decimation_saturations,
        },
    }
    generated_path = REPOSITORY_ROOT / "model" / "generated" / "halfband_coefficients.json"
    generated_path.write_text(json.dumps(generated, indent=2) + "\n", encoding="utf-8")
    report_path = REPOSITORY_ROOT / "reference" / "results" / "resampler_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
