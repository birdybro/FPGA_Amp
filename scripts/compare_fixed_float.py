#!/usr/bin/env python3
"""Compare the bit-accurate fixed chord candidate with full-Newton float."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.fixed import TubeLUT  # noqa: E402
from fpga_amp.fixed_circuit import FixedChordV1CircuitModel, LUTTubeAdapter  # noqa: E402
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


def metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    residual = candidate - reference
    reference_rms = float(np.sqrt(np.mean(np.square(reference))))
    candidate_rms = float(np.sqrt(np.mean(np.square(candidate))))
    residual_rms = float(np.sqrt(np.mean(np.square(residual))))
    return {
        "reference_rms_v": reference_rms,
        "candidate_rms_v": candidate_rms,
        "residual_rms_v": residual_rms,
        "normalized_residual_db": float(20.0 * np.log10(residual_rms / reference_rms)),
        "rms_gain_error_db": float(20.0 * np.log10(candidate_rms / reference_rms)),
        "max_absolute_error_v": float(np.max(np.abs(residual))),
        "mean_error_v": float(np.mean(residual)),
    }


def main() -> int:
    sample_rate_hz = 768_000.0
    time = np.arange(int(0.006 * sample_rate_hz)) / sample_rate_hz
    signal = (
        10.0e-3 * np.sin(2.0 * np.pi * 50.0 * time)
        + 10.0e-3 * np.sin(2.0 * np.pi * 1000.0 * time)
        + 5.0e-3 * np.sin(2.0 * np.pi * 10_000.0 * time)
    )
    float_model = V1CircuitModel(sample_rate_hz)
    reference = float_model.process(signal, max_iterations=8, tolerance_a=1.0e-12)
    lut = TubeLUT()
    lut.generate()
    lut_float_model = V1CircuitModel(
        sample_rate_hz,
        tube=LUTTubeAdapter(lut),  # type: ignore[arg-type]
        dc_tolerance_a=1.1e-9,
    )
    lut_float = lut_float_model.process(
        signal, max_iterations=8, tolerance_a=2.0e-9
    )
    fixed_model = FixedChordV1CircuitModel(sample_rate_hz)
    candidate = fixed_model.process(signal, max_iterations=3, residual_limit_a=2.0e-6)
    settled = time >= 0.002
    report = {
        "reference": "analytical Koren tube, backward Euler, full Newton to 1 pA",
        "candidate": "Q-format state/network, DSP-native Q17.1 inverse x 25-bit Q30 correction residual, 128x256 Q31 tube LUT, exactly 3 passes",
        "stimulus": "10 mV peak 50 Hz + 10 mV peak 1 kHz + 5 mV peak 10 kHz",
        "sample_rate_hz": sample_rate_hz,
        "all_samples": metrics(reference, candidate),
        "settled_2ms_to_6ms": metrics(reference[settled], candidate[settled]),
        "error_decomposition_settled": {
            "tube_lut_float_vs_analytical_float": metrics(
                reference[settled], lut_float[settled]
            ),
            "fixed_chord_vs_tube_lut_float": metrics(
                lut_float[settled], candidate[settled]
            ),
        },
        "diagnostics": {
            "fixed_residual_limit_a": 2.0e-6,
            "max_fixed_residual_a": fixed_model.max_residual_q44_observed / (1 << 44),
            "residual_limit_exceedance_count": fixed_model.nonconvergence_count,
            "arithmetic_saturation_count": fixed_model.saturation_count,
            "tube_lut_clip_count": fixed_model.lut_clip_count,
            "max_iterations_observed": fixed_model.max_iterations_observed,
            "chord_inverse_format": "signed 18-bit Q17.1",
            "chord_correction_residual_format": "signed 25-bit, 30 fractional bits",
            "lut_float_nonconvergence_count": lut_float_model.nonconvergence_count,
        },
    }
    path = REPOSITORY_ROOT / "reference" / "results" / "fixed_float_comparison.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if fixed_model.saturation_count or fixed_model.lut_clip_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
