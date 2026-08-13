#!/usr/bin/env python3
"""Generate V1 chord inverse ROM and bit-exact correction vectors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.fixed_circuit import round_shift, saturate_signed  # noqa: E402
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


NODE_FRACTIONAL_BITS = (24, 20, 24, 20, 24, 24, 20, 24, 20)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=int, default=1024)
    args = parser.parse_args()
    model = V1CircuitModel()
    coefficient = np.rint(model.chord_inverse * 2.0).astype(np.int64)
    if np.max(np.abs(coefficient)) >= (1 << 17):
        raise RuntimeError("Q17.1 coefficient does not fit signed 18 bits")

    generated = REPOSITORY_ROOT / "model" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    memory_path = generated / "v1_chord_inverse_q17_1.mem"
    with memory_path.open("w", encoding="ascii") as handle:
        for value in coefficient.flat:
            handle.write(f"{int(value) & 0x3ffff:05x}\n")

    rng = np.random.default_rng(0xC04D)
    vector_directory = REPOSITORY_ROOT / "sim" / "vectors" / "generated"
    vector_directory.mkdir(parents=True, exist_ok=True)
    vector_path = vector_directory / "chord_corrector_random.txt"
    saturation_vectors = 0
    with vector_path.open("w", encoding="ascii") as handle:
        for index in range(args.vectors):
            voltage = rng.integers(-(1 << 30), 1 << 30, size=9, dtype=np.int64)
            residual = rng.integers(-(1 << 22), 1 << 22, size=9, dtype=np.int64)
            if index < 18:
                # Force positive/negative output saturation for each row while
                # retaining arbitrary cross-coupled residuals.
                row = index // 2
                voltage[row] = (1 << 31) - 32 if index % 2 == 0 else -(1 << 31) + 32
                residual[row] = -(1 << 23) if index % 2 == 0 else (1 << 23) - 1
            expected: list[int] = []
            saturation = False
            saturation_count = 0
            for row, fractional_bits in enumerate(NODE_FRACTIONAL_BITS):
                accumulator = sum(
                    int(coefficient[row, column]) * int(residual[column])
                    for column in range(9)
                )
                correction = round_shift(accumulator, 31 - fractional_bits)
                result, clipped = saturate_signed(int(voltage[row]) - correction, 32)
                expected.append(result)
                saturation = saturation or clipped
                saturation_count += int(clipped)
            saturation_vectors += int(saturation)
            fields = [
                *map(int, voltage),
                *map(int, residual),
                *expected,
                int(saturation),
                saturation_count,
            ]
            handle.write(" ".join(str(value) for value in fields) + "\n")

    report = {
        "algorithm": "9x9 Q17.1 inverse by signed 25-bit Q30 residual",
        "vectors": args.vectors,
        "seed": 0xC04D,
        "coefficient_min": int(np.min(coefficient)),
        "coefficient_max": int(np.max(coefficient)),
        "saturation_vectors": saturation_vectors,
        "latency_clocks": 10,
        "outputs": [
            str(memory_path.relative_to(REPOSITORY_ROOT)),
            str(vector_path.relative_to(REPOSITORY_ROOT)),
        ],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
