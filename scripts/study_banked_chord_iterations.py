#!/usr/bin/env python3
"""Measure waveform and residual sensitivity to extra banked chord passes."""

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


LEVELS_PEAK_V = (1.0, 1.5)
INTEGRATION_METHODS = ("backward_euler", "trapezoidal")
CORRECTION_COUNTS = (3, 4, 5, 6)
BASE_LATENCY_CLOCKS = 116
EXTRA_SERIAL_PASS_CLOCKS = 29
DEADLINE_CLOCKS = 128


def run_case(integration_method: str, level_peak_v: float) -> dict[str, object]:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    stimulus = input_trajectory_q24(level_peak_v).astype(np.float64) / float(
        1 << 24
    )
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

    cases: list[dict[str, object]] = []
    for correction_count in CORRECTION_COUNTS:
        model = FixedWideStateBankedChordV1CircuitModel(
            SAMPLE_RATE_HZ,
            tube_lut=FixedFactorizedKoren12AX7(),
            integration_method=integration_method,
        )
        candidate = model.process(
            stimulus,
            max_iterations=correction_count,
            residual_limit_a=2.0e-6,
        )
        latency = BASE_LATENCY_CLOCKS + (
            correction_count - CORRECTION_COUNTS[0]
        ) * EXTRA_SERIAL_PASS_CLOCKS
        cases.append(
            {
                "chord_corrections": correction_count,
                "projected_serial_solver_latency_clocks": latency,
                "meets_128_clock_deadline": latency <= DEADLINE_CLOCKS,
                "windows": {
                    name: waveform_metrics(candidate, reference, mask)
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
                "bank_selection_count": model.chord_bank_selection_count,
                "slew_qualified_selection_count": (
                    model.slew_qualified_selection_count
                ),
            }
        )
    return {
        "integration_method": integration_method,
        "burst_input_peak_v": level_peak_v,
        "analytical_nonconvergence_count": reference_model.nonconvergence_count,
        "cases": cases,
    }


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
            three = result["cases"][0]
            six = result["cases"][-1]
            print(
                f"{result['integration_method']} "
                f"{result['burst_input_peak_v']:.1f} V: "
                f"burst {three['windows']['burst']['raw_error_rms_v'] * 1e3:.3f}"
                f" -> {six['windows']['burst']['raw_error_rms_v'] * 1e3:.3f} mV, "
                f"residual {three['maximum_residual_a'] * 1e6:.3f}"
                f" -> {six['maximum_residual_a'] * 1e6:.3f} uA",
                flush=True,
            )
    measurements.sort(
        key=lambda item: (
            str(item["integration_method"]),
            float(item["burst_input_peak_v"]),
        )
    )
    gates = {
        "analytical_newton_converged": all(
            int(item["analytical_nonconvergence_count"]) == 0
            for item in measurements
        ),
        "all_fixed_outputs_diagnostic_clean": all(
            int(case[key]) == 0
            for item in measurements
            for case in item["cases"]
            for key in (
                "residual_limit_exceedance_count",
                "saturation_count",
                "range_clip_count",
                "correction_scale_fallback_count",
            )
        ),
        "three_pass_meets_current_deadline": all(
            bool(item["cases"][0]["meets_128_clock_deadline"])
            for item in measurements
        ),
        "fourth_serial_pass_misses_current_deadline": all(
            not bool(item["cases"][1]["meets_128_clock_deadline"])
            for item in measurements
        ),
    }
    report = {
        "model": "12ax7_passive_riaa_v1",
        "study": "banked fixed chord-pass waveform sensitivity",
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
        "correction_counts": list(CORRECTION_COUNTS),
        "latency_projection": {
            "three_pass_measured_clocks": BASE_LATENCY_CLOCKS,
            "additional_serial_pass_clocks": EXTRA_SERIAL_PASS_CLOCKS,
            "deadline_clocks": DEADLINE_CLOCKS,
            "note": (
                "Each added pass serializes the measured 19-clock residual path "
                "and 10-clock chord path; only the three-pass value is RTL-measured."
            ),
        },
        "alignment": {"gain": False, "dc": False, "delay": False},
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "measurements": measurements,
    }
    generated = ROOT / "model" / "generated" / "banked_iteration_study.json"
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    reference = ROOT / "reference" / "results" / "banked_iteration_study.json"
    reference.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_gates_pass"]:
        raise RuntimeError("banked chord iteration study gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
