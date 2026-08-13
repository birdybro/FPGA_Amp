#!/usr/bin/env python3
"""Run a captured RTL frequency sweep at representative audio-band points."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def tag(frequency_hz: float) -> str:
    return f"{frequency_hz:g}".replace(".", "p")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verilator", default="verilator")
    args = parser.parse_args()
    frequencies_hz = (100.0, 1_000.0, 10_000.0, 20_000.0)
    measurements: list[dict[str, object]] = []
    for frequency_hz in frequencies_hz:
        subprocess.run(
            [
                sys.executable,
                "scripts/characterize_wide_solver_rtl.py",
                "--verilator",
                args.verilator,
                "--frequency-hz",
                str(frequency_hz),
            ],
            cwd=ROOT,
            check=True,
        )
        run_report = (
            ROOT / "build" / f"wide_solver_rtl_{tag(frequency_hz)}hz_report.json"
        )
        report = json.loads(run_report.read_text(encoding="utf-8"))
        measurements.append(report)
        rtl = report["rtl"]
        print(
            f"{frequency_hz:8.1f} Hz: gain {rtl['gain_error_db']:+.7f} dB, "
            f"phase {rtl['phase_error_deg']:+.7f} deg, "
            f"raw null {rtl['raw_normalized_residual_db']:.2f} dB",
            flush=True,
        )

    rtl_measurements = [measurement["rtl"] for measurement in measurements]
    summary = {
        "model": "12ax7_passive_riaa_v1",
        "implementation": "captured SystemVerilog wide factorized solver",
        "frequencies_hz": list(frequencies_hz),
        "input_peak_v": 0.005,
        "all_rtl_fixed_bit_exact": all(
            bool(measurement["rtl_fixed_bit_exact"]) for measurement in measurements
        ),
        "maximum_absolute_gain_error_db": max(
            abs(float(value["gain_error_db"])) for value in rtl_measurements
        ),
        "maximum_absolute_phase_error_deg": max(
            abs(float(value["phase_error_deg"])) for value in rtl_measurements
        ),
        "worst_raw_normalized_residual_db": max(
            float(value["raw_normalized_residual_db"]) for value in rtl_measurements
        ),
        "worst_mean_removed_normalized_residual_db": max(
            float(value["mean_removed_normalized_residual_db"])
            for value in rtl_measurements
        ),
        "total_saturation_count": sum(
            int(value["saturation_count"]) for value in rtl_measurements
        ),
        "total_range_clip_count": sum(
            int(value["range_clip_count"]) for value in rtl_measurements
        ),
        "total_residual_limit_exceedance_count": sum(
            int(value["residual_limit_exceedance_count"])
            for value in rtl_measurements
        ),
        "total_correction_scale_fallback_count": sum(
            int(value["correction_scale_fallback_count"])
            for value in rtl_measurements
        ),
        "measurements": measurements,
    }
    if not summary["all_rtl_fixed_bit_exact"]:
        raise RuntimeError("at least one captured RTL sweep point differs from fixed")
    diagnostic_total = sum(
        int(summary[key])
        for key in (
            "total_saturation_count",
            "total_range_clip_count",
            "total_residual_limit_exceedance_count",
            "total_correction_scale_fallback_count",
        )
    )
    if diagnostic_total:
        raise RuntimeError(f"nominal sweep produced {diagnostic_total} diagnostics")
    if float(summary["maximum_absolute_gain_error_db"]) > 0.00025:
        raise RuntimeError("captured RTL gain error exceeds 0.00025 dB")
    if float(summary["maximum_absolute_phase_error_deg"]) > 0.0011:
        raise RuntimeError("captured RTL phase error exceeds 0.0011 degrees")
    output = ROOT / "model" / "generated" / "wide_solver_rtl_frequency_summary.json"
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    result = ROOT / "reference" / "results" / "wide_solver_rtl_frequency.json"
    result.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
