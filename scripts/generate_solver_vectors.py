#!/usr/bin/env python3
"""Generate a sequential, bit-exact V1 mono-solver regression stream."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.fixed_circuit import FixedChordV1CircuitModel  # noqa: E402


def stimulus_q24(index: int, rng: np.random.Generator) -> int:
    """Return deterministic silence, tone, multitone, noise, and click cases."""

    if index < 32:
        value = 0.0
    elif index < 160:
        value = 0.005 * np.sin(2.0 * np.pi * 1_000.0 * (index - 32) / 768_000.0)
    elif index < 288:
        sample = index - 160
        value = (
            0.006 * np.sin(2.0 * np.pi * 70.0 * sample / 768_000.0)
            + 0.004 * np.sin(2.0 * np.pi * 7_000.0 * sample / 768_000.0)
            + 0.002 * np.sin(2.0 * np.pi * 19_000.0 * sample / 768_000.0)
        )
    else:
        value = float(np.clip(rng.normal(0.0, 0.008), -0.030, 0.030))
    if index in (320, 384):
        value = 0.100
    elif index in (321, 385):
        value = -0.100
    return int(round(value * (1 << 24)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=int, default=512)
    args = parser.parse_args()
    model = FixedChordV1CircuitModel()
    rng = np.random.default_rng(0x501A3)
    vector_directory = REPOSITORY_ROOT / "sim" / "vectors" / "generated"
    vector_directory.mkdir(parents=True, exist_ok=True)
    vector_path = vector_directory / "v1_solver_stream.txt"

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
            ]
            handle.write(" ".join(str(value) for value in fields) + "\n")

    metadata = {
        "model": "12ax7_passive_riaa_v1",
        "algorithm": "three Q17.1 chord corrections plus diagnostic residual",
        "sample_rate_hz": int(model.sample_rate_hz),
        "vectors": args.vectors,
        "seed": 0x501A3,
        "maximum_residual_q44": maximum_residual,
        "maximum_residual_a": maximum_residual / float(1 << 44),
        "saturation_count": model.saturation_count,
        "lut_clip_count": model.lut_clip_count,
        "nonconvergence_count": model.nonconvergence_count,
        "output": str(vector_path.relative_to(REPOSITORY_ROOT)),
    }
    metadata_path = REPOSITORY_ROOT / "model" / "generated" / "v1_solver_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
