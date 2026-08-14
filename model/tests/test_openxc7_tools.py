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


if __name__ == "__main__":
    unittest.main()
