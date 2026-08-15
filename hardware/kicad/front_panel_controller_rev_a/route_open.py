#!/usr/bin/env python3
"""Route the front-panel EVT board through KiCad DSN/SES and Freerouting."""

from __future__ import annotations

import argparse
import math
import subprocess
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parent
BOARD_PATH = ROOT / "front_panel_controller.kicad_pcb"
BUILD = ROOT.parents[2] / "build" / "kicad" / "front_panel_controller"


def finish_board(board: pcbnew.BOARD) -> None:
    """Apply reviewed deterministic finish work after heuristic routing."""
    footprints = {item.GetReference(): item for item in board.GetFootprints()}
    for reference, pad_number in (("J6", "2"), ("J7", "9")):
        pad = next(item for item in footprints[reference].Pads() if item.GetNumber() == pad_number)
        pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    # Keep a checked routed artifact aligned with a source-level annotation
    # correction when finish-only is used rather than a full reroute.
    for drawing in board.GetDrawings():
        if isinstance(drawing, pcbnew.PCB_TEXT) and drawing.GetText() == "J3 52271-0679":
            drawing.SetTextHeight(pcbnew.FromMM(0.8))
            drawing.SetTextWidth(pcbnew.FromMM(0.8))

    # Freerouting v2.2.4 occasionally terminates one segment short of U2.54
    # even though it leaves a same-net F.Cu endpoint 1.6 mm directly east.
    # Complete only that short, straight connection and let mandatory DRC
    # reject the finish if a future route makes the corridor unsafe.
    pad = next(item for item in footprints["U2"].Pads() if item.GetNumber() == "54")
    pad_position = pad.GetPosition()
    same_net_tracks = [
        item for item in board.GetTracks()
        if isinstance(item, pcbnew.PCB_TRACK)
        and not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetCode() == pad.GetNetCode()
        and item.GetLayer() == pcbnew.F_Cu
    ]
    # Remove the obsolete straight finish from early Rev-A work; it crossed
    # adjacent 0.8-mm-pitch pad U2.53.  The reviewed dogleg exits the TSOP row
    # outward before moving east.
    for item in list(same_net_tracks):
        touches_pad = item.GetStart() == pad_position or item.GetEnd() == pad_position
        if touches_pad and item.GetLength() == pcbnew.FromMM(1.60):
            board.Remove(item)
            same_net_tracks.remove(item)
    connected = any(
        pad.HitTest(endpoint)
        for item in same_net_tracks
        for endpoint in (item.GetStart(), item.GetEnd())
    )
    if not connected:
        endpoints = [endpoint for item in same_net_tracks for endpoint in (item.GetStart(), item.GetEnd())]
        endpoint = min(
            endpoints,
            key=lambda point: math.hypot(point.x - pad_position.x, point.y - pad_position.y),
        )
        distance_mm = math.hypot(endpoint.x - pad_position.x, endpoint.y - pad_position.y) / 1e6
        if distance_mm > 2.0 or endpoint.y != pad_position.y:
            raise SystemExit(
                f"U2.54 finish endpoint changed: distance={distance_mm:.3f} mm "
                f"dy={(endpoint.y - pad_position.y) / 1e6:.3f} mm"
            )
        outside_y = pad_position.y - pcbnew.FromMM(1.50)
        points = [
            pad_position,
            pcbnew.VECTOR2I(pad_position.x, outside_y),
            pcbnew.VECTOR2I(endpoint.x, outside_y),
            endpoint,
        ]
        for start, end in zip(points, points[1:]):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(start)
            track.SetEnd(end)
            track.SetLayer(pcbnew.F_Cu)
            track.SetWidth(pcbnew.FromMM(0.20))
            track.SetNet(pad.GetNet())
            board.Add(track)
        print(f"completed reviewed U2.54 GND finish dogleg: target {distance_mm:.3f} mm east")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jar", type=Path, help="Audited Freerouting executable JAR")
    parser.add_argument("--passes", type=int, default=80)
    parser.add_argument("--finish-only", action="store_true", help="Apply reviewed post-route finish and zone fill")
    args = parser.parse_args()
    if args.finish_only:
        board = pcbnew.LoadBoard(str(BOARD_PATH))
        finish_board(board)
        pcbnew.SaveBoard(str(BOARD_PATH), board)
        print(f"finished {BOARD_PATH}")
        return
    if args.jar is None:
        raise SystemExit("--jar is required unless --finish-only is used")
    if not args.jar.is_file():
        raise SystemExit(f"Freerouting JAR not found: {args.jar}")
    BUILD.mkdir(parents=True, exist_ok=True)
    dsn = BUILD / "front_panel_controller.dsn"
    ses = BUILD / "front_panel_controller.ses"
    board = pcbnew.LoadBoard(str(BOARD_PATH))
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
