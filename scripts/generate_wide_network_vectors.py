#!/usr/bin/env python3
"""Generate exact branch-current KCL vectors for the wide-state candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedWideStateV1CircuitModel,
    round_shift,
    saturate_signed,
)


def write_memory(path: Path, values: list[int], width: int) -> None:
    digits = (width + 3) // 4
    mask = (1 << width) - 1
    with path.open("w", encoding="ascii") as handle:
        for value in values:
            handle.write(f"{value & mask:0{digits}x}\n")


def capacitor_stamp(
    model: FixedWideStateV1CircuitModel,
    voltage: list[int],
    capacitor_state: list[int],
) -> list[int]:
    stamp = [0] * model.node_count
    for index, capacitor in enumerate(model.capacitors):
        voltage_a = 0
        voltage_b = 0
        if capacitor.node_a is not None:
            voltage_a = model._convert_fraction(
                voltage[capacitor.node_a],
                int(model.VOLTAGE_FRACTIONAL_BITS[capacitor.node_a]),
                model.CAPACITOR_STATE_FRACTIONAL_BITS,
            )
        if capacitor.node_b is not None:
            voltage_b = model._convert_fraction(
                voltage[capacitor.node_b],
                int(model.VOLTAGE_FRACTIONAL_BITS[capacitor.node_b]),
                model.CAPACITOR_STATE_FRACTIONAL_BITS,
            )
        branch = model._linear_product_current_q44(
            capacitor.conductance_q47,
            voltage_a - voltage_b - capacitor_state[index],
            model.CAPACITOR_STATE_FRACTIONAL_BITS,
        )
        if capacitor.node_a is not None:
            stamp[capacitor.node_a] += branch
        if capacitor.node_b is not None:
            stamp[capacitor.node_b] -= branch
    return stamp


def tube_stamp(current_q31: list[int]) -> list[int]:
    ip1, ig1, ip2, ig2 = current_q31
    stamp = [0] * 9
    stamp[0] += ig1 << 13
    stamp[1] += ip1 << 13
    stamp[2] -= (ip1 + ig1) << 13
    stamp[4] += ig2 << 13
    stamp[6] += ip2 << 13
    stamp[7] -= (ip2 + ig2) << 13
    return stamp


def requested_residual(index: int, rng: np.random.Generator) -> tuple[int, list[int]]:
    requested = (30, 34, 40)[index % 3]
    residual = [
        int(round(float(value) * (1 << 44)))
        for value in rng.uniform(-8.0e-6, 8.0e-6, size=9)
    ]
    lane = index % 9
    if index < 18:
        # Q40 cannot hold 100 uA, but Q34 can.
        requested = 40
        residual = [0] * 9
        residual[lane] = (1 if index < 9 else -1) * int(round(100.0e-6 * (1 << 44)))
    elif index < 36:
        # Q34 cannot hold 2 mA, but Q30 can.
        requested = 40 if index % 2 else 34
        residual = [0] * 9
        residual[lane] = (1 if index < 27 else -1) * int(round(2.0e-3 * (1 << 44)))
    elif index < 54:
        # Even Q30 overflows above approximately 15.625 mA.
        requested = (30, 34, 40)[index % 3]
        residual = [0] * 9
        residual[lane] = (1 if index < 45 else -1) * int(round(20.0e-3 * (1 << 44)))
    return requested, residual


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=int, default=1024)
    args = parser.parse_args()
    model = FixedWideStateV1CircuitModel(tube_lut=FixedFactorizedKoren12AX7())
    generated = REPOSITORY_ROOT / "model" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    matrix_path = generated / "v1_static_matrix_q0_47.mem"
    cap_g_path = generated / "v1_cap_conductance_q0_47.mem"
    cap_initial_path = generated / "v1_cap_initial_q30_wide.mem"
    node_initial_path = generated / "v1_node_initial_wide.mem"
    static_matrix = [int(value) for value in model.matrix_q47.flat]
    capacitor_conductance = [
        int(capacitor.conductance_q47) for capacitor in model.capacitors
    ]
    if not all(-(1 << 40) <= value < (1 << 40) for value in static_matrix):
        raise RuntimeError("static Q47 matrix exceeds signed 41-bit contract")
    if not all(-(1 << 46) <= value < (1 << 46) for value in capacitor_conductance):
        raise RuntimeError("capacitor Q47 conductance exceeds signed 47-bit contract")
    write_memory(matrix_path, static_matrix, 41)
    write_memory(
        cap_g_path,
        capacitor_conductance,
        47,
    )
    initial_capacitor = [
        int(capacitor.previous_voltage_q20) for capacitor in model.capacitors
    ]
    write_memory(cap_initial_path, initial_capacitor, 40)
    write_memory(node_initial_path, [int(value) for value in model.voltage_q], 40)

    rng = np.random.default_rng(0x574B434C)
    vector_path = (
        REPOSITORY_ROOT / "sim" / "vectors" / "generated" / "network_kcl_wide.txt"
    )
    vector_path.parent.mkdir(parents=True, exist_ok=True)
    rhs_vector_path = vector_path.with_name("network_rhs_wide.txt")
    with rhs_vector_path.open("w", encoding="ascii") as handle:
        for index in range(args.vectors):
            input_q24 = int(rng.integers(-(1 << 29), 1 << 29))
            if index == 0:
                input_q24 = 0
            rhs = model._rhs_q44(input_q24)
            handle.write(
                " ".join(str(value) for value in (input_q24, *rhs)) + "\n"
            )
    fallback_vectors = 0
    saturation_vectors = 0
    selected_counts = {30: 0, 34: 0, 40: 0}
    with vector_path.open("w", encoding="ascii") as handle:
        for index in range(args.vectors):
            voltage: list[int] = []
            for fraction in model.VOLTAGE_FRACTIONAL_BITS:
                limit_v = 300.0 if int(fraction) == 28 else 4.0
                voltage.append(int(round(rng.uniform(-limit_v, limit_v) * (1 << int(fraction)))))
            capacitor_state = [
                int(round(float(value) * (1 << 30)))
                for value in rng.uniform(-300.0, 300.0, size=10)
            ]
            current_q31 = [
                int(round(float(value) * (1 << 31)))
                for value in rng.uniform(-2.0e-3, 2.0e-3, size=4)
            ]
            if index == 0:
                voltage = [int(value) for value in model.voltage_q]
                capacitor_state = initial_capacitor.copy()
                current_q31 = [0] * 4

            linear = [0] * 9
            for row in range(9):
                for column in range(9):
                    linear[row] += model._linear_product_current_q44(
                        int(model.matrix_q47[row, column]),
                        voltage[column],
                        int(model.VOLTAGE_FRACTIONAL_BITS[column]),
                    )
            capacitive = capacitor_stamp(model, voltage, capacitor_state)
            nonlinear = tube_stamp(current_q31)
            requested, target_residual = requested_residual(index, rng)
            rhs = [
                linear[row] + capacitive[row] + nonlinear[row] - target_residual[row]
                for row in range(9)
            ]
            selected = model._select_correction_fraction(target_residual, requested)
            selected_counts[selected] += 1
            fallback = selected != requested
            fallback_vectors += int(fallback)
            converted: list[int] = []
            saturation_count = 0
            for value in target_residual:
                quantized = round_shift(value, 44 - selected)
                quantized, clipped = saturate_signed(quantized, 25)
                converted.append(quantized)
                saturation_count += int(clipped)
            saturation_vectors += int(saturation_count != 0)
            fields = [
                requested,
                *voltage,
                *capacitor_state,
                *rhs,
                *current_q31,
                selected,
                *converted,
                saturation_count,
                max(abs(value) for value in target_residual),
                int(fallback),
            ]
            handle.write(" ".join(str(value) for value in fields) + "\n")

    report = {
        "model": "12ax7_passive_riaa_v1",
        "algorithm": "static G*v plus ten direct Q30 capacitor branch stamps",
        "vectors": args.vectors,
        "seed": 0x574B434C,
        "node_fractional_bits": model.VOLTAGE_FRACTIONAL_BITS.tolist(),
        "node_width_bits": model.VOLTAGE_WIDTH,
        "capacitor_state_fractional_bits": model.CAPACITOR_STATE_FRACTIONAL_BITS,
        "static_matrix_width_bits": 41,
        "capacitor_conductance_width_bits": 47,
        "requested_residual_fractional_bits": [30, 34, 40],
        "selected_format_vectors": selected_counts,
        "fallback_vectors": fallback_vectors,
        "saturation_vectors": saturation_vectors,
        "rhs_latency_clocks": 2,
        "latency_clocks": 10,
        "outputs": [
            str(path.relative_to(REPOSITORY_ROOT))
            for path in (
                matrix_path,
                cap_g_path,
                cap_initial_path,
                node_initial_path,
                rhs_vector_path,
                vector_path,
            )
        ],
    }
    metadata = generated / "wide_network_metadata.json"
    metadata.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
