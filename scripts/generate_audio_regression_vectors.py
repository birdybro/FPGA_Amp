#!/usr/bin/env python3
"""Generate original, physically scaled 48 kHz V1 audio regression WAVs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.audio_io import write_pcm_wav  # noqa: E402


SAMPLE_RATE_HZ = 48_000


def _sine(indices: np.ndarray, frequency_hz: float, peak_v: float) -> np.ndarray:
    return peak_v * np.sin(2.0 * np.pi * frequency_hz * indices / SAMPLE_RATE_HZ)


def _log_sweep(frame_count: int, start_hz: float, stop_hz: float, peak_v: float) -> np.ndarray:
    time_s = np.arange(frame_count, dtype=np.float64) / SAMPLE_RATE_HZ
    duration_s = frame_count / SAMPLE_RATE_HZ
    ratio = stop_hz / start_hz
    phase = (
        2.0
        * np.pi
        * start_hz
        * duration_s
        / np.log(ratio)
        * (np.power(ratio, time_s / duration_s) - 1.0)
    )
    return peak_v * np.sin(phase)


def _vectors() -> list[dict[str, object]]:
    nominal_index = np.arange(4096, dtype=np.float64)
    short_index = np.arange(2048, dtype=np.float64)
    smpte_index = np.arange(4800, dtype=np.float64)
    long_index = np.arange(12_000, dtype=np.float64)
    overload = _sine(nominal_index, 1000.0, 0.005)
    burst_start = 1536
    burst_stop = burst_start + 240
    overload[burst_start:burst_stop] += _sine(
        nominal_index[burst_start:burst_stop], 1000.0, 1.5
    )
    pop = _sine(short_index, 1000.0, 0.005)
    pop[768] += 0.020
    pop[769] -= 0.012
    impulse_control = np.zeros(4096, dtype=np.float64)
    impulse = impulse_control.copy()
    impulse_event_sample = 1024
    impulse[impulse_event_sample] = 0.005
    recovery_control = _sine(long_index, 1000.0, 0.005)
    recovery = recovery_control.copy()
    recovery_burst_start = 480
    recovery_burst_stop = 720
    recovery[recovery_burst_start:recovery_burst_stop] = _sine(
        long_index[recovery_burst_start:recovery_burst_stop], 1000.0, 0.500
    )
    return [
        {
            "name": "silence",
            "description": "digital silence from initialized physical DC state",
            "samples_v": np.zeros(1024, dtype=np.float64),
            "input_full_scale_peak_v": 0.02,
            "output_full_scale_peak_v": 2.0,
            "analysis": {"kind": "summary"},
        },
        {
            "name": "nominal_1khz",
            "description": "nominal 5 mV-peak MM sine",
            "samples_v": _sine(nominal_index, 1000.0, 0.005),
            "input_full_scale_peak_v": 0.02,
            "output_full_scale_peak_v": 2.0,
            "analysis": {
                "kind": "harmonic",
                "fundamental_hz": 1000.0,
                "maximum_harmonic": 10,
                "start_sample": 2048,
            },
        },
        {
            "name": "low_level_1khz",
            "description": "0.5 mV-peak low-level MM sine",
            "samples_v": _sine(nominal_index, 1000.0, 0.0005),
            "input_full_scale_peak_v": 0.002,
            "output_full_scale_peak_v": 0.5,
            "analysis": {
                "kind": "harmonic",
                "fundamental_hz": 1000.0,
                "maximum_harmonic": 10,
                "start_sample": 2048,
            },
        },
        {
            "name": "ccif_like_19_20khz",
            "description": "equal 2.5 mV-peak 19/20 kHz tones; product amplitudes only",
            "samples_v": _sine(nominal_index, 19_000.0, 0.0025)
            + _sine(nominal_index, 20_000.0, 0.0025),
            "input_full_scale_peak_v": 0.02,
            "output_full_scale_peak_v": 2.0,
            "analysis": {
                "kind": "intermodulation_products",
                "fundamentals_hz": [19_000.0, 20_000.0],
                "products_hz": [1000.0, 18_000.0, 21_000.0],
                "start_sample": 2048,
            },
        },
        {
            "name": "smpte_profile_60hz_7khz",
            "description": (
                "SMPTE RP 120-style 60 Hz/7 kHz tones at 4:1 peak ratio; "
                "sideband-fit profile, not analyzer-conformance claim"
            ),
            "samples_v": _sine(smpte_index, 60.0, 0.004)
            + _sine(smpte_index, 7000.0, 0.001),
            "input_full_scale_peak_v": 0.01,
            "output_full_scale_peak_v": 4.0,
            "analysis": {
                "kind": "smpte_modulation",
                "low_frequency_hz": 60.0,
                "high_frequency_hz": 7000.0,
                "input_peak_ratio": 4.0,
                "maximum_sideband_order": 2,
                "start_sample": 2400,
            },
        },
        {
            "name": "multitone_100_1k_10k",
            "description": "three simultaneous 1.5 mV-peak audio-band tones",
            "samples_v": _sine(nominal_index, 100.0, 0.0015)
            + _sine(nominal_index, 1000.0, 0.0015)
            + _sine(nominal_index, 10_000.0, 0.0015),
            "input_full_scale_peak_v": 0.02,
            "output_full_scale_peak_v": 2.0,
            "analysis": {
                "kind": "tones",
                "frequencies_hz": [100.0, 1000.0, 10_000.0],
                "start_sample": 2048,
            },
        },
        {
            "name": "warp_11hz_plus_1khz",
            "description": "5 mV-peak infrasonic warp plus 1 mV-peak program tone",
            "samples_v": _sine(nominal_index, 11.0, 0.005)
            + _sine(nominal_index, 1000.0, 0.001),
            "input_full_scale_peak_v": 0.02,
            "output_full_scale_peak_v": 8.0,
            "analysis": {
                "kind": "tones",
                "frequencies_hz": [11.0, 1000.0],
                "start_sample": 2048,
            },
        },
        {
            "name": "synthetic_record_pop",
            "description": "nominal tone with +20/-12 mV adjacent-sample transient",
            "samples_v": pop,
            "input_full_scale_peak_v": 0.05,
            "output_full_scale_peak_v": 8.0,
            "analysis": {
                "kind": "transient",
                "event_start_sample": 768,
                "event_stop_sample": 770,
            },
        },
        {
            "name": "impulse_control_silence",
            "description": "matched silence control for differential impulse analysis",
            "samples_v": impulse_control,
            "input_full_scale_peak_v": 0.02,
            "output_full_scale_peak_v": 8.0,
            "analysis": {"kind": "summary"},
        },
        {
            "name": "impulse_5mv_one_sample",
            "description": "single 5 mV input sample with matched silence control",
            "samples_v": impulse,
            "input_full_scale_peak_v": 0.02,
            "output_full_scale_peak_v": 8.0,
            "analysis": {
                "kind": "paired_impulse",
                "control_vector": "impulse_control_silence",
                "event_sample": impulse_event_sample,
            },
        },
        {
            "name": "log_sweep_20hz_20khz",
            "description": "100 ms logarithmic 20 Hz to 20 kHz sweep at 5 mV peak",
            "samples_v": _log_sweep(4800, 20.0, 20_000.0, 0.005),
            "input_full_scale_peak_v": 0.02,
            "output_full_scale_peak_v": 8.0,
            "analysis": {"kind": "summary"},
        },
        {
            "name": "overload_1p5v_burst",
            "description": "nominal tone plus 5 ms, 1.5 V-peak grid-conduction burst",
            "samples_v": overload,
            "input_full_scale_peak_v": 2.0,
            "output_full_scale_peak_v": 128.0,
            "analysis": {
                "kind": "overload",
                "burst_start_sample": burst_start,
                "burst_stop_sample": burst_stop,
                "tail_start_sample": 3072,
            },
        },
        {
            "name": "recovery_control_250ms",
            "description": "undisturbed 5 mV-peak control for paired recovery analysis",
            "samples_v": recovery_control,
            "input_full_scale_peak_v": 1.0,
            "output_full_scale_peak_v": 128.0,
            "analysis": {"kind": "summary"},
        },
        {
            "name": "recovery_0p5v_250ms",
            "description": (
                "5 ms, 0.5 V-peak accepted-range burst with 235 ms observation"
            ),
            "samples_v": recovery,
            "input_full_scale_peak_v": 1.0,
            "output_full_scale_peak_v": 128.0,
            "analysis": {
                "kind": "paired_recovery",
                "control_vector": "recovery_control_250ms",
                "burst_start_sample": recovery_burst_start,
                "burst_stop_sample": recovery_burst_stop,
                "rms_window_seconds": 0.001,
            },
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=ROOT / "build" / "audio_regression" / "inputs",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "model" / "generated" / "audio_regression_vector_manifest.json",
    )
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)

    manifest_vectors: list[dict[str, object]] = []
    for vector in _vectors():
        samples_v = np.asarray(vector.pop("samples_v"), dtype=np.float64)
        input_full_scale_v = float(vector["input_full_scale_peak_v"])
        wav_path = args.output_directory / f"{vector['name']}.wav"
        write_report = write_pcm_wav(
            wav_path,
            samples_v / input_full_scale_v,
            SAMPLE_RATE_HZ,
            sample_width_bits=24,
        )
        if write_report["clipped_sample_count"] != 0:
            raise RuntimeError(f"vector {vector['name']} clipped its input WAV")
        manifest_vectors.append(
            {
                **vector,
                "path": str(wav_path.relative_to(ROOT)),
                "sample_rate_hz": SAMPLE_RATE_HZ,
                "frame_count": int(samples_v.size),
                "sample_width_bits": 24,
                "maximum_absolute_input_v": float(np.max(np.abs(samples_v))),
                "input_wav_clip_count": write_report["clipped_sample_count"],
            }
        )

    manifest = {
        "schema_version": 1,
        "license": "all stimuli are generated by this repository; no third-party audio",
        "category": "deterministic verification stimuli, not a reference-circuit change",
        "vectors": manifest_vectors,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    print(
        f"generated {len(manifest_vectors)} PCM24 vectors / "
        f"{sum(vector['frame_count'] for vector in manifest_vectors)} frames"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
