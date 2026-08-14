#!/usr/bin/env python3
"""Generate deterministic bit-exact PCM24/Q8.24 calibration vectors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.calibration import (  # noqa: E402
    PCM24_MAX,
    PCM24_MIN,
    pcm24_to_q8_24,
    q8_24_to_pcm24,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--random-vectors", type=int, default=4096)
    args = parser.parse_args()
    if args.random_vectors < 1:
        parser.error("--random-vectors must be positive")

    rng = np.random.default_rng(0xCA1_1B24)
    directory = REPOSITORY_ROOT / "sim" / "vectors" / "generated"
    directory.mkdir(parents=True, exist_ok=True)

    input_cases: list[tuple[int, int]] = []
    input_samples = [
        PCM24_MIN,
        PCM24_MAX,
        0,
        -1,
        1,
        -(1 << 22),
        1 << 22,
        -654321,
        123456,
    ]
    input_coefficients = [
        -(1 << 31),
        -1,
        0,
        1,
        round(0.020 * (1 << 24)),
        1 << 24,
        (1 << 31) - 1,
    ]
    input_cases.extend(
        (sample, coefficient)
        for coefficient in input_coefficients
        for sample in input_samples
    )
    for index in range(args.random_vectors):
        sample = int(rng.integers(PCM24_MIN, PCM24_MAX + 1, dtype=np.int64))
        coefficient = int(rng.integers(1, 1 << 31, dtype=np.int64))
        if index % 509 == 0:
            coefficient = -coefficient
        elif index % 257 == 0:
            coefficient = 0
        input_cases.append((sample, coefficient))

    input_path = directory / "pcm24_to_q8_24.txt"
    input_endpoints = 0
    input_configuration_errors = 0
    with input_path.open("w", encoding="ascii") as handle:
        handle.write("# pcm24 full_scale_peak_volts_q24 expected_q24 endpoint invalid\n")
        for sample, coefficient in input_cases:
            result = pcm24_to_q8_24(sample, coefficient)
            input_endpoints += int(result.pcm_endpoint)
            input_configuration_errors += int(result.configuration_error)
            handle.write(
                f"{sample} {coefficient} {result.sample_q24} "
                f"{int(result.pcm_endpoint)} {int(result.configuration_error)}\n"
            )

    output_cases: list[tuple[int, int]] = []
    output_samples = [
        -(1 << 31),
        (1 << 31) - 1,
        -(2 << 24),
        2 << 24,
        -(1 << 24),
        1 << 24,
        -1,
        0,
        1,
    ]
    output_coefficients = [
        -(1 << 31),
        -1,
        0,
        1,
        1 << 23,
        1 << 24,
        (1 << 31) - 1,
    ]
    output_cases.extend(
        (sample, coefficient)
        for coefficient in output_coefficients
        for sample in output_samples
    )
    for index in range(args.random_vectors):
        sample = int(rng.integers(-(1 << 31), 1 << 31, dtype=np.int64))
        coefficient = int(rng.integers(1, 1 << 31, dtype=np.int64))
        if index % 503 == 0:
            coefficient = -coefficient
        elif index % 251 == 0:
            coefficient = 0
        output_cases.append((sample, coefficient))

    output_path = directory / "q8_24_to_pcm24.txt"
    output_saturations = 0
    output_configuration_errors = 0
    with output_path.open("w", encoding="ascii") as handle:
        handle.write("# q24 reciprocal_full_scale_q24 expected_pcm24 saturated invalid\n")
        for sample, coefficient in output_cases:
            result = q8_24_to_pcm24(sample, coefficient)
            output_saturations += int(result.saturated)
            output_configuration_errors += int(result.configuration_error)
            handle.write(
                f"{sample} {coefficient} {result.sample_pcm24} "
                f"{int(result.saturated)} {int(result.configuration_error)}\n"
            )

    metadata = {
        "algorithm": "full-width multiply, symmetric nearest rounding, explicit saturation",
        "seed": 0xCA1_1B24,
        "random_vectors_per_direction": args.random_vectors,
        "input_vectors": len(input_cases),
        "input_pcm_endpoint_events": input_endpoints,
        "input_configuration_error_events": input_configuration_errors,
        "output_vectors": len(output_cases),
        "output_saturation_events": output_saturations,
        "output_configuration_error_events": output_configuration_errors,
        "latency_clocks": 1,
        "outputs": [
            str(input_path.relative_to(REPOSITORY_ROOT)),
            str(output_path.relative_to(REPOSITORY_ROOT)),
        ],
    }
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
