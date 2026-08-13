"""Regression tests for WAV scaling and explicit null transformations."""

from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import unittest

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.audio_io import read_pcm_wav, write_pcm_wav
from fpga_amp.null_compare import compare_signals, windowed_spectrum


class AudioIoTests(unittest.TestCase):
    def test_pcm24_stereo_round_trip_is_within_one_lsb(self) -> None:
        samples = np.array(
            [
                [-1.0, 0.999999],
                [-0.75, 0.125],
                [0.0, -0.25],
                [0.3123456, -0.8123456],
            ],
            dtype=np.float64,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roundtrip.wav"
            report = write_pcm_wav(path, samples, 48_000, sample_width_bits=24)
            decoded = read_pcm_wav(path)
        self.assertEqual(report["clipped_sample_count"], 0)
        self.assertEqual(decoded.sample_rate_hz, 48_000)
        self.assertEqual(decoded.sample_width_bits, 24)
        self.assertEqual(decoded.samples.shape, samples.shape)
        self.assertLessEqual(
            float(np.max(np.abs(decoded.samples - samples))), 0.5 / float(1 << 23)
        )

    def test_wav_writer_reports_positive_and_negative_clips(self) -> None:
        samples = np.array([-1.1, -1.0, 0.0, 1.0, 1.1], dtype=np.float64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clips.wav"
            report = write_pcm_wav(path, samples, 48_000, sample_width_bits=16)
            decoded = read_pcm_wav(path)
        self.assertEqual(report["clipped_sample_count"], 3)
        self.assertEqual(float(decoded.samples[0, 0]), -1.0)
        self.assertEqual(float(decoded.samples[-1, 0]), (32767.0 / 32768.0))


class NullComparisonTests(unittest.TestCase):
    @staticmethod
    def _reference() -> np.ndarray:
        generator = np.random.default_rng(0x12A7)
        noise = generator.normal(0.0, 0.1, 4096)
        return np.convolve(noise, np.array([0.1, 0.2, 0.4, 0.2, 0.1]), mode="same")

    def test_integer_latency_and_gain_are_recovered_without_dc_fit(self) -> None:
        reference = self._reference()
        candidate = np.zeros_like(reference)
        candidate[37:] = 0.97 * reference[:-37]
        comparison = compare_signals(
            reference,
            candidate,
            max_lag_samples=64,
            align_gain=True,
        )
        transforms = comparison.report["transformations"]
        self.assertEqual(transforms["estimated_integer_latency_samples"], 37)
        self.assertAlmostEqual(transforms["applied_candidate_gain"], 1.0 / 0.97, places=12)
        self.assertLess(comparison.report["final"]["normalized_residual_db"], -280.0)
        self.assertGreater(comparison.report["raw_zero_lag"]["normalized_residual_db"], -10.0)

    def test_default_lag_bound_retains_meaningful_overlap(self) -> None:
        reference = self._reference()
        candidate = np.zeros_like(reference)
        candidate[37:] = reference[:-37]
        comparison = compare_signals(reference, candidate)
        transforms = comparison.report["transformations"]
        self.assertEqual(transforms["estimated_integer_latency_samples"], 37)
        self.assertEqual(transforms["minimum_latency_overlap_samples"], 2048)
        self.assertEqual(transforms["maximum_lag_searched_samples"], 2048)

    def test_long_latency_search_uses_fft_dot_products(self) -> None:
        generator = np.random.default_rng(0xF17)
        reference = generator.normal(0.0, 0.05, 32768)
        candidate = np.zeros_like(reference)
        candidate[123:] = reference[:-123]
        comparison = compare_signals(
            reference, candidate, max_lag_samples=256
        )
        transforms = comparison.report["transformations"]
        self.assertEqual(transforms["estimated_integer_latency_samples"], 123)
        self.assertIn("FFT", transforms["latency_estimation_method"])

    def test_default_never_gain_normalizes(self) -> None:
        reference = self._reference()
        comparison = compare_signals(reference, 0.5 * reference, max_lag_samples=0)
        transforms = comparison.report["transformations"]
        self.assertFalse(transforms["gain_alignment_enabled"])
        self.assertEqual(transforms["applied_candidate_gain"], 1.0)
        self.assertAlmostEqual(
            comparison.report["final"]["normalized_residual_db"],
            20.0 * np.log10(0.5),
            places=12,
        )

    def test_fractional_latency_is_labeled_and_bounded(self) -> None:
        reference = self._reference()
        indices = np.arange(reference.size, dtype=np.float64)
        candidate = np.interp(indices - 17.25, indices, reference, left=0.0, right=0.0)
        comparison = compare_signals(
            reference,
            candidate,
            max_lag_samples=32,
            fractional_delay=True,
        )
        transforms = comparison.report["transformations"]
        self.assertTrue(transforms["fractional_delay_alignment_enabled"])
        self.assertIn("linear interpolation", transforms["fractional_delay_method"])
        self.assertAlmostEqual(
            transforms["estimated_total_latency_samples"], 17.25, delta=0.10
        )

    def test_spectrum_preserves_frequency_axis_and_residual(self) -> None:
        sample_rate = 48_000.0
        index = np.arange(4096, dtype=np.float64)
        reference = 0.25 * np.sin(2.0 * np.pi * 1000.0 * index / sample_rate)
        frequencies, ref_fft, candidate_fft, residual_fft = windowed_spectrum(
            reference, reference, sample_rate
        )
        self.assertEqual(frequencies.size, 2049)
        self.assertEqual(ref_fft.shape, candidate_fft.shape)
        self.assertEqual(ref_fft.shape, residual_fft.shape)
        self.assertEqual(float(np.max(residual_fft)), 0.0)

    def test_silence_has_finite_json_and_no_spurious_latency(self) -> None:
        comparison = compare_signals(np.zeros(128), np.zeros(128))
        transforms = comparison.report["transformations"]
        self.assertEqual(transforms["estimated_integer_latency_samples"], 0)
        self.assertFalse(transforms["latency_identifiable"])
        self.assertEqual(comparison.report["final"]["normalized_residual_db"], -300.0)
        json.dumps(comparison.report, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
