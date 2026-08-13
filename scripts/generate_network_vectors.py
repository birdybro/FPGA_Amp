#!/usr/bin/env python3
"""Generate fixed V1 network memories and exact RHS/KCL test vectors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.fixed_circuit import FixedChordV1CircuitModel, round_shift  # noqa: E402


def write_memory(path: Path, values: list[int], width: int) -> None:
    digits = (width + 3) // 4
    mask = (1 << width) - 1
    with path.open("w", encoding="ascii") as handle:
        for value in values:
            handle.write(f"{value & mask:0{digits}x}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=int, default=1024)
    args = parser.parse_args()
    model = FixedChordV1CircuitModel()
    if len(model.capacitors) != 10:
        raise RuntimeError(f"frozen V1 expected 10 capacitor branches, got {len(model.capacitors)}")

    generated = REPOSITORY_ROOT / "model" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    matrix_path = generated / "v1_dynamic_matrix_q0_47.mem"
    fixed_rhs_path = generated / "v1_fixed_rhs_q4_44.mem"
    cap_g_path = generated / "v1_cap_conductance_q0_47.mem"
    cap_initial_path = generated / "v1_cap_initial_q12_20.mem"
    node_initial_path = generated / "v1_node_initial.mem"
    write_memory(matrix_path, [int(value) for value in model.matrix_q47.flat], 48)
    write_memory(fixed_rhs_path, [int(value) for value in model.fixed_rhs_q44], 48)
    write_memory(
        cap_g_path, [int(capacitor.conductance_q47) for capacitor in model.capacitors], 48
    )
    initial_capacitor_q20 = [
        int(capacitor.previous_voltage_q20) for capacitor in model.capacitors
    ]
    write_memory(
        cap_initial_path,
        initial_capacitor_q20,
        32,
    )
    write_memory(node_initial_path, [int(value) for value in model.voltage_q], 32)

    rng = np.random.default_rng(0x4B434C)
    vector_directory = REPOSITORY_ROOT / "sim" / "vectors" / "generated"
    vector_directory.mkdir(parents=True, exist_ok=True)
    rhs_vector_path = vector_directory / "network_rhs_random.txt"
    with rhs_vector_path.open("w", encoding="ascii") as handle:
        for index in range(args.vectors):
            input_q24 = int(rng.integers(-(1 << 25), 1 << 25))
            capacitor_q20 = [
                int(value)
                for value in rng.integers(-(1 << 29), 1 << 29, size=10, dtype=np.int64)
            ]
            if index == 0:
                input_q24 = 0
                capacitor_q20 = [
                    int(capacitor.previous_voltage_q20) for capacitor in model.capacitors
                ]
            for capacitor, state in zip(model.capacitors, capacitor_q20, strict=True):
                capacitor.previous_voltage_q20 = state
            rhs = model._rhs_q44(input_q24)
            fields = [input_q24, *capacitor_q20, *rhs]
            handle.write(" ".join(str(int(value)) for value in fields) + "\n")

    # KCL vectors include arbitrary RHS and tube currents, and exercise every
    # heterogeneous voltage format. They define matrix product rounding and the
    # final Q44-to-Q30 saturation sequence independently of the scheduler.
    kcl_vector_path = vector_directory / "network_kcl_random.txt"
    kcl_saturation_vectors = 0
    with kcl_vector_path.open("w", encoding="ascii") as handle:
        for index in range(args.vectors):
            voltage = rng.integers(-(1 << 29), 1 << 29, size=9, dtype=np.int64)
            current_q31 = rng.integers(-(1 << 21), 1 << 21, size=4, dtype=np.int64)
            if index == 0:
                voltage = model.voltage_q.copy()
            linear_sum = [0] * 9
            for row in range(9):
                for column in range(9):
                    linear_sum[row] += model._linear_product_current_q44(
                        int(model.matrix_q47[row, column]),
                        int(voltage[column]),
                        int(model.VOLTAGE_FRACTIONAL_BITS[column]),
                    )
            rhs = np.asarray(
                [
                    value + int(rng.integers(-(1 << 32), 1 << 32))
                    for value in linear_sum
                ],
                dtype=np.int64,
            )
            if index == 0:
                for capacitor, state in zip(
                    model.capacitors, initial_capacitor_q20, strict=True
                ):
                    capacitor.previous_voltage_q20 = state
                rhs = np.asarray(model._rhs_q44(0), dtype=np.int64)
                current_q31[:] = 0
            elif index < 19:
                # Preserve explicit Q30 residual saturation coverage without
                # making every randomized vector an overload vector.
                rhs[index % 9] = linear_sum[index % 9] + (
                    (1 << 43) if index % 2 else -(1 << 43)
                )
            residual = [-int(value) for value in rhs]
            for row in range(9):
                residual[row] += linear_sum[row]
            ip1, ig1, ip2, ig2 = map(int, current_q31)
            residual[1] += ip1 << 13
            residual[2] -= (ip1 + ig1) << 13
            residual[0] += ig1 << 13
            residual[6] += ip2 << 13
            residual[7] -= (ip2 + ig2) << 13
            residual[4] += ig2 << 13
            residual_q30: list[int] = []
            saturated = False
            saturation_count = 0
            for value in residual:
                converted = round_shift(value, 14)
                clipped = converted < -(1 << 24) or converted > (1 << 24) - 1
                saturated = saturated or clipped
                saturation_count += int(clipped)
                residual_q30.append(min(max(converted, -(1 << 24)), (1 << 24) - 1))
            kcl_saturation_vectors += int(saturated)
            max_abs_q44 = max(abs(value) for value in residual)
            fields = [
                *map(int, voltage),
                *map(int, rhs),
                *map(int, current_q31),
                *residual_q30,
                int(saturated),
                saturation_count,
                int(max_abs_q44),
            ]
            handle.write(" ".join(str(value) for value in fields) + "\n")

    metadata = {
        "model": "12ax7_passive_riaa_v1",
        "sample_rate_hz": int(model.sample_rate_hz),
        "nodes": list(model.reference.NODE_NAMES),
        "node_fractional_bits": [int(value) for value in model.VOLTAGE_FRACTIONAL_BITS],
        "capacitors": [
            {
                "index": index,
                "node_a": capacitor.node_a,
                "node_b": capacitor.node_b,
                "conductance_q0_47": int(capacitor.conductance_q47),
                "initial_voltage_q12_20": initial_capacitor_q20[index],
            }
            for index, capacitor in enumerate(model.capacitors)
        ],
        "input_conductance_q0_47": model.input_conductance_q47,
        "rhs_vectors": args.vectors,
        "kcl_vectors": args.vectors,
        "kcl_saturation_vectors": kcl_saturation_vectors,
        "rhs_latency_clocks": 12,
        "kcl_latency_clocks": 10,
        "outputs": [
            str(path.relative_to(REPOSITORY_ROOT))
            for path in (
                matrix_path,
                fixed_rhs_path,
                cap_g_path,
                cap_initial_path,
                node_initial_path,
                rhs_vector_path,
                kcl_vector_path,
            )
        ],
    }
    metadata_path = generated / "v1_network_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
