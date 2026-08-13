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
    parser.add_argument("--trapezoidal", action="store_true")
    args = parser.parse_args()
    if args.trapezoidal:
        for command in (
            [sys.executable, "scripts/generate_wide_network_vectors.py"],
            [sys.executable, "scripts/generate_trapezoidal_network_vectors.py"],
            [
                sys.executable,
                "scripts/generate_wide_chord_vectors.py",
                "--trapezoidal",
            ],
            [sys.executable, "scripts/generate_factorized_tube.py"],
        ):
            subprocess.run(command, cwd=ROOT, check=True)
    stem_prefix = (
        "wide_solver_rtl_trapezoidal"
        if args.trapezoidal
        else "wide_solver_rtl"
    )
    frequencies_hz = (100.0, 1_000.0, 10_000.0, 20_000.0)
    measurements: list[dict[str, object]] = []
    for frequency_hz in frequencies_hz:
        command = [
            sys.executable,
            "scripts/characterize_wide_solver_rtl.py",
            "--verilator",
            args.verilator,
            "--frequency-hz",
            str(frequency_hz),
        ]
        if args.trapezoidal:
            command.append("--trapezoidal")
        subprocess.run(
            command,
            cwd=ROOT,
            check=True,
        )
        run_report = (
            ROOT / "build" / f"{stem_prefix}_{tag(frequency_hz)}hz_report.json"
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
        "implementation": (
            "captured SystemVerilog wide factorized trapezoidal solver"
            if args.trapezoidal
            else "captured SystemVerilog wide factorized solver"
        ),
        "integration_method": (
            "trapezoidal" if args.trapezoidal else "backward_euler"
        ),
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
    if args.trapezoidal:
        upstream_path = (
            ROOT / "model" / "generated" / "python_spice_frequency_summary.json"
        )
        upstream = json.loads(upstream_path.read_text(encoding="utf-8"))
        upstream_points: list[dict[str, object]] = []
        for study in upstream["high_frequency_method_study"]:
            candidate = next(
                item
                for item in study["candidates"]
                if item["integration_method"] == "trapezoidal"
                and float(item["sample_rate_hz"]) == 768_000.0
            )
            upstream_points.append(
                {
                    "frequency_hz": study["frequency_hz"],
                    **candidate["python_vs_spice"],
                }
            )
        summary["upstream_float_trapezoidal_vs_spice"] = {
            "source": str(upstream_path.relative_to(ROOT)),
            "note": (
                "Independent upstream transient comparison; errors are not "
                "arithmetically combined because the SPICE-input waveform and "
                "captured Q8.24 sine stimuli are not sample-identical."
            ),
            "measurements": upstream_points,
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
    gain_limit_db = 0.0002 if args.trapezoidal else 0.00025
    phase_limit_deg = 0.001 if args.trapezoidal else 0.0011
    if float(summary["maximum_absolute_gain_error_db"]) > gain_limit_db:
        raise RuntimeError(f"captured RTL gain error exceeds {gain_limit_db} dB")
    if float(summary["maximum_absolute_phase_error_deg"]) > phase_limit_deg:
        raise RuntimeError(
            f"captured RTL phase error exceeds {phase_limit_deg} degrees"
        )
    summary_name = (
        "wide_solver_rtl_trapezoidal_frequency_summary.json"
        if args.trapezoidal
        else "wide_solver_rtl_frequency_summary.json"
    )
    output = ROOT / "model" / "generated" / summary_name
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    result_name = summary_name.removesuffix("_summary.json") + ".json"
    result = ROOT / "reference" / "results" / result_name
    result.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
