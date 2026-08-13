#!/usr/bin/env python3
"""Extract frozen V1 small-signal poles from its physical nodal matrices."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


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


def _tube_derivatives(model: V1CircuitModel) -> list[dict[str, float]]:
    derivatives = []
    step_v = 1.0e-5
    for stage, (grid_name, plate_name, cathode_name) in enumerate(
        (("g1", "p1", "k1"), ("g2", "p2", "k2")), start=1
    ):
        grid = model.node[grid_name]
        plate = model.node[plate_name]
        cathode = model.node[cathode_name]
        v_gk = model.voltage[grid] - model.voltage[cathode]
        v_pk = model.voltage[plate] - model.voltage[cathode]
        gm = float(
            model.tube.plate_current(v_gk + step_v, v_pk)
            - model.tube.plate_current(v_gk - step_v, v_pk)
        ) / (2.0 * step_v)
        gp = float(
            model.tube.plate_current(v_gk, v_pk + step_v)
            - model.tube.plate_current(v_gk, v_pk - step_v)
        ) / (2.0 * step_v)
        gg = float(
            model.tube.grid_current(v_gk + step_v)
            - model.tube.grid_current(v_gk - step_v)
        ) / (2.0 * step_v)
        derivatives.append(
            {
                "stage": stage,
                "v_gk_v": float(v_gk),
                "v_pk_v": float(v_pk),
                "transconductance_s": gm,
                "plate_conductance_s": gp,
                "plate_resistance_ohm": 1.0 / gp,
                "grid_conductance_s": gg,
            }
        )
    return derivatives


def main() -> int:
    model = V1CircuitModel(768_000.0, integration_method="trapezoidal")
    linear_conductance = model.conductance.copy()
    residual = np.zeros(model.node_count, dtype=np.float64)
    model._tube_stamp(
        residual, linear_conductance, model.voltage, "g1", "p1", "k1"
    )
    model._tube_stamp(
        residual, linear_conductance, model.voltage, "g2", "p2", "k2"
    )
    capacitance = np.zeros_like(linear_conductance)
    for capacitor in model.capacitors:
        model._stamp_matrix_branch(
            capacitance,
            capacitor.node_a,
            capacitor.node_b,
            capacitor.capacitance_f,
        )

    # det(G+sC) = det(G) det(I+s G^-1 C). A nonzero eigenvalue
    # mu of G^-1 C therefore corresponds to the physical pole s=-1/mu.
    time_matrix = np.linalg.solve(linear_conductance, capacitance)
    eigenvalues, eigenvectors = np.linalg.eig(time_matrix)
    finite_indices = [
        index for index, value in enumerate(eigenvalues) if abs(value) > 1.0e-12
    ]
    finite_indices.sort(key=lambda index: abs(eigenvalues[index]), reverse=True)

    modes: list[dict[str, object]] = []
    for mode_number, index in enumerate(finite_indices, start=1):
        mu = complex(eigenvalues[index])
        pole = -1.0 / mu
        vector = np.asarray(eigenvectors[:, index], dtype=np.complex128)
        largest = int(np.argmax(np.abs(vector)))
        vector /= vector[largest]
        capacitor_energy = []
        for capacitor in model.capacitors:
            voltage_a = vector[capacitor.node_a] if capacitor.node_a is not None else 0.0
            voltage_b = vector[capacitor.node_b] if capacitor.node_b is not None else 0.0
            capacitor_energy.append(
                capacitor.capacitance_f * abs(voltage_a - voltage_b) ** 2
            )
        energy_total = float(sum(capacitor_energy))
        modes.append(
            {
                "mode": mode_number,
                "time_matrix_eigenvalue_s": {
                    "real": float(mu.real),
                    "imaginary": float(mu.imag),
                },
                "pole_per_s": {
                    "real": float(pole.real),
                    "imaginary": float(pole.imag),
                },
                "decay_time_constant_s": float(-1.0 / pole.real),
                "oscillation_frequency_hz": float(abs(pole.imag) / (2.0 * np.pi)),
                "normalized_node_voltage": {
                    name: {
                        "magnitude": float(abs(vector[node_index])),
                        "phase_deg": float(np.degrees(np.angle(vector[node_index]))),
                    }
                    for node_index, name in enumerate(model.NODE_NAMES)
                },
                "capacitor_energy_fraction": {
                    name: float(energy / energy_total)
                    for name, energy in zip(
                        CAPACITOR_NAMES, capacitor_energy, strict=True
                    )
                },
            }
        )

    slow = modes[0]
    medium = modes[1]
    prior_path = ROOT / "model" / "generated" / "long_overload_recovery_summary.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    empirical_early_time_constants = [
        float(measurement["dominant_exponential_fit"]["time_constant_s"])
        for measurement in prior["measurements"]
    ]
    severe_path = (
        ROOT / "model" / "generated" / "severe_overload_recovery_summary.json"
    )
    severe = json.loads(severe_path.read_text(encoding="utf-8"))
    slow_tau_s = float(slow["decay_time_constant_s"])
    severe_end_post_s = float(severe["stimulus"]["post_burst_observation_s"])
    modal_late_projections = []
    for measurement in severe["measurements"]:
        endpoint_rms_v = float(measurement["final_10ms_deviation_rms_v"])
        modal_late_projections.append(
            {
                "burst_input_peak_v": measurement["burst_input_peak_v"],
                "starting_post_burst_time_s": severe_end_post_s,
                "starting_deviation_rms_v": endpoint_rms_v,
                "estimated_recovery_s_after_burst": {
                    name: severe_end_post_s
                    + slow_tau_s * np.log(endpoint_rms_v / float(threshold))
                    for name, threshold in severe["recovery_thresholds_v_rms"].items()
                    if endpoint_rms_v > float(threshold)
                },
            }
        )
    report = {
        "model": "12ax7_passive_riaa_v1",
        "analysis": "continuous-time small-signal nodal modes at DC bias",
        "equation": "det(G + s*C)=0 via nonzero eigenvalues of inverse(G)*C",
        "node_count": model.node_count,
        "capacitance_matrix_rank": int(np.linalg.matrix_rank(capacitance)),
        "conductance_matrix_rank": int(np.linalg.matrix_rank(linear_conductance)),
        "conductance_matrix_condition_number": float(
            np.linalg.cond(linear_conductance)
        ),
        "dc_nodes_v": model.nodes,
        "tube_small_signal_parameters": _tube_derivatives(model),
        "finite_dynamic_modes": len(modes),
        "all_finite_poles_stable": all(
            float(mode["pole_per_s"]["real"]) < 0.0 for mode in modes
        ),
        "modes": modes,
        "overload_recovery_interpretation": {
            "slow_time_constant_s": slow["decay_time_constant_s"],
            "slow_output_capacitor_energy_fraction": slow[
                "capacitor_energy_fraction"
            ]["output_470nf"],
            "medium_time_constant_s": medium["decay_time_constant_s"],
            "medium_output_capacitor_energy_fraction": medium[
                "capacitor_energy_fraction"
            ]["output_470nf"],
            "empirical_50_to_240ms_fit_time_constants_s": (
                empirical_early_time_constants
            ),
            "interpretation": (
                "The early overload envelope follows the 143.9 ms mode while "
                "an oppositely signed 1.068 s output-coupling mode later emerges, "
                "causing the measured cancellation and rebound."
            ),
            "linearization_limit": (
                "Modes predict late recovery near the DC operating point; they "
                "do not validate the large-signal tube/grid-current model."
            ),
            "modal_late_recovery_estimates": modal_late_projections,
            "estimate_source": str(severe_path.relative_to(ROOT)),
            "recommended_direct_record_duration_s": 7.0,
            "duration_rationale": (
                "The slow-mode estimate places the latest 1 mV crossing near "
                "6.33 s after the burst; seven seconds directly tests it with "
                "margin. Estimates remain non-acceptance evidence."
            ),
        },
    }
    if report["capacitance_matrix_rank"] != 8 or len(modes) != 8:
        raise RuntimeError("unexpected V1 dynamic rank")
    if not report["all_finite_poles_stable"]:
        raise RuntimeError("linearized V1 contains an unstable pole")
    if not 1.05 <= float(slow["decay_time_constant_s"]) <= 1.09:
        raise RuntimeError("slow output-coupling mode left its measured bound")
    if not 0.140 <= float(medium["decay_time_constant_s"]) <= 0.150:
        raise RuntimeError("medium recovery mode left its measured bound")
    if float(slow["capacitor_energy_fraction"]["output_470nf"]) < 0.999:
        raise RuntimeError("slow mode is no longer output-capacitor dominated")

    summary = ROOT / "model" / "generated" / "linearized_mode_summary.json"
    summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result = ROOT / "reference" / "results" / "linearized_modes.json"
    result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
