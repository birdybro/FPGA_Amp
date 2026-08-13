#!/usr/bin/env python3
"""Run PCM WAV audio through the exact fixed-point V1 phono stream."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.audio_io import read_pcm_wav, write_pcm_wav  # noqa: E402
from fpga_amp.stream import EXTERNAL_SAMPLE_RATE_HZ, compose_fixed_wide_stream  # noqa: E402


MODES = {
    "wide-backward-euler": {},
    "wide-trapezoidal": {"trapezoidal": True},
    "banked-terminal-backward-euler": {"banked": True, "terminal_correction": True},
    "banked-terminal-trapezoidal": {
        "trapezoidal": True,
        "banked": True,
        "terminal_correction": True,
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--mode", choices=tuple(MODES), required=True)
    parser.add_argument("--input-full-scale-v", type=float, required=True)
    parser.add_argument("--output-full-scale-v", type=float, required=True)
    parser.add_argument("--output-width", type=int, choices=(16, 24, 32), default=24)
    args = parser.parse_args()
    if args.input_full_scale_v <= 0.0 or args.output_full_scale_v <= 0.0:
        parser.error("full-scale voltages must be positive peak values")

    audio = read_pcm_wav(args.input)
    if audio.sample_rate_hz != int(EXTERNAL_SAMPLE_RATE_HZ):
        parser.error(
            f"V1 fixed stream requires {int(EXTERNAL_SAMPLE_RATE_HZ)} Hz input; "
            f"received {audio.sample_rate_hz} Hz"
        )
    input_q24_unbounded = np.rint(
        audio.samples * args.input_full_scale_v * float(1 << 24)
    )
    input_fixed_clip_count = int(
        np.count_nonzero(
            (input_q24_unbounded < -(1 << 31))
            | (input_q24_unbounded > (1 << 31) - 1)
        )
    )
    input_q24 = np.clip(
        input_q24_unbounded, -(1 << 31), (1 << 31) - 1
    ).astype(np.int64)

    output_q24 = np.empty_like(input_q24)
    channel_reports: list[dict[str, object]] = []
    for channel in range(audio.channel_count):
        result = compose_fixed_wide_stream(
            input_q24[:, channel], **MODES[args.mode]
        )
        output_q24[:, channel] = result.output_q24
        channel_reports.append(
            {
                "channel": channel,
                "diagnostics": result.diagnostic_counts,
                "maximum_absolute_internal_input_q24": int(
                    np.max(np.abs(result.internal_input_q24))
                ),
                "maximum_absolute_circuit_output_q24": int(
                    np.max(np.abs(result.circuit_output_q24))
                ),
            }
        )

    output_normalized = (
        output_q24.astype(np.float64)
        / float(1 << 24)
        / args.output_full_scale_v
    )
    wav_write = write_pcm_wav(
        args.output,
        output_normalized,
        audio.sample_rate_hz,
        sample_width_bits=args.output_width,
    )
    report = {
        "schema_version": 1,
        "category": "FPGA approximation of frozen V1 reference circuit",
        "input_wav": str(args.input),
        "output_wav": str(args.output),
        "mode": args.mode,
        "sample_rate_hz": audio.sample_rate_hz,
        "frame_count": audio.frame_count,
        "channel_count": audio.channel_count,
        "input_full_scale_peak_v": args.input_full_scale_v,
        "output_full_scale_peak_v": args.output_full_scale_v,
        "scaling_note": (
            "WAV full-scale mappings are explicit interface conversions; no "
            "normalization or gain fitting changes the modeled circuit"
        ),
        "input_fixed_q8_24_clip_count": input_fixed_clip_count,
        "output_wav_write": wav_write,
        "channels": channel_reports,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    diagnostic_total = sum(
        sum(int(value) for value in channel["diagnostics"].values())
        for channel in channel_reports
    )
    print(
        f"processed {audio.frame_count} frames / {audio.channel_count} channels; "
        f"model diagnostics={diagnostic_total}, WAV clips={wav_write['clipped_sample_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
