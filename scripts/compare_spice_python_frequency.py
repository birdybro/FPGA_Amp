#!/usr/bin/env python3
"""Compare ngspice and the 768 kHz analytical model across audio frequency."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

from characterize_wide_state_audio import fit_harmonics  # noqa: E402
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


SAMPLE_RATE_HZ = 768_000.0
INPUT_PEAK_V = 0.005
FREQUENCIES_HZ = (100.0, 1_000.0, 10_000.0, 20_000.0)


def locate_ngspice(requested: str) -> Path | None:
    system = shutil.which(requested)
    if system:
        return Path(system)
    local = ROOT / ".tools" / "root" / "usr" / "bin" / requested
    return local if local.exists() else None


def frequency_tag(frequency_hz: float) -> str:
    return f"{frequency_hz:g}".replace(".", "p")


def wrap_phase_deg(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def compare_model(
    spice: np.ndarray,
    frequency_hz: float,
    duration_s: float,
    analysis_start_s: float,
    sample_rate_hz: float,
    integration_method: str,
) -> dict[str, object]:
    duration_actual_s = min(duration_s, float(spice[-1, 0]))
    time_s = np.arange(0.0, duration_actual_s, 1.0 / sample_rate_hz)
    input_v = np.interp(time_s, spice[:, 0], spice[:, 2])
    spice_output_v = np.interp(time_s, spice[:, 0], spice[:, 6])
    model = V1CircuitModel(
        sample_rate_hz, integration_method=integration_method
    )
    python_output_v = model.process(
        input_v, max_iterations=8, tolerance_a=1.0e-10
    )
    selected = time_s >= analysis_start_s
    spice_metrics = fit_harmonics(
        time_s[selected], spice_output_v[selected], frequency_hz
    )
    python_metrics = fit_harmonics(
        time_s[selected], python_output_v[selected], frequency_hz
    )
    residual = python_output_v[selected] - spice_output_v[selected]
    residual_mean_v = float(np.mean(residual))
    spice_rms_v = float(np.sqrt(np.mean(np.square(spice_output_v[selected]))))
    return {
        "sample_rate_hz": sample_rate_hz,
        "integration_method": integration_method,
        "samples": int(time_s.size),
        "spice": spice_metrics,
        "python": python_metrics,
        "python_vs_spice": {
            "fundamental_gain_error_db": float(
                20.0
                * np.log10(
                    python_metrics["fundamental_peak_v"]
                    / spice_metrics["fundamental_peak_v"]
                )
            ),
            "fundamental_phase_error_deg": wrap_phase_deg(
                python_metrics["phase_deg"] - spice_metrics["phase_deg"]
            ),
            "raw_normalized_residual_db": float(
                20.0
                * np.log10(np.sqrt(np.mean(np.square(residual))) / spice_rms_v)
            ),
            "mean_removed_normalized_residual_db": float(
                20.0
                * np.log10(
                    np.sqrt(np.mean(np.square(residual - residual_mean_v)))
                    / spice_rms_v
                )
            ),
            "residual_mean_v": residual_mean_v,
            "maximum_absolute_error_v": float(np.max(np.abs(residual))),
        },
        "python_solver": {
            "maximum_iterations": model.max_iterations_observed,
            "nonconvergence_count": model.nonconvergence_count,
        },
    }


def candidate_summary(measurement: dict[str, object]) -> dict[str, object]:
    return {
        "sample_rate_hz": measurement["sample_rate_hz"],
        "integration_method": measurement["integration_method"],
        "samples": measurement["samples"],
        "python_vs_spice": measurement["python_vs_spice"],
        "python_solver": measurement["python_solver"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ngspice", default="ngspice")
    args = parser.parse_args()
    executable = locate_ngspice(args.ngspice)
    if executable is None:
        print("ERROR: ngspice unavailable; run `make tools`", file=sys.stderr)
        return 2
    source = (ROOT / "reference" / "spice" / "v1_reference.cir").read_text(
        encoding="utf-8"
    )
    workspace = ROOT / "build" / "spice_python_frequency"
    workspace.mkdir(parents=True, exist_ok=True)
    measurements: list[dict[str, object]] = []
    high_frequency_method_study: list[dict[str, object]] = []

    for frequency_hz in FREQUENCIES_HZ:
        tag = frequency_tag(frequency_hz)
        duration_s = max(0.030, 10.0 / frequency_hz)
        analysis_start_s = round(
            duration_s - max(0.010, 5.0 / frequency_hz), 12
        )
        maximum_step_s = min(2.0e-6, 1.0 / (200.0 * frequency_hz))
        csv_relative = f"build/spice_python_frequency/{tag}hz.csv"
        netlist_text = source.replace(
            "SIN(0 5m 1k)", f"SIN(0 5m {frequency_hz:.12g})"
        ).replace(
            "tran 2u 30m 0 2u",
            f"tran {maximum_step_s:.12g} {duration_s:.12g} 0 {maximum_step_s:.12g}",
        ).replace(
            "reference/results/spice_tran_1khz_5mv.csv", csv_relative
        ).replace(
            "reference/results/spice_op.csv",
            f"build/spice_python_frequency/{tag}hz_op.csv",
        ).replace(
            "reference/results/spice_ac.csv",
            f"build/spice_python_frequency/{tag}hz_ac.csv",
        )
        netlist_path = workspace / f"{tag}hz.cir"
        netlist_path.write_text(netlist_text, encoding="utf-8")
        log_path = workspace / f"{tag}hz.log"
        completed = subprocess.run(
            [str(executable), "-b", "-o", str(log_path), str(netlist_path)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if completed.returncode:
            print(log_path.read_text(encoding="utf-8", errors="replace"), file=sys.stderr)
            return completed.returncode

        spice = np.loadtxt(ROOT / csv_relative, skiprows=1)
        measurement = compare_model(
            spice,
            frequency_hz,
            duration_s,
            analysis_start_s,
            SAMPLE_RATE_HZ,
            "backward_euler",
        )
        measurement.update({
            "frequency_hz": frequency_hz,
            "duration_s": duration_s,
            "analysis_start_s": analysis_start_s,
            "ngspice_maximum_step_s": maximum_step_s,
        })
        measurements.append(measurement)
        error = measurement["python_vs_spice"]
        print(
            f"{frequency_hz:8.1f} Hz: gain {error['fundamental_gain_error_db']:+.6f} dB, "
            f"phase {error['fundamental_phase_error_deg']:+.6f} deg, "
            f"raw null {error['raw_normalized_residual_db']:.2f} dB",
            flush=True,
        )
        if frequency_hz >= 10_000.0:
            candidates = [candidate_summary(measurement)]
            for integration_method, sample_rate_hz in (
                ("backward_euler", 1_536_000.0),
                ("backward_euler", 3_072_000.0),
                ("trapezoidal", 384_000.0),
                ("trapezoidal", 768_000.0),
            ):
                candidate = compare_model(
                    spice,
                    frequency_hz,
                    duration_s,
                    analysis_start_s,
                    sample_rate_hz,
                    integration_method,
                )
                candidates.append(candidate_summary(candidate))
                candidate_error = candidate["python_vs_spice"]
                print(
                    f"  {integration_method:14s} {sample_rate_hz / 1000:7.0f} kHz: "
                    f"gain {candidate_error['fundamental_gain_error_db']:+.6f} dB, "
                    f"phase {candidate_error['fundamental_phase_error_deg']:+.6f} deg",
                    flush=True,
                )
            high_frequency_method_study.append(
                {"frequency_hz": frequency_hz, "candidates": candidates}
            )

    errors = [measurement["python_vs_spice"] for measurement in measurements]
    trapezoidal_errors = [
        candidate["python_vs_spice"]
        for study in high_frequency_method_study
        for candidate in study["candidates"]
        if candidate["integration_method"] == "trapezoidal"
        and candidate["sample_rate_hz"] == SAMPLE_RATE_HZ
    ]
    trapezoidal_384khz_errors = [
        candidate["python_vs_spice"]
        for study in high_frequency_method_study
        for candidate in study["candidates"]
        if candidate["integration_method"] == "trapezoidal"
        and candidate["sample_rate_hz"] == 384_000.0
    ]
    report = {
        "comparison": "ngspice transient vs 768 kHz backward-Euler nonlinear MNA",
        "stimulus": {
            "input_peak_v": INPUT_PEAK_V,
            "frequencies_hz": list(FREQUENCIES_HZ),
            "source": "AT-VM95E INPUT node after cartridge R/L/load network",
        },
        "maximum_absolute_gain_error_db": max(
            abs(float(error["fundamental_gain_error_db"])) for error in errors
        ),
        "maximum_absolute_phase_error_deg": max(
            abs(float(error["fundamental_phase_error_deg"])) for error in errors
        ),
        "worst_raw_normalized_residual_db": max(
            float(error["raw_normalized_residual_db"]) for error in errors
        ),
        "trapezoidal_768khz_high_frequency": {
            "maximum_absolute_gain_error_db": max(
                abs(float(error["fundamental_gain_error_db"]))
                for error in trapezoidal_errors
            ),
            "maximum_absolute_phase_error_deg": max(
                abs(float(error["fundamental_phase_error_deg"]))
                for error in trapezoidal_errors
            ),
        },
        "trapezoidal_384khz_high_frequency": {
            "maximum_absolute_gain_error_db": max(
                abs(float(error["fundamental_gain_error_db"]))
                for error in trapezoidal_384khz_errors
            ),
            "maximum_absolute_phase_error_deg": max(
                abs(float(error["fundamental_phase_error_deg"]))
                for error in trapezoidal_384khz_errors
            ),
        },
        "total_python_nonconvergence_count": sum(
            int(measurement["python_solver"]["nonconvergence_count"])
            for measurement in measurements
        ),
        "total_method_study_nonconvergence_count": sum(
            int(candidate["python_solver"]["nonconvergence_count"])
            for study in high_frequency_method_study
            for candidate in study["candidates"]
        ),
        "measurements": measurements,
        "high_frequency_method_study": high_frequency_method_study,
    }
    if report["total_python_nonconvergence_count"] or report[
        "total_method_study_nonconvergence_count"
    ]:
        raise RuntimeError("analytical model failed to converge in SPICE sweep")
    if report["maximum_absolute_gain_error_db"] > 0.070 or report[
        "maximum_absolute_phase_error_deg"
    ] > 4.8:
        raise RuntimeError("768 kHz backward-Euler error exceeds measured bound")
    trapezoidal_bound = report["trapezoidal_768khz_high_frequency"]
    if trapezoidal_bound["maximum_absolute_gain_error_db"] > 0.012 or (
        trapezoidal_bound["maximum_absolute_phase_error_deg"] > 0.070
    ):
        raise RuntimeError("768 kHz trapezoidal high-frequency bound failed")
    for study in high_frequency_method_study:
        backward_euler = [
            candidate
            for candidate in study["candidates"]
            if candidate["integration_method"] == "backward_euler"
        ]
        phase_error = [
            abs(float(candidate["python_vs_spice"]["fundamental_phase_error_deg"]))
            for candidate in backward_euler
        ]
        if not phase_error[0] > phase_error[1] > phase_error[2]:
            raise RuntimeError("backward-Euler phase error did not improve with rate")
    summary = ROOT / "model" / "generated" / "python_spice_frequency_summary.json"
    summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result = ROOT / "reference" / "results" / "python_spice_frequency.json"
    result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
