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

from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import FixedWideStateV1CircuitModel  # noqa: E402
from generate_solver_vectors import stimulus_q24, write_memory  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=int, default=512)
    args = parser.parse_args()
    model = FixedWideStateV1CircuitModel(tube_lut=FixedFactorizedKoren12AX7())
    generated = REPOSITORY_ROOT / "model" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    write_memory(
        generated / "v1_node_initial_wide.mem",
        [int(value) for value in model.voltage_q],
        40,
    )
    write_memory(
        generated / "v1_cap_initial_q30_wide.mem",
        [int(capacitor.previous_voltage_q20) for capacitor in model.capacitors],
        40,
    )

    rng = np.random.default_rng(0x501A3)
    vector_path = (
        REPOSITORY_ROOT
        / "sim"
        / "vectors"
        / "generated"
        / "v1_solver_wide_factorized_stream.txt"
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
            maximum_residual = max(maximum_residual, model.last_residual_q44)
            fields = [
                input_q24,
                *nodes,
                *capacitors,
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
        "algorithm": "wide branch-current state, three adaptive Q30/Q34/Q40 chord corrections",
        "tube_implementation": "factorized",
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
        "latency_clocks": 116,
        "output": str(vector_path.relative_to(REPOSITORY_ROOT)),
    }
    metadata = generated / "v1_solver_wide_factorized_metadata.json"
    metadata.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
