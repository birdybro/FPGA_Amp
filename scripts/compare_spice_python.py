#!/usr/bin/env python3
"""Compare the 768 kHz nonlinear nodal model with the ngspice transient."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


def main() -> int:
    source_path = REPOSITORY_ROOT / "reference" / "results" / "spice_tran_1khz_5mv.csv"
    if not source_path.exists():
        print("ERROR: run scripts/run_spice.py first", file=sys.stderr)
        return 2
    spice = np.loadtxt(source_path, skiprows=1)
    fs = 768_000.0
    duration_s = float(spice[-1, 0])
    time = np.arange(0.0, duration_s, 1.0 / fs)
    spice_input = np.interp(time, spice[:, 0], spice[:, 2])
    spice_output = np.interp(time, spice[:, 0], spice[:, 6])

    model = V1CircuitModel(sample_rate_hz=fs)
    python_output = model.process(spice_input, max_iterations=8, tolerance_a=1.0e-10)

    # Compare after 20 ms so output-coupling startup and early interpolation
    # details cannot dominate the steady 1 kHz metric.
    selection = time >= 0.020
    reference = spice_output[selection]
    candidate = python_output[selection]
    residual = candidate - reference
    reference_rms = float(np.sqrt(np.mean(np.square(reference))))
    residual_rms = float(np.sqrt(np.mean(np.square(residual))))
    gain_error_db = 20.0 * np.log10(
        np.sqrt(np.mean(np.square(candidate))) / reference_rms
    )
    report = {
        "comparison": "ngspice transient vs 768 kHz backward-Euler nonlinear MNA",
        "stimulus": "AT-VM95E electrical source, 5 mV peak, 1 kHz",
        "compared_interval_s": [0.020, duration_s],
        "reference_output_rms_v": reference_rms,
        "residual_rms_v": residual_rms,
        "normalized_residual_db": 20.0 * np.log10(residual_rms / reference_rms),
        "rms_gain_error_db": float(gain_error_db),
        "max_absolute_error_v": float(np.max(np.abs(residual))),
        "solver_max_iterations": model.max_iterations_observed,
        "solver_nonconvergence_count": model.nonconvergence_count,
        "samples": int(time.size),
    }
    output_path = REPOSITORY_ROOT / "reference" / "results" / "python_spice_comparison.json"
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if model.nonconvergence_count else 0


if __name__ == "__main__":
    raise SystemExit(main())

