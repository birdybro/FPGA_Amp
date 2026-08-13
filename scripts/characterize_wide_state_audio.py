#!/usr/bin/env python3
"""Compare legacy and wide-state fixed paths at nominal cartridge level."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedChordV1CircuitModel,
    FixedWideStateV1CircuitModel,
)
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


def fit_harmonics(
    time_s: np.ndarray, waveform: np.ndarray, frequency_hz: float
) -> dict[str, float]:
    columns = [np.ones_like(time_s)]
    for harmonic in range(1, 11):
        angle = 2.0 * np.pi * frequency_hz * harmonic * time_s
        columns.extend((np.sin(angle), np.cos(angle)))
    coefficient, *_ = np.linalg.lstsq(np.column_stack(columns), waveform, rcond=None)
    peak = np.asarray(
        [
            np.hypot(coefficient[2 * harmonic - 1], coefficient[2 * harmonic])
            for harmonic in range(1, 11)
        ]
    )
    return {
        "fundamental_peak_v": float(peak[0]),
        "phase_deg": float(np.degrees(np.arctan2(coefficient[2], coefficient[1]))),
        "mean_v": float(coefficient[0]),
        "thd_percent_h2_to_h10": float(
            100.0 * np.sqrt(np.sum(np.square(peak[1:]))) / peak[0]
        ),
    }


def main() -> int:
    sample_rate_hz = 768_000.0
    frequency_hz = 1_000.0
    input_peak_v = 0.005
    duration_s = 0.030
    analysis_start_s = 0.020
    time_s = np.arange(int(duration_s * sample_rate_hz)) / sample_rate_hz
    stimulus = input_peak_v * np.sin(2.0 * np.pi * frequency_hz * time_s)
    selected = time_s >= analysis_start_s

    analytical_model = V1CircuitModel(sample_rate_hz)
    outputs = {
        "analytical": analytical_model.process(
            stimulus, max_iterations=8, tolerance_a=1.0e-12
        )
    }
    fixed_models = {
        "legacy_factorized": FixedChordV1CircuitModel(
            sample_rate_hz, tube_lut=FixedFactorizedKoren12AX7()
        ),
        "wide_state_factorized": FixedWideStateV1CircuitModel(
            sample_rate_hz, tube_lut=FixedFactorizedKoren12AX7()
        ),
    }
    for name, model in fixed_models.items():
        outputs[name] = model.process(
            stimulus, max_iterations=3, residual_limit_a=2.0e-6
        )

    reference_metrics = fit_harmonics(
        time_s[selected], outputs["analytical"][selected], frequency_hz
    )
    reference_rms = float(
        np.sqrt(np.mean(np.square(outputs["analytical"][selected])))
    )
    implementations: dict[str, object] = {
        "analytical": {
            **reference_metrics,
            "gain_db": float(
                20.0
                * np.log10(reference_metrics["fundamental_peak_v"] / input_peak_v)
            ),
            "nonconvergence_count": analytical_model.nonconvergence_count,
        }
    }
    for name, model in fixed_models.items():
        metrics = fit_harmonics(time_s[selected], outputs[name][selected], frequency_hz)
        residual = outputs[name][selected] - outputs["analytical"][selected]
        residual_mean = float(np.mean(residual))
        mean_removed = residual - residual_mean
        implementations[name] = {
            **metrics,
            "gain_db": float(
                20.0 * np.log10(metrics["fundamental_peak_v"] / input_peak_v)
            ),
            "gain_error_db": float(
                20.0
                * np.log10(
                    metrics["fundamental_peak_v"]
                    / reference_metrics["fundamental_peak_v"]
                )
            ),
            "phase_error_deg": metrics["phase_deg"]
            - reference_metrics["phase_deg"],
            "raw_normalized_residual_db": float(
                20.0
                * np.log10(np.sqrt(np.mean(np.square(residual))) / reference_rms)
            ),
            "mean_removed_normalized_residual_db": float(
                20.0
                * np.log10(
                    np.sqrt(np.mean(np.square(mean_removed))) / reference_rms
                )
            ),
            "residual_mean_v": residual_mean,
            "maximum_residual_a": model.max_residual_q44_observed / (1 << 44),
            "residual_limit_exceedance_count": model.nonconvergence_count,
            "saturation_count": model.saturation_count,
            "range_clip_count": model.lut_clip_count,
        }
    report = {
        "model": "12ax7_passive_riaa_v1",
        "sample_rate_hz": sample_rate_hz,
        "stimulus": {
            "frequency_hz": frequency_hz,
            "input_peak_v": input_peak_v,
            "duration_s": duration_s,
            "analysis_start_s": analysis_start_s,
        },
        "wide_state_contract": {
            "node_fractional_bits": [32, 28, 32, 28, 32, 32, 28, 32, 32],
            "node_width_bits": 40,
            "capacitor_state_fractional_bits": 30,
            "correction_residual_fractional_bits_by_pass": [30, 34, 40],
            "capacitor_stamp": "single rounded G*(Vnow-Vprevious) branch current",
        },
        "implementations": implementations,
    }
    result_path = REPOSITORY_ROOT / "reference" / "results" / "wide_state_audio.json"
    result_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary_path = (
        REPOSITORY_ROOT / "model" / "generated" / "wide_state_audio_summary.json"
    )
    summary_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
