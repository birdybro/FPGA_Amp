#!/usr/bin/env python3
"""Route the Rev-A PCM5242 DAC/line-output EVT with open tools."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parent
BOARD_PATH = ROOT / "dac_line_output_eval.kicad_pcb"
BUILD = ROOT.parents[2] / "build" / "kicad" / "dac_line_output_eval"


def finish_board(board: pcbnew.BOARD) -> None:
    """Restore reviewed pad/plane settings and refill ground zones."""
    footprints = {item.GetReference(): item for item in board.GetFootprints()}
    for pad in footprints["U1"].Pads():
        if pad.GetNumber() == "33":
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    # Output-harness signal escapes crowd the inner ground thermal spokes at
    # this edge.  These connector returns intentionally use direct plane joins.
    for ref in ("J4", "J5"):
        for pad in footprints[ref].Pads():
            if pad.GetNetname() == "GND":
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    # Freerouting cannot enter J2.4 from the right because every even-numbered
    # header pad is in that row.  Escape R10 locally, use the back-side board
    # edge corridor, and approach the SDA pad from above.  This is low-speed
    # I2C, well away from the DAC output reconstruction networks.
    start = next(pad for pad in footprints["R10"].Pads() if pad.GetNumber() == "1")
    end = next(pad for pad in footprints["J2"].Pads() if pad.GetNumber() == "4")
    if not any(item.GetNetCode() == start.GetNetCode() for item in board.GetTracks()):
        p0 = pcbnew.VECTOR2I(start.GetPosition().x, start.GetPosition().y)
        p1 = pcbnew.VECTOR2I(pcbnew.FromMM(21.0), p0.y)
        p2 = pcbnew.VECTOR2I(pcbnew.FromMM(19.5), p1.y)
        p3 = pcbnew.VECTOR2I(p2.x, pcbnew.FromMM(29.5))
        p4 = pcbnew.VECTOR2I(end.GetPosition().x, p3.y)
        p5 = pcbnew.VECTOR2I(end.GetPosition().x, end.GetPosition().y)
        for segment_start, segment_end, layer in (
            (p0, p1, pcbnew.F_Cu),
            (p1, p2, pcbnew.B_Cu),
            (p2, p3, pcbnew.B_Cu),
            (p3, p4, pcbnew.B_Cu),
            (p4, p5, pcbnew.B_Cu),
        ):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(segment_start)
            track.SetEnd(segment_end)
            track.SetLayer(layer)
            track.SetWidth(pcbnew.FromMM(0.25))
            track.SetNet(start.GetNet())
            board.Add(track)
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(p1)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetWidth(pcbnew.FromMM(0.70))
        via.SetDrill(pcbnew.FromMM(0.35))
        via.SetNet(start.GetNet())
        board.Add(via)
        print("completed reviewed R10.1-to-J2.4 I2C_SDA_IN back-edge corridor")

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jar", type=Path, help="Audited Freerouting executable JAR")
    parser.add_argument("--passes", type=int, default=80)
    parser.add_argument("--finish-only", action="store_true")
    args = parser.parse_args()

    board = pcbnew.LoadBoard(str(BOARD_PATH))
    if args.finish_only:
        finish_board(board)
        pcbnew.SaveBoard(str(BOARD_PATH), board)
        print(f"finished {BOARD_PATH}")
        return
    if args.jar is None:
        raise SystemExit("--jar is required unless --finish-only is used")
    if not args.jar.is_file():
        raise SystemExit(f"Freerouting JAR not found: {args.jar}")

    BUILD.mkdir(parents=True, exist_ok=True)
    dsn = BUILD / "dac_line_output_eval.dsn"
    ses = BUILD / "dac_line_output_eval.ses"
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise SystemExit("KiCad DSN export failed")
    subprocess.run([
        "java", "--enable-final-field-mutation=ALL-UNNAMED", "-jar", str(args.jar),
        "--gui.enabled=false", "-de", str(dsn), "-do", str(ses),
        "-mp", str(args.passes), "-mt", "1", "-da",
        "--logging.file.enabled=false", "--logging.console.level=INFO",
    ], check=True)
    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise SystemExit("KiCad SES import failed")
    finish_board(board)
    pcbnew.SaveBoard(str(BOARD_PATH), board)
    print(f"routed {BOARD_PATH}")


if __name__ == "__main__":
    main()
