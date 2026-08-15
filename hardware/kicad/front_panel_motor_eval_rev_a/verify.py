#!/usr/bin/env python3
"""Verify Rev-A motor board electrical, mechanical, and report invariants."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pcbnew

from generate import PARTS


ROOT = Path(__file__).resolve().parent
EXPECTED_U1 = {
    "1": "PWM_DRV",
    "2": "DIR_DRV",
    "3": "SLEEP_DRV",
    "4": "MOTOR_FAULT_N",
    "5": "VREF",
    "6": "IPROPI_SENSE",
    "7": "IMODE_CFG",
    "8": "MOTOR_OUT1",
    "9": "GND",
    "10": "MOTOR_OUT2",
    "11": "VM_DRV",
    "12": "VCP",
    "13": "CPH",
    "14": "CPL",
    "15": "GND",
    "16": "GND",
    "17": "GND",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def pad_map(footprint: pcbnew.FOOTPRINT) -> dict[str, str]:
    return {
        pad.GetNumber(): pad.GetNetname()
        for pad in footprint.Pads()
        if pad.GetNumber()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, default=ROOT / "front_panel_motor_eval.kicad_pcb")
    parser.add_argument("--erc", type=Path, required=True)
    parser.add_argument("--drc", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    erc = json.loads(args.erc.read_text(encoding="utf-8"))
    drc = json.loads(args.drc.read_text(encoding="utf-8"))
    erc_violations = sum(len(sheet["violations"]) for sheet in erc["sheets"])
    require(erc_violations == 0, f"ERC contains {erc_violations} violations")
    require(not drc["violations"], f"DRC contains {len(drc['violations'])} violations")
    require(not drc["unconnected_items"], f"DRC contains {len(drc['unconnected_items'])} unconnected items")

    board = pcbnew.LoadBoard(str(args.board))
    footprints = {item.GetReference(): item for item in board.GetFootprints()}
    expected_refs = {part.ref for part in PARTS} | {"H1", "H2", "H3", "H4"}
    require(set(footprints) == expected_refs, "footprint reference set differs from source model")
    require(board.GetCopperLayerCount() == 4, "board is not four-layer")

    bounds = board.GetBoardEdgesBoundingBox()
    width_mm = bounds.GetWidth() / 1e6
    height_mm = bounds.GetHeight() / 1e6
    require(abs(width_mm - 80.1) < 0.01, f"unexpected outline width {width_mm:.3f} mm")
    require(abs(height_mm - 48.1) < 0.01, f"unexpected outline height {height_mm:.3f} mm")

    require(pad_map(footprints["U1"]) == EXPECTED_U1, "DRV8874 pad/net map changed")
    require(pad_map(footprints["J3"]) == {"1": "MOTOR_OUT1", "2": "MOTOR_OUT2"}, "motor connector map changed")
    require(
        pad_map(footprints["J4"])
        == {
            "1": "POT_A_HIGH",
            "2": "POT_A_WIPER",
            "3": "GND",
            "4": "POT_B_HIGH",
            "5": "POT_B_WIPER",
            "6": "GND",
        },
        "position connector map changed",
    )
    require(footprints["R19"].IsDNP() and footprints["C10"].IsDNP(), "snubber tuning sites must be DNP")

    net_names = sorted(net.GetNetname() for net in board.GetNetInfo().NetsByNetcode().values() if net.GetNetname())
    require(not any("AUDIO" in name for name in net_names), "audio net found on motor-only board")
    require(len(net_names) == 28, f"expected 28 named nets, found {len(net_names)}")

    tracks = list(board.GetTracks())
    vias = [item for item in tracks if isinstance(item, pcbnew.PCB_VIA)]
    segments = [item for item in tracks if isinstance(item, pcbnew.PCB_TRACK) and not isinstance(item, pcbnew.PCB_VIA)]
    require(segments, "board has no routed track segments")
    require(vias, "board has no routed vias")
    min_track_mm = min(item.GetWidth() for item in segments) / 1e6
    min_via_drill_mm = min(item.GetDrillValue() for item in vias) / 1e6
    require(min_track_mm >= 0.25, f"track width below 0.25 mm: {min_track_mm:.3f} mm")
    require(min_via_drill_mm >= 0.35, f"via drill below 0.35 mm: {min_via_drill_mm:.3f} mm")

    stats = {
        "board": args.board.name,
        "kicad_version": drc["kicad_version"],
        "outline_mm": [round(width_mm - 0.1, 3), round(height_mm - 0.1, 3)],
        "copper_layers": board.GetCopperLayerCount(),
        "schematic_parts": len(PARTS),
        "board_footprints": len(footprints),
        "named_nets": len(net_names),
        "track_segments": len(segments),
        "vias": len(vias),
        "minimum_track_width_mm": min_track_mm,
        "minimum_via_drill_mm": min_via_drill_mm,
        "erc_violations": erc_violations,
        "drc_violations": len(drc["violations"]),
        "unconnected_items": len(drc["unconnected_items"]),
    }
    rendered = json.dumps(stats, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    print("PASS: motor-volume Rev-A board invariants verified")


if __name__ == "__main__":
    main()
