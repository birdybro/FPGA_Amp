#!/usr/bin/env python3
"""Generate sequential bit-exact vectors for the wide factorized V1 solver."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.factorized_tube import (  # noqa: E402
    FixedFactorizedKoren12AX7,
    FixedLinearFactorizedKoren12AX7,
)
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedWideStateBankedChordV1CircuitModel,
    FixedWideStateTrapezoidalV1CircuitModel,
    FixedWideStateV1CircuitModel,
)
from generate_solver_vectors import stimulus_q24, write_memory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=int, default=512)
    parser.add_argument("--trapezoidal", action="store_true")
    parser.add_argument("--banked", action="store_true")
    parser.add_argument("--terminal-correction", action="store_true")
    parser.add_argument("--linear-tube", action="store_true")
    parser.add_argument(
        "--sample-rate-hz", type=int, choices=(384_000, 768_000), default=768_000
    )
    args = parser.parse_args()
    tube = (
        FixedLinearFactorizedKoren12AX7()
        if args.linear_tube
        else FixedFactorizedKoren12AX7()
    )
    if args.banked:
        model = FixedWideStateBankedChordV1CircuitModel(
            sample_rate_hz=args.sample_rate_hz,
            tube_lut=tube,
            integration_method=(
                "trapezoidal" if args.trapezoidal else "backward_euler"
            ),
            terminal_correction=args.terminal_correction,
        )
    else:
        model_type = (
            FixedWideStateTrapezoidalV1CircuitModel
            if args.trapezoidal
            else FixedWideStateV1CircuitModel
        )
        model = model_type(
            sample_rate_hz=args.sample_rate_hz,
            tube_lut=tube,
            terminal_correction=args.terminal_correction,
        )
    generated = REPOSITORY_ROOT / "model" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    rate_suffix = "" if args.sample_rate_hz == 768_000 else "_384khz"
    asset_suffix = ("_trapezoidal" if args.trapezoidal else "") + rate_suffix
    vector_suffix = (
        asset_suffix
        + ("_banked" if args.banked else "")
        + ("_terminal" if args.terminal_correction else "")
        + ("_linear" if args.linear_tube else "")
    )
    write_memory(
        generated / f"v1_node_initial_wide{asset_suffix}.mem",
        [int(value) for value in model.voltage_q],
        40,
    )
    write_memory(
        generated / f"v1_cap_initial_q30_wide{asset_suffix}.mem",
        [int(capacitor.previous_voltage_q20) for capacitor in model.capacitors],
        40,
    )
    if args.trapezoidal:
        write_memory(
            generated
            / f"v1_cap_current_initial_q4_44_trapezoidal{rate_suffix}.mem",
            [int(capacitor.previous_current_q44) for capacitor in model.capacitors],
            48,
        )

    rng = np.random.default_rng(0x501A3)
    vector_path = (
        REPOSITORY_ROOT
        / "sim"
        / "vectors"
        / "generated"
        / f"v1_solver_wide_factorized_stream{vector_suffix}.txt"
    )
    vector_path.parent.mkdir(parents=True, exist_ok=True)
    maximum_residual = 0
    with vector_path.open("w", encoding="ascii") as handle:
        for index in range(args.vectors):
            input_q24 = stimulus_q24(index, rng)
            model.process_sample(input_q24 / float(1 << 24))
            nodes = [int(value) for value in model.voltage_q]
            capacitors = [
                int(capacitor.previous_voltage_q20) for capacitor in model.capacitors
            ]
            capacitor_currents = [
                int(capacitor.previous_current_q44) for capacitor in model.capacitors
            ]
            maximum_residual = max(maximum_residual, model.last_residual_q44)
            fields = [
                input_q24,
                *nodes,
                *capacitors,
                *(capacitor_currents if args.trapezoidal else []),
                model.last_residual_q44,
                model.saturation_count,
                model.lut_clip_count,
                model.nonconvergence_count,
                model.correction_scale_fallback_count,
                model.minimum_correction_residual_fractional_bits or 0,
            ]
            handle.write(" ".join(str(value) for value in fields) + "\n")

    report = {
        "model": "12ax7_passive_riaa_v1",
        "algorithm": (
            (
                "wide trapezoidal Q30-voltage/Q4.44-current state, three adaptive Q30/Q34/Q40 chord corrections plus terminal Q40 correction with corrected current-history commit and preterminal residual diagnostic"
                if args.terminal_correction
                else "wide trapezoidal Q30-voltage/Q4.44-current state, three adaptive Q30/Q34/Q40 chord corrections"
            )
            if args.trapezoidal
            else (
                "wide branch-current state, three adaptive Q30/Q34/Q40 chord corrections plus terminal Q40 correction with preterminal residual diagnostic"
                if args.terminal_correction
                else "wide branch-current state, three adaptive Q30/Q34/Q40 chord corrections"
            )
        ),
        "integration_method": (
            "trapezoidal" if args.trapezoidal else "backward_euler"
        ),
        "tube_implementation": (
            "factorized_linear" if args.linear_tube else "factorized_hermite"
        ),
        "sample_rate_hz": int(model.sample_rate_hz),
        "vectors": args.vectors,
        "seed": 0x501A3,
        "maximum_residual_q44": maximum_residual,
        "maximum_residual_a": maximum_residual / float(1 << 44),
        "saturation_count": model.saturation_count,
        "lut_clip_count": model.lut_clip_count,
        "nonconvergence_count": model.nonconvergence_count,
        "correction_scale_fallback_count": model.correction_scale_fallback_count,
        "minimum_correction_residual_fractional_bits": model.minimum_correction_residual_fractional_bits,
        "banked_chord": args.banked,
        "terminal_correction": args.terminal_correction,
        "residual_diagnostic_state": (
            "preterminal_correction"
            if args.terminal_correction
            else "committed_output_state"
        ),
        "chord_bank_selection_count": (
            model.chord_bank_selection_count if args.banked else None
        ),
        "slew_qualified_selection_count": (
            model.slew_qualified_selection_count if args.banked else None
        ),
        "latency_clocks": 127 if args.terminal_correction else 116,
        "output": str(vector_path.relative_to(REPOSITORY_ROOT)),
    }
    metadata = generated / f"v1_solver_wide_factorized{vector_suffix}_metadata.json"
    metadata.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
