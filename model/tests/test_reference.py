from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.cartridge import CartridgeModel  # noqa: E402
from fpga_amp.fixed import TubeLUT  # noqa: E402
from fpga_amp.fixed_circuit import FixedChordV1CircuitModel  # noqa: E402
from fpga_amp.riaa import riaa_db  # noqa: E402
from fpga_amp.tube import Koren12AX7  # noqa: E402
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


class RIAAReferenceTests(unittest.TestCase):
    def test_canonical_equation_matches_published_table(self) -> None:
        table = np.loadtxt(
            REPOSITORY_ROOT / "reference" / "vectors" / "riaa_e1_1978.csv",
            delimiter=",",
        )
        error = riaa_db(table[:, 0]) - table[:, 1]
        # The standard's two-decimal table is not internally exact at every
        # row (14 kHz differs by 0.0705 dB from its stated time constants).
        self.assertLess(float(np.max(np.abs(error))), 0.075)


class CartridgeTests(unittest.TestCase):
    def test_at_vm95e_nominal_resonance_is_above_audio_midband(self) -> None:
        cartridge = CartridgeModel()
        self.assertAlmostEqual(cartridge.undamped_resonance_hz, 17524.0, delta=2.0)
        frequencies = np.geomspace(1000.0, 50_000.0, 4000)
        peak_frequency = float(frequencies[np.argmax(np.abs(cartridge.transfer(frequencies)))])
        # The damped terminal-voltage maximum is below the undamped LC pole.
        self.assertGreater(peak_frequency, 7_000.0)
        self.assertLess(peak_frequency, 8_500.0)


class TubeModelTests(unittest.TestCase):
    def test_common_cathode_bias_points_are_stable(self) -> None:
        tube = Koren12AX7()
        stage1 = tube.solve_cathode_bias(300.0, 121_000.0, 1_210.0)
        stage2 = tube.solve_cathode_bias(300.0, 100_000.0, 1_210.0)
        self.assertAlmostEqual(stage1["plate_v"], 179.9978, places=3)
        self.assertAlmostEqual(stage1["cathode_v"], 1.20002, places=4)
        self.assertAlmostEqual(stage2["plate_v"], 192.8909, places=3)
        self.assertAlmostEqual(stage2["cathode_v"], 1.29602, places=4)

    def test_lut_error_stays_below_absolute_budget(self) -> None:
        tube = Koren12AX7()
        lut = TubeLUT()
        lut.generate(tube)
        rng = np.random.default_rng(0xB17)
        worst = 0.0
        for vg, vp in zip(
            rng.uniform(-5.0, 1.0, 2000),
            rng.uniform(0.0, 400.0, 2000),
            strict=True,
        ):
            approximate, _, clipped = lut.evaluate(float(vg), float(vp))
            self.assertFalse(clipped)
            worst = max(worst, abs(approximate - float(tube.plate_current(vg, vp))))
        # Worst error is at positive grid and nearly zero plate volts, far
        # outside either quiescent point but retained for clipping behavior.
        self.assertLess(worst, 10.5e-6)


class V1CircuitTests(unittest.TestCase):
    def test_dc_nodes_match_spice_baseline(self) -> None:
        model = V1CircuitModel()
        expected = {
            "p1": 179.993992,
            "k1": 1.20005887,
            "g2": 0.00221284,
            "p2": 192.808422,
            "k2": 1.29701689,
        }
        for node, voltage in expected.items():
            self.assertAlmostEqual(model.nodes[node], voltage, delta=0.006)

    def test_small_signal_1khz_gain_and_convergence(self) -> None:
        sample_rate = 768_000.0
        time = np.arange(int(0.012 * sample_rate)) / sample_rate
        input_signal = 5.0e-3 * np.sin(2.0 * np.pi * 1000.0 * time)
        model = V1CircuitModel(sample_rate)
        output = model.process(input_signal)
        settled = time >= 0.008
        gain_db = 20.0 * np.log10(
            np.sqrt(np.mean(np.square(output[settled])))
            / np.sqrt(np.mean(np.square(input_signal[settled])))
        )
        self.assertGreater(gain_db, 40.9)
        self.assertLess(gain_db, 41.2)
        self.assertEqual(model.nonconvergence_count, 0)
        self.assertLessEqual(model.max_iterations_observed, 3)

    def test_three_pass_chord_candidate_tracks_newton(self) -> None:
        sample_rate = 768_000.0
        time = np.arange(int(0.002 * sample_rate)) / sample_rate
        input_signal = (
            10.0e-3 * np.sin(2.0 * np.pi * 50.0 * time)
            + 10.0e-3 * np.sin(2.0 * np.pi * 1000.0 * time)
            + 5.0e-3 * np.sin(2.0 * np.pi * 10_000.0 * time)
        )
        reference_model = V1CircuitModel(sample_rate)
        reference = reference_model.process(
            input_signal, max_iterations=8, tolerance_a=1.0e-12
        )
        chord_model = V1CircuitModel(sample_rate)
        candidate = chord_model.process(
            input_signal,
            solver="chord",
            relaxation=1.0,
            max_iterations=3,
            tolerance_a=1.0e-10,
        )
        normalized_residual_db = 20.0 * np.log10(
            np.sqrt(np.mean(np.square(candidate - reference)))
            / np.sqrt(np.mean(np.square(reference)))
        )
        self.assertLess(normalized_residual_db, -120.0)
        self.assertEqual(chord_model.nonconvergence_count, 0)

    def test_fixed_circuit_candidate_has_bounded_multitone_error(self) -> None:
        sample_rate = 768_000.0
        time = np.arange(int(0.003 * sample_rate)) / sample_rate
        input_signal = (
            10.0e-3 * np.sin(2.0 * np.pi * 50.0 * time)
            + 10.0e-3 * np.sin(2.0 * np.pi * 1000.0 * time)
            + 5.0e-3 * np.sin(2.0 * np.pi * 10_000.0 * time)
        )
        reference_model = V1CircuitModel(sample_rate)
        reference = reference_model.process(
            input_signal, max_iterations=8, tolerance_a=1.0e-12
        )
        fixed_model = FixedChordV1CircuitModel(sample_rate)
        candidate = fixed_model.process(input_signal)
        # Exclude the first millisecond: the 50 Hz component begins at a zero
        # crossing, making an early residual ratio depend mostly on a small
        # denominator rather than settled model accuracy.
        settled = time >= 0.001
        normalized_residual_db = 20.0 * np.log10(
            np.sqrt(np.mean(np.square(candidate[settled] - reference[settled])))
            / np.sqrt(np.mean(np.square(reference[settled])))
        )
        self.assertLess(normalized_residual_db, -50.0)
        self.assertEqual(fixed_model.nonconvergence_count, 0)
        self.assertEqual(fixed_model.saturation_count, 0)
        self.assertEqual(fixed_model.lut_clip_count, 0)


if __name__ == "__main__":
    unittest.main()
