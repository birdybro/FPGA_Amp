#!/usr/bin/env python3
"""Compare floating backward-Euler/trapezoidal overload stability."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from characterize_overload_recovery import (  # noqa: E402
    burst_metrics,
    run_analytical,
    sustained_recovery_s,
)


SAMPLE_RATE_HZ = 768_000.0
FREQUENCY_HZ = 1_000.0
NOMINAL_PEAK_V = 0.005
BURST_START_S = 0.010
BURST_END_S = 0.015
DURATION_S = 0.100
LEVELS_PEAK_V = (0.020, 0.500, 1.000, 1.500)
METHODS = ("backward_euler", "trapezoidal")


def stimulus(level_peak_v: float) -> np.ndarray:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    amplitude = np.full(time_s.size, NOMINAL_PEAK_V)
    amplitude[(time_s >= BURST_START_S) & (time_s < BURST_END_S)] = level_peak_v
    return amplitude * np.sin(2.0 * np.pi * FREQUENCY_HZ * time_s)


def main() -> int:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    burst_mask = (time_s >= BURST_START_S) & (time_s < BURST_END_S)
    post_index = int(round(BURST_END_S * SAMPLE_RATE_HZ))
    final_window = time_s >= DURATION_S - 0.010

    controls: dict[str, np.ndarray] = {}
    control_grid: dict[str, np.ndarray] = {}
    control_failures: dict[str, int] = {}
    for method in METHODS:
        controls[method], control_grid[method], control_failures[method] = (
            run_analytical(stimulus(NOMINAL_PEAK_V), method)
        )
    nominal_output_rms = float(
        np.sqrt(np.mean(np.square(controls["backward_euler"][final_window])))
    )
    thresholds = {
        "ten_percent_nominal_output_rms": 0.10 * nominal_output_rms,
        "one_percent_nominal_output_rms": 0.01 * nominal_output_rms,
        "one_millivolt_rms": 0.001,
    }

    measurements: list[dict[str, object]] = []
    for level_peak_v in LEVELS_PEAK_V:
        samples = stimulus(level_peak_v)
        outputs: dict[str, np.ndarray] = {}
        method_results: dict[str, object] = {}
        for method in METHODS:
            output, maximum_grid_current, failures = run_analytical(samples, method)
            outputs[method] = output
            recovery_residual = output - controls[method]
            method_results[method] = {
                "burst_output": burst_metrics(output, burst_mask),
                "maximum_grid_current_a": maximum_grid_current.tolist(),
                "nonconvergence_count": failures,
                "peak_post_burst_deviation_v": float(
                    np.max(np.abs(recovery_residual[post_index:]))
                ),
                "recovery_s": {
                    name: sustained_recovery_s(
                        recovery_residual, threshold, post_index
                    )
                    for name, threshold in thresholds.items()
                },
                "final_10ms_deviation_rms_v": float(
                    np.sqrt(np.mean(np.square(recovery_residual[final_window])))
                ),
                "finite": bool(np.all(np.isfinite(output))),
            }
        difference = outputs["trapezoidal"] - outputs["backward_euler"]
        measurement = {
            "burst_input_peak_v": level_peak_v,
            "methods": method_results,
            "trapezoidal_vs_backward_euler": {
                "burst_residual_rms_v": float(
                    np.sqrt(np.mean(np.square(difference[burst_mask])))
                ),
                "post_burst_residual_rms_v": float(
                    np.sqrt(np.mean(np.square(difference[post_index:])))
                ),
                "final_10ms_residual_rms_v": float(
                    np.sqrt(np.mean(np.square(difference[final_window])))
                ),
                "maximum_absolute_difference_v": float(
                    np.max(np.abs(difference))
                ),
            },
        }
        measurements.append(measurement)
        trapezoidal = method_results["trapezoidal"]
        print(
            f"{level_peak_v:5.3f} V peak: trapezoidal failures "
            f"{trapezoidal['nonconvergence_count']}, final deviation "
            f"{trapezoidal['final_10ms_deviation_rms_v'] * 1e3:.3f} mV RMS",
            flush=True,
        )

    report = {
        "model": "12ax7_passive_riaa_v1",
        "comparison": "floating backward-Euler versus trapezoidal integration",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "stimulus": {
            "frequency_hz": FREQUENCY_HZ,
            "nominal_peak_v": NOMINAL_PEAK_V,
            "burst_start_s": BURST_START_S,
            "burst_end_s": BURST_END_S,
            "duration_s": DURATION_S,
            "post_burst_observation_s": DURATION_S - BURST_END_S,
            "burst_levels_peak_v": list(LEVELS_PEAK_V),
        },
        "nominal_backward_euler_output_rms_v": nominal_output_rms,
        "recovery_thresholds_v_rms": thresholds,
        "control": {
            method: {
                "maximum_grid_current_a": control_grid[method].tolist(),
                "nonconvergence_count": control_failures[method],
            }
            for method in METHODS
        },
        "measurements": measurements,
    }
    if any(control_failures.values()):
        raise RuntimeError("nominal integration control failed to converge")
    for measurement in measurements:
        for method in METHODS:
            result = measurement["methods"][method]
            if int(result["nonconvergence_count"]) or not bool(result["finite"]):
                raise RuntimeError(
                    f"{method} failed at {measurement['burst_input_peak_v']} V"
                )
    summary = ROOT / "model" / "generated" / "trapezoidal_overload_summary.json"
    summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result = ROOT / "reference" / "results" / "trapezoidal_overload.json"
    result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
