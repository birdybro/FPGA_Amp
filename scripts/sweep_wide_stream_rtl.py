#!/usr/bin/env python3
"""Capture complete-stream RTL frequency response at the 48 kHz boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.stream import (  # noqa: E402
    CONVERTER_GROUP_DELAY_EXTERNAL_SAMPLES,
    EXTERNAL_SAMPLE_RATE_HZ,
    compose_fixed_converter_only,
    compose_fixed_wide_stream,
    compose_floating_converter_only,
    compose_floating_stream,
)


def _tag(frequency_hz: float) -> str:
    return f"{frequency_hz:g}".replace(".", "p")


def _fit_tone(
    waveform: np.ndarray,
    indices: np.ndarray,
    frequency_hz: float,
) -> dict[str, float]:
    angle = 2.0 * np.pi * frequency_hz * indices / EXTERNAL_SAMPLE_RATE_HZ
    basis = np.column_stack((np.ones(indices.size), np.sin(angle), np.cos(angle)))
    coefficient, *_ = np.linalg.lstsq(basis, waveform[indices], rcond=None)
    return {
        "mean_v": float(coefficient[0]),
        "fundamental_peak_v": float(np.hypot(coefficient[1], coefficient[2])),
        "phase_deg": float(np.degrees(np.arctan2(coefficient[2], coefficient[1]))),
    }


def _wrap_phase_deg(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def _response(
    input_metrics: dict[str, float], output_metrics: dict[str, float]
) -> dict[str, float]:
    return {
        **output_metrics,
        "gain_db": float(
            20.0
            * np.log10(
                output_metrics["fundamental_peak_v"]
                / input_metrics["fundamental_peak_v"]
            )
        ),
        "phase_deg_relative_to_input": _wrap_phase_deg(
            output_metrics["phase_deg"] - input_metrics["phase_deg"]
        ),
    }


def _write_vectors(path: Path, inputs: np.ndarray, outputs: np.ndarray) -> None:
    with path.open("w", encoding="ascii") as handle:
        for value in inputs:
            handle.write(f"{int(value)}\n")
        handle.write("EXPECTED\n")
        for value in outputs:
            handle.write(f"{int(value)}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verilator", default="verilator")
    parser.add_argument("--trapezoidal", action="store_true")
    parser.add_argument("--banked", action="store_true")
    parser.add_argument("--terminal-correction", action="store_true")
    parser.add_argument(
        "--run-only",
        action="store_true",
        help="reuse the simulator built by an earlier matching sweep",
    )
    parser.add_argument("--vectors", type=int, default=4800)
    parser.add_argument("--analysis-vectors", type=int, default=2400)
    parser.add_argument(
        "--frequencies-hz",
        type=float,
        nargs="+",
        default=(100.0, 1_000.0, 10_000.0, 20_000.0),
    )
    args = parser.parse_args()
    if args.terminal_correction and not args.banked:
        parser.error("terminal correction requires --banked")
    if (args.banked or args.terminal_correction) and not args.trapezoidal:
        parser.error("this captured banked sweep is defined for trapezoidal mode")
    if not 0 < args.vectors <= 8192:
        parser.error("--vectors must be within 1..8192")
    if not 0 < args.analysis_vectors <= args.vectors:
        parser.error("--analysis-vectors must be within 1..vectors")
    if any(value <= 0.0 or value > 20_000.0 for value in args.frequencies_hz):
        parser.error("frequencies must be within 0 < f <= 20 kHz")

    integration_method = "trapezoidal" if args.trapezoidal else "backward_euler"
    if args.trapezoidal and args.terminal_correction:
        stem = "wide_stream_rtl_trapezoidal_banked_terminal_frequency"
    elif args.trapezoidal:
        stem = "wide_stream_rtl_trapezoidal_frequency"
    else:
        stem = "wide_stream_rtl_frequency"
    analysis_indices = np.arange(
        args.vectors - args.analysis_vectors,
        args.vectors,
        dtype=np.int64,
    )
    external_index = np.arange(args.vectors, dtype=np.float64)
    measurements: list[dict[str, object]] = []
    built = args.run_only
    for frequency_hz in args.frequencies_hz:
        input_q24 = np.rint(
            0.005
            * np.sin(
                2.0
                * np.pi
                * frequency_hz
                * external_index
                / EXTERNAL_SAMPLE_RATE_HZ
            )
            * (1 << 24)
        ).astype(np.int64)
        fixed = compose_fixed_wide_stream(
            input_q24,
            trapezoidal=args.trapezoidal,
            banked=args.banked,
            terminal_correction=args.terminal_correction,
        )
        floating = compose_floating_stream(
            input_q24, integration_method=integration_method
        )
        fixed_converter_q24, converter_saturations = (
            compose_fixed_converter_only(input_q24)
        )
        floating_converter_v = compose_floating_converter_only(input_q24)
        if converter_saturations:
            raise RuntimeError("nominal converter-only trajectory saturated")

        point_tag = _tag(frequency_hz)
        vector_path = ROOT / "build" / f"{stem}_{point_tag}hz_vectors.txt"
        capture_path = ROOT / "build" / f"{stem}_{point_tag}hz_capture.txt"
        vector_path.parent.mkdir(parents=True, exist_ok=True)
        _write_vectors(vector_path, input_q24, fixed.output_q24)
        command = [
            sys.executable,
            "scripts/run_wide_stream_rtl.py",
            "--verilator",
            args.verilator,
            "--vectors-file",
            str(vector_path.relative_to(ROOT)),
            "--vector-count",
            str(args.vectors),
            "--capture-file",
            str(capture_path.relative_to(ROOT)),
        ]
        if args.trapezoidal:
            command.append("--trapezoidal")
        if args.banked:
            command.append("--banked")
        if args.terminal_correction:
            command.append("--terminal-correction")
        if built:
            command.extend(("--skip-generate", "--run-only"))
        subprocess.run(command, cwd=ROOT, check=True)
        built = True

        captured = np.atleast_2d(np.loadtxt(capture_path, dtype=np.int64))
        if captured.shape != (args.vectors, 2):
            raise RuntimeError(
                f"expected {args.vectors} outputs, captured {captured.shape}"
            )
        if not np.array_equal(captured[:, 0], np.arange(args.vectors)):
            raise RuntimeError("captured output indices are not contiguous")
        if not np.array_equal(captured[:, 1], fixed.output_q24):
            difference = np.flatnonzero(captured[:, 1] != fixed.output_q24)
            raise RuntimeError(
                f"captured RTL differs from fixed at output {int(difference[0])}"
            )

        input_v = input_q24.astype(np.float64) / float(1 << 24)
        rtl_v = captured[:, 1].astype(np.float64) / float(1 << 24)
        fixed_converter_v = (
            fixed_converter_q24.astype(np.float64) / float(1 << 24)
        )
        input_metrics = _fit_tone(input_v, analysis_indices, frequency_hz)
        rtl_response = _response(
            input_metrics, _fit_tone(rtl_v, analysis_indices, frequency_hz)
        )
        floating_response = _response(
            input_metrics,
            _fit_tone(floating.output_v, analysis_indices, frequency_hz),
        )
        fixed_converter_response = _response(
            input_metrics,
            _fit_tone(fixed_converter_v, analysis_indices, frequency_hz),
        )
        floating_converter_response = _response(
            input_metrics,
            _fit_tone(floating_converter_v, analysis_indices, frequency_hz),
        )
        residual = rtl_v[analysis_indices] - floating.output_v[analysis_indices]
        residual_mean = float(np.mean(residual))
        centered_index = (
            np.arange(residual.size, dtype=np.float64)
            - 0.5 * (residual.size - 1)
        )
        drift_basis = np.column_stack(
            (np.ones(residual.size), centered_index)
        )
        drift_coefficient, *_ = np.linalg.lstsq(
            drift_basis, residual, rcond=None
        )
        residual_detrended = residual - drift_basis @ drift_coefficient
        reference_rms = float(
            np.sqrt(np.mean(np.square(floating.output_v[analysis_indices])))
        )
        expected_converter_phase = _wrap_phase_deg(
            -360.0
            * frequency_hz
            * CONVERTER_GROUP_DELAY_EXTERNAL_SAMPLES
            / EXTERNAL_SAMPLE_RATE_HZ
        )
        diagnostics = fixed.diagnostic_counts
        diagnostic_total = sum(diagnostics.values())
        if diagnostic_total:
            raise RuntimeError(
                f"nominal {frequency_hz:g} Hz trajectory produced "
                f"{diagnostic_total} diagnostics"
            )
        measurement = {
            "frequency_hz": frequency_hz,
            "analysis_cycles": (
                frequency_hz * args.analysis_vectors / EXTERNAL_SAMPLE_RATE_HZ
            ),
            "rtl_fixed_bit_exact": True,
            "input": input_metrics,
            "end_to_end": {
                "floating": floating_response,
                "captured_rtl": {
                    **rtl_response,
                    "gain_error_vs_floating_db": (
                        rtl_response["gain_db"] - floating_response["gain_db"]
                    ),
                    "phase_error_vs_floating_deg": _wrap_phase_deg(
                        rtl_response["phase_deg_relative_to_input"]
                        - floating_response["phase_deg_relative_to_input"]
                    ),
                    "raw_normalized_residual_db": float(
                        20.0
                        * np.log10(
                            np.sqrt(np.mean(np.square(residual))) / reference_rms
                        )
                    ),
                    "mean_removed_normalized_residual_db": float(
                        20.0
                        * np.log10(
                            np.sqrt(
                                np.mean(np.square(residual - residual_mean))
                            )
                            / reference_rms
                        )
                    ),
                    "residual_mean_v": residual_mean,
                    "linear_residual_drift_v_per_external_sample": float(
                        drift_coefficient[1]
                    ),
                    "linear_residual_drift_v_across_window": float(
                        drift_coefficient[1] * (residual.size - 1)
                    ),
                    "linear_detrended_normalized_residual_db": float(
                        20.0
                        * np.log10(
                            np.sqrt(np.mean(np.square(residual_detrended)))
                            / reference_rms
                        )
                    ),
                },
            },
            "converter_only": {
                "nominal_group_delay_phase_deg": expected_converter_phase,
                "floating": floating_converter_response,
                "fixed": fixed_converter_response,
                "fixed_phase_error_vs_nominal_deg": _wrap_phase_deg(
                    fixed_converter_response["phase_deg_relative_to_input"]
                    - expected_converter_phase
                ),
            },
            "circuit_attributed_after_converter_removal": {
                "floating_gain_db": (
                    floating_response["gain_db"]
                    - floating_converter_response["gain_db"]
                ),
                "floating_phase_deg": _wrap_phase_deg(
                    floating_response["phase_deg_relative_to_input"]
                    - floating_converter_response["phase_deg_relative_to_input"]
                ),
                "rtl_gain_db": (
                    rtl_response["gain_db"] - fixed_converter_response["gain_db"]
                ),
                "rtl_phase_deg": _wrap_phase_deg(
                    rtl_response["phase_deg_relative_to_input"]
                    - fixed_converter_response["phase_deg_relative_to_input"]
                ),
            },
            "diagnostics": {
                **diagnostics,
                "maximum_solver_residual_a": (
                    fixed.circuit.max_residual_q44_observed / float(1 << 44)
                ),
                "floating_nonconvergence_count": (
                    floating.circuit.nonconvergence_count
                ),
            },
        }
        measurements.append(measurement)
        print(
            f"{frequency_hz:8.1f} Hz: "
            "RTL/float "
            f"{measurement['end_to_end']['captured_rtl']['gain_error_vs_floating_db']:+.7f} dB, "
            f"{measurement['end_to_end']['captured_rtl']['phase_error_vs_floating_deg']:+.7f} deg; "
            f"converter {fixed_converter_response['phase_deg_relative_to_input']:+.3f} deg",
            flush=True,
        )

    rtl_points = [point["end_to_end"]["captured_rtl"] for point in measurements]
    summary = {
        "model": "12ax7_passive_riaa_v1",
        "implementation": "captured complete SystemVerilog wide stream",
        "integration_method": integration_method,
        "banked_chord": args.banked,
        "terminal_correction": args.terminal_correction,
        "solver_latency_clocks": 127 if args.terminal_correction else 116,
        "external_sample_rate_hz": EXTERNAL_SAMPLE_RATE_HZ,
        "internal_sample_rate_hz": 16.0 * EXTERNAL_SAMPLE_RATE_HZ,
        "input_peak_v": 0.005,
        "vectors_per_frequency": args.vectors,
        "analysis_vectors_per_frequency": args.analysis_vectors,
        "converter_group_delay_external_samples": (
            CONVERTER_GROUP_DELAY_EXTERNAL_SAMPLES
        ),
        "converter_group_delay_ms": (
            1000.0
            * CONVERTER_GROUP_DELAY_EXTERNAL_SAMPLES
            / EXTERNAL_SAMPLE_RATE_HZ
        ),
        "phase_reporting": (
            "End-to-end phase includes the causal converters. Circuit-attributed "
            "phase subtracts a separately measured identity-path converter phase."
        ),
        "all_rtl_fixed_bit_exact": all(
            bool(point["rtl_fixed_bit_exact"]) for point in measurements
        ),
        "maximum_absolute_gain_error_vs_floating_db": max(
            abs(float(point["gain_error_vs_floating_db"])) for point in rtl_points
        ),
        "maximum_absolute_phase_error_vs_floating_deg": max(
            abs(float(point["phase_error_vs_floating_deg"])) for point in rtl_points
        ),
        "worst_mean_removed_normalized_residual_db": max(
            float(point["mean_removed_normalized_residual_db"])
            for point in rtl_points
        ),
        "worst_linear_detrended_normalized_residual_db": max(
            float(point["linear_detrended_normalized_residual_db"])
            for point in rtl_points
        ),
        "measurements": measurements,
    }
    if not summary["all_rtl_fixed_bit_exact"]:
        raise RuntimeError("captured complete stream is not fixed bit-exact")
    if float(summary["maximum_absolute_gain_error_vs_floating_db"]) > 0.0002:
        raise RuntimeError("complete-stream gain error exceeds 0.0002 dB")
    if float(summary["maximum_absolute_phase_error_vs_floating_deg"]) > 0.0015:
        raise RuntimeError("complete-stream phase error exceeds 0.0015 degrees")
    if args.terminal_correction:
        # The terminal trajectory resolves the long circuit modes differently
        # from floating Newton during startup. Preserve its raw/mean-removed
        # nulls and fitted drift, but gate audio-shape error independently of
        # that documented 143.9 ms / 1.068 s recovery. No gain or phase
        # alignment is applied.
        if (
            float(summary["worst_linear_detrended_normalized_residual_db"])
            > -70.0
        ):
            raise RuntimeError(
                "complete-stream linear-detrended residual exceeds -70 dB"
            )
    elif float(summary["worst_mean_removed_normalized_residual_db"]) > -65.0:
        raise RuntimeError("complete-stream mean-removed residual exceeds -65 dB")
    if any(
        int(point["diagnostics"]["floating_nonconvergence_count"])
        for point in measurements
    ):
        raise RuntimeError("floating complete stream failed to converge")
    output = ROOT / "model" / "generated" / f"{stem}_summary.json"
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    result = ROOT / "reference" / "results" / f"{stem}.json"
    result.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
