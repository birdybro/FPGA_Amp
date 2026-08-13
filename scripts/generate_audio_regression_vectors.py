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
    overload = _sine(nominal_index, 1000.0, 0.005)
    burst_start = 1536
    burst_stop = burst_start + 240
    overload[burst_start:burst_stop] += _sine(
        nominal_index[burst_start:burst_stop], 1000.0, 1.5
    )
    pop = _sine(short_index, 1000.0, 0.005)
    pop[768] += 0.020
    pop[769] -= 0.012
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
