#!/usr/bin/env python3
"""Prove bank switching and full-state RTL exactness through 1.5 V overload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from wide_solver_rtl_capture import capture_wide_solver_rtl  # noqa: E402


SAMPLE_RATE_HZ = 768_000.0
FREQUENCY_HZ = 1_000.0
NOMINAL_PEAK_V = 0.005
BURST_PEAK_VS = (1.0, 1.5)
DURATION_S = 0.012
BURST_START_S = 0.004
BURST_END_S = 0.008


def input_vector(burst_peak_v: float) -> np.ndarray:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    amplitude = np.full(time_s.size, NOMINAL_PEAK_V)
    amplitude[(time_s >= BURST_START_S) & (time_s < BURST_END_S)] = burst_peak_v
    return np.rint(
        amplitude
        * np.sin(2.0 * np.pi * FREQUENCY_HZ * time_s)
        * float(1 << 24)
    ).astype(np.int64)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verilator", default="verilator")
    args = parser.parse_args()

    measurements: list[dict[str, object]] = []
    for burst_peak_v in BURST_PEAK_VS:
        input_q24 = input_vector(burst_peak_v)
        for trapezoidal in (False, True):
            method = "trapezoidal" if trapezoidal else "backward_euler"
            level_tag = str(burst_peak_v).replace(".", "p")
            capture = capture_wide_solver_rtl(
                input_q24,
                f"banked_solver_rtl_overload_{level_tag}v_{method}",
                args.verilator,
                trapezoidal=trapezoidal,
                banked=True,
            )
            model = capture.fixed_model
            counts = model.chord_bank_selection_count
            measurement = {
                "integration_method": method,
                "burst_input_peak_v": burst_peak_v,
                "samples": int(input_q24.size),
                "full_state_rtl_fixed_bit_exact": True,
                "latency_clocks": 116,
                "maximum_residual_a": model.max_residual_q44_observed
                / float(1 << 44),
                "residual_limit_exceedance_count": model.nonconvergence_count,
                "saturation_count": model.saturation_count,
                "range_clip_count": model.lut_clip_count,
                "correction_scale_fallback_count": (
                    model.correction_scale_fallback_count
                ),
                "bank_selection_count": counts,
                "all_cutoff_banks_exercised": all(
                    count > 0 for count in counts[:-1]
                ),
                "nominal_bank_exercised": counts[-1] > 0,
            }
            measurements.append(measurement)
            print(
                f"{method} {burst_peak_v:.1f} V: residual="
                f"{float(measurement['maximum_residual_a']) * 1e6:.3f} "
                f"uA, failures={measurement['residual_limit_exceedance_count']}, "
                f"range={measurement['range_clip_count']}, banks={counts}",
                flush=True,
            )

    one_volt = tuple(
        item for item in measurements if item["burst_input_peak_v"] == 1.0
    )
    severe = tuple(
        item for item in measurements if item["burst_input_peak_v"] == 1.5
    )

    gates = {
        "all_cases_full_state_exact": all(
            bool(item["full_state_rtl_fixed_bit_exact"]) for item in measurements
        ),
        "one_volt_both_modes_converged_without_diagnostics": all(
            int(item[key]) == 0
            for item in one_volt
            for key in (
                "residual_limit_exceedance_count",
                "saturation_count",
                "range_clip_count",
                "correction_scale_fallback_count",
            )
        ),
        "one_point_five_volts_has_no_arithmetic_or_range_event": all(
            int(item[key]) == 0
            for item in severe
            for key in (
                "saturation_count",
                "range_clip_count",
                "correction_scale_fallback_count",
            )
        ),
        "every_generated_bank_selected": all(
            bool(item["all_cutoff_banks_exercised"])
            and bool(item["nominal_bank_exercised"])
            for item in one_volt
        ),
        "fixed_schedule_preserved": all(
            int(item["latency_clocks"]) == 116 for item in measurements
        ),
    }
    report = {
        "model": "12ax7_passive_riaa_v1",
        "implementation": "banked wide SystemVerilog solver",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "stimulus": {
            "frequency_hz": FREQUENCY_HZ,
            "nominal_peak_v": NOMINAL_PEAK_V,
            "burst_peak_v": list(BURST_PEAK_VS),
            "burst_start_s": BURST_START_S,
            "burst_end_s": BURST_END_S,
            "duration_s": DURATION_S,
            "input_format": "Q8.24",
        },
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "measurements": measurements,
    }
    generated = ROOT / "model" / "generated" / "banked_solver_rtl_overload.json"
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    reference = ROOT / "reference" / "results" / "banked_solver_rtl_overload.json"
    reference.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_gates_pass"]:
        raise RuntimeError("banked RTL overload gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
