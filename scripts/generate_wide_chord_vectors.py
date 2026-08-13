#!/usr/bin/env python3
"""Generate exact Q28/Q32 40-bit chord-correction RTL vectors."""

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
    FixedWideStateBankedChordV1CircuitModel,
    FixedWideStateTrapezoidalV1CircuitModel,
    FixedWideStateV1CircuitModel,
    round_shift,
    saturate_signed,
)
from generate_solver_vectors import write_memory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trapezoidal", action="store_true")
    parser.add_argument("--banked", action="store_true")
    args = parser.parse_args()
    vectors = 1024
    rng = np.random.default_rng(0x40C0DE)
    if args.banked:
        model = FixedWideStateBankedChordV1CircuitModel(
            tube_lut=FixedFactorizedKoren12AX7(),
            integration_method=(
                "trapezoidal" if args.trapezoidal else "backward_euler"
            ),
        )
    else:
        model_type = (
            FixedWideStateTrapezoidalV1CircuitModel
            if args.trapezoidal
            else FixedWideStateV1CircuitModel
        )
        model = model_type(tube_lut=FixedFactorizedKoren12AX7())
    suffix = "_trapezoidal" if args.trapezoidal else ""
    path = (
        REPOSITORY_ROOT
        / "sim"
        / "vectors"
        / "generated"
        / f"wide_chord{suffix}.txt"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    coefficient_path = (
        REPOSITORY_ROOT
        / "model"
        / "generated"
        / (
            f"v1_chord_inverse_banked_q17_1{suffix}.mem"
            if args.banked
            else f"v1_chord_inverse_q17_1{suffix}.mem"
        )
    )
    if args.banked:
        coefficient_sets = [
            *model.chord_inverse_banks_q,
            model.nominal_chord_inverse_q,
        ]
        coefficients = [
            int(value) for bank in coefficient_sets for value in bank.flat
        ]
    else:
        coefficient_sets = [model.chord_inverse_q]
        coefficients = [int(value) for value in model.chord_inverse_q.flat]
    if not all(-(1 << 17) <= value < (1 << 17) for value in coefficients):
        raise RuntimeError("chord inverse exceeds signed 18-bit contract")
    write_memory(coefficient_path, coefficients, 18)
    if args.banked:
        report = {
            "algorithm": "Vgk2-selected bank of 9x9 Q17.1 chord inverses",
            "integration_method": (
                "trapezoidal" if args.trapezoidal else "backward_euler"
            ),
            "coefficient_sets": len(coefficient_sets),
            "coefficients_per_set": 81,
            "coefficient_min": min(coefficients),
            "coefficient_max": max(coefficients),
            "cutoff_regimes": [
                {
                    "upper_v_gk_v": upper,
                    "representative_v_gk_v": v_gk,
                    "representative_v_pk_v": v_pk,
                }
                for upper, v_gk, v_pk in model.cutoff_jacobian_regimes
            ],
            "slew_qualified_shallow_selector": {
                "upper_v_gk_v": model.SHALLOW_SLEW_UPPER_V_GK_V,
                "minimum_absolute_delta_v_gk_v_per_sample": (
                    model.SHALLOW_SLEW_THRESHOLD_V_PER_SAMPLE
                ),
                "set_index": len(model.chord_inverse_banks_q) - 1,
                "representative_v_gk_vpk_v": (
                    list(model.BACKWARD_EULER_SLEW_JACOBIAN_REPRESENTATIVE)
                    if not args.trapezoidal
                    else [
                        model.cutoff_jacobian_regimes[-1][1],
                        model.cutoff_jacobian_regimes[-1][2],
                    ]
                ),
                "reuses_existing_cutoff_set": args.trapezoidal,
            },
            "nominal_set_index": len(coefficient_sets) - 1,
            "output": str(coefficient_path.relative_to(REPOSITORY_ROOT)),
        }
        metadata = (
            REPOSITORY_ROOT
            / "model"
            / "generated"
            / f"wide_chord_banked{suffix}_metadata.json"
        )
        metadata.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    saturation_vectors = 0
    fractions = (30, 34, 40)
    with path.open("w", encoding="ascii") as handle:
        for index in range(vectors):
            fraction = fractions[index % len(fractions)]
            voltage = [
                int(rng.integers(-(1 << 38), 1 << 38)) for _ in range(9)
            ]
            residual = [
                int(rng.integers(-(1 << 21), 1 << 21)) for _ in range(9)
            ]
            if index < 18:
                voltage[index % 9] = (1 << 39) - 1 if index < 9 else -(1 << 39)
                residual = [0] * 9
                residual[index % 9] = -(1 << 24) if index < 9 else (1 << 24) - 1
                fraction = 30
            corrected: list[int] = []
            saturation_count = 0
            for row in range(9):
                accumulator = sum(
                    int(model.chord_inverse_q[row, column]) * residual[column]
                    for column in range(9)
                )
                correction = round_shift(
                    accumulator,
                    model.inverse_fractional_bits
                    + fraction
                    - int(model.VOLTAGE_FRACTIONAL_BITS[row]),
                )
                value, clipped = saturate_signed(voltage[row] - correction, 40)
                corrected.append(value)
                saturation_count += int(clipped)
            saturation_vectors += int(saturation_count != 0)
            fields = [fraction, *voltage, *residual, *corrected, saturation_count]
            handle.write(" ".join(str(value) for value in fields) + "\n")
    report = {
        "algorithm": "9x9 Q17.1 inverse by adaptive signed 25-bit residual",
        "integration_method": (
            "trapezoidal" if args.trapezoidal else "backward_euler"
        ),
        "vectors": vectors,
        "seed": 0x40C0DE,
        "node_fractional_bits": model.VOLTAGE_FRACTIONAL_BITS.tolist(),
        "node_width_bits": 40,
        "residual_fractional_bits": list(fractions),
        "saturation_vectors": saturation_vectors,
        "latency_clocks": 10,
        "outputs": [
            str(item.relative_to(REPOSITORY_ROOT))
            for item in (coefficient_path, path)
        ],
    }
    metadata = (
        REPOSITORY_ROOT
        / "model"
        / "generated"
        / f"wide_chord{suffix}_metadata.json"
    )
    metadata.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
