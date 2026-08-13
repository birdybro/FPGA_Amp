#!/usr/bin/env python3
"""Process and measure the physically scaled deterministic audio-vector suite."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.audio_analysis import (  # noqa: E402
    fit_tones,
    harmonic_analysis,
    intermodulation_analysis,
    signal_summary,
)
from fpga_amp.audio_io import read_pcm_wav  # noqa: E402


def _process_vector(vector: dict[str, object], output_directory: Path) -> tuple[dict, np.ndarray]:
    name = str(vector["name"])
    output_wav = output_directory / f"{name}.wav"
    report_path = output_directory / f"{name}.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/process_wav.py",
            str(vector["path"]),
            str(output_wav.relative_to(ROOT)),
            "--report",
            str(report_path.relative_to(ROOT)),
            "--mode",
            "banked-terminal-trapezoidal",
            "--input-full-scale-v",
            str(vector["input_full_scale_peak_v"]),
            "--output-full-scale-v",
            str(vector["output_full_scale_peak_v"]),
        ],
        cwd=ROOT,
        check=True,
    )
    process_report = json.loads(report_path.read_text())
    normalized_output = read_pcm_wav(output_wav).samples[:, 0]
    output_v = normalized_output * float(vector["output_full_scale_peak_v"])
    return process_report, output_v


def _measure(vector: dict[str, object], output_v: np.ndarray) -> dict[str, object]:
    analysis = vector["analysis"]
    kind = str(analysis["kind"])
    sample_rate_hz = float(vector["sample_rate_hz"])
    result: dict[str, object] = {
        "full_output": signal_summary(output_v),
        "analysis_kind": kind,
    }
    if kind == "harmonic":
        result["analysis"] = harmonic_analysis(
            output_v,
            sample_rate_hz,
            float(analysis["fundamental_hz"]),
            maximum_harmonic=int(analysis["maximum_harmonic"]),
            start_sample=int(analysis["start_sample"]),
        )
    elif kind == "intermodulation_products":
        result["analysis"] = intermodulation_analysis(
            output_v,
            sample_rate_hz,
            tuple(float(value) for value in analysis["fundamentals_hz"]),
            [float(value) for value in analysis["products_hz"]],
            start_sample=int(analysis["start_sample"]),
        )
    elif kind == "tones":
        result["analysis"] = fit_tones(
            output_v,
            sample_rate_hz,
            [float(value) for value in analysis["frequencies_hz"]],
            start_sample=int(analysis["start_sample"]),
        )
    elif kind == "overload":
        burst_start = int(analysis["burst_start_sample"])
        burst_stop = int(analysis["burst_stop_sample"])
        tail_start = int(analysis["tail_start_sample"])
        result["analysis"] = {
            "input_burst_start_sample": burst_start,
            "input_burst_stop_sample": burst_stop,
            "burst_window_output": signal_summary(output_v[burst_start:burst_stop]),
            "late_tail_output": signal_summary(output_v[tail_start:]),
        }
    elif kind == "transient":
        event_start = int(analysis["event_start_sample"])
        event_stop = int(analysis["event_stop_sample"])
        window_start = max(0, event_start - 64)
        window_stop = min(output_v.size, event_stop + 512)
        result["analysis"] = {
            "input_event_start_sample": event_start,
            "input_event_stop_sample": event_stop,
            "output_observation_start_sample": window_start,
            "output_observation_stop_sample": window_stop,
            "output_observation": signal_summary(output_v[window_start:window_stop]),
        }
    elif kind != "summary":
        raise ValueError(f"unknown analysis kind {kind}")
    return result


def main() -> int:
    subprocess.run(
        [sys.executable, "scripts/generate_audio_regression_vectors.py"],
        cwd=ROOT,
        check=True,
    )
    manifest_path = (
        ROOT / "model" / "generated" / "audio_regression_vector_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text())
    output_directory = ROOT / "build" / "audio_regression" / "outputs"
    output_directory.mkdir(parents=True, exist_ok=True)

    reports: list[dict[str, object]] = []
    total_diagnostics = 0
    total_output_clips = 0
    for vector in manifest["vectors"]:
        process_report, output_v = _process_vector(vector, output_directory)
        diagnostic_count = sum(
            sum(channel["diagnostics"].values())
            for channel in process_report["channels"]
        )
        output_clips = int(
            process_report["output_wav_write"]["clipped_sample_count"]
        )
        total_diagnostics += diagnostic_count
        total_output_clips += output_clips
        reports.append(
            {
                "name": vector["name"],
                "description": vector["description"],
                "frame_count": vector["frame_count"],
                "input_full_scale_peak_v": vector["input_full_scale_peak_v"],
                "output_full_scale_peak_v": vector["output_full_scale_peak_v"],
                "fixed_model_diagnostic_count": diagnostic_count,
                "output_wav_clip_count": output_clips,
                **_measure(vector, output_v),
            }
        )
        print(
            f"measured {vector['name']}: diagnostics={diagnostic_count}, "
            f"clips={output_clips}"
        )

    by_name = {str(report["name"]): report for report in reports}
    nominal_thd = float(by_name["nominal_1khz"]["analysis"]["thd_percent"])
    low_level_thd = float(by_name["low_level_1khz"]["analysis"]["thd_percent"])
    silence_rms_v = float(by_name["silence"]["full_output"]["rms"])
    if total_diagnostics != 0:
        raise RuntimeError(f"audio suite produced {total_diagnostics} fixed-model events")
    if total_output_clips != 0:
        raise RuntimeError(f"audio suite clipped {total_output_clips} output WAV samples")
    if nominal_thd >= 0.1:
        raise RuntimeError(f"nominal WAV THD {nominal_thd:.6f}% exceeds 0.1% gate")
    if low_level_thd >= 0.2:
        raise RuntimeError(f"low-level WAV THD {low_level_thd:.6f}% exceeds 0.2% gate")
    if silence_rms_v >= 0.001:
        raise RuntimeError(f"initialized silence output {silence_rms_v:.9f} V exceeds 1 mV")

    summary = {
        "schema_version": 1,
        "model_mode": "banked-terminal-trapezoidal",
        "category": "FPGA approximation verification; no creative processing",
        "vector_count": len(reports),
        "total_external_frames": sum(int(report["frame_count"]) for report in reports),
        "total_internal_model_updates": 16
        * sum(int(report["frame_count"]) for report in reports),
        "total_fixed_model_diagnostic_count": total_diagnostics,
        "total_output_wav_clip_count": total_output_clips,
        "acceptance": {
            "nominal_1khz_thd_percent_limit": 0.1,
            "low_level_1khz_thd_percent_limit": 0.2,
            "silence_rms_v_limit": 0.001,
        },
        "vectors": reports,
        "artifact_note": "PCM WAVs and per-vector reports are reproducible under build/",
    }
    destination = ROOT / "model" / "generated" / "audio_regression_summary.json"
    destination.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(
        f"audio regression passed: {len(reports)} vectors, "
        f"nominal THD={nominal_thd:.6f}%, low-level THD={low_level_thd:.6f}%"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
