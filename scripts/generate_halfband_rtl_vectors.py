#!/usr/bin/env python3
"""Generate Q1.23 half-band memories and exact 2x RTL stream vectors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.resampling import (  # noqa: E402
    DEFAULT_STAGES,
    decimate_2x_fixed_q24,
    interpolate_2x_fixed_q24,
    quantized_coefficients_q23,
)


def write_memory(path: Path, values: np.ndarray) -> None:
    with path.open("w", encoding="ascii") as handle:
        for value in values:
            handle.write(f"{int(value) & 0xFFFFFF:06x}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=int, default=256)
    args = parser.parse_args()
    generated = REPOSITORY_ROOT / "model" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    memories: list[str] = []
    for index, stage in enumerate(DEFAULT_STAGES, start=1):
        path = generated / f"halfband_stage{index}_q1_23.mem"
        write_memory(path, quantized_coefficients_q23(stage))
        memories.append(str(path.relative_to(REPOSITORY_ROOT)))

    rng = np.random.default_rng(0x48_768)
    index = np.arange(args.vectors, dtype=np.float64)
    input_values = (
        0.25 * np.sin(2.0 * np.pi * 0.03125 * index)
        + 0.125 * np.sin(2.0 * np.pi * 0.171875 * index)
        + rng.normal(0.0, 0.01, args.vectors)
    )
    input_values[0] += 0.5
    input_q24 = np.rint(input_values * (1 << 24)).astype(np.int64)
    stage1_q23 = quantized_coefficients_q23(DEFAULT_STAGES[0])
    interpolated_q24, interpolation_saturations = interpolate_2x_fixed_q24(
        input_q24, stage1_q23
    )

    vector_directory = REPOSITORY_ROOT / "sim" / "vectors" / "generated"
    vector_directory.mkdir(parents=True, exist_ok=True)
    interpolation_path = vector_directory / "halfband_interpolator_stage1.txt"
    with interpolation_path.open("w", encoding="ascii") as handle:
        for sample, even, odd in zip(
            input_q24,
            interpolated_q24[0 : 2 * args.vectors : 2],
            interpolated_q24[1 : 2 * args.vectors : 2],
            strict=True,
        ):
            handle.write(f"{int(sample)} {int(even)} {int(odd)}\n")

    high_index = np.arange(2 * args.vectors, dtype=np.float64)
    high_values = (
        0.35 * np.sin(2.0 * np.pi * 0.1171875 * high_index)
        + 0.08 * np.sin(2.0 * np.pi * 0.4140625 * high_index)
        + rng.normal(0.0, 0.01, high_index.size)
    )
    high_values[0] += 0.4
    high_q24 = np.rint(high_values * (1 << 24)).astype(np.int64)
    decimated_q24, decimation_saturations = decimate_2x_fixed_q24(
        high_q24, stage1_q23
    )
    decimation_path = vector_directory / "halfband_decimator_stage1.txt"
    with decimation_path.open("w", encoding="ascii") as handle:
        for pair_index in range(args.vectors):
            handle.write(
                f"{int(high_q24[2 * pair_index])} "
                f"{int(high_q24[2 * pair_index + 1])} "
                f"{int(decimated_q24[pair_index])}\n"
            )

    metadata = {
        "format": {"sample": "signed Q8.24", "coefficient": "signed Q1.23"},
        "stage_under_test": 1,
        "taps": DEFAULT_STAGES[0].taps,
        "nonzero_taps": DEFAULT_STAGES[0].nonzero_taps,
        "vectors": args.vectors,
        "seed": 0x48_768,
        "interpolation_saturations": interpolation_saturations,
        "decimation_saturations": decimation_saturations,
        "interpolator_pair_delay": 1,
        "outputs": [
            *memories,
            str(interpolation_path.relative_to(REPOSITORY_ROOT)),
            str(decimation_path.relative_to(REPOSITORY_ROOT)),
        ],
    }

    chain_vectors = min(args.vectors, 128)
    chain_input_q24 = input_q24[:chain_vectors]
    chain_interpolated = chain_input_q24
    chain_interpolation_saturations = 0
    for stage in DEFAULT_STAGES:
        chain_interpolated, count = interpolate_2x_fixed_q24(
            chain_interpolated, quantized_coefficients_q23(stage)
        )
        chain_interpolation_saturations += count
    chain_pipeline_delay = 18
    chain_interpolation_expected = np.concatenate(
        (np.zeros(chain_pipeline_delay, dtype=np.int64), chain_interpolated)
    )[: 16 * chain_vectors]
    chain_interpolation_path = vector_directory / "interpolator_16x_stream.txt"
    with chain_interpolation_path.open("w", encoding="ascii") as handle:
        for value in chain_input_q24:
            handle.write(f"{int(value)}\n")
        handle.write("EXPECTED\n")
        for value in chain_interpolation_expected:
            handle.write(f"{int(value)}\n")

    chain_high_index = np.arange(16 * chain_vectors, dtype=np.float64)
    chain_high_values = (
        0.35 * np.sin(2.0 * np.pi * 0.00732421875 * chain_high_index)
        + 0.08 * np.sin(2.0 * np.pi * 0.2138671875 * chain_high_index)
        + rng.normal(0.0, 0.01, chain_high_index.size)
    )
    chain_high_values[0] += 0.4
    chain_high_q24 = np.rint(chain_high_values * (1 << 24)).astype(np.int64)
    chain_decimated = chain_high_q24
    chain_decimation_saturations = 0
    for stage in reversed(DEFAULT_STAGES):
        chain_decimated, count = decimate_2x_fixed_q24(
            chain_decimated, quantized_coefficients_q23(stage)
        )
        chain_decimation_saturations += count
    chain_decimation_path = vector_directory / "decimator_16x_stream.txt"
    with chain_decimation_path.open("w", encoding="ascii") as handle:
        for value in chain_high_q24:
            handle.write(f"{int(value)}\n")
        handle.write("EXPECTED\n")
        for value in chain_decimated[:chain_vectors]:
            handle.write(f"{int(value)}\n")

    metadata.update(
        {
            "chain_input_vectors": chain_vectors,
            "chain_interpolation_output_vectors": 16 * chain_vectors,
            "chain_pipeline_delay_internal_samples": chain_pipeline_delay,
            "chain_interpolation_saturations": chain_interpolation_saturations,
            "chain_decimation_saturations": chain_decimation_saturations,
        }
    )
    metadata["outputs"].extend(
        (
            str(chain_interpolation_path.relative_to(REPOSITORY_ROOT)),
            str(chain_decimation_path.relative_to(REPOSITORY_ROOT)),
        )
    )
    metadata_path = generated / "halfband_rtl_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
