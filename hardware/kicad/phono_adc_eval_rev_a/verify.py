#!/usr/bin/env python3
"""Verify Rev-A phono/ADC electrical, physical, and routed-board invariants."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pcbnew

from design import calculate
from generate import PARTS


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


def route_lengths(board: pcbnew.BOARD) -> dict[str, float]:
    result: dict[str, float] = defaultdict(float)
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_TRACK) and not isinstance(item, pcbnew.PCB_VIA):
            result[item.GetNetname()] += item.GetLength() / 1e6
    return dict(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, default=ROOT / "phono_adc_eval.kicad_pcb")
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
    require(board.GetCopperLayerCount() == 4, "phono/ADC board is not four-layer")
    require(board.GetLayerName(pcbnew.In1_Cu) == "GND", "L2 is not the continuous GND reference")
    require(board.GetLayerName(pcbnew.In2_Cu) == "POWER_SIG", "L3 name changed")

    bounds = board.GetBoardEdgesBoundingBox()
    width_mm = bounds.GetWidth() / 1e6
    height_mm = bounds.GetHeight() / 1e6
    require(abs(width_mm - 130.1) < 0.01, f"unexpected outline width {width_mm:.3f} mm")
    require(abs(height_mm - 90.1) < 0.01, f"unexpected outline height {height_mm:.3f} mm")

    expected_adc = {
        "1": "VREF_L", "2": "GND", "3": "VCOM_L", "4": "ADC_L_IN_P", "5": "ADC_L_IN_N",
        "6": "+3V3D", "7": "GND", "8": "GND", "9": "+3V3D", "10": "GND", "11": "GND",
        "12": "+3V3D", "13": "GND", "14": "+3V3D", "15": "ADC_DATA_SRC", "16": "ADC_BCK_SRC",
        "17": "ADC_LRCK_SRC", "18": "SCKI_24M576", "19": "ADC_RESET_N", "20": "ADC_CLIP_R",
        "21": "ADC_CLIP_L", "22": "+5VA", "23": "GND", "24": "ADC_R_IN_N", "25": "ADC_R_IN_P",
        "26": "VCOM_R", "27": "GND", "28": "VREF_R",
    }
    require(pad_map(footprints["U7"]) == expected_adc, "PCM4202 pad/net map changed")
    require(footprints["U7"].GetFPID().GetLibItemName() == "SSOP-28_5.3x10.2mm_P0.65mm",
            "PCM4202 footprint is not TI DB-compatible SSOP-28")
    require(pad_map(footprints["U1"]) == {
        "1": "+15V5_IN", "2": "+15V5_IN", "3": "LDO_NR", "4": "GND", "5": "-15V5_IN",
        "6": "-12VA", "7": "LDO_FBN", "8": "LDO_BUF", "9": "LDO_FBP", "10": "+12VA", "11": "GND",
    }, "TPS7A39 pad/net map changed")
    require(pad_map(footprints["U4"]) == {
        "1": "L_GAIN_OUT", "2": "L_GAIN_N", "3": "L_INPUT", "4": "-12VA",
        "5": "R_INPUT", "6": "R_GAIN_N", "7": "R_GAIN_OUT", "8": "+12VA",
    }, "OPA1656 gain-stage pad/net map changed")

    require(pad_map(footprints["K1"]) == {
        "1": "+5V_RELAY", "2": "L_GAIN26", "3": "L_GAIN_N", "4": "L_GAIN_ALT",
        "5": "R_GAIN_ALT", "6": "R_GAIN_N", "7": "R_GAIN26", "8": "K1_COIL_LOW",
    }, "K1 no longer defaults both channels to the 26 dB branches")
    require(pad_map(footprints["K3"]) == {
        "1": "+5V_RELAY", "3": "L_INPUT", "4": "L_CAP47",
        "5": "R_CAP47", "6": "R_INPUT", "8": "K3_COIL_LOW",
    }, "K3 no longer defaults the 47 pF branches open")
    require(pad_map(footprints["K4"]) == {
        "1": "+5V_RELAY", "3": "L_INPUT", "4": "L_CAP100",
        "5": "R_CAP100", "6": "R_INPUT", "8": "K4_COIL_LOW",
    }, "K4 no longer defaults the 100 pF branches open")

    values = {component.ref: component.value for component in PARTS}
    require(values["R3"].startswith("47.5k_0.1%") and values["R4"].startswith("47.5k_0.1%"),
            "cartridge termination is not 47.5 kilohm 0.1% on both channels")
    require(values["R5"].startswith("19.1k_0.1%") and values["R6"].startswith("19.1k_0.1%"),
            "gain feedback resistors changed")
    for reference in ("C5", "C6", "R71", "C81"):
        require(footprints[reference].IsDNP(), f"{reference} must remain DNP in the reference EVT population")

    calculations = calculate()
    committed_calculations = json.loads((ROOT / "design_calculations.json").read_text(encoding="utf-8"))
    require(committed_calculations == calculations, "design_calculations.json is stale")
    adc = calculations["adc"]
    require(adc["straps"] == {"S/M": 0, "FMT1": 0, "FMT0": 1, "FS2": 0, "FS1": 0, "FS0": 1, "HPFD": 1},
            "ADC strap calculation changed")
    require(adc["bck_hz"] == 6_144_000.0 and adc["system_clock_hz"] == 24_576_000.0,
            "ADC clock contract changed")
    gain_settings = calculations["gain"]["settings"]
    require(abs(gain_settings["26_db_default"]["gain_db"] - 26.0639211484) < 1e-9,
            "default gain calculation changed")
    require(gain_settings["32_db"]["stress"]["100_mv_rms"]["adc_level_dbfs"] > 0.0,
            "32 dB stress case must remain documented as clipping")

    tracks = list(board.GetTracks())
    vias = [item for item in tracks if isinstance(item, pcbnew.PCB_VIA)]
    segments = [item for item in tracks if isinstance(item, pcbnew.PCB_TRACK) and not isinstance(item, pcbnew.PCB_VIA)]
    require(segments, "board has no routed track segments")
    require(vias, "board has no routed vias")
    min_track_mm = min(item.GetWidth() for item in segments) / 1e6
    min_via_drill_mm = min(item.GetDrillValue() for item in vias) / 1e6
    require(min_track_mm >= 0.25, f"track width below 0.25 mm: {min_track_mm:.3f} mm")
    require(min_via_drill_mm >= 0.35, f"via drill below 0.35 mm: {min_via_drill_mm:.3f} mm")

    lengths = route_lengths(board)
    stats = {
        "board": args.board.name,
        "kicad_version": drc["kicad_version"],
        "status": "EVT routed artifact; not fabricated or physically validated",
        "outline_mm": [round(width_mm - 0.1, 3), round(height_mm - 0.1, 3)],
        "copper_layers": board.GetCopperLayerCount(),
        "schematic_parts": len(PARTS),
        "board_footprints": len(footprints),
        "named_nets": len([net for net in board.GetNetInfo().NetsByNetcode().values() if net.GetNetname()]),
        "track_segments": len(segments),
        "vias": len(vias),
        "minimum_track_width_mm": min_track_mm,
        "minimum_via_drill_mm": min_via_drill_mm,
        "erc_violations": erc_violations,
        "drc_violations": len(drc["violations"]),
        "unconnected_items": len(drc["unconnected_items"]),
        "clock_route_lengths_mm": {
            name: round(lengths.get(name, 0.0), 3)
            for name in ("SCKI_24M576_IN", "SCKI_24M576", "ADC_BCK_SRC", "ADC_BCK_OUT", "ADC_LRCK_SRC", "ADC_LRCK_OUT")
        },
        "release_gates": [
            "enclosure-qualified isolated RCA and ground-post mechanics",
            "measured total input capacitance for every relay state",
            "input-referred noise, hum, overload, crosstalk, RF injection, and IEC ESD tests",
            "stackup review and controlled return-current inspection",
            "PCM4202 clock/data timing and 128fS FPGA receiver validation",
            "relay switching only while the complete output path is hardware-muted",
        ],
    }
    rendered = json.dumps(stats, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    print("PASS: phono/ADC Rev-A EVT board invariants verified")


if __name__ == "__main__":
    main()
