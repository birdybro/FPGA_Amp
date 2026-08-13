"""Known-signal tests for harmonic and intermodulation measurements."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.audio_analysis import (  # noqa: E402
    fit_tones,
    harmonic_analysis,
    intermodulation_analysis,
    signal_summary,
)


class AudioAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_rate_hz = 48_000.0
        self.indices = np.arange(4096, dtype=np.float64)

    def _sine(self, frequency_hz: float, peak: float, phase: float = 0.0) -> np.ndarray:
        return peak * np.sin(
            2.0 * np.pi * frequency_hz * self.indices / self.sample_rate_hz + phase
        )

    def test_noncoherent_tone_fit_recovers_amplitude_phase_and_dc(self) -> None:
        values = 0.031 + self._sine(997.3, 0.42, 0.37)
        result = fit_tones(values, self.sample_rate_hz, [997.3])
        tone = result["tones"][0]
        self.assertAlmostEqual(result["dc"], 0.031, places=12)
        self.assertAlmostEqual(tone["peak_amplitude"], 0.42, places=12)
        self.assertAlmostEqual(tone["phase_deg"], np.degrees(0.37), places=10)
        self.assertLess(result["normalized_residual_db"], -250.0)

    def test_harmonic_analysis_reports_known_thd(self) -> None:
        values = (
            self._sine(1000.0, 0.5)
            + self._sine(2000.0, 0.01, 0.2)
            + self._sine(3000.0, 0.005, -0.4)
        )
        result = harmonic_analysis(
            values, self.sample_rate_hz, 1000.0, maximum_harmonic=5
        )
        expected = np.hypot(0.01, 0.005) / 0.5
        self.assertAlmostEqual(result["thd_ratio"], expected, places=12)
        self.assertAlmostEqual(result["thd_percent"], 100.0 * expected, places=10)

    def test_selected_intermodulation_products_are_not_renamed_as_standard(self) -> None:
        values = (
            self._sine(19_000.0, 0.2)
            + self._sine(20_000.0, 0.2, 0.1)
            + self._sine(1000.0, 0.002)
            + self._sine(18_000.0, 0.001)
        )
        result = intermodulation_analysis(
            values,
            self.sample_rate_hz,
            (19_000.0, 20_000.0),
            [1000.0, 18_000.0, 21_000.0],
        )
        amplitudes = [tone["peak_amplitude"] for tone in result["tones"]]
        self.assertAlmostEqual(amplitudes[2], 0.002, places=12)
        self.assertAlmostEqual(amplitudes[3], 0.001, places=12)
        self.assertIn("not labeled", result["note"])

    def test_signal_summary_preserves_signed_extrema(self) -> None:
        result = signal_summary(np.array([-0.75, -0.25, 0.25, 0.5]))
        self.assertEqual(result["minimum"], -0.75)
        self.assertEqual(result["maximum"], 0.5)
        self.assertEqual(result["maximum_absolute"], 0.75)

    def test_harmonic_analysis_rejects_nonphysical_fundamental(self) -> None:
        with self.assertRaisesRegex(ValueError, "between DC and Nyquist"):
            harmonic_analysis(np.zeros(128), self.sample_rate_hz, 0.0)


if __name__ == "__main__":
    unittest.main()
