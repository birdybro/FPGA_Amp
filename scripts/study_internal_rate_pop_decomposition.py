#!/usr/bin/env python3
"""Decompose the 8x/16x record-pop discrepancy by implementation layer."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.null_compare import compare_signals, windowed_spectrum  # noqa: E402
from fpga_amp.stream import (  # noqa: E402
    compose_fixed_converter_only,
    compose_fixed_wide_stream,
    compose_floating_stream,
)


EXTERNAL_SAMPLE_RATE_HZ = 48_000.0
FRAME_COUNT = 4_096
Q24_SCALE = float(1 << 24)


def _input_q24(values_v: np.ndarray) -> np.ndarray:
    values = np.rint(np.asarray(values_v, dtype=np.float64) * Q24_SCALE)
    if np.any((values < -(1 << 31)) | (values > (1 << 31) - 1)):
        raise RuntimeError("pop decomposition stimulus exceeds signed Q8.24")
    return values.astype(np.int64)


def _spectral_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    frequencies, reference_spectrum, _, residual_spectrum = windowed_spectrum(
        reference, candidate, EXTERNAL_SAMPLE_RATE_HZ
    )
    report: dict[str, float] = {}
    for name, lower_hz, upper_hz in (
        ("audio_band", 20.0, 20_000.0),
        ("upper_audio_band", 10_000.0, 20_000.0),
    ):
        selected = (frequencies >= lower_hz) & (frequencies <= upper_hz)
        reference_rss = float(np.linalg.norm(reference_spectrum[selected]))
        residual_rss = float(np.linalg.norm(residual_spectrum[selected]))
        report[f"{name}_reference_spectral_rss_v"] = reference_rss
        report[f"{name}_residual_spectral_rss_v"] = residual_rss
        report[f"{name}_residual_relative_db"] = float(
            20.0
            * np.log10(max(residual_rss, 1.0e-300) / max(reference_rss, 1.0e-300))
        )
    return report


def _compare(
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    known_latency_samples: float,
) -> dict[str, object]:
    use_fractional_delay = not float(known_latency_samples).is_integer()
    comparison = compare_signals(
        reference,
        candidate,
        max_lag_samples=8,
        align_latency=True,
        fractional_delay=use_fractional_delay,
        fractional_delay_method="windowed_sinc",
        known_latency_samples=known_latency_samples,
        align_gain=False,
    )
    return {
        **comparison.report,
        "aligned_spectral_delta": _spectral_metrics(
            comparison.reference_aligned, comparison.candidate_aligned
        ),
    }


def main() -> int:
    index = np.arange(FRAME_COUNT, dtype=np.float64)
    control_v = 0.005 * np.sin(
        2.0 * np.pi * 1_000.0 * index / EXTERNAL_SAMPLE_RATE_HZ
    )
    pop_v = control_v.copy()
    pop_v[1_024] += 0.020
    pop_v[1_025] -= 0.012
    control_q24 = _input_q24(control_v)
    pop_q24 = _input_q24(pop_v)

    converter_responses: dict[int, np.ndarray] = {}
    floating_responses: dict[int, np.ndarray] = {}
    fixed_responses: dict[int, np.ndarray] = {}
    rates: dict[str, object] = {}
    total_nonlinear_updates = 0
    for factor in (8, 16):
        sample_rate_hz = int(factor * EXTERNAL_SAMPLE_RATE_HZ)
        print(f"processing pop decomposition at {sample_rate_hz} Hz", flush=True)
        converter_pop, converter_pop_saturations = compose_fixed_converter_only(
            pop_q24, internal_sample_rate_hz=sample_rate_hz
        )
        converter_control, converter_control_saturations = (
            compose_fixed_converter_only(
                control_q24, internal_sample_rate_hz=sample_rate_hz
            )
        )
        converter_responses[factor] = (
            converter_pop.astype(np.float64)
            - converter_control.astype(np.float64)
        ) / Q24_SCALE

        floating_pop = compose_floating_stream(
            pop_q24,
            integration_method="trapezoidal",
            internal_sample_rate_hz=sample_rate_hz,
        )
        floating_control = compose_floating_stream(
            control_q24,
            integration_method="trapezoidal",
            internal_sample_rate_hz=sample_rate_hz,
        )
        floating_responses[factor] = (
            floating_pop.output_v - floating_control.output_v
        )

        fixed_pop = compose_fixed_wide_stream(
            pop_q24,
            trapezoidal=True,
            banked=True,
            terminal_correction=True,
            internal_sample_rate_hz=sample_rate_hz,
        )
        fixed_control = compose_fixed_wide_stream(
            control_q24,
            trapezoidal=True,
            banked=True,
            terminal_correction=True,
            internal_sample_rate_hz=sample_rate_hz,
        )
        fixed_responses[factor] = (
            fixed_pop.output_q24.astype(np.float64)
            - fixed_control.output_q24.astype(np.float64)
        ) / Q24_SCALE
        diagnostic_counts = {
            "pop": fixed_pop.diagnostic_counts,
            "control": fixed_control.diagnostic_counts,
        }
        diagnostic_total = sum(
            sum(values.values()) for values in diagnostic_counts.values()
        )
        if diagnostic_total != 0:
            raise RuntimeError(
                f"{factor}x fixed decomposition produced {diagnostic_total} events"
            )
        nonconvergence = (
            floating_pop.circuit.nonconvergence_count
            + floating_control.circuit.nonconvergence_count
        )
        if nonconvergence != 0:
            raise RuntimeError(
                f"{factor}x floating decomposition produced {nonconvergence} failures"
            )
        total_nonlinear_updates += 4 * factor * FRAME_COUNT
        rates[str(factor)] = {
            "internal_sample_rate_hz": sample_rate_hz,
            "converter_saturation_count": (
                converter_pop_saturations + converter_control_saturations
            ),
            "floating_nonconvergence_count": nonconvergence,
            "fixed_diagnostics": diagnostic_counts,
            "response_peak_v": {
                "converter_only": float(
                    np.max(np.abs(converter_responses[factor]))
                ),
                "floating_newton": float(
                    np.max(np.abs(floating_responses[factor]))
                ),
                "fixed_banked_terminal": float(
                    np.max(np.abs(fixed_responses[factor]))
                ),
            },
            "fixed_vs_floating": _compare(
                floating_responses[factor],
                fixed_responses[factor],
                known_latency_samples=0.0,
            ),
        }

    rate_comparisons = {
        "converter_only": _compare(
            converter_responses[16],
            converter_responses[8],
            known_latency_samples=-1.25,
        ),
        "floating_newton_complete_stream": _compare(
            floating_responses[16],
            floating_responses[8],
            known_latency_samples=-1.25,
        ),
        "fixed_banked_terminal_complete_stream": _compare(
            fixed_responses[16],
            fixed_responses[8],
            known_latency_samples=-1.25,
        ),
    }
    prior_path = ROOT / "model" / "generated" / "internal_sample_rate_study.json"
    if prior_path.is_file():
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        prior_comparison = prior["complete_fixed_stream_transients"][
            "synthetic_record_pop"
        ]["candidate_8x_vs_reference_16x"]
        if (
            prior_comparison["transformations"].get("known_latency_samples")
            == -1.25
        ):
            prior_db = float(prior_comparison["final"]["normalized_residual_db"])
            current_db = float(
                rate_comparisons["fixed_banked_terminal_complete_stream"]["final"]
                ["normalized_residual_db"]
            )
            if abs(prior_db - current_db) > 1.0e-12:
                raise RuntimeError(
                    f"fixed pop decomposition {current_db} dB does not "
                    f"reproduce {prior_db} dB"
                )

    report = {
        "model": "12ax7_passive_riaa_v1",
        "category": "8x architecture diagnosis; reference remains 16x",
        "external_sample_rate_hz": int(EXTERNAL_SAMPLE_RATE_HZ),
        "frame_count": FRAME_COUNT,
        "total_nonlinear_updates": total_nonlinear_updates,
        "stimulus": {
            "nominal_tone_hz": 1_000,
            "nominal_tone_peak_v": 0.005,
            "event_start_sample": 1_024,
            "event_samples_v": [0.020, -0.012],
        },
        "rates": rates,
        "candidate_8x_vs_reference_16x": rate_comparisons,
        "comparison_policy": (
            "known -1.25-sample converter-delay alignment with 64-tap "
            "Lanczos-windowed sinc interpolation; no gain or DC fit"
        ),
    }
    output = ROOT / "model" / "generated" / "internal_rate_pop_decomposition.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
