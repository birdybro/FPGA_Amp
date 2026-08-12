#!/usr/bin/env python3
"""Measure previous-sample Newton convergence versus iteration cap."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


def main() -> int:
    sample_rate = 768_000.0
    time = np.arange(int(0.012 * sample_rate)) / sample_rate
    # 20 mV peak is a deliberate overload-adjacent cartridge transient test.
    stimulus = 20.0e-3 * np.sin(2.0 * np.pi * 1000.0 * time)
    baseline_model = V1CircuitModel(sample_rate)
    baseline = baseline_model.process(stimulus, max_iterations=10, tolerance_a=1.0e-12)
    selected = time >= 0.008
    baseline_rms = float(np.sqrt(np.mean(np.square(baseline[selected]))))
    results = []
    for cap in (1, 2, 3, 4):
        model = V1CircuitModel(sample_rate)
        output = model.process(stimulus, max_iterations=cap, tolerance_a=1.0e-10)
        error = output[selected] - baseline[selected]
        error_rms = float(np.sqrt(np.mean(np.square(error))))
        results.append(
            {
                "iteration_cap": cap,
                "normalized_residual_db": (
                    float(20.0 * np.log10(error_rms / baseline_rms))
                    if error_rms > 0.0
                    else -300.0
                ),
                "worst_output_error_v": float(np.max(np.abs(error))),
                "samples_not_meeting_100pa_residual": model.nonconvergence_count,
                "max_iterations_observed": model.max_iterations_observed,
            }
        )
    report = {
        "sample_rate_hz": sample_rate,
        "stimulus": "20 mV peak, 1 kHz sine",
        "samples": int(time.size),
        "baseline_max_iterations": baseline_model.max_iterations_observed,
        "baseline_nonconvergence_count": baseline_model.nonconvergence_count,
        "results": results,
    }
    output_path = REPOSITORY_ROOT / "reference" / "results" / "solver_iterations.json"
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

