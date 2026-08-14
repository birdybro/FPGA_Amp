#!/usr/bin/env python3
"""Measure the value-only tube candidate against the Hermite fixed reference."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.factorized_tube import (  # noqa: E402
    FixedFactorizedKoren12AX7,
    FixedLinearFactorizedKoren12AX7,
)
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedWideStateBankedChordV1CircuitModel,
)
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


SAMPLE_RATE_HZ = 768_000.0
FREQUENCY_HZ = 1_000.0
DURATION_S = 0.020
ANALYSIS_START_S = 0.010
LEVELS_V_PEAK = (0.005, 0.020, 0.500, 1.000, 1.500)


def fit_harmonics(time_s: np.ndarray, waveform: np.ndarray) -> dict[str, float]:
    columns = [np.ones_like(time_s)]
    for harmonic in range(1, 11):
        angle = 2.0 * np.pi * FREQUENCY_HZ * harmonic * time_s
        columns.extend((np.sin(angle), np.cos(angle)))
    coefficients, *_ = np.linalg.lstsq(
        np.column_stack(columns), waveform, rcond=None
    )
    complex_harmonics = np.asarray(
        [
            coefficients[2 * harmonic - 1]
            + 1j * coefficients[2 * harmonic]
            for harmonic in range(1, 11)
        ]
    )
    magnitude = np.abs(complex_harmonics)
    return {
        "fundamental_peak_v": float(magnitude[0]),
        "fundamental_phase_deg": float(np.degrees(np.angle(complex_harmonics[0]))),
        "thd_h2_to_h10_percent": float(
            100.0 * np.sqrt(np.sum(np.square(magnitude[1:]))) / magnitude[0]
        ),
    }


def model(tube: object) -> FixedWideStateBankedChordV1CircuitModel:
    return FixedWideStateBankedChordV1CircuitModel(
        SAMPLE_RATE_HZ,
        tube_lut=tube,
        integration_method="trapezoidal",
        terminal_correction=True,
    )


def diagnostics(candidate: FixedWideStateBankedChordV1CircuitModel) -> dict[str, object]:
    return {
        "saturation_count": candidate.saturation_count,
        "lut_clip_count": candidate.lut_clip_count,
        "nonconvergence_count": candidate.nonconvergence_count,
        "correction_scale_fallback_count": candidate.correction_scale_fallback_count,
        "chord_bank_selection_count": candidate.chord_bank_selection_count,
        "slew_qualified_selection_count": candidate.slew_qualified_selection_count,
    }


def compare_outputs(
    reference: np.ndarray,
    candidate: np.ndarray,
    selected: np.ndarray,
    time_s: np.ndarray,
) -> dict[str, object]:
    reference_window = reference[selected]
    candidate_window = candidate[selected]
    difference = candidate_window - reference_window
    reference_rms = float(np.sqrt(np.mean(np.square(reference_window))))
    difference_rms = float(np.sqrt(np.mean(np.square(difference))))
    reference_harmonics = fit_harmonics(time_s[selected], reference_window)
    candidate_harmonics = fit_harmonics(time_s[selected], candidate_window)
    return {
        "difference_rms_v": difference_rms,
        "difference_peak_v": float(np.max(np.abs(difference))),
        "difference_mean_v": float(np.mean(difference)),
        "normalized_difference_db": float(
            20.0 * np.log10(difference_rms / reference_rms)
            if difference_rms > 0.0 and reference_rms > 0.0
            else -float("inf")
        ),
        "fundamental_gain_difference_db": float(
            20.0
            * np.log10(
                candidate_harmonics["fundamental_peak_v"]
                / reference_harmonics["fundamental_peak_v"]
            )
        ),
        "fundamental_phase_difference_deg": float(
            candidate_harmonics["fundamental_phase_deg"]
            - reference_harmonics["fundamental_phase_deg"]
        ),
        "hermite": reference_harmonics,
        "linear": candidate_harmonics,
    }


def run_level(input_peak_v: float) -> dict[str, object]:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    input_q24 = np.rint(
        input_peak_v
        * np.sin(2.0 * np.pi * FREQUENCY_HZ * time_s)
        * float(1 << 24)
    ).astype(np.int64)
    stimulus = input_q24 / float(1 << 24)
    hermite_model = model(FixedFactorizedKoren12AX7())
    linear_model = model(FixedLinearFactorizedKoren12AX7())
    hermite_output = hermite_model.process(
        stimulus, max_iterations=3, residual_limit_a=2.0e-6
    )
    linear_output = linear_model.process(
        stimulus, max_iterations=3, residual_limit_a=2.0e-6
    )
    analytical_model = V1CircuitModel(SAMPLE_RATE_HZ)
    analytical_output = analytical_model.process(
        stimulus, max_iterations=8, tolerance_a=1.0e-12
    )
    selected = time_s >= ANALYSIS_START_S
    return {
        "input_peak_v": input_peak_v,
        **compare_outputs(hermite_output, linear_output, selected, time_s),
        "against_analytical_full_newton": {
            "hermite": compare_outputs(
                analytical_output, hermite_output, selected, time_s
            ),
            "linear": compare_outputs(
                analytical_output, linear_output, selected, time_s
            ),
            "analytical_nonconvergence_count": analytical_model.nonconvergence_count,
        },
        "hermite_diagnostics": diagnostics(hermite_model),
        "linear_diagnostics": diagnostics(linear_model),
    }


def run_burst() -> dict[str, object]:
    duration_s = 0.012
    time_s = np.arange(int(round(duration_s * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    amplitude = np.full(time_s.size, 0.005)
    amplitude[(time_s >= 0.004) & (time_s < 0.008)] = 1.5
    input_q24 = np.rint(
        amplitude
        * np.sin(2.0 * np.pi * FREQUENCY_HZ * time_s)
        * float(1 << 24)
    ).astype(np.int64)
    stimulus = input_q24 / float(1 << 24)
    hermite_model = model(FixedFactorizedKoren12AX7())
    linear_model = model(FixedLinearFactorizedKoren12AX7())
    hermite_output = hermite_model.process(
        stimulus, max_iterations=3, residual_limit_a=2.0e-6
    )
    linear_output = linear_model.process(
        stimulus, max_iterations=3, residual_limit_a=2.0e-6
    )
    windows = {
        "preburst": time_s < 0.004,
        "burst": (time_s >= 0.004) & (time_s < 0.008),
        "recovery": time_s >= 0.008,
    }
    return {
        "stimulus": "5 mV peak, 1.5 V peak from 4--8 ms, 1 kHz",
        "windows": {
            name: compare_outputs(
                hermite_output, linear_output, selected, time_s
            )
            for name, selected in windows.items()
        },
        "hermite_diagnostics": diagnostics(hermite_model),
        "linear_diagnostics": diagnostics(linear_model),
    }


def main() -> int:
    with ProcessPoolExecutor(max_workers=3) as executor:
        level_results = list(executor.map(run_level, LEVELS_V_PEAK))
    burst = run_burst()
    report = {
        "comparison": (
            "fixed value-only linear factorized 12AX7 versus established fixed "
            "cubic-Hermite factorized 12AX7 in the identical trapezoidal, "
            "banked, terminal-corrected V1 circuit"
        ),
        "sample_rate_hz": int(SAMPLE_RATE_HZ),
        "continuous_sine_duration_s": DURATION_S,
        "continuous_sine_analysis_window_s": [ANALYSIS_START_S, DURATION_S],
        "levels": level_results,
        "burst": burst,
        "interpretation": (
            "The continuous-sine cases include the analytical Koren/full-Newton "
            "software reference; the burst isolates the two fixed candidates. "
            "This is not an analog/SPICE or hardware comparison and does not "
            "promote the linear candidate to reference mode."
        ),
    }
    generated = ROOT / "model" / "generated" / "linear_factorized_circuit_comparison.json"
    result = ROOT / "reference" / "results" / "linear_factorized_circuit_comparison.json"
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
