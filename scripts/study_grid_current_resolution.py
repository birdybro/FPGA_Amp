#!/usr/bin/env python3
"""Measure grid-current table resolution in the banked fixed circuit."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

from characterize_banked_solver_accuracy import (  # noqa: E402
    BURST_END_S,
    BURST_START_S,
    DURATION_S,
    FREQUENCY_HZ,
    NOMINAL_PEAK_V,
    SAMPLE_RATE_HZ,
    input_trajectory_q24,
    waveform_metrics,
)
from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedWideStateBankedChordV1CircuitModel,
)
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


GRID_POINTS = (128, 256, 512, 1024)
LEVELS_PEAK_V = (1.0, 1.5)
INTEGRATION_METHODS = ("backward_euler", "trapezoidal")


def run_case(integration_method: str, level_peak_v: float) -> dict[str, object]:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    input_q24 = input_trajectory_q24(level_peak_v)
    stimulus = input_q24.astype(np.float64) / float(1 << 24)
    masks = {
        "burst": (time_s >= BURST_START_S) & (time_s < BURST_END_S),
        "complete_post_burst": time_s >= BURST_END_S,
        "final_10ms": time_s >= DURATION_S - 0.010,
    }
    reference_model = V1CircuitModel(
        SAMPLE_RATE_HZ, integration_method=integration_method
    )
    reference = reference_model.process(
        stimulus, max_iterations=8, tolerance_a=1.0e-12
    )

    candidates: dict[str, object] = {}
    for points in GRID_POINTS:
        tube = FixedFactorizedKoren12AX7(grid_points=points)
        model = FixedWideStateBankedChordV1CircuitModel(
            SAMPLE_RATE_HZ,
            tube_lut=tube,
            integration_method=integration_method,
        )
        output = model.process(
            stimulus, max_iterations=3, residual_limit_a=2.0e-6
        )
        candidates[str(points)] = {
            "grid_storage_bits": points * 32,
            "windows": {
                name: waveform_metrics(output, reference, mask)
                for name, mask in masks.items()
            },
            "maximum_residual_a": (
                model.max_residual_q44_observed / float(1 << 44)
            ),
            "residual_limit_exceedance_count": model.nonconvergence_count,
            "saturation_count": model.saturation_count,
            "range_clip_count": model.lut_clip_count,
            "correction_scale_fallback_count": (
                model.correction_scale_fallback_count
            ),
            "slew_qualified_selection_count": (
                model.slew_qualified_selection_count
            ),
        }
    return {
        "integration_method": integration_method,
        "burst_input_peak_v": level_peak_v,
        "analytical_nonconvergence_count": reference_model.nonconvergence_count,
        "candidates": candidates,
    }


def direct_grid_current_error() -> dict[str, object]:
    grid_v = np.linspace(-5.0, 1.0, 200_001)
    active = grid_v >= 0.0
    measurements: dict[str, object] = {}
    for points in GRID_POINTS:
        tube = FixedFactorizedKoren12AX7(grid_points=points)
        reference = tube.tube.grid_current(grid_v)
        approximate = np.interp(
            grid_v,
            np.linspace(tube.grid_v_gk_min_v, tube.v_gk_max_v, points),
            tube.grid_value_q31 / float(1 << tube.current_fractional_bits),
        )
        error = approximate - reference
        measurements[str(points)] = {
            "spacing_v": 6.0 / (points - 1),
            "storage_bits": points * 32,
            "maximum_absolute_error_a": float(np.max(np.abs(error))),
            "active_region_rms_error_a": float(
                np.sqrt(np.mean(np.square(error[active])))
            ),
        }
    return measurements


def main() -> int:
    jobs = [
        (method, level)
        for method in INTEGRATION_METHODS
        for level in LEVELS_PEAK_V
    ]
    measurements: list[dict[str, object]] = []
    workers = min(len(jobs), max(1, min(os.cpu_count() or 1, 4)))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_case, *job): job for job in jobs}
        for future in as_completed(futures):
            result = future.result()
            measurements.append(result)
            errors = {
                points: candidate["windows"]["final_10ms"]["raw_error_rms_v"]
                for points, candidate in result["candidates"].items()
            }
            print(
                f"{result['integration_method']} "
                f"{result['burst_input_peak_v']:.1f} V final mV: "
                + ", ".join(
                    f"{points}={float(error) * 1e3:.3f}"
                    for points, error in errors.items()
                ),
                flush=True,
            )
    measurements.sort(
        key=lambda item: (
            str(item["integration_method"]),
            float(item["burst_input_peak_v"]),
        )
    )

    def candidate(item: dict[str, object], points: int) -> dict[str, object]:
        return item["candidates"][str(points)]

    direct_error = direct_grid_current_error()
    gates = {
        "analytical_newton_converged": all(
            int(item["analytical_nonconvergence_count"]) == 0
            for item in measurements
        ),
        "all_fixed_candidates_diagnostic_clean": all(
            int(candidate(item, points)[key]) == 0
            for item in measurements
            for points in GRID_POINTS
            for key in (
                "residual_limit_exceedance_count",
                "saturation_count",
                "range_clip_count",
                "correction_scale_fallback_count",
            )
        ),
        "direct_grid_error_decreases_monotonically": all(
            float(
                direct_error[str(high)]["maximum_absolute_error_a"]
            )
            <= float(
                direct_error[str(low)]["maximum_absolute_error_a"]
            )
            for low, high in zip(GRID_POINTS[:-1], GRID_POINTS[1:], strict=True)
        ),
        "selected_one_point_five_volt_final_error_below_one_millivolt": all(
            float(
                candidate(item, 1024)["windows"]["final_10ms"][
                    "raw_error_rms_v"
                ]
            ) < 1.0e-3
            for item in measurements
            if item["burst_input_peak_v"] == 1.5
        ),
        "selected_one_volt_burst_error_does_not_regress": all(
            float(
                candidate(item, 1024)["windows"]["burst"]["raw_error_rms_v"]
            )
            <= float(
                candidate(item, 128)["windows"]["burst"]["raw_error_rms_v"]
            )
            for item in measurements
            if item["burst_input_peak_v"] == 1.0
        ),
        "selected_worst_one_volt_final_error_improves": max(
            float(
                candidate(item, 1024)["windows"]["final_10ms"][
                    "raw_error_rms_v"
                ]
            )
            for item in measurements
            if item["burst_input_peak_v"] == 1.0
        )
        < max(
            float(
                candidate(item, 128)["windows"]["final_10ms"][
                    "raw_error_rms_v"
                ]
            )
            for item in measurements
            if item["burst_input_peak_v"] == 1.0
        ),
    }
    report = {
        "model": "12ax7_passive_riaa_v1",
        "study": "factorized grid-current linear-table resolution",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "stimulus": {
            "frequency_hz": FREQUENCY_HZ,
            "nominal_peak_v": NOMINAL_PEAK_V,
            "burst_start_s": BURST_START_S,
            "burst_end_s": BURST_END_S,
            "duration_s": DURATION_S,
            "burst_levels_peak_v": list(LEVELS_PEAK_V),
            "input_format": "Q8.24",
        },
        "alignment": {"gain": False, "dc": False, "delay": False},
        "grid_points": list(GRID_POINTS),
        "direct_grid_current_error": direct_error,
        "selection": {
            "grid_points": 1024,
            "selected_for_implementation": all(gates.values()),
            "reason": (
                "32,768 table bits put direct grid-current error below the "
                "measured fixed plate-law error and reduce both 1.5 V final "
                "windows below 1 mV without a 1.0 V burst regression"
            ),
            "known_tradeoff": (
                "backward-Euler 1.0 V final error loses a favorable 128-entry "
                "cancellation, while the worst error across modes improves"
            ),
        },
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "measurements": measurements,
    }
    generated = ROOT / "model" / "generated" / "grid_current_resolution_study.json"
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    reference = ROOT / "reference" / "results" / "grid_current_resolution_study.json"
    reference.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_gates_pass"]:
        raise RuntimeError("grid-current resolution study gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
