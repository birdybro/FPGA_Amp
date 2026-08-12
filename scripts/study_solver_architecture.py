#!/usr/bin/env python3
"""Measure fixed-linear-inverse iteration against the Newton reference."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


def main() -> int:
    sample_rate_hz = 768_000.0
    time = np.arange(int(0.006 * sample_rate_hz)) / sample_rate_hz
    # A multitone makes intersample state less repetitive than the existing
    # single-frequency iteration-cap study while retaining deterministic input.
    signal = (
        10.0e-3 * np.sin(2.0 * np.pi * 50.0 * time)
        + 10.0e-3 * np.sin(2.0 * np.pi * 1000.0 * time)
        + 5.0e-3 * np.sin(2.0 * np.pi * 10_000.0 * time)
    )
    reference_model = V1CircuitModel(sample_rate_hz)
    reference = reference_model.process(signal, max_iterations=8, tolerance_a=1.0e-12)
    reference_rms = float(np.sqrt(np.mean(np.square(reference))))
    cases: list[dict[str, float | int | str]] = []
    candidates = (
        ("fixed_point", (0.125, 0.25, 0.5, 0.75, 1.0), (4, 8, 12)),
        ("chord", (0.5, 0.75, 1.0), (1, 2, 3, 4, 6)),
    )
    for solver, relaxations, iteration_caps in candidates:
        for relaxation in relaxations:
            for iteration_cap in iteration_caps:
                model = V1CircuitModel(sample_rate_hz)
                output = model.process(
                    signal,
                    solver=solver,
                    relaxation=relaxation,
                    max_iterations=iteration_cap,
                    tolerance_a=1.0e-10,
                )
                residual = output - reference
                cases.append(
                    {
                        "solver": solver,
                        "relaxation": relaxation,
                        "iteration_cap": iteration_cap,
                        "normalized_output_residual_db": float(
                            20.0
                            * np.log10(
                                np.sqrt(np.mean(np.square(residual))) / reference_rms
                            )
                        ),
                        "worst_output_error_v": float(np.max(np.abs(residual))),
                        "nonconverged_samples": model.nonconvergence_count,
                        "max_iterations_observed": model.max_iterations_observed,
                    }
                )
    report = {
        "candidate": "constant inverse: tube-current fixed point versus quiescent-Jacobian chord iteration",
        "sample_rate_hz": sample_rate_hz,
        "stimulus": "10 mV peak 50 Hz + 10 mV peak 1 kHz + 5 mV peak 10 kHz",
        "duration_s": float(time[-1] + 1.0 / sample_rate_hz),
        "reference_solver": "Newton, 1 pA residual",
        "cases": cases,
    }
    output_path = REPOSITORY_ROOT / "reference" / "results" / "solver_architecture.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
