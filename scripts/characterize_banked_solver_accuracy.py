#!/usr/bin/env python3
"""Compare cutoff-bank output waveforms against full-Newton circuit truth."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
import os
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedWideStateBankedChordV1CircuitModel,
    FixedWideStateV1CircuitModel,
)
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


SAMPLE_RATE_HZ = 768_000.0
FREQUENCY_HZ = 1_000.0
NOMINAL_PEAK_V = 0.005
BURST_START_S = 0.010
BURST_END_S = 0.015
DURATION_S = 0.100
LEVELS_PEAK_V = (0.020, 0.500, 1.000)
INTEGRATION_METHODS = ("backward_euler", "trapezoidal")


def input_trajectory_q24(level_peak_v: float) -> np.ndarray:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    amplitude = np.full(time_s.size, NOMINAL_PEAK_V)
    amplitude[(time_s >= BURST_START_S) & (time_s < BURST_END_S)] = level_peak_v
    return np.rint(
        amplitude * np.sin(2.0 * np.pi * FREQUENCY_HZ * time_s) * (1 << 24)
    ).astype(np.int64)


def rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def normalized_db(error_rms_v: float, reference_rms_v: float) -> float:
    return float(
        20.0
        * math.log10(max(error_rms_v, 1.0e-30) / max(reference_rms_v, 1.0e-30))
    )


def waveform_metrics(
    candidate: np.ndarray,
    reference: np.ndarray,
    mask: np.ndarray,
) -> dict[str, float]:
    candidate_window = candidate[mask]
    reference_window = reference[mask]
    error = candidate_window - reference_window
    error_mean = float(np.mean(error))
    reference_rms_v = rms(reference_window)
    error_rms_v = rms(error)
    mean_removed_error_rms_v = rms(error - error_mean)
    return {
        "reference_rms_v": reference_rms_v,
        "candidate_rms_v": rms(candidate_window),
        "raw_error_rms_v": error_rms_v,
        "raw_normalized_error_db": normalized_db(error_rms_v, reference_rms_v),
        "error_mean_v": error_mean,
        "mean_removed_error_rms_v": mean_removed_error_rms_v,
        "mean_removed_normalized_error_db": normalized_db(
            mean_removed_error_rms_v, reference_rms_v
        ),
        "maximum_absolute_error_v": float(np.max(np.abs(error))),
    }


def run_case(integration_method: str, level_peak_v: float) -> dict[str, object]:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    input_q24 = input_trajectory_q24(level_peak_v)
    stimulus = input_q24.astype(np.float64) / float(1 << 24)
    masks = {
        "settled_pre_burst": (time_s >= 0.005) & (time_s < BURST_START_S),
        "burst": (time_s >= BURST_START_S) & (time_s < BURST_END_S),
        "early_recovery_10ms": (time_s >= BURST_END_S)
        & (time_s < BURST_END_S + 0.010),
        "complete_post_burst": time_s >= BURST_END_S,
        "final_10ms": time_s >= DURATION_S - 0.010,
    }

    reference_model = V1CircuitModel(
        SAMPLE_RATE_HZ, integration_method=integration_method
    )
    reference = reference_model.process(
        stimulus, max_iterations=8, tolerance_a=1.0e-12
    )
    fixed_outputs: dict[str, np.ndarray] = {}
    fixed_models: dict[str, FixedWideStateV1CircuitModel] = {}
    for solver_name, model_type in (
        ("dc_chord_baseline", FixedWideStateV1CircuitModel),
        ("banked_cutoff_chord", FixedWideStateBankedChordV1CircuitModel),
    ):
        model = model_type(
            SAMPLE_RATE_HZ,
            tube_lut=FixedFactorizedKoren12AX7(),
            integration_method=integration_method,
        )
        fixed_outputs[solver_name] = model.process(
            stimulus,
            max_iterations=3,
            residual_limit_a=2.0e-6,
        )
        fixed_models[solver_name] = model

    solver_results: dict[str, object] = {}
    for solver_name, output in fixed_outputs.items():
        model = fixed_models[solver_name]
        solver_result: dict[str, object] = {
            "windows": {
                name: waveform_metrics(output, reference, mask)
                for name, mask in masks.items()
            },
            "maximum_residual_a": model.max_residual_q44_observed
            / float(1 << 44),
            "residual_limit_exceedance_count": model.nonconvergence_count,
            "saturation_count": model.saturation_count,
            "range_clip_count": model.lut_clip_count,
            "correction_scale_fallback_count": (
                model.correction_scale_fallback_count
            ),
            "output_finite": bool(np.all(np.isfinite(output))),
        }
        if solver_name == "banked_cutoff_chord":
            solver_result["bank_selection_count"] = (
                model.chord_bank_selection_count
            )
            solver_result["slew_qualified_selection_count"] = (
                model.slew_qualified_selection_count
            )
        solver_results[solver_name] = solver_result

    banked_vs_baseline = fixed_outputs["banked_cutoff_chord"] - fixed_outputs[
        "dc_chord_baseline"
    ]
    return {
        "integration_method": integration_method,
        "burst_input_peak_v": level_peak_v,
        "analytical_nonconvergence_count": reference_model.nonconvergence_count,
        "solvers": solver_results,
        "banked_vs_baseline": {
            name: {
                "raw_difference_rms_v": rms(banked_vs_baseline[mask]),
                "maximum_absolute_difference_v": float(
                    np.max(np.abs(banked_vs_baseline[mask]))
                ),
            }
            for name, mask in masks.items()
        },
    }


def main() -> int:
    jobs = [
        (integration_method, level_peak_v)
        for integration_method in INTEGRATION_METHODS
        for level_peak_v in LEVELS_PEAK_V
    ]
    measurements: list[dict[str, object]] = []
    workers = min(len(jobs), max(1, min(os.cpu_count() or 1, 6)))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_job = {executor.submit(run_case, *job): job for job in jobs}
        for future in as_completed(future_to_job):
            result = future.result()
            measurements.append(result)
            banked = result["solvers"]["banked_cutoff_chord"]
            burst = banked["windows"]["burst"]
            print(
                f"{result['integration_method']} "
                f"{result['burst_input_peak_v']:.3f} V: "
                f"burst error={burst['raw_normalized_error_db']:.2f} dB, "
                f"fail={banked['residual_limit_exceedance_count']}",
                flush=True,
            )
    measurements.sort(
        key=lambda item: (
            str(item["integration_method"]),
            float(item["burst_input_peak_v"]),
        )
    )

    def banked_case(method: str, level: float) -> dict[str, object]:
        measurement = next(
            item
            for item in measurements
            if item["integration_method"] == method
            and item["burst_input_peak_v"] == level
        )
        return measurement["solvers"]["banked_cutoff_chord"]

    gates = {
        "analytical_newton_converged": all(
            int(item["analytical_nonconvergence_count"]) == 0
            for item in measurements
        ),
        "banked_fixed_converged_without_diagnostics_through_one_volt": all(
            int(banked_case(method, level)[key]) == 0
            for method in INTEGRATION_METHODS
            for level in LEVELS_PEAK_V
            for key in (
                "residual_limit_exceedance_count",
                "saturation_count",
                "range_clip_count",
                "correction_scale_fallback_count",
            )
        ),
        "banked_outputs_finite": all(
            bool(banked_case(method, level)["output_finite"])
            for method in INTEGRATION_METHODS
            for level in LEVELS_PEAK_V
        ),
        "burst_raw_normalized_error_below_minus_70_db": all(
            float(
                banked_case(method, level)["windows"]["burst"][
                    "raw_normalized_error_db"
                ]
            )
            <= -70.0
            for method in INTEGRATION_METHODS
            for level in LEVELS_PEAK_V
        ),
        "one_volt_burst_error_improves_by_at_least_20_db": all(
            float(
                next(
                    item
                    for item in measurements
                    if item["integration_method"] == method
                    and item["burst_input_peak_v"] == 1.0
                )["solvers"]["dc_chord_baseline"]["windows"]["burst"][
                    "raw_normalized_error_db"
                ]
            )
            - float(
                banked_case(method, 1.0)["windows"]["burst"][
                    "raw_normalized_error_db"
                ]
            )
            >= 20.0
            for method in INTEGRATION_METHODS
        ),
    }
    report = {
        "model": "12ax7_passive_riaa_v1",
        "comparison": (
            "fixed factorized banked and baseline chord solvers versus "
            "full-Newton analytical circuit"
        ),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "stimulus": {
            "frequency_hz": FREQUENCY_HZ,
            "nominal_peak_v": NOMINAL_PEAK_V,
            "burst_start_s": BURST_START_S,
            "burst_end_s": BURST_END_S,
            "duration_s": DURATION_S,
            "post_burst_observation_s": DURATION_S - BURST_END_S,
            "burst_levels_peak_v": list(LEVELS_PEAK_V),
            "input_format": "Q8.24",
        },
        "comparison_policy": {
            "gain_alignment": False,
            "dc_alignment": False,
            "fractional_delay_alignment": False,
            "raw_burst_normalized_error_limit_db": -70.0,
            "minimum_one_volt_improvement_over_dc_chord_db": 20.0,
            "rtl_link": (
                "banked_solver_rtl_overload.json proves fixed full-state "
                "equivalence at 1.0 V and 1.5 V"
            ),
        },
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "measurements": measurements,
    }
    generated = ROOT / "model" / "generated" / "banked_solver_accuracy.json"
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    reference = ROOT / "reference" / "results" / "banked_solver_accuracy.json"
    reference.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_gates_pass"]:
        raise RuntimeError("banked solver accuracy gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
