from __future__ import annotations

from pathlib import Path
import sys
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.calibration import (
    PCM24_MAX,
    PCM24_MIN,
    input_full_scale_coefficient_q24,
    output_reciprocal_coefficient_q24,
    pcm24_to_q8_24,
    q8_24_to_pcm24,
    round_shift_symmetric,
)


class CalibrationTests(unittest.TestCase):
    def test_symmetric_rounding_ties_away_from_zero(self) -> None:
        self.assertEqual(round_shift_symmetric(4, 3), 1)
        self.assertEqual(round_shift_symmetric(3, 3), 0)
        self.assertEqual(round_shift_symmetric(-4, 3), -1)
        self.assertEqual(round_shift_symmetric(-3, 3), 0)

    def test_pcm_endpoints_map_to_physical_peak_contract(self) -> None:
        peak_q24 = round(0.020 * (1 << 24))
        negative = pcm24_to_q8_24(PCM24_MIN, peak_q24)
        positive = pcm24_to_q8_24(PCM24_MAX, peak_q24)
        self.assertEqual(negative.sample_q24, -peak_q24)
        self.assertIn(positive.sample_q24, (peak_q24 - 1, peak_q24))
        self.assertTrue(negative.pcm_endpoint)
        self.assertTrue(positive.pcm_endpoint)
        self.assertFalse(negative.configuration_error)

    def test_invalid_input_coefficient_mutes_but_preserves_endpoint_flag(self) -> None:
        result = pcm24_to_q8_24(PCM24_MIN, 0)
        self.assertEqual(result.sample_q24, 0)
        self.assertTrue(result.pcm_endpoint)
        self.assertTrue(result.configuration_error)

    def test_output_full_scale_asymmetry_is_explicit(self) -> None:
        reciprocal_q24 = 1 << 23  # 0.5 / V, for 2 V peak full scale.
        positive = q8_24_to_pcm24(2 << 24, reciprocal_q24)
        negative = q8_24_to_pcm24(-(2 << 24), reciprocal_q24)
        self.assertEqual(positive.sample_pcm24, PCM24_MAX)
        self.assertTrue(positive.saturated)
        self.assertEqual(negative.sample_pcm24, PCM24_MIN)
        self.assertFalse(negative.saturated)

    def test_invalid_output_coefficient_mutes_without_saturation(self) -> None:
        result = q8_24_to_pcm24(1 << 24, -1)
        self.assertEqual(result.sample_pcm24, 0)
        self.assertFalse(result.saturated)
        self.assertTrue(result.configuration_error)

    def test_reference_study_coefficients_are_reproducible(self) -> None:
        input_coefficient = input_full_scale_coefficient_q24(
            adc_full_scale_peak_volts=2.0 * (2.0**0.5),
            measured_frontend_gain=10.0 ** (26.0 / 20.0),
        )
        output_coefficient = output_reciprocal_coefficient_q24(
            2.0 * (2.0**0.5)
        )
        self.assertEqual(input_coefficient, 2_378_290)
        self.assertEqual(output_coefficient, 5_931_642)


if __name__ == "__main__":
    unittest.main()
