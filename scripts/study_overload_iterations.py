#!/usr/bin/env python3
"""Measure whether extra fixed chord corrections resolve overload residuals."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import FixedChordV1CircuitModel  # noqa: E402
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


def main() -> int:
    sample_rate_hz = 768_000.0
    frequency_hz = 1_000.0
    duration_s = 0.012
    burst_start_s = 0.004
    burst_end_s = 0.008
    levels_peak_v = (1.0, 1.5)
    correction_counts = (3, 4, 5, 6)
    time_s = np.arange(int(duration_s * sample_rate_hz)) / sample_rate_hz
    burst_mask = (time_s >= burst_start_s) & (time_s < burst_end_s)
    post_mask = time_s >= burst_end_s
    measurements: list[dict[str, object]] = []

    for level_peak_v in levels_peak_v:
        amplitude = np.full(time_s.size, 0.005)
        amplitude[burst_mask] = level_peak_v
        stimulus = amplitude * np.sin(2.0 * np.pi * frequency_hz * time_s)
        reference_model = V1CircuitModel(sample_rate_hz)
        reference = reference_model.process(
            stimulus, max_iterations=8, tolerance_a=1.0e-12
        )
        cases: list[dict[str, object]] = []
        for corrections in correction_counts:
            model = FixedChordV1CircuitModel(
                sample_rate_hz, tube_lut=FixedFactorizedKoren12AX7()
            )
            candidate = model.process(
                stimulus,
                max_iterations=corrections,
                residual_limit_a=2.0e-6,
            )
            burst_residual = candidate[burst_mask] - reference[burst_mask]
            post_residual = candidate[post_mask] - reference[post_mask]
            case = {
                "chord_corrections": corrections,
                "projected_serial_solver_latency_clocks": 126
                + (corrections - 3) * 29,
                "maximum_residual_a": model.max_residual_q44_observed / (1 << 44),
                "residual_limit_exceedance_count": model.nonconvergence_count,
                "saturation_count": model.saturation_count,
                "range_clip_count": model.lut_clip_count,
                "burst_residual_rms_v": float(
                    np.sqrt(np.mean(np.square(burst_residual)))
                ),
                "burst_max_absolute_error_v": float(np.max(np.abs(burst_residual))),
                "post_residual_rms_v": float(
                    np.sqrt(np.mean(np.square(post_residual)))
                ),
                "post_max_absolute_error_v": float(np.max(np.abs(post_residual))),
            }
            cases.append(case)
            print(
                f"{level_peak_v:.1f} V, {corrections} corrections: "
                f"max residual {case['maximum_residual_a'] * 1e6:.3f} uA, "
                f"failures {model.nonconvergence_count}",
                flush=True,
            )
        measurements.append(
            {
                "burst_input_peak_v": level_peak_v,
                "analytical_nonconvergence_count": reference_model.nonconvergence_count,
                "cases": cases,
            }
        )

    report = {
        "model": "12ax7_passive_riaa_v1",
        "tube_implementation": "fixed factorized 1-D cubic-Hermite",
        "sample_rate_hz": sample_rate_hz,
        "residual_limit_a": 2.0e-6,
        "stimulus": {
            "frequency_hz": frequency_hz,
            "nominal_peak_v": 0.005,
            "burst_start_s": burst_start_s,
            "burst_end_s": burst_end_s,
            "duration_s": duration_s,
        },
        "correction_counts": list(correction_counts),
        "latency_projection_note": "one extra serialized residual/correction pass adds the measured 19-clock residual path plus 10-clock chord path; not an RTL timing result",
        "measurements": measurements,
    }
    result_path = REPOSITORY_ROOT / "reference" / "results" / "overload_iteration_study.json"
    result_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary_path = REPOSITORY_ROOT / "model" / "generated" / "overload_iteration_summary.json"
    summary_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
