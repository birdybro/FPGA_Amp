from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "verify_product_hardware_spec.py"
SPEC_PATH = ROOT / "hardware" / "product_v1" / "requirements.json"
SPEC = importlib.util.spec_from_file_location("verify_product_hardware_spec", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ProductHardwareSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(SPEC_PATH.read_text(encoding="utf-8"))

    def validate_mutation(self, mutation: dict) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "requirements.json"
            path.write_text(json.dumps(mutation), encoding="utf-8")
            MODULE.validate(path)

    def test_repository_spec_passes(self) -> None:
        report = MODULE.validate(SPEC_PATH)
        self.assertGreaterEqual(report["requirements"], 40)
        self.assertEqual(report["boards"], 5)
        self.assertGreaterEqual(report["interfaces"], 6)
        self.assertGreaterEqual(report["interface_signal_rows"], 30)

    def test_duplicate_requirement_is_rejected(self) -> None:
        mutation = copy.deepcopy(self.data)
        mutation["requirements"].append(copy.deepcopy(mutation["requirements"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate requirement id"):
            self.validate_mutation(mutation)

    def test_unknown_board_is_rejected(self) -> None:
        mutation = copy.deepcopy(self.data)
        mutation["requirements"][0]["boards"] = ["NOT-A-BOARD"]
        with self.assertRaisesRegex(ValueError, "unknown boards"):
            self.validate_mutation(mutation)

    def test_reference_boundary_cannot_be_downgraded(self) -> None:
        mutation = copy.deepcopy(self.data)
        record = next(item for item in mutation["requirements"] if item["id"] == "SYS-002")
        record["status"] = "provisional"
        with self.assertRaisesRegex(ValueError, "must remain frozen and mandatory"):
            self.validate_mutation(mutation)

    def test_interface_budget_drift_is_rejected(self) -> None:
        mutation = copy.deepcopy(self.data)
        mutation["interfaces"][0]["signals"].append("UNBUDGETED_SIGNAL")
        with self.assertRaisesRegex(ValueError, "interface budget signals differ"):
            self.validate_mutation(mutation)

    def test_connector_contact_overcommit_is_rejected(self) -> None:
        mutation = copy.deepcopy(self.data)
        mutation["interfaces"][0]["minimum_connector_contacts"] = 8
        with self.assertRaisesRegex(ValueError, "budgets .* contacts"):
            self.validate_mutation(mutation)

    def test_untraced_requirement_is_rejected(self) -> None:
        mutation = copy.deepcopy(self.data)
        mutation["requirements"][0]["id"] = "SYS-999"
        with self.assertRaisesRegex(ValueError, "absent from traceability document"):
            self.validate_mutation(mutation)


if __name__ == "__main__":
    unittest.main()
