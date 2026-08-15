from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "nexys_video_hardware_preflight.py"
SPEC = importlib.util.spec_from_file_location(
    "nexys_video_hardware_preflight", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)


class NexysVideoHardwarePreflightTests(unittest.TestCase):
    def _artifact(self, directory: str) -> tuple[Path, Path]:
        bitstream = Path(directory) / "candidate.bit"
        bitstream.write_bytes(b"deterministic-open-xc7-bitstream")
        manifest = bitstream.with_suffix(".bit.json")
        manifest.write_text(
            json.dumps(
                {
                    "part": PREFLIGHT.EXPECTED_PART,
                    "bitstream_bytes": bitstream.stat().st_size,
                    "bitstream_sha256": hashlib.sha256(
                        bitstream.read_bytes()
                    ).hexdigest(),
                    "bitread_crc_validation": True,
                    "bitread_configuration_words": 2_432_650,
                    "bitread_configuration_frames": 24_060,
                }
            ),
            encoding="utf-8",
        )
        return bitstream, manifest

    def test_exact_manifest_and_crc_evidence_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bitstream, manifest = self._artifact(directory)
            report = PREFLIGHT.validate_artifact(bitstream, manifest)
        self.assertTrue(all(report["checks"].values()))
        self.assertEqual(report["bitread_configuration_frames"], 24_060)

    def test_tampered_bitstream_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bitstream, manifest = self._artifact(directory)
            bitstream.write_bytes(bitstream.read_bytes() + b"tamper")
            with self.assertRaisesRegex(ValueError, "validation failed"):
                PREFLIGHT.validate_artifact(bitstream, manifest)

    def test_missing_programmer_is_reported_without_programming(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bitstream, manifest = self._artifact(directory)
            report = PREFLIGHT.build_report(
                bitstream,
                manifest,
                "definitely-not-an-installed-programmer",
                probe_hardware=True,
            )
        self.assertFalse(report["programmer"]["available"])
        self.assertFalse(report["hardware_detected"])
        self.assertFalse(report["programming_performed"])
        self.assertEqual(report["sram_program_command"][2], "nexysVideo")


if __name__ == "__main__":
    unittest.main()
