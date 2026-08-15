from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "verify_nexys_video_audio_top.py"
SPEC = importlib.util.spec_from_file_location(
    "verify_nexys_video_audio_top", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
BOARD_TOP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOARD_TOP)


class NexysVideoAudioTopTests(unittest.TestCase):
    def _changed_file(
        self, original: Path, old: str, new: str
    ) -> tempfile.TemporaryDirectory:
        directory = tempfile.TemporaryDirectory()
        changed = original.read_text(encoding="utf-8").replace(old, new)
        self.assertNotEqual(changed, original.read_text(encoding="utf-8"))
        path = Path(directory.name) / original.name
        path.write_text(changed, encoding="utf-8")
        return directory

    def test_checked_board_top_matches_pin_and_audio_contract(self) -> None:
        report = BOARD_TOP.verify_top()
        self.assertEqual(report["part"], "xc7a200tsbg484-1")
        self.assertEqual(report["pin_count"], 18)
        self.assertEqual(report["clock_constraints"]["bclk_hz"], 3_072_000)
        self.assertEqual(report["audio_profile"]["model_sample_rate_hz"], 384_000)
        self.assertTrue(report["validation"]["fail_closed_audio_release_checked"])
        self.assertTrue(
            report["validation"]["preconfiguration_serial_frames_blocked"]
        )

    def test_active_high_reset_drift_is_rejected(self) -> None:
        with self._changed_file(
            BOARD_TOP.DEFAULT_RTL,
            "board_reset = !cpu_resetn;",
            "board_reset = cpu_resetn;",
        ) as directory:
            rtl = Path(directory) / BOARD_TOP.DEFAULT_RTL.name
            with self.assertRaisesRegex(ValueError, "active-low reset"):
                BOARD_TOP.verify_top(rtl)

    def test_unconstrained_internal_bclk_is_rejected(self) -> None:
        with self._changed_file(
            BOARD_TOP.DEFAULT_XDC,
            "[get_nets audio_and_control.i2s_bclk]",
            "[get_ports codec_bclk]",
        ) as directory:
            xdc = Path(directory) / BOARD_TOP.DEFAULT_XDC.name
            with self.assertRaisesRegex(ValueError, "shared-BCLK"):
                BOARD_TOP.verify_top(xdc_path=xdc)

    def test_wrong_model_rate_is_rejected(self) -> None:
        with self._changed_file(
            BOARD_TOP.DEFAULT_RTL,
            ".MODEL_SAMPLE_RATE_HZ(384000)",
            ".MODEL_SAMPLE_RATE_HZ(768000)",
        ) as directory:
            rtl = Path(directory) / BOARD_TOP.DEFAULT_RTL.name
            with self.assertRaisesRegex(ValueError, "384 kHz schedule"):
                BOARD_TOP.verify_top(rtl)

    def test_early_i2s_transport_release_is_rejected(self) -> None:
        with self._changed_file(
            BOARD_TOP.DEFAULT_RTL,
            ".codec_transport_rst_n(i2s_rst_n)",
            ".codec_transport_rst_n(serial_rst_n)",
        ) as directory:
            rtl = Path(directory) / BOARD_TOP.DEFAULT_RTL.name
            with self.assertRaisesRegex(ValueError, "transport reset"):
                BOARD_TOP.verify_top(rtl)


if __name__ == "__main__":
    unittest.main()
