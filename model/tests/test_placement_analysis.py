from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "analyze_openxc7_placement.py"
SPEC = importlib.util.spec_from_file_location(
    "analyze_openxc7_placement", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
PLACEMENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLACEMENT)


class PlacementAnalysisTests(unittest.TestCase):
    def test_complete_stream_hierarchy_is_separated(self) -> None:
        cases = {
            "$flatten\\candidate.\\stream.\\core."
            "\\generate_interpolator_8x.interpolator.$abc$1": "interpolator_8x",
            "$flatten\\candidate.\\stream.\\core."
            "\\generate_decimator_8x.decimator.stage3.$abc$2": "decimator_8x",
            "$flatten\\candidate.\\stream.\\core."
            "\\solver.\\kcl_engine.$abc$3": "kcl",
            "$flatten\\candidate.\\stream.\\core."
            "\\solver.\\chord_engine.$abc$4": "chord",
            "$flatten\\candidate.\\stream.\\core."
            "\\solver.\\terminal_current_engine.$mul$5": "terminal_current",
            "$flatten\\candidate.\\stream.\\core."
            "\\solver.\\rhs_engine.$abc$6": "rhs",
            "$flatten\\candidate.\\stream.\\core."
            "\\solver.$abc$7": "solver_control_and_state",
        }
        for cell_name, expected in cases.items():
            with self.subTest(cell_name=cell_name):
                self.assertEqual(PLACEMENT.hierarchy_group(cell_name), expected)


if __name__ == "__main__":
    unittest.main()
