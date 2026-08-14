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
    smpte_modulation_analysis,
    sustained_recovery_analysis,
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
    elif kind == "smpte_modulation":
        result["analysis"] = smpte_modulation_analysis(
            output_v,
            sample_rate_hz,
            float(analysis["low_frequency_hz"]),
            float(analysis["high_frequency_hz"]),
            maximum_sideband_order=int(analysis["maximum_sideband_order"]),
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
    elif kind not in ("summary", "paired_impulse", "paired_recovery"):
        raise ValueError(f"unknown analysis kind {kind}")
    return result


def _paired_impulse_measurement(
    vector: dict[str, object], output_v: np.ndarray, control_v: np.ndarray
) -> dict[str, object]:
    if output_v.shape != control_v.shape:
        raise RuntimeError("impulse/control WAV lengths differ")
    event_sample = int(vector["analysis"]["event_sample"])
    residual = output_v - control_v
    output_lsb_v = float(vector["output_full_scale_peak_v"]) / float(1 << 23)
    detection_threshold_v = 4.0 * output_lsb_v
    detected = np.flatnonzero(np.abs(residual) > detection_threshold_v)
    first_detected = None if detected.size == 0 else int(detected[0])
    peak_index = int(np.argmax(np.abs(residual)))
    final_tail = residual[-512:]
    return {
        "control_vector": vector["analysis"]["control_vector"],
        "input_event_sample": event_sample,
        "detection_threshold_v": detection_threshold_v,
        "first_detected_output_sample": first_detected,
        "causal_delay_samples": (
            None if first_detected is None else first_detected - event_sample
        ),
        "pre_event_maximum_absolute_v": float(np.max(np.abs(residual[:event_sample]))),
        "peak_output_sample": peak_index,
        "peak_output_v": float(residual[peak_index]),
        "maximum_absolute_output_v": float(np.max(np.abs(residual))),
        "final_512_sample_tail": signal_summary(final_tail),
    }


def _paired_recovery_measurement(
    vector: dict[str, object], output_v: np.ndarray, control_v: np.ndarray
) -> dict[str, object]:
    if output_v.shape != control_v.shape:
        raise RuntimeError("recovery/control WAV lengths differ")
    analysis = vector["analysis"]
    sample_rate_hz = float(vector["sample_rate_hz"])
    burst_start = int(analysis["burst_start_sample"])
    burst_stop = int(analysis["burst_stop_sample"])
    residual = output_v - control_v
    nominal_tail = control_v[-4800:]
    nominal_rms_v = float(np.sqrt(np.mean(np.square(nominal_tail))))
    threshold_v = 0.10 * nominal_rms_v
    recovery = sustained_recovery_analysis(
        residual,
        sample_rate_hz,
        threshold_v,
        burst_stop,
        window_seconds=float(analysis["rms_window_seconds"]),
    )
    return {
        "control_vector": analysis["control_vector"],
        "input_burst_start_sample": burst_start,
        "input_burst_stop_sample": burst_stop,
        "nominal_control_tail_rms_v": nominal_rms_v,
        "ten_percent_nominal_threshold_v_rms": threshold_v,
        "recovery": recovery,
        "peak_post_burst_deviation_v": float(np.max(np.abs(residual[burst_stop:]))),
        "final_10ms_deviation_rms_v": float(
            np.sqrt(np.mean(np.square(residual[-480:])))
        ),
        "timing_note": (
            "recovery is relative to the input burst stop and therefore retains "
            "the causal interpolation/circuit/decimation delay"
        ),
    }


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
    outputs_by_name: dict[str, np.ndarray] = {}
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
        outputs_by_name[str(vector["name"])] = output_v
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
    manifest_by_name = {str(vector["name"]): vector for vector in manifest["vectors"]}
    impulse_name = "impulse_5mv_one_sample"
    impulse_vector = manifest_by_name[impulse_name]
    impulse_control_name = str(impulse_vector["analysis"]["control_vector"])
    impulse_measurement = _paired_impulse_measurement(
        impulse_vector,
        outputs_by_name[impulse_name],
        outputs_by_name[impulse_control_name],
    )
    by_name[impulse_name]["analysis"] = impulse_measurement
    recovery_name = "recovery_0p5v_250ms"
    recovery_vector = manifest_by_name[recovery_name]
    recovery_control_name = str(recovery_vector["analysis"]["control_vector"])
    recovery_measurement = _paired_recovery_measurement(
        recovery_vector,
        outputs_by_name[recovery_name],
        outputs_by_name[recovery_control_name],
    )
    by_name[recovery_name]["analysis"] = recovery_measurement
    nominal_thd = float(by_name["nominal_1khz"]["analysis"]["thd_percent"])
    low_level_thd = float(by_name["low_level_1khz"]["analysis"]["thd_percent"])
    silence_rms_v = float(by_name["silence"]["full_output"]["rms"])
    smpte_imd_percent = float(
        by_name["smpte_profile_60hz_7khz"]["analysis"]["imd_percent"]
    )
    impulse_delay = impulse_measurement["causal_delay_samples"]
    impulse_peak_v = float(impulse_measurement["maximum_absolute_output_v"])
    recovery_seconds = recovery_measurement["recovery"][
        "recovery_seconds_after_start"
    ]
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
    if not 0.40 <= smpte_imd_percent <= 0.55:
        raise RuntimeError(
            f"SMPTE-profile sideband IMD {smpte_imd_percent:.6f}% is outside "
            "the frozen 0.40..0.55% behavior range"
        )
    if impulse_measurement["pre_event_maximum_absolute_v"] != 0.0:
        raise RuntimeError("impulse residual is nonzero before the input event")
    if impulse_delay is None or not 0 <= int(impulse_delay) <= 128:
        raise RuntimeError(f"impulse response delay {impulse_delay} is outside 0..128 samples")
    if impulse_peak_v <= 0.0001:
        raise RuntimeError(f"impulse response peak {impulse_peak_v:.9f} V is not observable")
    if recovery_seconds is None or not 0.140 <= float(recovery_seconds) <= 0.160:
        raise RuntimeError(
            f"0.5 V paired WAV recovery {recovery_seconds} s is outside 140..160 ms"
        )
    if float(recovery_measurement["final_10ms_deviation_rms_v"]) >= 0.030:
        raise RuntimeError("0.5 V recovery final 10 ms residual exceeds 30 mV RMS")

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
            "smpte_profile_sideband_imd_percent_range": [0.40, 0.55],
            "impulse_causal_delay_samples_range": [0, 128],
            "impulse_minimum_response_peak_v": 0.0001,
            "recovery_0p5v_seconds_after_input_burst_range": [0.140, 0.160],
            "recovery_0p5v_final_10ms_rms_v_limit": 0.030,
        },
        "vectors": reports,
        "artifact_note": "PCM WAVs and per-vector reports are reproducible under build/",
    }
    destination = ROOT / "model" / "generated" / "audio_regression_summary.json"
    destination.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(
        f"audio regression passed: {len(reports)} vectors, "
        f"nominal THD={nominal_thd:.6f}%, low-level THD={low_level_thd:.6f}%, "
        f"profile IMD={smpte_imd_percent:.6f}%, recovery={recovery_seconds:.6f} s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
