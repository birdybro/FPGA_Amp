from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "run_openxc7.py"
SPEC = importlib.util.spec_from_file_location("run_openxc7", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
RUN_OPENXC7 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN_OPENXC7)

SYNTHESIS_MODULE_PATH = REPOSITORY_ROOT / "scripts" / "run_synthesis.py"
SYNTHESIS_SPEC = importlib.util.spec_from_file_location(
    "run_synthesis", SYNTHESIS_MODULE_PATH
)
assert SYNTHESIS_SPEC is not None and SYNTHESIS_SPEC.loader is not None
RUN_SYNTHESIS = importlib.util.module_from_spec(SYNTHESIS_SPEC)
SYNTHESIS_SPEC.loader.exec_module(RUN_SYNTHESIS)

BITSTREAM_MODULE_PATH = REPOSITORY_ROOT / "scripts" / "generate_openxc7_bitstream.py"
BITSTREAM_SPEC = importlib.util.spec_from_file_location(
    "generate_openxc7_bitstream", BITSTREAM_MODULE_PATH
)
assert BITSTREAM_SPEC is not None and BITSTREAM_SPEC.loader is not None
GENERATE_BITSTREAM = importlib.util.module_from_spec(BITSTREAM_SPEC)
BITSTREAM_SPEC.loader.exec_module(GENERATE_BITSTREAM)


class OpenXc7ToolTests(unittest.TestCase):
    def test_chipdb_density_is_derived_from_supported_part_names(self) -> None:
        cases = {
            "xc7a100tcsg324-1": "xc7a100t",
            "xc7a200tsbg484-1": "xc7a200t",
            "xc7s50csga324-1": "xc7s50",
            "xc7z020clg400-1": "xc7z020",
        }
        for part, expected in cases.items():
            with self.subTest(part=part):
                self.assertEqual(RUN_OPENXC7.chipdb_device_name(part), expected)

    def test_non_xc7_part_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot derive"):
            RUN_OPENXC7.chipdb_device_name("ice40up5k")

    def test_run_tag_accepts_safe_bounded_names(self) -> None:
        for tag in ("timingweight20", "seed_2", "kcl-share-v1", "a"):
            with self.subTest(tag=tag):
                self.assertEqual(RUN_OPENXC7.validated_run_tag(tag), tag)

    def test_run_tag_rejects_paths_and_ambiguous_names(self) -> None:
        for tag in (
            "../baseline",
            "nested/run",
            "UpperCase",
            "-leading",
            "contains space",
            "x" * 65,
        ):
            with self.subTest(tag=tag):
                with self.assertRaisesRegex(
                    RUN_OPENXC7.argparse.ArgumentTypeError, "run tag"
                ):
                    RUN_OPENXC7.validated_run_tag(tag)

    def test_synthesis_result_tag_uses_the_same_safe_contract(self) -> None:
        self.assertEqual(
            RUN_SYNTHESIS.validated_result_tag("soft_kcl-v1"),
            "soft_kcl-v1",
        )
        with self.assertRaisesRegex(
            RUN_SYNTHESIS.argparse.ArgumentTypeError, "result tag"
        ):
            RUN_SYNTHESIS.validated_result_tag("../escape")

    def test_pack_only_report_does_not_claim_placement_or_timing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "pack.json"
            report.write_text(
                json.dumps({"utilization": {"SLICE_LUTX": {"used": 7}}}),
                encoding="utf-8",
            )
            summary = RUN_OPENXC7.measured_report_summary(
                report,
                placement_requested=False,
                route_requested=False,
            )
        self.assertTrue(summary["pack_completed"])
        self.assertFalse(summary["placement_completed"])
        self.assertFalse(summary["route_completed"])
        self.assertIsNone(summary["timing_pass"])
        self.assertEqual(summary["utilization"]["SLICE_LUTX"], {"used": 7})

    def test_bitstream_artifact_names_stay_beside_fasm(self) -> None:
        fasm = Path("build/openxc7/candidate.fasm")
        self.assertEqual(
            GENERATE_BITSTREAM.default_output_paths(fasm),
            (
                Path("build/openxc7/candidate.frm"),
                Path("build/openxc7/candidate.bit"),
                Path("build/openxc7/candidate.bit.json"),
            ),
        )

    def test_bitstream_digest_is_streamed_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact.bin"
            artifact.write_bytes(b"open-xc7\x00bitstream")
            digest = GENERATE_BITSTREAM.file_sha256(artifact)
        self.assertEqual(
            digest,
            "1924c7d5416caf8881eeffbb7324379775ec29d7548004735fc6baf6e9ccede5",
        )

    def test_bitstream_timestamp_normalization_preserves_payload(self) -> None:
        prefix = bytes(
            (0x00, 0x09, 0x0F, 0xF0, 0x0F, 0xF0, 0x0F, 0xF0, 0x0F, 0xF0, 0, 0, 1)
        )

        def field(tag: str, value: bytes) -> bytes:
            encoded = value + b"\0"
            return tag.encode("ascii") + len(encoded).to_bytes(2, "big") + encoded

        payload = b"\xaa\x99\x55\x66configuration"
        original = (
            prefix
            + field("a", b"candidate.frm;Generator=xc7frames2bit")
            + field("b", b"xc7a200tsbg484-1")
            + field("c", b"2026/08/15")
            + field("d", b"06:24:01")
            + b"e"
            + len(payload).to_bytes(4, "big")
            + payload
        )
        with tempfile.TemporaryDirectory() as directory:
            bitstream = Path(directory) / "candidate.bit"
            bitstream.write_bytes(original)
            timestamp = GENERATE_BITSTREAM.normalize_bitstream_timestamp(bitstream, 0)
            normalized = bitstream.read_bytes()

        self.assertEqual(timestamp, "1970-01-01T00:00:00Z")
        self.assertIn(b"1970/01/01\0", normalized)
        self.assertIn(b"00:00:00\0", normalized)
        self.assertTrue(normalized.endswith(payload))
        self.assertEqual(len(normalized), len(original))

    def test_bitread_measurements_are_parsed_exactly(self) -> None:
        output = """Bitstream size: 9730907 bytes
Config size: 2432650 words
Number of configuration frames: 24060
DONE
"""
        self.assertEqual(
            GENERATE_BITSTREAM.parse_bitread_measurements(output),
            (9_730_907, 2_432_650, 24_060),
        )


if __name__ == "__main__":
    unittest.main()
