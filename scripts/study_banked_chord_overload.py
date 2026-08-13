#!/usr/bin/env python3
"""Measure a fixed-schedule cutoff-Jacobian bank under severe overload."""

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
    FixedWideStateV1CircuitModel,
)


SAMPLE_RATE_HZ = 768_000.0
FREQUENCY_HZ = 1_000.0
NOMINAL_PEAK_V = 0.005
BURST_START_S = 0.010
BURST_END_S = 0.015
DURATION_S = 0.100
LEVELS_PEAK_V = (0.5, 1.0, 1.5)
INTEGRATION_METHODS = ("backward_euler", "trapezoidal")


def run_case(integration_method: str, banked: bool, level_peak_v: float) -> dict[str, object]:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    amplitude = np.full(time_s.size, NOMINAL_PEAK_V)
    amplitude[(time_s >= BURST_START_S) & (time_s < BURST_END_S)] = level_peak_v
    stimulus = amplitude * np.sin(2.0 * np.pi * FREQUENCY_HZ * time_s)
    model_type = (
        FixedWideStateBankedChordV1CircuitModel
        if banked
        else FixedWideStateV1CircuitModel
    )
    model = model_type(
        tube_lut=FixedFactorizedKoren12AX7(),
        integration_method=integration_method,
    )
    output = model.process(
        stimulus,
        max_iterations=3,
        residual_limit_a=2.0e-6,
    )
    result: dict[str, object] = {
        "integration_method": integration_method,
        "solver": "banked_cutoff_chord" if banked else "dc_chord_baseline",
        "burst_input_peak_v": level_peak_v,
        "output_finite": bool(np.all(np.isfinite(output))),
        "maximum_absolute_output_v": float(np.max(np.abs(output))),
        "maximum_residual_a": model.max_residual_q44_observed / float(1 << 44),
        "residual_limit_exceedance_count": model.nonconvergence_count,
        "saturation_count": model.saturation_count,
        "range_clip_count": model.lut_clip_count,
        "correction_scale_fallback_count": model.correction_scale_fallback_count,
    }
    if banked:
        result["bank_selection_count"] = model.chord_bank_selection_count
        result["slew_qualified_selection_count"] = (
            model.slew_qualified_selection_count
        )
    return result


def main() -> int:
    jobs = [
        (integration_method, banked, level_peak_v)
        for integration_method in INTEGRATION_METHODS
        for banked in (False, True)
        for level_peak_v in LEVELS_PEAK_V
    ]
    results: list[dict[str, object]] = []
    workers = min(len(jobs), max(1, min(os.cpu_count() or 1, 6)))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_job = {
            executor.submit(run_case, *job): job for job in jobs
        }
        for future in as_completed(future_to_job):
            result = future.result()
            results.append(result)
            print(
                f"{result['integration_method']} {result['solver']} "
                f"{result['burst_input_peak_v']:.1f} V: "
                f"fail={result['residual_limit_exceedance_count']}, "
                f"max={float(result['maximum_residual_a']) * 1e6:.3f} uA, "
                f"clip={result['range_clip_count']}",
                flush=True,
            )
    results.sort(
        key=lambda item: (
            str(item["integration_method"]),
            str(item["solver"]),
            float(item["burst_input_peak_v"]),
        )
    )

    def case(method: str, solver: str, level: float) -> dict[str, object]:
        return next(
            item
            for item in results
            if item["integration_method"] == method
            and item["solver"] == solver
            and item["burst_input_peak_v"] == level
        )

    gates = {
        "baseline_reproduces_one_volt_failure": all(
            int(case(method, "dc_chord_baseline", 1.0)["residual_limit_exceedance_count"])
            > 0
            for method in INTEGRATION_METHODS
        ),
        "banked_one_volt_has_no_residual_failure": all(
            int(case(method, "banked_cutoff_chord", 1.0)["residual_limit_exceedance_count"])
            == 0
            for method in INTEGRATION_METHODS
        ),
        "banked_through_one_point_five_volts_has_no_residual_failure": all(
            int(
                case(method, "banked_cutoff_chord", level)[
                    "residual_limit_exceedance_count"
                ]
            ) == 0
            for method in INTEGRATION_METHODS
            for level in LEVELS_PEAK_V
        ),
        "banked_through_one_point_five_volts_has_no_arithmetic_or_range_event": all(
            int(case(method, "banked_cutoff_chord", level)[key]) == 0
            for method in INTEGRATION_METHODS
            for level in LEVELS_PEAK_V
            for key in (
                "saturation_count",
                "range_clip_count",
                "correction_scale_fallback_count",
            )
        ),
        "all_outputs_finite": all(bool(item["output_finite"]) for item in results),
    }
    banked_model = FixedWideStateBankedChordV1CircuitModel
    report = {
        "model": "12ax7_passive_riaa_v1",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "tube_implementation": "fixed factorized 1-D cubic-Hermite",
        "candidate": {
            "selection_state": "previous-sample second-stage Vgk",
            "selection_held_for_all_corrections": True,
            "corrections_per_sample": 3,
            "projected_rtl_latency_clocks": 116,
            "cutoff_regimes_by_integration_method": {
                method: [
                    {
                        "upper_v_gk_v": upper,
                        "representative_v_gk_v": v_gk,
                        "representative_v_pk_v": v_pk,
                    }
                    for upper, v_gk, v_pk in regimes
                ]
                for method, regimes in (
                    (
                        "backward_euler",
                        FixedWideStateBankedChordV1CircuitModel.BACKWARD_EULER_CUTOFF_JACOBIAN_REGIMES,
                    ),
                    (
                        "trapezoidal",
                        FixedWideStateBankedChordV1CircuitModel.TRAPEZOIDAL_CUTOFF_JACOBIAN_REGIMES,
                    ),
                )
            },
            "slew_qualified_shallow_regime": {
                "upper_v_gk_v": (
                    banked_model.SHALLOW_SLEW_UPPER_V_GK_V
                ),
                "minimum_absolute_v_gk_delta_v_per_sample": (
                    banked_model.SHALLOW_SLEW_THRESHOLD_V_PER_SAMPLE
                ),
                "backward_euler_representative_v_gk_vpk_v": list(
                    banked_model.BACKWARD_EULER_SLEW_JACOBIAN_REPRESENTATIVE
                ),
                "trapezoidal_reuses_last_cutoff_regime": True,
            },
            "nominal_bank": "existing DC operating-point Jacobian",
        },
        "stimulus": {
            "frequency_hz": FREQUENCY_HZ,
            "nominal_peak_v": NOMINAL_PEAK_V,
            "burst_start_s": BURST_START_S,
            "burst_end_s": BURST_END_S,
            "duration_s": DURATION_S,
            "burst_levels_peak_v": list(LEVELS_PEAK_V),
        },
        "residual_limit_a": 2.0e-6,
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "measurements": results,
    }
    generated = ROOT / "model" / "generated" / "banked_chord_overload_summary.json"
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    reference = ROOT / "reference" / "results" / "banked_chord_overload.json"
    reference.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_gates_pass"]:
        raise RuntimeError("banked chord overload acceptance failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
