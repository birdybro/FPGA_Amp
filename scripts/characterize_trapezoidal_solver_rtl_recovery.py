#!/usr/bin/env python3
"""Capture accepted-range trapezoidal RTL through long overload recovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from characterize_overload_recovery import (  # noqa: E402
    sliding_rms,
    sustained_recovery_s,
)
from wide_solver_rtl_capture import capture_wide_solver_rtl  # noqa: E402


SAMPLE_RATE_HZ = 768_000.0
FREQUENCY_HZ = 1_000.0
NOMINAL_PEAK_V = 0.005
BURST_PEAK_V = 0.500
BURST_START_S = 0.010
BURST_END_S = 0.015
DURATION_S = 0.250


def _input_q24(level_peak_v: float) -> np.ndarray:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    amplitude = np.full(time_s.size, NOMINAL_PEAK_V)
    amplitude[(time_s >= BURST_START_S) & (time_s < BURST_END_S)] = level_peak_v
    return np.rint(
        amplitude * np.sin(2.0 * np.pi * FREQUENCY_HZ * time_s) * (1 << 24)
    ).astype(np.int64)


def _diagnostics(capture: object) -> dict[str, float | int | None]:
    fixed = capture.fixed_model
    return {
        "maximum_residual_a": fixed.max_residual_q44_observed / float(1 << 44),
        "residual_limit_exceedance_count": fixed.nonconvergence_count,
        "saturation_count": fixed.saturation_count,
        "range_clip_count": fixed.lut_clip_count,
        "correction_scale_fallback_count": (
            fixed.correction_scale_fallback_count
        ),
        "minimum_correction_residual_fractional_bits": (
            fixed.minimum_correction_residual_fractional_bits
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verilator", default="verilator")
    args = parser.parse_args()
    for command in (
        [sys.executable, "scripts/generate_wide_network_vectors.py"],
        [sys.executable, "scripts/generate_trapezoidal_network_vectors.py"],
        [
            sys.executable,
            "scripts/generate_wide_chord_vectors.py",
            "--trapezoidal",
        ],
        [sys.executable, "scripts/generate_factorized_tube.py"],
    ):
        subprocess.run(command, cwd=ROOT, check=True)

    control_capture = capture_wide_solver_rtl(
        _input_q24(NOMINAL_PEAK_V),
        "trapezoidal_solver_rtl_recovery_control",
        args.verilator,
        trapezoidal=True,
    )
    overload_capture = capture_wide_solver_rtl(
        _input_q24(BURST_PEAK_V),
        "trapezoidal_solver_rtl_recovery_0p5v",
        args.verilator,
        trapezoidal=True,
    )
    control = control_capture.rtl_output_q32.astype(np.float64) / float(1 << 32)
    overload = overload_capture.rtl_output_q32.astype(np.float64) / float(1 << 32)
    residual = overload - control
    sample_count = residual.size
    post_index = int(round(BURST_END_S * SAMPLE_RATE_HZ))
    final_window = slice(sample_count - int(round(0.010 * SAMPLE_RATE_HZ)), None)
    nominal_output_rms = float(
        np.sqrt(np.mean(np.square(control[final_window])))
    )
    thresholds = {
        "ten_percent_nominal_output_rms": 0.10 * nominal_output_rms,
        "one_percent_nominal_output_rms": 0.01 * nominal_output_rms,
        "one_millivolt_rms": 0.001,
    }
    recovery = {
        name: sustained_recovery_s(residual, threshold, post_index)
        for name, threshold in thresholds.items()
    }
    window_samples = int(round(0.001 * SAMPLE_RATE_HZ))
    envelope = sliding_rms(residual, window_samples)
    checkpoints = {}
    for absolute_time_s in (0.050, 0.100, 0.150, 0.200, 0.250):
        index = min(
            envelope.size - 1,
            int(round(absolute_time_s * SAMPLE_RATE_HZ)) - window_samples,
        )
        checkpoints[f"{absolute_time_s:g}"] = float(envelope[index])

    upstream_path = (
        ROOT / "model" / "generated" / "long_overload_recovery_summary.json"
    )
    upstream = json.loads(upstream_path.read_text(encoding="utf-8"))
    upstream_half_volt = next(
        measurement
        for measurement in upstream["measurements"]
        if float(measurement["burst_input_peak_v"]) == BURST_PEAK_V
    )
    upstream_recovery = upstream_half_volt[
        "measured_recovery_s_after_burst"
    ]
    report = {
        "model": "12ax7_passive_riaa_v1",
        "implementation": "captured SystemVerilog wide factorized solver",
        "integration_method": "trapezoidal",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "stimulus": {
            "frequency_hz": FREQUENCY_HZ,
            "nominal_peak_v": NOMINAL_PEAK_V,
            "burst_peak_v": BURST_PEAK_V,
            "burst_start_s": BURST_START_S,
            "burst_end_s": BURST_END_S,
            "duration_s": DURATION_S,
            "post_burst_observation_s": DURATION_S - BURST_END_S,
            "quantized_input": "Q8.24",
        },
        "captured_samples_per_trajectory": sample_count,
        "total_captured_solver_updates": 2 * sample_count,
        "control_rtl_fixed_all_state_exact": True,
        "overload_rtl_fixed_all_state_exact": True,
        "nominal_output_rms_v": nominal_output_rms,
        "recovery_thresholds_v_rms": thresholds,
        "measured_recovery_s_after_burst": recovery,
        "one_ms_deviation_rms_v_at_absolute_time_s": checkpoints,
        "final_10ms_deviation_rms_v": float(
            np.sqrt(np.mean(np.square(residual[final_window])))
        ),
        "peak_post_burst_deviation_v": float(
            np.max(np.abs(residual[post_index:]))
        ),
        "control_diagnostics": _diagnostics(control_capture),
        "overload_diagnostics": _diagnostics(overload_capture),
        "upstream_float_trapezoidal": {
            "source": str(upstream_path.relative_to(ROOT)),
            "measured_recovery_s_after_burst": upstream_recovery,
            "ten_percent_recovery_difference_s": (
                float(recovery["ten_percent_nominal_output_rms"])
                - float(upstream_recovery["ten_percent_nominal_output_rms"])
            ),
            "note": (
                "The difference includes Q8.24 input quantization and fixed "
                "circuit arithmetic; trajectories are not sample-identical."
            ),
        },
    }
    diagnostic_total = 0
    for name in ("control_diagnostics", "overload_diagnostics"):
        diagnostic_total += sum(
            int(report[name][field])
            for field in (
                "residual_limit_exceedance_count",
                "saturation_count",
                "range_clip_count",
                "correction_scale_fallback_count",
            )
        )
    if diagnostic_total:
        raise RuntimeError(
            f"accepted-range long recovery produced {diagnostic_total} diagnostics"
        )
    ten_percent_s = recovery["ten_percent_nominal_output_rms"]
    if ten_percent_s is None or not 0.140 <= float(ten_percent_s) <= 0.155:
        raise RuntimeError("RTL 0.5 V 10%-recovery left its measured bound")
    if recovery["one_percent_nominal_output_rms"] is not None:
        raise RuntimeError("unexpected RTL 0.5 V 1%-recovery inside 235 ms")
    if abs(float(report["upstream_float_trapezoidal"]["ten_percent_recovery_difference_s"])) > 0.001:
        raise RuntimeError("RTL/float 10%-recovery difference exceeds 1 ms")

    summary = (
        ROOT
        / "model"
        / "generated"
        / "trapezoidal_solver_rtl_recovery_summary.json"
    )
    summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result = (
        ROOT / "reference" / "results" / "trapezoidal_solver_rtl_recovery.json"
    )
    result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
