#!/usr/bin/env python3
"""Route the motor-volume PCB using KiCad DSN/SES and Freerouting.

The Freerouting JAR is intentionally not vendored. Pass an audited local JAR;
the version used for the checked-in Rev-A board is recorded in README.md.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parent
BOARD_PATH = ROOT / "front_panel_motor_eval.kicad_pcb"
BUILD = ROOT.parents[2] / "build" / "kicad" / "front_panel_motor_eval"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jar", type=Path, required=True, help="Freerouting executable JAR")
    parser.add_argument("--passes", type=int, default=30)
    args = parser.parse_args()
    if not args.jar.is_file():
        raise SystemExit(f"Freerouting JAR not found: {args.jar}")
    BUILD.mkdir(parents=True, exist_ok=True)
    dsn = BUILD / "front_panel_motor_eval.dsn"
    ses = BUILD / "front_panel_motor_eval.ses"
    board = pcbnew.LoadBoard(str(BOARD_PATH))
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise SystemExit("KiCad DSN export failed")
    subprocess.run([
        "java", "--enable-final-field-mutation=ALL-UNNAMED", "-jar", str(args.jar),
        "--gui.enabled=false", "-de", str(dsn), "-do", str(ses),
        "-mp", str(args.passes), "-mt", "4", "-da",
        "--logging.file.enabled=false", "--logging.console.level=INFO",
    ], check=True)
    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise SystemExit("KiCad SES import failed")
    pcbnew.SaveBoard(str(BOARD_PATH), board)
    print(f"routed {BOARD_PATH}")


if __name__ == "__main__":
    main()
