#!/usr/bin/env python3
"""Measure the long floating-model tail after severe V1 overload.

This deliberately uses the floating trapezoidal physical-circuit model.  The
present fixed solver is accepted through 0.5 V but is not overload-equivalent at
1.0/1.5 V, so extrapolating its severe trajectory would blur a known numerical
limitation with the circuit's recovery behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

from characterize_overload_recovery import (  # noqa: E402
    sliding_rms,
    sustained_recovery_s,
)
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


SAMPLE_RATE_HZ = 768_000.0
FREQUENCY_HZ = 1_000.0
NOMINAL_PEAK_V = 0.005
BURST_START_S = 0.010
BURST_END_S = 0.015
DURATION_S = 0.250
LEVELS_PEAK_V = (0.500, 1.000, 1.500)
CHECKPOINTS_S = (0.020, 0.050, 0.100, 0.150, 0.200, 0.250)
FIT_START_S = 0.050
FIT_END_S = 0.240

CAPACITOR_NAMES = (
    "stage1_grid_cathode",
    "stage1_grid_plate",
    "stage1_plate_cathode",
    "stage2_grid_cathode",
    "stage2_grid_plate",
    "stage2_plate_cathode",
    "interstage_47nf",
    "riaa_10nf",
    "riaa_3p3nf",
    "output_470nf",
)


def _stimulus(level_peak_v: float) -> np.ndarray:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    amplitude = np.full(time_s.size, NOMINAL_PEAK_V)
    amplitude[(time_s >= BURST_START_S) & (time_s < BURST_END_S)] = level_peak_v
    return amplitude * np.sin(2.0 * np.pi * FREQUENCY_HZ * time_s)


def _run(
    level_peak_v: float,
) -> tuple[np.ndarray, int, dict[float, dict[str, object]]]:
    model = V1CircuitModel(
        SAMPLE_RATE_HZ, integration_method="trapezoidal"
    )
    samples = _stimulus(level_peak_v)
    output = np.empty_like(samples)
    checkpoint_indices = {
        int(round(value * SAMPLE_RATE_HZ)) - 1: value for value in CHECKPOINTS_S
    }
    checkpoints: dict[float, dict[str, object]] = {}
    for index, sample in enumerate(samples):
        output[index] = model.process_sample(
            float(sample), max_iterations=8, tolerance_a=1.0e-12
        )
        if index in checkpoint_indices:
            checkpoints[checkpoint_indices[index]] = {
                "nodes_v": model.nodes,
                "capacitor_voltage_v": {
                    name: capacitor.previous_voltage_v
                    for name, capacitor in zip(
                        CAPACITOR_NAMES, model.capacitors, strict=True
                    )
                },
                "capacitor_current_a": {
                    name: capacitor.previous_current_a
                    for name, capacitor in zip(
                        CAPACITOR_NAMES, model.capacitors, strict=True
                    )
                },
            }
    return output, model.nonconvergence_count, checkpoints


def _exponential_fit(
    envelope: np.ndarray, threshold_by_name: dict[str, float]
) -> dict[str, object]:
    window_samples = int(round(0.001 * SAMPLE_RATE_HZ))
    end_time_s = np.arange(envelope.size, dtype=np.float64)
    end_time_s = (end_time_s + window_samples - 1) / SAMPLE_RATE_HZ
    selected = (
        (end_time_s >= FIT_START_S)
        & (end_time_s <= FIT_END_S)
        & (envelope > 0.0)
    )
    post_burst_time_s = end_time_s[selected] - BURST_END_S
    observed = envelope[selected]
    basis = np.column_stack((np.ones(observed.size), post_burst_time_s))
    coefficient, *_ = np.linalg.lstsq(basis, np.log(observed), rcond=None)
    fitted = np.exp(basis @ coefficient)
    log_residual = np.log(observed) - np.log(fitted)
    log_total = np.log(observed) - float(np.mean(np.log(observed)))
    slope = float(coefficient[1])
    projected: dict[str, float | None] = {}
    for name, threshold in threshold_by_name.items():
        crossing = (np.log(threshold) - float(coefficient[0])) / slope
        projected[name] = float(crossing) if crossing >= 0.0 else None
    return {
        "fit_start_s_absolute": FIT_START_S,
        "fit_end_s_absolute": FIT_END_S,
        "samples": int(observed.size),
        "time_constant_s": -1.0 / slope,
        "r_squared_log_envelope": float(
            1.0 - np.sum(np.square(log_residual)) / np.sum(np.square(log_total))
        ),
        "rms_relative_envelope_error": float(
            np.sqrt(np.mean(np.square(fitted / observed - 1.0)))
        ),
        "projected_recovery_s_after_burst": projected,
        "projection_is_not_measured_recovery": True,
    }


def _state_difference(
    candidate: dict[float, dict[str, object]],
    control: dict[float, dict[str, object]],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for checkpoint_s in CHECKPOINTS_S:
        node_difference = {
            name: float(candidate[checkpoint_s]["nodes_v"][name])
            - float(control[checkpoint_s]["nodes_v"][name])
            for name in V1CircuitModel.NODE_NAMES
        }
        capacitor_difference = {
            name: float(
                candidate[checkpoint_s]["capacitor_voltage_v"][name]
            )
            - float(control[checkpoint_s]["capacitor_voltage_v"][name])
            for name in CAPACITOR_NAMES
        }
        largest_node = max(node_difference, key=lambda name: abs(node_difference[name]))
        largest_capacitor = max(
            capacitor_difference,
            key=lambda name: abs(capacitor_difference[name]),
        )
        result.append(
            {
                "absolute_time_s": checkpoint_s,
                "post_burst_time_s": max(0.0, checkpoint_s - BURST_END_S),
                "largest_node_difference": {
                    "node": largest_node,
                    "voltage_v": node_difference[largest_node],
                },
                "largest_capacitor_voltage_difference": {
                    "capacitor": largest_capacitor,
                    "voltage_v": capacitor_difference[largest_capacitor],
                },
                "node_difference_v": node_difference,
                "capacitor_voltage_difference_v": capacitor_difference,
            }
        )
    return result


def main() -> int:
    sample_count = int(round(DURATION_S * SAMPLE_RATE_HZ))
    post_index = int(round(BURST_END_S * SAMPLE_RATE_HZ))
    window_samples = int(round(0.001 * SAMPLE_RATE_HZ))
    final_window = slice(sample_count - int(0.010 * SAMPLE_RATE_HZ), None)
    control, control_failures, control_checkpoints = _run(NOMINAL_PEAK_V)
    nominal_output_rms = float(
        np.sqrt(np.mean(np.square(control[final_window])))
    )
    thresholds = {
        "ten_percent_nominal_output_rms": 0.10 * nominal_output_rms,
        "one_percent_nominal_output_rms": 0.01 * nominal_output_rms,
        "one_millivolt_rms": 0.001,
    }

    measurements: list[dict[str, object]] = []
    for level_peak_v in LEVELS_PEAK_V:
        output, failures, checkpoints = _run(level_peak_v)
        residual = output - control
        envelope = sliding_rms(residual, window_samples)
        envelope_samples = {
            f"{time_s:g}": float(
                envelope[int(round(time_s * SAMPLE_RATE_HZ)) - window_samples]
            )
            for time_s in CHECKPOINTS_S[:-1]
        }
        measurement = {
            "burst_input_peak_v": level_peak_v,
            "nonconvergence_count": failures,
            "peak_post_burst_deviation_v": float(
                np.max(np.abs(residual[post_index:]))
            ),
            "measured_recovery_s_after_burst": {
                name: sustained_recovery_s(residual, threshold, post_index)
                for name, threshold in thresholds.items()
            },
            "one_ms_deviation_rms_v_at_absolute_time_s": envelope_samples,
            "final_10ms_deviation_rms_v": float(
                np.sqrt(np.mean(np.square(residual[final_window])))
            ),
            "dominant_exponential_fit": _exponential_fit(envelope, thresholds),
            "state_difference_checkpoints": _state_difference(
                checkpoints, control_checkpoints
            ),
        }
        measurements.append(measurement)
        recovery = measurement["measured_recovery_s_after_burst"]
        fit = measurement["dominant_exponential_fit"]
        print(
            f"{level_peak_v:5.3f} V peak: 10% recovery "
            f"{recovery['ten_percent_nominal_output_rms']}, "
            f"fit tau {fit['time_constant_s']:.6f} s",
            flush=True,
        )

    report = {
        "model": "12ax7_passive_riaa_v1",
        "implementation": "floating nonlinear nodal circuit model",
        "integration_method": "trapezoidal",
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
        "nominal_output_rms_v": nominal_output_rms,
        "recovery_thresholds_v_rms": thresholds,
        "recovery_definition": (
            "last 1 ms sliding-RMS threshold crossing relative to a nominal "
            "undisturbed trajectory"
        ),
        "simple_component_products_not_fitted_poles": {
            "output_470nf_times_2p21m_s": 470.0e-9 * 2.21e6,
            "riaa_3p3nf_times_2p21m_s": 3.3e-9 * 2.21e6,
            "interstage_47nf_times_210k_s": 47.0e-9 * 210_000.0,
            "note": (
                "These products are context only; the coupled nonlinear nodal "
                "response determines the measured recovery."
            ),
        },
        "control_nonconvergence_count": control_failures,
        "measurements": measurements,
        "fixed_rtl_scope": (
            "No fixed/RTL equivalence is claimed here. The existing solver is "
            "accepted through 0.5 V and has known residual/range failures at "
            "1.0/1.5 V."
        ),
    }
    if control_failures or any(
        int(measurement["nonconvergence_count"]) for measurement in measurements
    ):
        raise RuntimeError("long floating recovery failed to converge")
    half_volt_recovery = measurements[0]["measured_recovery_s_after_burst"]
    ten_percent_s = half_volt_recovery["ten_percent_nominal_output_rms"]
    if ten_percent_s is None or not 0.140 <= float(ten_percent_s) <= 0.155:
        raise RuntimeError("0.5 V 10%-recovery time left its measured bound")
    if any(
        float(measurement["dominant_exponential_fit"]["rms_relative_envelope_error"])
        > 0.05
        for measurement in measurements
    ):
        raise RuntimeError("long recovery is not represented by the gated fit")

    summary = ROOT / "model" / "generated" / "long_overload_recovery_summary.json"
    summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result = ROOT / "reference" / "results" / "long_overload_recovery.json"
    result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
