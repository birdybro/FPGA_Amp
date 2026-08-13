#!/usr/bin/env python3
"""Exercise the fixed V1 WAV path and null CLI with a licensed synthetic vector."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.audio_io import read_pcm_wav, write_pcm_wav  # noqa: E402


def _run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    build = ROOT / "build" / "wav_null_regression"
    build.mkdir(parents=True, exist_ok=True)
    sample_rate_hz = 48_000
    frame_count = 1024
    index = np.arange(frame_count, dtype=np.float64)
    # Original synthetic stimulus: nominal MM tone, warp, multitone, and a
    # short record-pop-like transient. The WAV full scale maps to 20 mV peak.
    input_normalized = (
        0.22 * np.sin(2.0 * np.pi * 997.0 * index / sample_rate_hz)
        + 0.035 * np.sin(2.0 * np.pi * 73.0 * index / sample_rate_hz)
        + 0.020 * np.sin(2.0 * np.pi * 7013.0 * index / sample_rate_hz)
        + 0.015 * np.sin(2.0 * np.pi * 11.0 * index / sample_rate_hz)
    )
    input_normalized[211] += 0.30
    input_normalized[212] -= 0.18

    input_wav = build / "v1_input.wav"
    output_wav = build / "v1_output_reference.wav"
    process_report_path = build / "v1_process_report.json"
    input_write = write_pcm_wav(input_wav, input_normalized, sample_rate_hz)
    _run(
        [
            sys.executable,
            "scripts/process_wav.py",
            str(input_wav.relative_to(ROOT)),
            str(output_wav.relative_to(ROOT)),
            "--report",
            str(process_report_path.relative_to(ROOT)),
            "--mode",
            "banked-terminal-trapezoidal",
            "--input-full-scale-v",
            "0.02",
            "--output-full-scale-v",
            "2.0",
        ]
    )
    process_report = json.loads(process_report_path.read_text())

    reference = read_pcm_wav(output_wav).samples[:, 0]
    known_delay_samples = 23
    delayed = np.zeros_like(reference)
    delayed[known_delay_samples:] = reference[:-known_delay_samples]
    # Emulate an independently captured path with known latency, -0.265 dB
    # gain, and a deliberately retained weak cubic difference.
    candidate = 0.97 * delayed + 1.0e-4 * np.power(delayed, 3)
    candidate_wav = build / "v1_output_candidate.wav"
    candidate_write = write_pcm_wav(candidate_wav, candidate, sample_rate_hz)
    null_report_path = build / "v1_null_report.json"
    residual_wav = build / "v1_residual.wav"
    spectrum_csv = build / "v1_residual_spectrum.csv"
    _run(
        [
            sys.executable,
            "scripts/compare_wav.py",
            str(output_wav.relative_to(ROOT)),
            str(candidate_wav.relative_to(ROOT)),
            "--report",
            str(null_report_path.relative_to(ROOT)),
            "--max-lag",
            "64",
            "--gain-align",
            "--residual-wav",
            str(residual_wav.relative_to(ROOT)),
            "--spectrum-csv",
            str(spectrum_csv.relative_to(ROOT)),
        ]
    )
    null_report = json.loads(null_report_path.read_text())

    diagnostic_total = sum(
        sum(channel["diagnostics"].values()) for channel in process_report["channels"]
    )
    measured_delay = null_report["transformations"][
        "estimated_integer_latency_samples"
    ]
    final_residual_db = null_report["final"]["normalized_residual_db"]
    if input_write["clipped_sample_count"] != 0:
        raise RuntimeError("synthetic input clipped while being written")
    if process_report["input_fixed_q8_24_clip_count"] != 0 or diagnostic_total != 0:
        raise RuntimeError("fixed V1 WAV processing reported a diagnostic event")
    if process_report["output_wav_write"]["clipped_sample_count"] != 0:
        raise RuntimeError("V1 output clipped at the explicit 2 V peak WAV mapping")
    if candidate_write["clipped_sample_count"] != 0:
        raise RuntimeError("synthetic capture candidate clipped")
    if measured_delay != known_delay_samples:
        raise RuntimeError(
            f"latency estimate {measured_delay} did not recover {known_delay_samples}"
        )
    if final_residual_db > -70.0:
        raise RuntimeError(f"aligned synthetic null is only {final_residual_db:.3f} dB")

    summary = {
        "schema_version": 1,
        "stimulus": {
            "license": "generated in-repository; no third-party audio",
            "sample_rate_hz": sample_rate_hz,
            "frame_count": frame_count,
            "input_full_scale_peak_v": 0.02,
            "components_hz": [11.0, 73.0, 997.0, 7013.0],
            "synthetic_pop_samples": [211, 212],
        },
        "v1_processing": {
            "mode": process_report["mode"],
            "output_full_scale_peak_v": process_report["output_full_scale_peak_v"],
            "diagnostic_total": diagnostic_total,
            "output_wav_clip_count": process_report["output_wav_write"][
                "clipped_sample_count"
            ],
        },
        "null_fixture": {
            "known_integer_latency_samples": known_delay_samples,
            "measured_integer_latency_samples": measured_delay,
            "known_candidate_gain": 0.97,
            "reported_gain_to_apply": null_report["latency_aligned_before_gain"][
                "least_squares_gain_to_apply"
            ],
            "raw_zero_lag_normalized_residual_db": null_report["raw_zero_lag"][
                "normalized_residual_db"
            ],
            "latency_aligned_before_gain_normalized_residual_db": null_report[
                "latency_aligned_before_gain"
            ]["normalized_residual_db"],
            "gain_aligned_normalized_residual_db": final_residual_db,
            "fractional_delay_alignment_enabled": null_report["transformations"][
                "fractional_delay_alignment_enabled"
            ],
            "residual_wav_clip_count": null_report["residual_wav"][
                "clipped_sample_count"
            ],
        },
        "artifacts": {
            "note": "WAV/CSV/report artifacts are reproducible under build/ and are not tracked",
            "process_report": str(process_report_path.relative_to(ROOT)),
            "null_report": str(null_report_path.relative_to(ROOT)),
            "residual_spectrum": str(spectrum_csv.relative_to(ROOT)),
        },
    }
    destination = ROOT / "model" / "generated" / "wav_null_regression_summary.json"
    destination.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(
        f"WAV/null regression: {frame_count} V1 frames, diagnostics={diagnostic_total}, "
        f"lag={measured_delay}, final residual={final_residual_db:.3f} dB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
