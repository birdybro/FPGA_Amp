#!/usr/bin/env python3
"""Measure long fixed/analytical state drift around synthetic record clicks."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedChordV1CircuitModel,
    FixedWideStateV1CircuitModel,
)
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


SAMPLE_RATE_HZ = 768_000.0
POSITIVE_CLICK_S = 0.100
NEGATIVE_CLICK_S = 0.300
CLICK_PEAK_V = 0.100


def db_ratio(numerator: float, denominator: float) -> float | None:
    if numerator <= 0.0 or denominator <= 0.0:
        return None
    return float(20.0 * math.log10(numerator / denominator))


def capacitor_name(model: V1CircuitModel, index: int) -> str:
    capacitor = model.capacitors[index]
    names = {node_index: name for name, node_index in model.node.items()}
    node_a = "ground" if capacitor.node_a is None else names[capacitor.node_a]
    node_b = "ground" if capacitor.node_b is None else names[capacitor.node_b]
    return f"C{index}_{node_a}_{node_b}_{capacitor.capacitance_f:.6g}F"


def state_snapshot(
    analytical: V1CircuitModel, fixed: FixedChordV1CircuitModel
) -> dict[str, object]:
    nodes: dict[str, object] = {}
    for name in analytical.NODE_NAMES:
        analytical_v = analytical.nodes[name]
        fixed_v = fixed.nodes[name]
        nodes[name] = {
            "analytical_v": analytical_v,
            "fixed_v": fixed_v,
            "error_v": fixed_v - analytical_v,
        }
    capacitors: dict[str, object] = {}
    for index, (analytical_cap, fixed_cap) in enumerate(
        zip(analytical.capacitors, fixed.capacitors, strict=True)
    ):
        analytical_v = analytical_cap.previous_voltage_v
        fixed_v = fixed_cap.previous_voltage_q20 / (
            1 << fixed.CAPACITOR_STATE_FRACTIONAL_BITS
        )
        capacitors[capacitor_name(analytical, index)] = {
            "analytical_v": analytical_v,
            "fixed_v": fixed_v,
            "error_v": fixed_v - analytical_v,
        }
    return {"nodes": nodes, "capacitors": capacitors}


def window_metrics(
    time_s: np.ndarray,
    analytical: np.ndarray,
    fixed: np.ndarray,
    start_s: float,
    end_s: float,
    baseline_residual_v: float,
) -> dict[str, float | None]:
    selected = (time_s >= start_s) & (time_s < end_s)
    reference = analytical[selected]
    candidate = fixed[selected]
    residual = candidate - reference
    baseline_corrected = residual - baseline_residual_v
    reference_rms = float(np.sqrt(np.mean(np.square(reference))))
    residual_rms = float(np.sqrt(np.mean(np.square(residual))))
    corrected_rms = float(np.sqrt(np.mean(np.square(baseline_corrected))))
    return {
        "start_s": start_s,
        "end_s": end_s,
        "sample_count": int(np.count_nonzero(selected)),
        "analytical_mean_v": float(np.mean(reference)),
        "analytical_rms_v": reference_rms,
        "fixed_mean_v": float(np.mean(candidate)),
        "fixed_rms_v": float(np.sqrt(np.mean(np.square(candidate)))),
        "raw_residual_mean_v": float(np.mean(residual)),
        "raw_residual_rms_v": residual_rms,
        "raw_residual_peak_v": float(np.max(np.abs(residual))),
        "baseline_corrected_residual_rms_v": corrected_rms,
        "baseline_corrected_residual_peak_v": float(
            np.max(np.abs(baseline_corrected))
        ),
        "raw_normalized_residual_db": db_ratio(residual_rms, reference_rms),
        "baseline_corrected_normalized_residual_db": db_ratio(
            corrected_rms, reference_rms
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-s", type=float, default=1.0)
    parser.add_argument("--wide-candidate", action="store_true")
    parser.add_argument("--corrections", type=int, default=3)
    args = parser.parse_args()
    if args.duration_s < 1.0:
        raise SystemExit("--duration-s must be at least 1.0 for the fixed windows")

    sample_count = int(round(args.duration_s * SAMPLE_RATE_HZ))
    time_s = np.arange(sample_count, dtype=np.float64) / SAMPLE_RATE_HZ
    stimulus = np.zeros(sample_count, dtype=np.float64)
    positive_index = int(round(POSITIVE_CLICK_S * SAMPLE_RATE_HZ))
    negative_index = int(round(NEGATIVE_CLICK_S * SAMPLE_RATE_HZ))
    stimulus[positive_index] = CLICK_PEAK_V
    stimulus[negative_index] = -CLICK_PEAK_V

    analytical_model = V1CircuitModel(SAMPLE_RATE_HZ)
    fixed_type = (
        FixedWideStateV1CircuitModel
        if args.wide_candidate
        else FixedChordV1CircuitModel
    )
    fixed_model = fixed_type(SAMPLE_RATE_HZ, tube_lut=FixedFactorizedKoren12AX7())
    analytical_output = np.empty(sample_count, dtype=np.float64)
    fixed_output = np.empty(sample_count, dtype=np.float64)

    snapshot_indices = {
        "before_positive_click": positive_index - 1,
        "after_positive_click": positive_index,
        "before_negative_click": negative_index - 1,
        "after_negative_click": negative_index,
        "half_second": int(round(0.500 * SAMPLE_RATE_HZ)),
        "final": sample_count - 1,
    }
    snapshots: dict[str, object] = {
        "initial": state_snapshot(analytical_model, fixed_model)
    }
    progress_interval = int(round(0.100 * SAMPLE_RATE_HZ))
    for index, sample in enumerate(stimulus):
        analytical_output[index] = analytical_model.process_sample(
            float(sample), max_iterations=8, tolerance_a=1.0e-12
        )
        fixed_output[index] = fixed_model.process_sample(
            float(sample),
            max_iterations=args.corrections,
            residual_limit_a=2.0e-6,
        )
        for name, snapshot_index in snapshot_indices.items():
            if index == snapshot_index:
                snapshots[name] = state_snapshot(analytical_model, fixed_model)
        if (index + 1) % progress_interval == 0:
            print(
                f"processed {(index + 1) / SAMPLE_RATE_HZ:.1f} / "
                f"{args.duration_s:.1f} s",
                flush=True,
            )

    pre_click = (time_s >= 0.050) & (time_s < 0.090)
    residual = fixed_output - analytical_output
    baseline_residual_v = float(np.mean(residual[pre_click]))
    windows = {
        "pre_click_silence": (0.050, 0.090),
        "positive_click_response": (0.100, 0.150),
        "between_clicks": (0.200, 0.250),
        "negative_click_response": (0.300, 0.350),
        "late_settling": (0.900, 1.000),
    }
    window_report = {
        name: window_metrics(
            time_s,
            analytical_output,
            fixed_output,
            start_s,
            end_s,
            baseline_residual_v,
        )
        for name, (start_s, end_s) in windows.items()
    }

    late_selected = (time_s >= 0.500) & (time_s < 1.000)
    late_time = time_s[late_selected]
    late_residual = residual[late_selected]
    residual_slope_v_per_s = float(np.polyfit(late_time, late_residual, 1)[0])
    final_snapshot = snapshots["final"]
    node_errors = [
        abs(float(value["error_v"]))
        for value in final_snapshot["nodes"].values()  # type: ignore[union-attr]
    ]
    capacitor_errors = [
        abs(float(value["error_v"]))
        for value in final_snapshot["capacitors"].values()  # type: ignore[union-attr]
    ]
    report = {
        "model": "12ax7_passive_riaa_v1",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "duration_s": args.duration_s,
        "sample_count": sample_count,
        "stimulus": {
            "description": "silence with one-sample bipolar synthetic clicks",
            "positive_click_time_s": POSITIVE_CLICK_S,
            "negative_click_time_s": NEGATIVE_CLICK_S,
            "click_peak_v": CLICK_PEAK_V,
        },
        "comparison": "analytical Koren/full Newton versus factorized fixed chord candidate",
        "fixed_implementation": (
            "40-bit Q28/Q32 nodes, Q30 capacitor history, and explicit branch-current stamps"
            if args.wide_candidate
            else "legacy Q12.20 output/history with matrix-plus-history stamps"
        ),
        "fixed_chord_corrections": args.corrections,
        "fixed_correction_residual_fractional_bits": list(
            fixed_model.correction_residual_fractional_bits
        ),
        "baseline_residual_mean_v": baseline_residual_v,
        "baseline_note": "baseline correction is reported separately and never applied to raw output",
        "late_residual_linear_slope_v_per_s": residual_slope_v_per_s,
        "maximum_final_node_state_error_v": max(node_errors),
        "maximum_final_capacitor_state_error_v": max(capacitor_errors),
        "analytical_nonconvergence_count": analytical_model.nonconvergence_count,
        "fixed": {
            "residual_limit_exceedance_count": fixed_model.nonconvergence_count,
            "maximum_residual_a": fixed_model.max_residual_q44_observed / (1 << 44),
            "saturation_count": fixed_model.saturation_count,
            "range_clip_count": fixed_model.lut_clip_count,
        },
        "windows": window_report,
        "state_snapshots": snapshots,
    }
    report_stem = "state_drift_wide" if args.wide_candidate else "state_drift"
    result_path = REPOSITORY_ROOT / "reference" / "results" / f"{report_stem}.json"
    result_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary_path = (
        REPOSITORY_ROOT / "model" / "generated" / f"{report_stem}_summary.json"
    )
    summary_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
