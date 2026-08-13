#!/usr/bin/env python3
"""Find the smallest cutoff-bank prefix that preserves overload convergence."""

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
LEVELS_PEAK_V = (0.500, 1.000)
CUTOFF_BANK_COUNTS = {
    "backward_euler": (0, 1, 2),
    "trapezoidal": (0, 1, 2, 3, 4),
}


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


def run_case(
    integration_method: str,
    cutoff_bank_count: int,
    level_peak_v: float,
) -> dict[str, object]:
    if cutoff_bank_count == 0:
        model: FixedWideStateV1CircuitModel = FixedWideStateV1CircuitModel(
            SAMPLE_RATE_HZ,
            tube_lut=FixedFactorizedKoren12AX7(),
            integration_method=integration_method,
        )
    else:
        banked = FixedWideStateBankedChordV1CircuitModel(
            SAMPLE_RATE_HZ,
            tube_lut=FixedFactorizedKoren12AX7(),
            integration_method=integration_method,
        )
        banked.cutoff_jacobian_regimes = banked.cutoff_jacobian_regimes[
            :cutoff_bank_count
        ]
        banked.chord_inverse_banks_q = banked.chord_inverse_banks_q[
            :cutoff_bank_count
        ]
        banked.chord_bank_selection_count = [0] * (cutoff_bank_count + 1)
        model = banked
    output = model.process(
        stimulus(level_peak_v), max_iterations=3, residual_limit_a=2.0e-6
    )
    return {
        "integration_method": integration_method,
        "cutoff_bank_count": cutoff_bank_count,
        "total_coefficient_sets": cutoff_bank_count + 1,
        "burst_input_peak_v": level_peak_v,
        "maximum_residual_a": model.max_residual_q44_observed / float(1 << 44),
        "residual_limit_exceedance_count": model.nonconvergence_count,
        "saturation_count": model.saturation_count,
        "range_clip_count": model.lut_clip_count,
        "correction_scale_fallback_count": model.correction_scale_fallback_count,
        "output_finite": bool(np.all(np.isfinite(output))),
        "bank_selection_count": (
            model.chord_bank_selection_count
            if isinstance(model, FixedWideStateBankedChordV1CircuitModel)
            else [int(output.size)]
        ),
    }


def main() -> int:
    jobs = [
        (method, count, level)
        for method, counts in CUTOFF_BANK_COUNTS.items()
        for count in counts
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
                f"{result['integration_method']} "
                f"banks={result['cutoff_bank_count']} "
                f"level={result['burst_input_peak_v']:.1f} V: "
                f"fail={result['residual_limit_exceedance_count']}, "
                f"max={float(result['maximum_residual_a']) * 1e6:.3f} uA, "
                f"select={result['bank_selection_count']}",
                flush=True,
            )
    results.sort(
        key=lambda item: (
            str(item["integration_method"]),
            int(item["cutoff_bank_count"]),
            float(item["burst_input_peak_v"]),
        )
    )

    selected_counts: dict[str, int] = {}
    for method, counts in CUTOFF_BANK_COUNTS.items():
        passing_counts = [
            count
            for count in counts
            if all(
                int(item[key]) == 0
                for item in results
                if item["integration_method"] == method
                and item["cutoff_bank_count"] == count
                for key in (
                    "residual_limit_exceedance_count",
                    "saturation_count",
                    "range_clip_count",
                    "correction_scale_fallback_count",
                )
            )
        ]
        if not passing_counts:
            raise RuntimeError(f"no passing bank prefix for {method}")
        selected_counts[method] = min(passing_counts)

    gates = {
        "both_modes_have_convergent_prefix": all(
            method in selected_counts for method in CUTOFF_BANK_COUNTS
        ),
        "all_existing_cutoff_banks_are_required": all(
            selected_counts[method] == max(CUTOFF_BANK_COUNTS[method])
            for method in CUTOFF_BANK_COUNTS
        ),
        "all_outputs_finite": all(bool(item["output_finite"]) for item in results),
    }
    report = {
        "model": "12ax7_passive_riaa_v1",
        "study": "cutoff Jacobian bank prefix minimization",
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
        "selection_policy": (
            "retain the most-negative cutoff regimes in order and use the "
            "nominal Jacobian above the last retained threshold"
        ),
        "selected_cutoff_bank_count": selected_counts,
        "selected_total_coefficient_sets": {
            method: count + 1 for method, count in selected_counts.items()
        },
        "bank_prefix_reduction_rejected": True,
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "measurements": results,
    }
    generated = ROOT / "model" / "generated" / "banked_selector_study.json"
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    reference = ROOT / "reference" / "results" / "banked_selector_study.json"
    reference.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_gates_pass"]:
        raise RuntimeError("banked selector study failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
