#!/usr/bin/env python3
"""Route the Rev-A phono/ADC EVT board through KiCad DSN and Freerouting."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parent
BOARD_PATH = ROOT / "phono_adc_eval.kicad_pcb"
BUILD = ROOT.parents[2] / "build" / "kicad" / "phono_adc_eval"


def finish_board(board: pcbnew.BOARD) -> None:
    """Refill the reviewed ground planes after importing heuristic routing."""
    footprints = {item.GetReference(): item for item in board.GetFootprints()}
    for pad in footprints["U1"].Pads():
        if pad.GetNumber() == "11":
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    # The two vertically adjacent G6K pads are the same low-impedance gain
    # branch.  Freerouting 2.2.4 leaves this straight 11.8 mm corridor as its
    # sole unrouted connection.  Keep the finish deterministic and let DRC
    # prove that future placement changes have not obstructed the corridor.
    start = next(pad for pad in footprints["K1"].Pads() if pad.GetNumber() == "4")
    end = next(pad for pad in footprints["K2"].Pads() if pad.GetNumber() == "3")
    all_route_items = list(board.GetTracks())
    tracks = [
        item for item in all_route_items
        if isinstance(item, pcbnew.PCB_TRACK)
        and not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetCode() == start.GetNetCode()
    ]
    obsolete_positions = {
        (pcbnew.FromMM(37.0), pcbnew.FromMM(33.5)),
        (pcbnew.FromMM(37.0), pcbnew.FromMM(44.5)),
        (pcbnew.FromMM(42.0), pcbnew.FromMM(33.5)),
        (pcbnew.FromMM(42.0), pcbnew.FromMM(44.5)),
        (pcbnew.FromMM(37.0), pcbnew.FromMM(48.0)),
    }
    for item in list(tracks):
        item_start = item.GetStart()
        item_end = item.GetEnd()
        is_direct = (
            (item_start == start.GetPosition() and item_end == end.GetPosition())
            or (item_start == end.GetPosition() and item_end == start.GetPosition())
        )
        if is_direct:
            board.Remove(item)
            tracks.remove(item)
        elif (
            (item_start.x, item_start.y) in obsolete_positions
            or (item_end.x, item_end.y) in obsolete_positions
        ):
            board.Remove(item)
            tracks.remove(item)
    for item in all_route_items:
        if (
            isinstance(item, pcbnew.PCB_VIA)
            and item.GetNetCode() == start.GetNetCode()
            and (item.GetPosition().x, item.GetPosition().y) in obsolete_positions
        ):
            board.Remove(item)
    start_connected = any(start.HitTest(point) for item in tracks for point in (item.GetStart(), item.GetEnd()))
    end_connected = any(end.HitTest(point) for item in tracks for point in (item.GetStart(), item.GetEnd()))
    if not (start_connected and end_connected):
        upper_via_position = pcbnew.VECTOR2I(pcbnew.FromMM(42.0), pcbnew.FromMM(33.5))
        lower_via_position = pcbnew.VECTOR2I(pcbnew.FromMM(37.0), pcbnew.FromMM(48.0))
        lower_escape_position = pcbnew.VECTOR2I(pcbnew.FromMM(37.0), end.GetPosition().y)
        segments = [
            (start.GetPosition(), upper_via_position, pcbnew.F_Cu),
            (upper_via_position, lower_via_position, pcbnew.B_Cu),
            (lower_via_position, lower_escape_position, pcbnew.F_Cu),
            (lower_escape_position, end.GetPosition(), pcbnew.F_Cu),
        ]
        for segment_start, segment_end, layer in segments:
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(segment_start)
            track.SetEnd(segment_end)
            track.SetLayer(layer)
            track.SetWidth(pcbnew.FromMM(0.25))
            track.SetNet(start.GetNet())
            board.Add(track)
        for position in (upper_via_position, lower_via_position):
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(position)
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetWidth(pcbnew.FromMM(0.70))
            via.SetDrill(pcbnew.FromMM(0.35))
            via.SetNet(start.GetNet())
            board.Add(via)
        print("completed reviewed K1.4-to-K2.3 L_GAIN_ALT two-via finish")

    # Keep the low-speed gain-bank control off the sensitive top-layer analog
    # corridors when the autorouter cannot escape J5.  The long segment uses
    # the dedicated inner signal layer and approaches the through-hole header
    # from the clear board-edge corridor; it is not an audio or clock net.
    control_start = next(pad for pad in footprints["R51"].Pads() if pad.GetNumber() == "1")
    control_end = next(pad for pad in footprints["J5"].Pads() if pad.GetNumber() == "4")
    control_route_items = list(board.GetTracks())
    control_tracks = [
        item for item in control_route_items
        if isinstance(item, pcbnew.PCB_TRACK)
        and not isinstance(item, pcbnew.PCB_VIA)
        and item.GetNetCode() == control_start.GetNetCode()
    ]
    old_control_positions = {
        (pcbnew.FromMM(52.0), control_start.GetPosition().y),
        (pcbnew.FromMM(52.0), pcbnew.FromMM(10.0)),
        (pcbnew.FromMM(129.0), pcbnew.FromMM(10.0)),
        (pcbnew.FromMM(129.0), control_end.GetPosition().y),
        (pcbnew.FromMM(50.0), pcbnew.FromMM(55.0)),
        (pcbnew.FromMM(35.0), pcbnew.FromMM(55.0)),
        (pcbnew.FromMM(50.0), pcbnew.FromMM(84.0)),
        (pcbnew.FromMM(130.0), pcbnew.FromMM(84.0)),
        (pcbnew.FromMM(130.0), control_end.GetPosition().y),
    }
    for item in list(control_tracks):
        if (
            (item.GetStart().x, item.GetStart().y) in old_control_positions
            or (item.GetEnd().x, item.GetEnd().y) in old_control_positions
        ):
            board.Remove(item)
            control_tracks.remove(item)
    for item in control_route_items:
        if (
            isinstance(item, pcbnew.PCB_VIA)
            and item.GetNetCode() == control_start.GetNetCode()
            and (item.GetPosition().x, item.GetPosition().y) in old_control_positions
        ):
            board.Remove(item)
    control_start_connected = any(
        control_start.HitTest(point) for item in control_tracks for point in (item.GetStart(), item.GetEnd())
    )
    control_end_connected = any(
        control_end.HitTest(point) for item in control_tracks for point in (item.GetStart(), item.GetEnd())
    )
    if not (control_start_connected and control_end_connected):
        control_via_position = pcbnew.VECTOR2I(pcbnew.FromMM(50.0), pcbnew.FromMM(55.0))
        upper_turn = pcbnew.VECTOR2I(pcbnew.FromMM(50.0), pcbnew.FromMM(50.0))
        escape_left = pcbnew.VECTOR2I(pcbnew.FromMM(35.0), pcbnew.FromMM(50.0))
        lower_left = pcbnew.VECTOR2I(pcbnew.FromMM(35.0), pcbnew.FromMM(84.0))
        lower_right = pcbnew.VECTOR2I(pcbnew.FromMM(130.0), pcbnew.FromMM(84.0))
        header_right = pcbnew.VECTOR2I(pcbnew.FromMM(130.0), control_end.GetPosition().y)
        control_segments = [
            (control_start.GetPosition(), control_via_position, pcbnew.F_Cu),
            (control_via_position, upper_turn, pcbnew.In2_Cu),
            (upper_turn, escape_left, pcbnew.In2_Cu),
            (escape_left, lower_left, pcbnew.In2_Cu),
            (lower_left, lower_right, pcbnew.In2_Cu),
            (lower_right, header_right, pcbnew.In2_Cu),
            (header_right, control_end.GetPosition(), pcbnew.In2_Cu),
        ]
        for segment_start, segment_end, layer in control_segments:
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(segment_start)
            track.SetEnd(segment_end)
            track.SetLayer(layer)
            track.SetWidth(pcbnew.FromMM(0.25))
            track.SetNet(control_start.GetNet())
            board.Add(track)
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(control_via_position)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetWidth(pcbnew.FromMM(0.70))
        via.SetDrill(pcbnew.FromMM(0.35))
        via.SetNet(control_start.GetNet())
        board.Add(via)
        print("completed reviewed R51.1-to-J5.4 GAIN_BANK_CTL inner-layer finish")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jar", type=Path, help="Audited Freerouting executable JAR")
    parser.add_argument("--passes", type=int, default=80)
    parser.add_argument("--finish-only", action="store_true")
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
    dsn = BUILD / "phono_adc_eval.dsn"
    ses = BUILD / "phono_adc_eval.ses"
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
