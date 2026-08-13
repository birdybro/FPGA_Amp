#!/usr/bin/env python3
"""Compare one channel of two PCM WAV files with explicit alignment policy."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.audio_io import read_pcm_wav, write_pcm_wav  # noqa: E402
from fpga_amp.null_compare import compare_signals, windowed_spectrum  # noqa: E402


def _dbfs(value: np.ndarray) -> np.ndarray:
    return 20.0 * np.log10(np.maximum(value, 1.0e-15))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--max-lag", type=int, default=4096)
    parser.add_argument("--no-latency-align", action="store_true")
    parser.add_argument("--fractional-delay", action="store_true")
    parser.add_argument("--gain-align", action="store_true")
    parser.add_argument("--residual-wav", type=Path)
    parser.add_argument("--spectrum-csv", type=Path)
    parser.add_argument("--residual-width", type=int, choices=(16, 24, 32), default=24)
    args = parser.parse_args()

    reference = read_pcm_wav(args.reference)
    candidate = read_pcm_wav(args.candidate)
    if reference.sample_rate_hz != candidate.sample_rate_hz:
        parser.error(
            f"sample rates differ: {reference.sample_rate_hz} vs "
            f"{candidate.sample_rate_hz} Hz"
        )
    if not 0 <= args.channel < reference.channel_count:
        parser.error("--channel is outside the reference channel count")
    if not 0 <= args.channel < candidate.channel_count:
        parser.error("--channel is outside the candidate channel count")
    if args.fractional_delay and args.no_latency_align:
        parser.error("--fractional-delay requires latency alignment")

    comparison = compare_signals(
        reference.samples[:, args.channel],
        candidate.samples[:, args.channel],
        max_lag_samples=args.max_lag,
        align_latency=not args.no_latency_align,
        fractional_delay=args.fractional_delay,
        align_gain=args.gain_align,
    )
    report = {
        "schema_version": 1,
        "reference_wav": str(args.reference),
        "candidate_wav": str(args.candidate),
        "sample_rate_hz": reference.sample_rate_hz,
        "channel": args.channel,
        **comparison.report,
    }

    if args.residual_wav is not None:
        residual_write = write_pcm_wav(
            args.residual_wav,
            comparison.residual,
            reference.sample_rate_hz,
            sample_width_bits=args.residual_width,
        )
        report["residual_wav"] = {
            "path": str(args.residual_wav),
            **residual_write,
        }
    if args.spectrum_csv is not None:
        frequencies, ref_fft, candidate_fft, residual_fft = windowed_spectrum(
            comparison.reference_aligned,
            comparison.candidate_aligned,
            reference.sample_rate_hz,
        )
        args.spectrum_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.spectrum_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ("frequency_hz", "reference_dbfs", "candidate_dbfs", "residual_dbfs")
            )
            writer.writerows(
                zip(
                    frequencies,
                    _dbfs(ref_fft),
                    _dbfs(candidate_fft),
                    _dbfs(residual_fft),
                )
            )
        report["spectrum_csv"] = str(args.spectrum_csv)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    final = report["final"]
    transformations = report["transformations"]
    print(
        f"lag={transformations['estimated_total_latency_samples']:.6f} samples, "
        f"applied_gain={transformations['applied_candidate_gain']:.9f}, "
        f"residual={final['normalized_residual_db']:.3f} dB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
