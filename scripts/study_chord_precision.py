#!/usr/bin/env python3
"""Find a DSP-friendly chord correction precision against the fixed baseline."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.fixed_circuit import FixedChordV1CircuitModel  # noqa: E402


def main() -> int:
    sample_rate_hz = 768_000.0
    time = np.arange(int(0.004 * sample_rate_hz)) / sample_rate_hz
    signal = (
        10.0e-3 * np.sin(2.0 * np.pi * 50.0 * time)
        + 10.0e-3 * np.sin(2.0 * np.pi * 1000.0 * time)
        + 5.0e-3 * np.sin(2.0 * np.pi * 10_000.0 * time)
    )
    baseline_model = FixedChordV1CircuitModel(
        sample_rate_hz,
        inverse_fractional_bits=15,
        correction_residual_fractional_bits=44,
        correction_residual_width=48,
    )
    baseline = baseline_model.process(signal)
    selection = time >= 0.001
    reference = baseline[selection]
    reference_rms = float(np.sqrt(np.mean(np.square(reference))))
    cases: list[dict[str, float | int]] = []
    for inverse_fractional_bits in (1, 2, 4, 8, 15):
        for residual_fractional_bits in (28, 29, 30, 31):
            model = FixedChordV1CircuitModel(
                sample_rate_hz,
                inverse_fractional_bits=inverse_fractional_bits,
                correction_residual_fractional_bits=residual_fractional_bits,
                correction_residual_width=25,
            )
            candidate = model.process(signal)
            residual = candidate[selection] - reference
            residual_rms = float(np.sqrt(np.mean(np.square(residual))))
            cases.append(
                {
                    "inverse_fractional_bits": inverse_fractional_bits,
                    "inverse_width_bits": 18 if inverse_fractional_bits <= 1 else 17 + inverse_fractional_bits,
                    "correction_residual_fractional_bits": residual_fractional_bits,
                    "correction_residual_width_bits": 25,
                    "correction_residual_range_a": (1 << 24)
                    / (1 << residual_fractional_bits),
                    "normalized_residual_db_vs_q15_q44": float(
                        20.0 * np.log10(max(residual_rms, 1.0e-30) / reference_rms)
                    ),
                    "worst_output_error_v": float(np.max(np.abs(residual))),
                    "rms_gain_error_db": float(
                        20.0
                        * np.log10(
                            np.sqrt(np.mean(np.square(candidate[selection])))
                            / reference_rms
                        )
                    ),
                    "saturation_count": model.saturation_count,
                    "residual_limit_exceedance_count": model.nonconvergence_count,
                }
            )
    report = {
        "baseline": "Q17.15 inverse x Q4.44 residual",
        "stimulus": "10 mV peak 50 Hz + 10 mV peak 1 kHz + 5 mV peak 10 kHz",
        "comparison_interval_s": [0.001, 0.004],
        "dsp48e1_native_multiplier": "25 x 18 bits",
        "cases": cases,
    }
    path = REPOSITORY_ROOT / "reference" / "results" / "chord_precision_study.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
