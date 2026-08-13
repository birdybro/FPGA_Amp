#!/usr/bin/env python3
"""Generate a bit-exact 48 kHz V1 phono-stream integration regression."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.fixed_circuit import FixedChordV1CircuitModel, saturate_signed  # noqa: E402
from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.resampling import (  # noqa: E402
    decimate_16x_fixed_q24,
    interpolate_16x_fixed_q24,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=int, default=64)
    parser.add_argument("--factorized", action="store_true")
    args = parser.parse_args()
    rng = np.random.default_rng(0xA0D10)
    index = np.arange(args.vectors, dtype=np.float64)
    input_v = (
        0.004 * np.sin(2.0 * np.pi * 1_000.0 * index / 48_000.0)
        + 0.0015 * np.sin(2.0 * np.pi * 11_000.0 * index / 48_000.0)
        + rng.normal(0.0, 50.0e-6, args.vectors)
    )
    input_v[0] += 0.010
    input_v[32] -= 0.010
    input_q24 = np.rint(input_v * (1 << 24)).astype(np.int64)

    interpolated_q24, interpolation_saturations = interpolate_16x_fixed_q24(
        input_q24
    )
    # The scheduled RTL cascade has 18 visible internal-sample pipeline states.
    internal_q24 = np.concatenate((np.zeros(18, dtype=np.int64), interpolated_q24))[
        : 16 * args.vectors
    ]
    tube = FixedFactorizedKoren12AX7() if args.factorized else None
    model = FixedChordV1CircuitModel(tube_lut=tube)
    circuit_output_q24: list[int] = []
    conversion_saturations = 0
    for sample_q24 in internal_q24:
        model.process_sample(int(sample_q24) / float(1 << 24))
        output_q24, clipped = saturate_signed(int(model.voltage_q[8]) << 4, 32)
        circuit_output_q24.append(output_q24)
        conversion_saturations += int(clipped)
    output_q24, decimation_saturations = decimate_16x_fixed_q24(
        np.asarray(circuit_output_q24, dtype=np.int64)
    )
    output_q24 = output_q24[: args.vectors]

    vector_directory = REPOSITORY_ROOT / "sim" / "vectors" / "generated"
    vector_directory.mkdir(parents=True, exist_ok=True)
    vector_path = vector_directory / (
        "phono_stream_mono_factorized.txt"
        if args.factorized
        else "phono_stream_mono.txt"
    )
    with vector_path.open("w", encoding="ascii") as handle:
        for value in input_q24:
            handle.write(f"{int(value)}\n")
        handle.write("EXPECTED\n")
        for value in output_q24:
            handle.write(f"{int(value)}\n")

    metadata = {
        "model": "12ax7_passive_riaa_v1",
        "tube_implementation": "factorized" if args.factorized else "surface",
        "input_rate_hz": 48_000,
        "circuit_rate_hz": 768_000,
        "vectors": args.vectors,
        "internal_samples": int(internal_q24.size),
        "interpolator_pipeline_delay_internal_samples": 18,
        "interpolation_saturations": interpolation_saturations,
        "output_conversion_saturations": conversion_saturations,
        "decimation_saturations": decimation_saturations,
        "solver_saturations": model.saturation_count,
        "solver_lut_clips": model.lut_clip_count,
        "solver_nonconvergence": model.nonconvergence_count,
        "maximum_solver_residual_q44": model.max_residual_q44_observed,
        "output": str(vector_path.relative_to(REPOSITORY_ROOT)),
    }
    metadata_path = REPOSITORY_ROOT / "model" / "generated" / (
        "phono_stream_factorized_metadata.json"
        if args.factorized
        else "phono_stream_metadata.json"
    )
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
