#!/usr/bin/env python3
"""Sweep the shallow trapezoidal cutoff-bank activation threshold."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedWideStateBankedChordV1CircuitModel,
)


SAMPLE_RATE_HZ = 768_000.0
FREQUENCY_HZ = 1_000.0
NOMINAL_PEAK_V = 0.005
BURST_START_S = 0.010
BURST_END_S = 0.015
DURATION_S = 0.100
LEVELS_PEAK_V = (0.500, 1.000)
SHALLOW_UPPER_THRESHOLDS_V = (
    -2.500,
    -2.625,
    -2.675,
    -2.680,
    -2.700,
    -2.750,
    -2.800,
    -2.900,
)


def stimulus(level_peak_v: float) -> np.ndarray:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    amplitude = np.full(time_s.size, NOMINAL_PEAK_V)
    amplitude[(time_s >= BURST_START_S) & (time_s < BURST_END_S)] = level_peak_v
    return (
        np.rint(
            amplitude
            * np.sin(2.0 * np.pi * FREQUENCY_HZ * time_s)
            * float(1 << 24)
        ).astype(np.int64)
        / float(1 << 24)
    )


def run_case(threshold_v: float, level_peak_v: float) -> dict[str, object]:
    model = FixedWideStateBankedChordV1CircuitModel(
        SAMPLE_RATE_HZ,
        tube_lut=FixedFactorizedKoren12AX7(),
        integration_method="trapezoidal",
    )
    last_regime = model.cutoff_jacobian_regimes[-1]
    model.cutoff_jacobian_regimes = (
        *model.cutoff_jacobian_regimes[:-1],
        (threshold_v, last_regime[1], last_regime[2]),
    )
    output = model.process(
        stimulus(level_peak_v), max_iterations=3, residual_limit_a=2.0e-6
    )
    return {
        "shallow_bank_upper_v_gk_v": threshold_v,
        "burst_input_peak_v": level_peak_v,
        "maximum_residual_a": model.max_residual_q44_observed / float(1 << 44),
        "residual_limit_exceedance_count": model.nonconvergence_count,
        "saturation_count": model.saturation_count,
        "range_clip_count": model.lut_clip_count,
        "correction_scale_fallback_count": model.correction_scale_fallback_count,
        "output_finite": bool(np.all(np.isfinite(output))),
        "bank_selection_count": model.chord_bank_selection_count,
    }


def main() -> int:
    jobs = [
        (threshold, level)
        for threshold in SHALLOW_UPPER_THRESHOLDS_V
        for level in LEVELS_PEAK_V
    ]
    results: list[dict[str, object]] = []
    workers = min(len(jobs), max(1, min(os.cpu_count() or 1, 8)))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_job = {executor.submit(run_case, *job): job for job in jobs}
        for future in as_completed(future_to_job):
            result = future.result()
            results.append(result)
            print(
                f"threshold={result['shallow_bank_upper_v_gk_v']:.3f} V "
                f"level={result['burst_input_peak_v']:.1f} V: "
                f"fail={result['residual_limit_exceedance_count']}, "
                f"max={float(result['maximum_residual_a']) * 1e6:.3f} uA, "
                f"shallow={result['bank_selection_count'][-2]}",
                flush=True,
            )
    results.sort(
        key=lambda item: (
            float(item["shallow_bank_upper_v_gk_v"]),
            float(item["burst_input_peak_v"]),
        )
    )

    passing_thresholds: list[float] = []
    for threshold in SHALLOW_UPPER_THRESHOLDS_V:
        cases = [
            item
            for item in results
            if item["shallow_bank_upper_v_gk_v"] == threshold
        ]
        no_diagnostics = all(
            int(item[key]) == 0
            for item in cases
            for key in (
                "residual_limit_exceedance_count",
                "saturation_count",
                "range_clip_count",
                "correction_scale_fallback_count",
            )
        )
        half_volt = next(
            item for item in cases if item["burst_input_peak_v"] == 0.5
        )
        no_half_volt_shallow_activation = (
            int(half_volt["bank_selection_count"][-2]) == 0
        )
        if no_diagnostics and no_half_volt_shallow_activation:
            passing_thresholds.append(threshold)
    if not passing_thresholds:
        raise RuntimeError("no threshold preserves convergence and excludes 0.5 V")
    selected_threshold = min(passing_thresholds)
    selected_cases = [
        item
        for item in results
        if item["shallow_bank_upper_v_gk_v"] == selected_threshold
    ]
    selected_one_volt = next(
        item for item in selected_cases if item["burst_input_peak_v"] == 1.0
    )
    gates = {
        "selected_threshold_is_stricter_than_original": selected_threshold < -2.5,
        "selected_threshold_avoids_half_volt_shallow_bank": all(
            int(item["bank_selection_count"][-2]) == 0
            for item in selected_cases
            if item["burst_input_peak_v"] == 0.5
        ),
        "selected_threshold_preserves_one_volt_convergence": int(
            selected_one_volt["residual_limit_exceedance_count"]
        )
        == 0,
        "all_outputs_finite": all(bool(item["output_finite"]) for item in results),
    }
    report = {
        "model": "12ax7_passive_riaa_v1",
        "study": "trapezoidal shallow cutoff-bank threshold sweep",
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
        "thresholds_tested_v": list(SHALLOW_UPPER_THRESHOLDS_V),
        "passing_thresholds_v": passing_thresholds,
        "selection_policy": "most-negative passing threshold",
        "selected_threshold_v": selected_threshold,
        "selected_one_volt_shallow_bank_activations": int(
            selected_one_volt["bank_selection_count"][-2]
        ),
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "measurements": results,
    }
    generated = ROOT / "model" / "generated" / "banked_shallow_threshold_study.json"
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    reference = ROOT / "reference" / "results" / "banked_shallow_threshold_study.json"
    reference.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_gates_pass"]:
        raise RuntimeError("shallow cutoff-bank threshold study failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
