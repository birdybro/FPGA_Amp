#!/usr/bin/env python3
"""Measure an explicit 8x internal-rate candidate against the 16x reference.

This is an architecture study, not a change to reference mode.  It separates
the physical circuit integration error (reported by the SPICE comparison) from
audio-band products caused by sampling a nonlinear tube/circuit at 384 kHz.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.audio_analysis import fit_tones  # noqa: E402
from fpga_amp.resampling import (  # noqa: E402
    DEFAULT_STAGES,
    EIGHT_X_STAGES,
    decimate_16x,
    interpolation_delay_internal_samples,
)
from fpga_amp.tube import Koren12AX7  # noqa: E402
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


EXTERNAL_RATE_HZ = 48_000.0
FUNDAMENTAL_HZ = 20_000.0
SELECTED_PRODUCT_HZ = (4_000.0, 8_000.0, 12_000.0, 16_000.0)
FIT_FREQUENCIES_HZ = (*SELECTED_PRODUCT_HZ, FUNDAMENTAL_HZ)
DURATION_S = 0.040
ANALYSIS_START_S = 0.020
ANALYSIS_DURATION_S = 0.010


def stages_for_factor(factor: int):
    if factor not in (8, 16):
        raise ValueError("only the measured 8x and 16x chains are supported")
    return EIGHT_X_STAGES if factor == 8 else DEFAULT_STAGES


def analyze_decimated(values: np.ndarray, factor: int) -> dict[str, object]:
    stages = stages_for_factor(factor)
    decimated = decimate_16x(values, stages=stages)
    delay_external_samples = interpolation_delay_internal_samples(stages) / factor
    start = int(
        np.ceil(delay_external_samples + ANALYSIS_START_S * EXTERNAL_RATE_HZ)
    )
    # Use an exact 10 ms/480-sample coherent window, kept well before the input
    # record ends. The selected 4 kHz-spaced products and 20 kHz fundamental
    # then neither leak into one another nor include FIR end-of-record decay.
    stop = start + int(round(ANALYSIS_DURATION_S * EXTERNAL_RATE_HZ))
    fit = fit_tones(
        decimated,
        EXTERNAL_RATE_HZ,
        FIT_FREQUENCIES_HZ,
        start_sample=start,
        stop_sample=stop,
    )
    amplitudes = {
        str(int(tone["frequency_hz"])): float(tone["peak_amplitude"])
        for tone in fit["tones"]
    }
    fundamental = amplitudes[str(int(FUNDAMENTAL_HZ))]
    selected_product_rss = float(
        np.sqrt(
            sum(
                amplitudes[str(int(frequency_hz))] ** 2
                for frequency_hz in SELECTED_PRODUCT_HZ
            )
        )
    )
    return {
        "factor": factor,
        "internal_sample_rate_hz": int(factor * EXTERNAL_RATE_HZ),
        "decimator_delay_external_samples": delay_external_samples,
        "analysis_start_sample": start,
        "analysis_stop_sample": stop,
        "fundamental_peak": fundamental,
        "selected_product_peaks": {
            key: amplitudes[key]
            for key in (str(int(value)) for value in SELECTED_PRODUCT_HZ)
        },
        "selected_product_rss": selected_product_rss,
        "selected_product_relative_db": float(
            20.0 * np.log10(max(selected_product_rss, 1.0e-300) / fundamental)
        ),
        "fit_residual_relative_db": float(fit["normalized_residual_db"]),
    }


def compare_rates(results: dict[int, dict[str, object]]) -> dict[str, float]:
    eight = results[8]
    sixteen = results[16]
    return {
        "eight_vs_sixteen_fundamental_gain_db": float(
            20.0
            * np.log10(
                float(eight["fundamental_peak"])
                / float(sixteen["fundamental_peak"])
            )
        ),
        "eight_vs_sixteen_selected_product_delta_db": float(
            float(eight["selected_product_relative_db"])
            - float(sixteen["selected_product_relative_db"])
        ),
    }


def tube_study(drive_peak_v: float) -> dict[str, object]:
    results: dict[int, dict[str, object]] = {}
    tube = Koren12AX7()
    for factor in (8, 16):
        sample_rate_hz = factor * EXTERNAL_RATE_HZ
        time_s = np.arange(int(DURATION_S * sample_rate_hz)) / sample_rate_hz
        v_gk = -1.2 + drive_peak_v * np.sin(
            2.0 * np.pi * FUNDAMENTAL_HZ * time_s
        )
        plate_current = tube.plate_current(v_gk, np.full_like(v_gk, 200.0))
        results[factor] = analyze_decimated(plate_current, factor)
    return {
        "drive_peak_v": drive_peak_v,
        "quiescent_v_gk_v": -1.2,
        "v_pk_v": 200.0,
        "rates": {str(key): value for key, value in results.items()},
        "comparison": compare_rates(results),
    }


def circuit_study(input_peak_v: float) -> dict[str, object]:
    results: dict[int, dict[str, object]] = {}
    for factor in (8, 16):
        sample_rate_hz = factor * EXTERNAL_RATE_HZ
        time_s = np.arange(int(DURATION_S * sample_rate_hz)) / sample_rate_hz
        stimulus = input_peak_v * np.sin(
            2.0 * np.pi * FUNDAMENTAL_HZ * time_s
        )
        circuit = V1CircuitModel(
            sample_rate_hz, integration_method="trapezoidal"
        )
        output = circuit.process(
            stimulus, max_iterations=8, tolerance_a=1.0e-10
        )
        analyzed = analyze_decimated(output, factor)
        analyzed["maximum_solver_iterations"] = circuit.max_iterations_observed
        analyzed["solver_nonconvergence_count"] = circuit.nonconvergence_count
        results[factor] = analyzed
    return {
        "input_peak_v": input_peak_v,
        "rates": {str(key): value for key, value in results.items()},
        "comparison": compare_rates(results),
    }


def main() -> int:
    report = {
        "status": "architecture study; reference mode remains 16x/768 kHz",
        "external_sample_rate_hz": int(EXTERNAL_RATE_HZ),
        "fundamental_hz": int(FUNDAMENTAL_HZ),
        "selected_audio_band_product_hz": [
            int(value) for value in SELECTED_PRODUCT_HZ
        ],
        "duration_s": DURATION_S,
        "analysis_start_s": ANALYSIS_START_S,
        "analysis_duration_s": ANALYSIS_DURATION_S,
        "tube_static_stress": [tube_study(0.5), tube_study(2.0)],
        "complete_circuit": [
            circuit_study(0.005),
            circuit_study(0.020),
            circuit_study(0.500),
        ],
        "limitations": [
            "selected products are an alias stress metric, not a complete perceptual error metric",
            "the complete-circuit cases cover steady 20 kHz drive, not clicks or post-burst overload recovery",
            "the fixed-point model, RTL coefficients, and resampler scheduling remain 16x only",
        ],
    }
    output = ROOT / "model" / "generated" / "internal_sample_rate_study.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
