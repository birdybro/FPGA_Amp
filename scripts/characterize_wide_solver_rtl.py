#!/usr/bin/env python3
"""Measure nominal 1 kHz behavior from captured wide-solver RTL output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

from characterize_wide_state_audio import fit_harmonics  # noqa: E402
from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import FixedWideStateV1CircuitModel  # noqa: E402
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verilator", default="verilator")
    parser.add_argument("--frequency-hz", type=float, default=1_000.0)
    args = parser.parse_args()
    sample_rate_hz = 768_000.0
    frequency_hz = args.frequency_hz
    if frequency_hz <= 0.0 or frequency_hz > 20_000.0:
        raise ValueError("frequency must be within 0 < f <= 20 kHz")
    input_peak_v = 0.005
    duration_s = max(0.030, 10.0 / frequency_hz)
    analysis_start_s = round(
        duration_s - max(0.010, 5.0 / frequency_hz), 12
    )
    sample_count = int(round(duration_s * sample_rate_hz))
    time_s = np.arange(sample_count, dtype=np.float64) / sample_rate_hz
    input_q24 = np.rint(
        input_peak_v * np.sin(2.0 * np.pi * frequency_hz * time_s) * (1 << 24)
    ).astype(np.int64)
    stimulus = input_q24.astype(np.float64) / float(1 << 24)

    fixed = FixedWideStateV1CircuitModel(tube_lut=FixedFactorizedKoren12AX7())
    analytical = V1CircuitModel(sample_rate_hz)
    analytical_output = analytical.process(
        stimulus, max_iterations=8, tolerance_a=1.0e-12
    )
    fixed_output = np.empty(sample_count, dtype=np.float64)
    frequency_tag = f"{frequency_hz:g}".replace(".", "p")
    vector_path = (
        ROOT
        / "sim"
        / "vectors"
        / "generated"
        / f"wide_solver_rtl_{frequency_tag}hz.txt"
    )
    vector_path.parent.mkdir(parents=True, exist_ok=True)
    with vector_path.open("w", encoding="ascii") as handle:
        for index, sample in enumerate(input_q24):
            fixed_output[index] = fixed.process_sample(int(sample) / float(1 << 24))
            fields = [
                int(sample),
                *[int(value) for value in fixed.voltage_q],
                *[int(cap.previous_voltage_q20) for cap in fixed.capacitors],
                fixed.last_residual_q44,
                fixed.saturation_count,
                fixed.lut_clip_count,
                fixed.nonconvergence_count,
                fixed.correction_scale_fallback_count,
                fixed.minimum_correction_residual_fractional_bits or 0,
            ]
            handle.write(" ".join(str(value) for value in fields) + "\n")

    capture_path = ROOT / "build" / f"wide_solver_rtl_{frequency_tag}hz_capture.txt"
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "scripts/run_wide_solver_rtl.py",
            "--verilator",
            args.verilator,
            "--skip-generate",
            "--vectors-file",
            str(vector_path.relative_to(ROOT)),
            "--capture-file",
            str(capture_path.relative_to(ROOT)),
        ],
        cwd=ROOT,
        check=True,
    )
    captured = np.loadtxt(capture_path, dtype=np.int64)
    if captured.shape != (sample_count, 2):
        raise RuntimeError(f"expected {sample_count} captured samples, got {captured.shape}")
    if not np.array_equal(captured[:, 0], np.arange(sample_count)):
        raise RuntimeError("RTL capture indices are not contiguous")
    rtl_output = captured[:, 1].astype(np.float64) / float(1 << 32)
    fixed_q32 = np.rint(fixed_output * (1 << 32)).astype(np.int64)
    bit_exact = bool(np.array_equal(captured[:, 1], fixed_q32))
    if not bit_exact:
        raise RuntimeError("captured RTL output is not Q32-exact to fixed Python")

    selected = time_s >= analysis_start_s
    reference_metrics = fit_harmonics(
        time_s[selected], analytical_output[selected], frequency_hz
    )
    rtl_metrics = fit_harmonics(time_s[selected], rtl_output[selected], frequency_hz)
    reference_rms = float(np.sqrt(np.mean(np.square(analytical_output[selected]))))
    residual = rtl_output[selected] - analytical_output[selected]
    residual_mean = float(np.mean(residual))
    report = {
        "model": "12ax7_passive_riaa_v1",
        "implementation": "captured SystemVerilog wide factorized solver",
        "sample_rate_hz": sample_rate_hz,
        "stimulus": {
            "frequency_hz": frequency_hz,
            "input_peak_v": input_peak_v,
            "duration_s": duration_s,
            "analysis_start_s": analysis_start_s,
            "quantized_input": "Q8.24",
        },
        "captured_samples": sample_count,
        "rtl_fixed_bit_exact": bit_exact,
        "analytical": reference_metrics,
        "rtl": {
            **rtl_metrics,
            "gain_db": float(
                20.0 * np.log10(rtl_metrics["fundamental_peak_v"] / input_peak_v)
            ),
            "gain_error_db": float(
                20.0
                * np.log10(
                    rtl_metrics["fundamental_peak_v"]
                    / reference_metrics["fundamental_peak_v"]
                )
            ),
            "phase_error_deg": rtl_metrics["phase_deg"]
            - reference_metrics["phase_deg"],
            "raw_normalized_residual_db": float(
                20.0
                * np.log10(np.sqrt(np.mean(np.square(residual))) / reference_rms)
            ),
            "mean_removed_normalized_residual_db": float(
                20.0
                * np.log10(
                    np.sqrt(np.mean(np.square(residual - residual_mean)))
                    / reference_rms
                )
            ),
            "residual_mean_v": residual_mean,
            "maximum_residual_a": fixed.max_residual_q44_observed / (1 << 44),
            "saturation_count": fixed.saturation_count,
            "range_clip_count": fixed.lut_clip_count,
            "residual_limit_exceedance_count": fixed.nonconvergence_count,
            "correction_scale_fallback_count": fixed.correction_scale_fallback_count,
        },
    }
    run_report = ROOT / "build" / f"wide_solver_rtl_{frequency_tag}hz_report.json"
    run_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if frequency_hz == 1_000.0:
        summary = ROOT / "model" / "generated" / "wide_solver_rtl_audio_summary.json"
        summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result = (
        ROOT / "reference" / "results" / f"wide_solver_rtl_{frequency_tag}hz.json"
    )
    result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
