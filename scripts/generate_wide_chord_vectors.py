#!/usr/bin/env python3
"""Generate exact Q28/Q32 40-bit chord-correction RTL vectors."""

from __future__ import annotations

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


def main() -> int:
    vectors = 1024
    rng = np.random.default_rng(0x40C0DE)
    model = FixedWideStateV1CircuitModel(tube_lut=FixedFactorizedKoren12AX7())
    path = REPOSITORY_ROOT / "sim" / "vectors" / "generated" / "wide_chord.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
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
        "vectors": vectors,
        "seed": 0x40C0DE,
        "node_fractional_bits": model.VOLTAGE_FRACTIONAL_BITS.tolist(),
        "node_width_bits": 40,
        "residual_fractional_bits": list(fractions),
        "saturation_vectors": saturation_vectors,
        "latency_clocks": 10,
        "output": str(path.relative_to(REPOSITORY_ROOT)),
    }
    metadata = REPOSITORY_ROOT / "model" / "generated" / "wide_chord_metadata.json"
    metadata.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
