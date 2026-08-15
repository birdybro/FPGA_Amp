#!/usr/bin/env python3
"""Verify Rev-A controller connectivity and record routed-board statistics."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import pcbnew

from generate import DISPLAY_SERIES, LCD_PINS, MCU_NETS, PARTS


ROOT = Path(__file__).resolve().parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def pad_map(footprint: pcbnew.FOOTPRINT) -> dict[str, str]:
    return {
        pad.GetNumber(): pad.GetNetname()
        for pad in footprint.Pads()
        if pad.GetNumber() and pad.GetNetname()
    }


def require_ffc_geometry(
    footprint: pcbnew.FOOTPRINT,
    *,
    name: str,
    signal_count: int,
    pitch_mm: float,
    signal_size_mm: tuple[float, float],
    mp_centers_x_mm: tuple[float, float],
    mp_size_mm: tuple[float, float],
) -> None:
    """Lock manufacturer-drawing land dimensions into the regression."""
    require(footprint.GetFPID().GetLibItemName() == name, f"{footprint.GetReference()}: wrong footprint")
    signals = {
        int(pad.GetNumber()): pad
        for pad in footprint.Pads()
        if pad.GetNumber().isdigit()
    }
    require(set(signals) == set(range(1, signal_count + 1)),
            f"{footprint.GetReference()}: signal pad-number set changed")
    positions = [signals[index].GetFPRelativePosition() for index in range(1, signal_count + 1)]
    for left, right in zip(positions, positions[1:]):
        require(abs((right.x - left.x) / 1e6 - pitch_mm) < 0.001,
                f"{footprint.GetReference()}: signal pitch changed")
        require(right.y == left.y, f"{footprint.GetReference()}: signal row is not straight")
    for pad in signals.values():
        size = pad.GetSize()
        require(abs(size.x / 1e6 - signal_size_mm[0]) < 0.001
                and abs(size.y / 1e6 - signal_size_mm[1]) < 0.001,
                f"{footprint.GetReference()}: signal land size changed")
    mounting = sorted(
        (pad for pad in footprint.Pads() if pad.GetNumber() == "MP"),
        key=lambda pad: pad.GetFPRelativePosition().x,
    )
    require(len(mounting) == 2, f"{footprint.GetReference()}: expected two fitting-nail lands")
    for pad, expected_x in zip(mounting, mp_centers_x_mm):
        position = pad.GetFPRelativePosition()
        size = pad.GetSize()
        require(abs(position.x / 1e6 - expected_x) < 0.001,
                f"{footprint.GetReference()}: fitting-nail position changed")
        require(abs(size.x / 1e6 - mp_size_mm[0]) < 0.001
                and abs(size.y / 1e6 - mp_size_mm[1]) < 0.001,
                f"{footprint.GetReference()}: fitting-nail land size changed")


def routed_lengths(board: pcbnew.BOARD) -> dict[str, float]:
    result: dict[str, float] = defaultdict(float)
    net_by_code = {
        net.GetNetCode(): net.GetNetname()
        for net in board.GetNetInfo().NetsByNetcode().values()
    }
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_TRACK) and not isinstance(item, pcbnew.PCB_VIA):
            result[net_by_code[item.GetNetCode()]] += item.GetLength() / 1e6
    return dict(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, default=ROOT / "front_panel_controller.kicad_pcb")
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
    expected_refs = {component.ref for component in PARTS} | {"H1", "H2", "H3", "H4"}
    require(set(footprints) == expected_refs, "footprint reference set differs from source model")
    require(board.GetCopperLayerCount() == 6, "controller board is not six-layer")
    require(board.GetLayerName(pcbnew.In1_Cu) == "GND1", "L2 is not GND1")
    require(board.GetLayerName(pcbnew.In2_Cu) == "PWR", "L3 is not PWR")
    require(board.GetLayerName(pcbnew.In3_Cu) == "SIG2", "L4 is not SIG2")
    require(board.GetLayerName(pcbnew.In4_Cu) == "GND2", "L5 is not GND2")

    bounds = board.GetBoardEdgesBoundingBox()
    width_mm = bounds.GetWidth() / 1e6
    height_mm = bounds.GetHeight() / 1e6
    require(abs(width_mm - 150.1) < 0.01, f"unexpected outline width {width_mm:.3f} mm")
    require(abs(height_mm - 90.1) < 0.01, f"unexpected outline height {height_mm:.3f} mm")

    require(pad_map(footprints["U1"]) == MCU_NETS, "STM32 package pad/net map changed")
    require(pad_map(footprints["J2"]) == LCD_PINS, "TFT electrical connector map changed")
    require_ffc_geometry(
        footprints["J2"],
        name="Molex_54104-4031_1x40-2MP_P0.50mm_Horizontal",
        signal_count=40,
        pitch_mm=0.50,
        signal_size_mm=(0.30, 1.20),
        mp_centers_x_mm=(-11.85, 11.85),
        mp_size_mm=(2.40, 2.40),
    )
    require_ffc_geometry(
        footprints["J3"],
        name="Molex_52271-0679_1x06-2MP_P1.00mm_Horizontal",
        signal_count=6,
        pitch_mm=1.00,
        signal_size_mm=(0.60, 2.20),
        mp_centers_x_mm=(-5.65, 5.65),
        mp_size_mm=(2.10, 2.20),
    )
    require(footprints["U4"].GetValue().startswith("TPS62132"), "3.3 V buck part changed from TPS62132")
    require(footprints["U5"].GetValue().startswith("TPS61165"), "LCD LED driver changed")
    require(
        pad_map(footprints["U5"])
        == {
            "1": "BL_FB", "2": "BL_COMP", "3": "GND", "4": "BL_SW",
            "5": "BACKLIGHT_PWM", "6": "+12V_UI", "7": "GND",
        },
        "TPS61165 DRV WSON pad order changed",
    )
    require(
        pad_map(footprints["U4"])
        == {
            "1": "BUCK_SW", "2": "BUCK_SW", "3": "BUCK_SW", "4": "BUCK_PG",
            "5": "GND", "6": "GND", "7": "GND", "8": "GND", "9": "BUCK_SS",
            "10": "+12V_UI", "11": "+12V_UI", "12": "+12V_UI", "13": "BUCK_EN",
            "14": "+3V3", "15": "GND", "16": "GND", "17": "GND",
        },
        "TPS62132 RGT VQFN pad order changed",
    )

    with (ROOT / "pin_assignment.csv").open(newline="", encoding="utf-8") as handle:
        pin_rows = list(csv.DictReader(handle))
    require(len(pin_rows) == 106, f"expected 106 assigned MCU I/Os, found {len(pin_rows)}")
    for signal in DISPLAY_SERIES:
        resistors = [
            component for component in PARTS
            if component.value == "33R"
            and set(component.nets.values()) == {signal, signal + "_MCU"}
        ]
        require(len(resistors) == 1, f"{signal}: expected one 33-ohm source damper")

    tracks = list(board.GetTracks())
    vias = [item for item in tracks if isinstance(item, pcbnew.PCB_VIA)]
    segments = [item for item in tracks if isinstance(item, pcbnew.PCB_TRACK) and not isinstance(item, pcbnew.PCB_VIA)]
    require(segments, "board has no routed track segments")
    require(vias, "board has no routed vias")
    min_track_mm = min(item.GetWidth() for item in segments) / 1e6
    min_via_drill_mm = min(item.GetDrillValue() for item in vias) / 1e6
    require(min_track_mm >= 0.20, f"track width below 0.20 mm: {min_track_mm:.3f} mm")
    require(min_via_drill_mm >= 0.30, f"via drill below 0.30 mm: {min_via_drill_mm:.3f} mm")

    lengths = routed_lengths(board)
    sdram_signal_names = sorted({
        net for component in PARTS for net in component.nets.values()
        if net.startswith("SDRAM_") and not net.endswith("_MCU")
    })
    sdram_lengths = {name: round(lengths.get(name, 0.0), 3) for name in sdram_signal_names}
    display_lengths = {
        name: round(lengths.get(name, 0.0) + lengths.get(name + "_MCU", 0.0), 3)
        for name in sorted(DISPLAY_SERIES)
    }
    stats = {
        "board": args.board.name,
        "kicad_version": drc["kicad_version"],
        "outline_mm": [round(width_mm - 0.1, 3), round(height_mm - 0.1, 3)],
        "copper_layers": board.GetCopperLayerCount(),
        "schematic_parts": len(PARTS),
        "board_footprints": len(footprints),
        "assigned_mcu_ios": len(pin_rows),
        "named_nets": len([net for net in board.GetNetInfo().NetsByNetcode().values() if net.GetNetname()]),
        "track_segments": len(segments),
        "vias": len(vias),
        "minimum_track_width_mm": min_track_mm,
        "minimum_via_drill_mm": min_via_drill_mm,
        "erc_violations": erc_violations,
        "drc_violations": len(drc["violations"]),
        "unconnected_items": len(drc["unconnected_items"]),
        "sdram_route_lengths_mm": sdram_lengths,
        "display_route_lengths_mm": display_lengths,
        "release_gates": [
            "physical connector fit/coupon and first-article land-pattern signoff",
            "stackup-specific impedance and SDRAM timing review",
            "switching-regulator and LED-boost layout review",
            "enclosure/mechanical connector signoff",
        ],
    }
    rendered = json.dumps(stats, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    print("PASS: front-panel controller Rev-A EVT board invariants verified")


if __name__ == "__main__":
    main()
