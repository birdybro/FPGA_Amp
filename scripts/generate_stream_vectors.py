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
from fpga_amp.stream import compose_fixed_wide_stream  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=int, default=64)
    parser.add_argument("--factorized", action="store_true")
    parser.add_argument("--wide", action="store_true")
    parser.add_argument("--trapezoidal", action="store_true")
    parser.add_argument("--banked", action="store_true")
    parser.add_argument("--terminal-correction", action="store_true")
    args = parser.parse_args()
    if args.terminal_correction and not args.banked:
        parser.error("terminal correction requires --banked")
    if args.trapezoidal:
        args.wide = True
    if (args.banked or args.terminal_correction) and not args.wide:
        parser.error("banked and terminal modes require --wide")
    if args.wide:
        args.factorized = True
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

    if args.wide:
        composed = compose_fixed_wide_stream(
            input_q24,
            trapezoidal=args.trapezoidal,
            banked=args.banked,
            terminal_correction=args.terminal_correction,
        )
        internal_q24 = composed.internal_input_q24
        model = composed.circuit
        output_q24 = composed.output_q24
        interpolation_saturations = composed.interpolation_saturation_count
        conversion_saturations = composed.output_conversion_saturation_count
        decimation_saturations = composed.decimation_saturation_count
    else:
        interpolated_q24, interpolation_saturations = interpolate_16x_fixed_q24(
            input_q24
        )
        # The scheduled RTL cascade has 18 visible internal-sample pipeline states.
        internal_q24 = np.concatenate(
            (np.zeros(18, dtype=np.int64), interpolated_q24)
        )[: 16 * args.vectors]
        tube = FixedFactorizedKoren12AX7() if args.factorized else None
        model = FixedChordV1CircuitModel(tube_lut=tube)
        circuit_output_q24: list[int] = []
        conversion_saturations = 0
        for sample_q24 in internal_q24:
            model.process_sample(int(sample_q24) / float(1 << 24))
            converted = int(model.voltage_q[8]) << 4
            converted_q24, clipped = saturate_signed(converted, 32)
            circuit_output_q24.append(converted_q24)
            conversion_saturations += int(clipped)
        output_q24, decimation_saturations = decimate_16x_fixed_q24(
            np.asarray(circuit_output_q24, dtype=np.int64)
        )
        output_q24 = output_q24[: args.vectors]

    vector_directory = REPOSITORY_ROOT / "sim" / "vectors" / "generated"
    vector_directory.mkdir(parents=True, exist_ok=True)
    if args.trapezoidal and args.banked and args.terminal_correction:
        vector_name = "phono_stream_mono_wide_factorized_trapezoidal_banked_terminal.txt"
    elif args.trapezoidal and args.banked:
        vector_name = "phono_stream_mono_wide_factorized_trapezoidal_banked.txt"
    elif args.trapezoidal:
        vector_name = "phono_stream_mono_wide_factorized_trapezoidal.txt"
    elif args.banked and args.terminal_correction:
        vector_name = "phono_stream_mono_wide_factorized_banked_terminal.txt"
    elif args.banked:
        vector_name = "phono_stream_mono_wide_factorized_banked.txt"
    elif args.wide:
        vector_name = "phono_stream_mono_wide_factorized.txt"
    elif args.factorized:
        vector_name = "phono_stream_mono_factorized.txt"
    else:
        vector_name = "phono_stream_mono.txt"
    vector_path = vector_directory / vector_name
    with vector_path.open("w", encoding="ascii") as handle:
        for value in input_q24:
            handle.write(f"{int(value)}\n")
        handle.write("EXPECTED\n")
        for value in output_q24:
            handle.write(f"{int(value)}\n")

    metadata = {
        "model": "12ax7_passive_riaa_v1",
        "tube_implementation": "factorized" if args.factorized else "surface",
        "state_implementation": "wide_branch_current" if args.wide else "legacy_companion_rhs",
        "integration_method": (
            "trapezoidal" if args.trapezoidal else "backward_euler"
        ),
        "banked_chord": args.banked,
        "terminal_correction": args.terminal_correction,
        "residual_diagnostic_state": (
            "preterminal_correction"
            if args.terminal_correction
            else "committed_output_state"
        ),
        "solver_latency_clocks": (
            127 if args.terminal_correction else (116 if args.wide else 126)
        ),
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
        "solver_correction_scale_fallbacks": model.correction_scale_fallback_count,
        "maximum_solver_residual_q44": model.max_residual_q44_observed,
        "output": str(vector_path.relative_to(REPOSITORY_ROOT)),
    }
    if args.trapezoidal and args.banked and args.terminal_correction:
        metadata_name = "phono_stream_wide_factorized_trapezoidal_banked_terminal_metadata.json"
    elif args.trapezoidal and args.banked:
        metadata_name = "phono_stream_wide_factorized_trapezoidal_banked_metadata.json"
    elif args.trapezoidal:
        metadata_name = "phono_stream_wide_factorized_trapezoidal_metadata.json"
    elif args.banked and args.terminal_correction:
        metadata_name = "phono_stream_wide_factorized_banked_terminal_metadata.json"
    elif args.banked:
        metadata_name = "phono_stream_wide_factorized_banked_metadata.json"
    elif args.wide:
        metadata_name = "phono_stream_wide_factorized_metadata.json"
    elif args.factorized:
        metadata_name = "phono_stream_factorized_metadata.json"
    else:
        metadata_name = "phono_stream_metadata.json"
    metadata_path = REPOSITORY_ROOT / "model" / "generated" / metadata_name
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
