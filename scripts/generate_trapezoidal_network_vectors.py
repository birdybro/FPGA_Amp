#!/usr/bin/env python3
"""Generate exact wide-state trapezoidal KCL/current-history vectors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedWideStateTrapezoidalV1CircuitModel,
    round_shift,
    saturate_signed,
)
from generate_wide_network_vectors import (  # noqa: E402
    requested_residual,
    tube_stamp,
    write_memory,
)


def capacitor_stamp_and_next(
    model: FixedWideStateTrapezoidalV1CircuitModel,
    voltage: list[int],
    capacitor_voltage: list[int],
    capacitor_current: list[int],
) -> tuple[list[int], list[int], int]:
    stamp = [0] * model.node_count
    next_current: list[int] = []
    saturation_count = 0
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
            voltage_a - voltage_b - capacitor_voltage[index],
            model.CAPACITOR_STATE_FRACTIONAL_BITS,
        ) - capacitor_current[index]
        if capacitor.node_a is not None:
            stamp[capacitor.node_a] += branch
        if capacitor.node_b is not None:
            stamp[capacitor.node_b] -= branch
        committed, clipped = saturate_signed(branch, model.CAPACITOR_CURRENT_WIDTH)
        next_current.append(committed)
        saturation_count += int(clipped)
    return stamp, next_current, saturation_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=int, default=1024)
    args = parser.parse_args()
    model = FixedWideStateTrapezoidalV1CircuitModel(
        tube_lut=FixedFactorizedKoren12AX7()
    )
    generated = ROOT / "model" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    cap_g_path = generated / "v1_cap_conductance_q0_47_trapezoidal.mem"
    cap_current_initial_path = (
        generated / "v1_cap_current_initial_q4_44_trapezoidal.mem"
    )
    conductance = [
        int(capacitor.conductance_q47) for capacitor in model.capacitors
    ]
    if not all(-(1 << 47) <= value < (1 << 47) for value in conductance):
        raise RuntimeError("trapezoidal capacitor conductance exceeds signed 48-bit")
    if max(conductance) < (1 << 46):
        raise RuntimeError("trapezoidal width regression no longer exercises bit 47")
    write_memory(cap_g_path, conductance, 48)
    write_memory(cap_current_initial_path, [0] * 10, 48)

    rng = np.random.default_rng(0x54524150)
    vector_path = (
        ROOT / "sim" / "vectors" / "generated" / "network_kcl_wide_trapezoidal.txt"
    )
    vector_path.parent.mkdir(parents=True, exist_ok=True)
    fallback_vectors = 0
    correction_saturation_vectors = 0
    current_saturation_vectors = 0
    selected_counts = {30: 0, 34: 0, 40: 0}
    with vector_path.open("w", encoding="ascii") as handle:
        for index in range(args.vectors):
            voltage: list[int] = []
            for fraction in model.VOLTAGE_FRACTIONAL_BITS:
                limit_v = 300.0 if int(fraction) == 28 else 4.0
                voltage.append(
                    int(round(rng.uniform(-limit_v, limit_v) * (1 << int(fraction))))
                )
            capacitor_voltage = [
                int(round(float(value) * (1 << 30)))
                for value in rng.uniform(-300.0, 300.0, size=10)
            ]
            capacitor_current = [
                int(round(float(value) * (1 << 44)))
                for value in rng.uniform(-1.0e-3, 1.0e-3, size=10)
            ]
            current_q31 = [
                int(round(float(value) * (1 << 31)))
                for value in rng.uniform(-2.0e-3, 2.0e-3, size=4)
            ]
            if index == 0:
                voltage = [int(value) for value in model.voltage_q]
                capacitor_voltage = [
                    int(capacitor.previous_voltage_q20)
                    for capacitor in model.capacitors
                ]
                capacitor_current = [0] * 10
                current_q31 = [0] * 4
            elif index in (54, 55):
                # Directed full-range check for capacitor 6, the only branch
                # joining two Q28 nodes.  Include the worst legal Q30 voltage
                # history and Q4.44 current history signs.
                voltage = [0] * model.node_count
                capacitor_voltage = [0] * len(model.capacitors)
                capacitor_current = [0] * len(model.capacitors)
                polarity = 1 if index == 54 else -1
                voltage[1] = (1 << 39) - 1 if polarity > 0 else -(1 << 39)
                voltage[3] = -(1 << 39) if polarity > 0 else (1 << 39) - 1
                capacitor_voltage[6] = (
                    -(1 << 39) if polarity > 0 else (1 << 39) - 1
                )
                capacitor_current[6] = (
                    -(1 << 47) if polarity > 0 else (1 << 47) - 1
                )
                current_q31 = [0] * 4
            elif index in (56, 57):
                # Full signed-current boundary for the cathode sum.
                voltage = [0] * model.node_count
                capacitor_voltage = [0] * len(model.capacitors)
                capacitor_current = [0] * len(model.capacitors)
                current_q31 = [0] * 4
                pair = 0 if index == 56 else 2
                current_q31[pair] = -(1 << 31)
                current_q31[pair + 1] = -(1 << 31)

            linear = [0] * model.node_count
            for row in range(model.node_count):
                for column in range(model.node_count):
                    linear[row] += model._linear_product_current_q44(
                        int(model.matrix_q47[row, column]),
                        voltage[column],
                        int(model.VOLTAGE_FRACTIONAL_BITS[column]),
                    )
            capacitive, next_current, current_saturation_count = (
                capacitor_stamp_and_next(
                    model, voltage, capacitor_voltage, capacitor_current
                )
            )
            nonlinear = tube_stamp(current_q31)
            requested, target_residual = requested_residual(index, rng)
            rhs = [
                linear[row] + capacitive[row] + nonlinear[row] - target_residual[row]
                for row in range(model.node_count)
            ]
            selected = model._select_correction_fraction(target_residual, requested)
            selected_counts[selected] += 1
            fallback = selected != requested
            fallback_vectors += int(fallback)
            converted: list[int] = []
            correction_saturation_count = 0
            for value in target_residual:
                quantized = round_shift(value, 44 - selected)
                quantized, clipped = saturate_signed(quantized, 25)
                converted.append(quantized)
                correction_saturation_count += int(clipped)
            correction_saturation_vectors += int(correction_saturation_count != 0)
            current_saturation_vectors += int(current_saturation_count != 0)
            fields = [
                requested,
                *voltage,
                *capacitor_voltage,
                *capacitor_current,
                *rhs,
                *current_q31,
                selected,
                *converted,
                correction_saturation_count,
                max(abs(value) for value in target_residual),
                int(fallback),
                *next_current,
                current_saturation_count,
            ]
            handle.write(" ".join(str(value) for value in fields) + "\n")

    report = {
        "model": "12ax7_passive_riaa_v1",
        "algorithm": "trapezoidal Q30 voltage/Q4.44 current branch stamps",
        "vectors": args.vectors,
        "seed": 0x54524150,
        "capacitor_conductance_width_bits": 48,
        "maximum_capacitor_conductance_q47": max(conductance),
        "maximum_capacitor_conductance_s": max(conductance) / (1 << 47),
        "capacitor_current_width_bits": 48,
        "capacitor_current_fractional_bits": 44,
        "selected_format_vectors": selected_counts,
        "fallback_vectors": fallback_vectors,
        "correction_saturation_vectors": correction_saturation_vectors,
        "current_saturation_vectors": current_saturation_vectors,
        "latency_clocks": 10,
        "outputs": [
            str(path.relative_to(ROOT))
            for path in (cap_g_path, cap_current_initial_path, vector_path)
        ],
    }
    metadata = generated / "wide_network_trapezoidal_metadata.json"
    metadata.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
