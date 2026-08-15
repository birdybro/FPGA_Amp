#!/usr/bin/env python3
"""Generate bit-exact vectors across PCM calibration and the V1 mono stream."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.calibration import pcm24_to_q8_24, q8_24_to_pcm24  # noqa: E402
from fpga_amp.stream import compose_fixed_wide_stream  # noqa: E402


INPUT_FULL_SCALE_PEAK_VOLTS_Q24 = round(0.020 * (1 << 24))
# Eight-volt model-output peak at PCM full scale leaves deliberate bring-up
# headroom. It is a test calibration, not a selected DAC or line-output level.
OUTPUT_RECIPROCAL_FULL_SCALE_Q24 = round((1.0 / 8.0) * (1 << 24))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=int, default=64)
    parser.add_argument(
        "--sample-rate-hz", type=int, choices=(384_000, 768_000), default=768_000
    )
    args = parser.parse_args()
    if not 1 <= args.vectors <= 512:
        parser.error("--vectors must be within 1..512")

    rng = np.random.default_rng(0xFABC_0024)
    index = np.arange(args.vectors, dtype=np.float64)
    normalized = (
        0.2 * np.sin(2.0 * np.pi * 1_000.0 * index / 48_000.0)
        + 0.075 * np.sin(2.0 * np.pi * 11_000.0 * index / 48_000.0)
        + rng.normal(0.0, 0.0025, args.vectors)
    )
    normalized[0] += 0.5
    if args.vectors > 32:
        normalized[32] -= 0.5
    if np.max(np.abs(normalized)) >= 1.0:
        raise RuntimeError("test stimulus exceeded the PCM24 input boundary")
    left_pcm24 = np.rint(normalized * (1 << 23)).astype(np.int64)

    # The right channel is intentionally unrelated. Exact output equivalence
    # therefore proves that this explicitly mono adapter selects only left.
    right_pcm24 = np.asarray(
        [((0x13579B * value + 0x2468A) & 0xFFFFFF) - (1 << 23)
         for value in range(args.vectors)],
        dtype=np.int64,
    )

    model_input_q24 = np.asarray(
        [
            pcm24_to_q8_24(
                int(sample), INPUT_FULL_SCALE_PEAK_VOLTS_Q24
            ).sample_q24
            for sample in left_pcm24
        ],
        dtype=np.int64,
    )
    composed = compose_fixed_wide_stream(
        model_input_q24,
        trapezoidal=True,
        banked=True,
        terminal_correction=True,
        internal_sample_rate_hz=args.sample_rate_hz,
    )
    output_results = [
        q8_24_to_pcm24(
            int(sample), OUTPUT_RECIPROCAL_FULL_SCALE_Q24
        )
        for sample in composed.output_q24
    ]
    output_pcm24 = np.asarray(
        [result.sample_pcm24 for result in output_results], dtype=np.int64
    )
    output_saturations = sum(result.saturated for result in output_results)
    output_configuration_errors = sum(
        result.configuration_error for result in output_results
    )
    if any(composed.diagnostic_counts.values()):
        raise RuntimeError(
            f"unexpected core diagnostic: {composed.diagnostic_counts}"
        )
    if output_saturations or output_configuration_errors:
        raise RuntimeError("test output calibration was not diagnostic-clean")

    directory = REPOSITORY_ROOT / "sim" / "vectors" / "generated"
    directory.mkdir(parents=True, exist_ok=True)
    rate_suffix = "_384khz" if args.sample_rate_hz == 384_000 else ""
    vector_path = directory / f"phono_fabric_mono_adapter{rate_suffix}.txt"
    with vector_path.open("w", encoding="ascii") as handle:
        for left, right, physical in zip(
            left_pcm24, right_pcm24, model_input_q24, strict=True
        ):
            handle.write(f"{int(left)} {int(right)} {int(physical)}\n")
        handle.write("EXPECTED\n")
        for pcm, physical in zip(
            output_pcm24, composed.output_q24, strict=True
        ):
            handle.write(f"{int(pcm)} {int(physical)}\n")

    # Preserve the exact core-boundary companion vector so failures can be
    # localized between scheduling/calibration and the nonlinear stream.
    core_vector_path = (
        directory / f"phono_fabric_mono_adapter_core{rate_suffix}.txt"
    )
    with core_vector_path.open("w", encoding="ascii") as handle:
        for sample in model_input_q24:
            handle.write(f"{int(sample)}\n")
        handle.write("EXPECTED\n")
        for sample in composed.output_q24:
            handle.write(f"{int(sample)}\n")

    metadata = {
        "model": "12ax7_passive_riaa_v1",
        "mode": "mono_left_input_duplicated_output",
        "integration_method": "trapezoidal",
        "banked_chord": True,
        "terminal_correction": True,
        "internal_sample_rate_hz": args.sample_rate_hz,
        "vectors": args.vectors,
        "input_full_scale_peak_volts_q24": INPUT_FULL_SCALE_PEAK_VOLTS_Q24,
        "input_full_scale_peak_volts": (
            INPUT_FULL_SCALE_PEAK_VOLTS_Q24 / float(1 << 24)
        ),
        "output_reciprocal_full_scale_q24": (
            OUTPUT_RECIPROCAL_FULL_SCALE_Q24
        ),
        "output_model_peak_volts_at_pcm_full_scale": 8.0,
        "maximum_abs_input_q24": int(np.max(np.abs(model_input_q24))),
        "maximum_abs_output_q24": int(np.max(np.abs(composed.output_q24))),
        "maximum_abs_output_pcm24": int(np.max(np.abs(output_pcm24))),
        "output_calibration_saturations": output_saturations,
        "core_diagnostics": composed.diagnostic_counts,
        "solver_latency_clocks": 127,
        "outputs": [
            str(vector_path.relative_to(REPOSITORY_ROOT)),
            str(core_vector_path.relative_to(REPOSITORY_ROOT)),
        ],
    }
    metadata_path = (
        REPOSITORY_ROOT
        / "model"
        / "generated"
        / f"phono_fabric_mono_adapter{rate_suffix}_metadata.json"
    )
    metadata_path.write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
