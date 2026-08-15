#!/usr/bin/env python3
"""Measure an explicit 8x internal-rate candidate against the 16x reference.

This is an architecture study, not a change to reference mode.  It separates
the physical circuit integration error (reported by the SPICE comparison) from
audio-band products caused by sampling a nonlinear tube/circuit at 384 kHz and
compares complete fixed-stream pop and overload-recovery trajectories.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.audio_analysis import (  # noqa: E402
    fit_tones,
    signal_summary,
    sustained_recovery_analysis,
)
from fpga_amp.null_compare import compare_signals, windowed_spectrum  # noqa: E402
from fpga_amp.resampling import (  # noqa: E402
    DEFAULT_STAGES,
    EIGHT_X_STAGES,
    decimate_16x,
    interpolation_delay_internal_samples,
)
from fpga_amp.tube import Koren12AX7  # noqa: E402
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402
from fpga_amp.stream import compose_fixed_wide_stream  # noqa: E402


EXTERNAL_RATE_HZ = 48_000.0
FUNDAMENTAL_HZ = 20_000.0
SELECTED_PRODUCT_HZ = (4_000.0, 8_000.0, 12_000.0, 16_000.0)
FIT_FREQUENCIES_HZ = (*SELECTED_PRODUCT_HZ, FUNDAMENTAL_HZ)
DURATION_S = 0.040
ANALYSIS_START_S = 0.020
ANALYSIS_DURATION_S = 0.010
Q24_SCALE = float(1 << 24)


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


def _fixed_input_q24(values_v: np.ndarray) -> np.ndarray:
    unbounded = np.rint(np.asarray(values_v, dtype=np.float64) * Q24_SCALE)
    if np.any((unbounded < -(1 << 31)) | (unbounded > (1 << 31) - 1)):
        raise RuntimeError("internal-rate stimulus exceeds signed Q8.24")
    return unbounded.astype(np.int64)


def _fixed_stream(values_v: np.ndarray, sample_rate_hz: int) -> tuple[np.ndarray, dict]:
    result = compose_fixed_wide_stream(
        _fixed_input_q24(values_v),
        trapezoidal=True,
        banked=True,
        terminal_correction=True,
        internal_sample_rate_hz=sample_rate_hz,
    )
    diagnostics = result.diagnostic_counts
    if sum(diagnostics.values()) != 0:
        raise RuntimeError(
            f"{sample_rate_hz} Hz fixed stream produced diagnostics: {diagnostics}"
        )
    return result.output_q24.astype(np.float64) / Q24_SCALE, diagnostics


def _audio_band_spectral_delta(
    reference: np.ndarray,
    candidate: np.ndarray,
) -> dict[str, float]:
    frequencies, reference_spectrum, _, residual_spectrum = windowed_spectrum(
        reference, candidate, EXTERNAL_RATE_HZ
    )
    result: dict[str, float] = {}
    for name, lower_hz, upper_hz in (
        ("audio_band", 20.0, 20_000.0),
        ("upper_audio_band", 10_000.0, 20_000.0),
    ):
        selected = (frequencies >= lower_hz) & (frequencies <= upper_hz)
        reference_rss = float(np.linalg.norm(reference_spectrum[selected]))
        residual_rss = float(np.linalg.norm(residual_spectrum[selected]))
        result[f"{name}_reference_spectral_rss_v"] = reference_rss
        result[f"{name}_residual_spectral_rss_v"] = residual_rss
        result[f"{name}_residual_relative_db"] = float(
            20.0
            * np.log10(max(residual_rss, 1.0e-300) / max(reference_rss, 1.0e-300))
        )
    return result


def _rate_comparison(
    reference_16x: np.ndarray,
    candidate_8x: np.ndarray,
) -> dict[str, object]:
    comparison = compare_signals(
        reference_16x,
        candidate_8x,
        max_lag_samples=8,
        align_latency=True,
        fractional_delay=True,
        align_gain=False,
    )
    return {
        **comparison.report,
        "aligned_spectral_delta": _audio_band_spectral_delta(
            comparison.reference_aligned,
            comparison.candidate_aligned,
        ),
    }


def fixed_pop_study() -> dict[str, object]:
    frame_count = 4_096
    event_start = 1_024
    indices = np.arange(frame_count, dtype=np.float64)
    control = 0.005 * np.sin(2.0 * np.pi * 1_000.0 * indices / EXTERNAL_RATE_HZ)
    stimulus = control.copy()
    stimulus[event_start] += 0.020
    stimulus[event_start + 1] -= 0.012

    responses: dict[int, np.ndarray] = {}
    rates: dict[str, object] = {}
    for factor in (8, 16):
        sample_rate_hz = int(factor * EXTERNAL_RATE_HZ)
        output, output_diagnostics = _fixed_stream(stimulus, sample_rate_hz)
        baseline, baseline_diagnostics = _fixed_stream(control, sample_rate_hz)
        response = output - baseline
        responses[factor] = response
        detected = np.flatnonzero(np.abs(response) > 4.0 / Q24_SCALE)
        rates[str(factor)] = {
            "internal_sample_rate_hz": sample_rate_hz,
            "output_diagnostics": output_diagnostics,
            "control_diagnostics": baseline_diagnostics,
            "first_detected_output_sample": (
                None if detected.size == 0 else int(detected[0])
            ),
            "peak_output_sample": int(np.argmax(np.abs(response))),
            "response": signal_summary(response),
        }

    comparison = _rate_comparison(responses[16], responses[8])
    return {
        "stimulus": {
            "frame_count": frame_count,
            "nominal_tone_hz": 1_000,
            "nominal_tone_peak_v": 0.005,
            "event_start_sample": event_start,
            "event_samples_v": [0.020, -0.012],
        },
        "rates": rates,
        "candidate_8x_vs_reference_16x": comparison,
    }


def fixed_recovery_study() -> dict[str, object]:
    frame_count = 12_000
    burst_start = 480
    burst_stop = 720
    indices = np.arange(frame_count, dtype=np.float64)
    control = 0.005 * np.sin(2.0 * np.pi * 1_000.0 * indices / EXTERNAL_RATE_HZ)
    stimulus = control.copy()
    stimulus[burst_start:burst_stop] = 0.500 * np.sin(
        2.0
        * np.pi
        * 1_000.0
        * indices[burst_start:burst_stop]
        / EXTERNAL_RATE_HZ
    )

    controls: dict[int, np.ndarray] = {}
    responses: dict[int, np.ndarray] = {}
    diagnostics: dict[str, object] = {}
    for factor in (8, 16):
        sample_rate_hz = int(factor * EXTERNAL_RATE_HZ)
        output, output_diagnostics = _fixed_stream(stimulus, sample_rate_hz)
        baseline, baseline_diagnostics = _fixed_stream(control, sample_rate_hz)
        controls[factor] = baseline
        responses[factor] = output - baseline
        diagnostics[str(factor)] = {
            "output": output_diagnostics,
            "control": baseline_diagnostics,
        }

    reference_nominal_rms = float(
        np.sqrt(np.mean(np.square(controls[16][-4_800:])))
    )
    threshold_v_rms = 0.10 * reference_nominal_rms
    rates: dict[str, object] = {}
    recovery_seconds: dict[int, float] = {}
    for factor in (8, 16):
        recovery = sustained_recovery_analysis(
            responses[factor],
            EXTERNAL_RATE_HZ,
            threshold_v_rms,
            burst_stop,
            window_seconds=0.001,
        )
        measured = recovery["recovery_seconds_after_start"]
        if measured is None:
            raise RuntimeError(f"{factor}x stream did not recover inside 250 ms")
        recovery_seconds[factor] = float(measured)
        rates[str(factor)] = {
            "internal_sample_rate_hz": int(factor * EXTERNAL_RATE_HZ),
            "diagnostics": diagnostics[str(factor)],
            "recovery": recovery,
            "peak_post_burst_deviation_v": float(
                np.max(np.abs(responses[factor][burst_stop:]))
            ),
            "final_10ms_deviation_rms_v": float(
                np.sqrt(np.mean(np.square(responses[factor][-480:])))
            ),
        }

    recovery_delta_s = recovery_seconds[8] - recovery_seconds[16]
    if abs(recovery_delta_s) >= 0.005:
        raise RuntimeError(
            f"8x/16x recovery delta {recovery_delta_s:.6f} s exceeds 5 ms"
        )
    comparison = _rate_comparison(responses[16], responses[8])
    return {
        "stimulus": {
            "frame_count": frame_count,
            "nominal_tone_hz": 1_000,
            "nominal_tone_peak_v": 0.005,
            "burst_peak_v": 0.500,
            "burst_start_sample": burst_start,
            "burst_stop_sample": burst_stop,
            "post_burst_observation_s": (frame_count - burst_stop)
            / EXTERNAL_RATE_HZ,
        },
        "common_recovery_threshold_v_rms": threshold_v_rms,
        "rates": rates,
        "eight_minus_sixteen_recovery_s": recovery_delta_s,
        "candidate_8x_vs_reference_16x": comparison,
    }


def main() -> int:
    print("running floating steady-state rate study", flush=True)
    tube_results = [tube_study(0.5), tube_study(2.0)]
    circuit_results = [
        circuit_study(0.005),
        circuit_study(0.020),
        circuit_study(0.500),
    ]
    print("running complete fixed pop rate study", flush=True)
    pop_result = fixed_pop_study()
    print("running complete fixed overload-recovery rate study", flush=True)
    recovery_result = fixed_recovery_study()
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
        "tube_static_stress": tube_results,
        "complete_circuit": circuit_results,
        "complete_fixed_stream_transients": {
            "synthetic_record_pop": pop_result,
            "accepted_range_overload_recovery": recovery_result,
        },
        "limitations": [
            "selected products are an alias stress metric, not a complete perceptual error metric",
            "the aligned transient residual includes integration, fixed-point, and resampler-rate differences; it is not labeled as alias alone",
            "fixed transient outputs are bit-accurate model results; only the short deterministic stream has direct RTL equivalence so far",
            "named-part timing remains open and reference mode remains 16x",
        ],
    }
    output = ROOT / "model" / "generated" / "internal_sample_rate_study.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
