from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "verify_audio_clock_plan.py"
SPEC = importlib.util.spec_from_file_location("verify_audio_clock_plan", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
CLOCK_PLAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLOCK_PLAN)


class AudioClockPlanTests(unittest.TestCase):
    def test_checked_rtl_produces_exact_audio_family(self) -> None:
        report = CLOCK_PLAN.verify_plan()
        self.assertEqual(report["codec_mclk_hz"], 12_288_000)
        self.assertEqual(report["fabric_clock_hz"], 49_152_000)
        self.assertEqual(report["fabric_clocks_per_384khz_sample"], 128)
        self.assertEqual(
            [stage["vco_hz"] for stage in report["stages"]],
            [960_000_000, 614_400_000],
        )
        self.assertTrue(report["validation"]["ratios_are_exact"])
        self.assertTrue(report["validation"]["active_low_board_reset_checked"])

    def test_rtl_parameter_drift_is_rejected(self) -> None:
        source = CLOCK_PLAN.DEFAULT_RTL.read_text(encoding="utf-8")
        changed = source.replace(".CLKFBOUT_MULT_F(48.000)", ".CLKFBOUT_MULT_F(47.000)")
        self.assertNotEqual(changed, source)
        with tempfile.TemporaryDirectory() as directory:
            rtl = Path(directory) / "changed.sv"
            rtl.write_text(changed, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "mclk_mmcm parameter mismatch"):
                CLOCK_PLAN.verify_plan(rtl)

    def test_active_low_board_reset_drift_is_rejected(self) -> None:
        source = CLOCK_PLAN.DEFAULT_RTL.read_text(encoding="utf-8")
        changed = source.replace(
            "always_comb board_reset = !cpu_resetn;",
            "always_comb board_reset = cpu_resetn;",
        )
        self.assertNotEqual(changed, source)
        with tempfile.TemporaryDirectory() as directory:
            rtl = Path(directory) / "changed.sv"
            rtl.write_text(changed, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invert active-low"):
                CLOCK_PLAN.verify_plan(rtl)


if __name__ == "__main__":
    unittest.main()
