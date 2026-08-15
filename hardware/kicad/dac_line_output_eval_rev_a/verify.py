#!/usr/bin/env python3
"""Verify Rev-A PCM5242 DAC/line-output electrical and PCB invariants."""

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
    parser.add_argument("--board", type=Path, default=ROOT / "dac_line_output_eval.kicad_pcb")
    parser.add_argument("--erc", type=Path, required=True)
    parser.add_argument("--drc", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    erc = json.loads(args.erc.read_text(encoding="utf-8"))
    drc = json.loads(args.drc.read_text(encoding="utf-8"))
    erc_violations = sum(len(sheet["violations"]) for sheet in erc["sheets"])
    require(erc_violations == 0, f"ERC contains {erc_violations} violations")
    require(not drc["violations"], f"DRC contains {len(drc['violations'])} violations")
    require(not drc["unconnected_items"],
            f"DRC contains {len(drc['unconnected_items'])} unconnected items")

    board = pcbnew.LoadBoard(str(args.board))
    footprints = {item.GetReference(): item for item in board.GetFootprints()}
    expected_refs = {component.ref for component in PARTS} | {"H1", "H2", "H3", "H4"}
    require(set(footprints) == expected_refs, "footprint reference set differs from source model")
    require(board.GetCopperLayerCount() == 4, "DAC board is not four-layer")
    require(board.GetLayerName(pcbnew.In1_Cu) == "GND", "L2 is not the continuous GND reference")
    require(board.GetLayerName(pcbnew.In2_Cu) == "POWER_SIG", "L3 name changed")

    bounds = board.GetBoardEdgesBoundingBox()
    width_mm = bounds.GetWidth() / 1e6
    height_mm = bounds.GetHeight() / 1e6
    require(abs(width_mm - 112.1) < 0.01, f"unexpected outline width {width_mm:.3f} mm")
    require(abs(height_mm - 72.1) < 0.01, f"unexpected outline height {height_mm:.3f} mm")

    expected_dac = {
        "1": "DAC_XSMT_PIN", "2": "DAC_LDOO", "3": "GND", "4": "+3V3D",
        "5": "+3V3A", "6": "CP_FLY_P", "7": "GND", "8": "CP_FLY_N",
        "9": "DAC_VNEG", "10": "DAC_LP", "11": "DAC_LN", "12": "DAC_RN",
        "13": "DAC_RP", "14": "+3V3A", "15": "GND", "17": "I2C_SDA",
        "18": "I2C_SCL", "22": "GND", "23": "GND", "24": "+3V3D",
        "26": "DAC_SCK", "27": "DAC_BCK", "28": "DAC_DIN", "31": "DAC_LRCK",
        "32": "GND", "33": "GND",
    }
    require(pad_map(footprints["U1"]) == expected_dac, "PCM5242 pad/net map changed")
    require(footprints["U1"].GetFPID().GetLibItemName() ==
            "Texas_RHB0032E_VQFN-32-1EP_5x5mm_P0.5mm_EP3.45x3.45mm_ThermalVias",
            "PCM5242 footprint is not the TI RHB-32 exposed-pad package")
    require(abs(footprints["U1"].GetOrientationDegrees() - 90.0) < 0.01,
            "PCM5242 no longer faces analog outputs toward the reconstruction network")

    require(pad_map(footprints["U4"]) == {
        "1": "LINE_RELAY_EN_CTL", "2": "HARD_MUTE_N", "3": "GND",
        "4": "LINE_RELAY_EN_SAFE", "5": "+3V3D",
    }, "relay hardware-interlock gate map changed")
    require(pad_map(footprints["U5"]) == {
        "1": "DAC_SOFT_UNMUTE_CTL", "2": "HARD_MUTE_N", "3": "GND",
        "4": "DAC_XSMT_SAFE", "5": "+3V3D",
    }, "XSMT hardware-interlock gate map changed")
    for reference, source, safe in (
        ("U4", "LINE_RELAY_EN_CTL", "LINE_RELAY_EN_SAFE"),
        ("U5", "DAC_SOFT_UNMUTE_CTL", "DAC_XSMT_SAFE"),
    ):
        mapping = pad_map(footprints[reference])
        require(mapping["1"] == source and mapping["2"] == "HARD_MUTE_N" and mapping["4"] == safe,
                f"{reference} no longer requires controller and supervisor release")

    require(pad_map(footprints["K1"]) == {
        "1": "+5V_RELAY", "3": "L_BAL_P_FILT", "4": "L_BAL_P_OUT",
        "5": "L_BAL_N_OUT", "6": "L_BAL_N_FILT", "8": "K1_COIL_LOW",
    }, "left balanced relay no longer uses normally-open contacts")
    require(pad_map(footprints["K2"]) == {
        "1": "+5V_RELAY", "3": "R_BAL_P_FILT", "4": "R_BAL_P_OUT",
        "5": "R_BAL_N_OUT", "6": "R_BAL_N_FILT", "8": "K2_COIL_LOW",
    }, "right balanced relay no longer uses normally-open contacts")
    require(pad_map(footprints["K3"]) == {
        "1": "+5V_RELAY", "3": "L_RCA_FILT", "4": "L_RCA_OUT",
        "5": "R_RCA_OUT", "6": "R_RCA_FILT", "8": "K3_COIL_LOW",
    }, "RCA relay no longer uses normally-open contacts")

    values = {component.ref: component.value for component in PARTS}
    for reference in ("R20", "R21", "R22", "R23", "R24", "R25"):
        require(values[reference] == "499R_0.1%", f"{reference} reconstruction resistance changed")
    require(values["C20"] == values["C21"] == "1nF_C0G_DIFF",
            "balanced differential reconstruction capacitors changed")
    require(values["C22"] == values["C23"] == "2.2nF_C0G_SE",
            "RCA reconstruction capacitors changed")
    for reference in ("R6", "R12", "R13", "R14"):
        require(values[reference] == "100k_FAIL_MUTE", f"{reference} fail-mute pull-down changed")
    for reference in ("R31", "R32", "R33"):
        require(pad_map(footprints[reference])["1"] == "LINE_RELAY_EN_SAFE",
                f"{reference} bypasses the hardware relay interlock")
    require(pad_map(footprints["R5"]) == {"1": "DAC_XSMT_SAFE", "2": "DAC_XSMT_PIN"},
            "PCM5242 XSMT bypasses its hardware interlock")
    for reference in ("R50", "C50"):
        require(footprints[reference].IsDNP(), f"{reference} must remain DNP")

    calculations = calculate()
    committed = json.loads((ROOT / "design_calculations.json").read_text(encoding="utf-8"))
    require(committed == calculations, "design_calculations.json is stale")
    converter = calculations["converter"]
    require(converter["sample_rate_hz"] == 48_000.0 and converter["sck_ratio_fs"] == 512.0,
            "DAC sample/master-clock contract changed")
    require(converter["bck_ratio_fs"] == 64.0, "DAC BCK contract is not 64 fS")
    outputs = calculations["outputs"]
    require(abs(outputs["balanced"]["full_scale_at_dc_rms_v"] - 4.0003809887) < 1e-9,
            "loaded balanced full-scale calculation changed")
    require(abs(outputs["rca"]["full_scale_at_dc_rms_v"] - 2.0001904943) < 1e-9,
            "loaded RCA full-scale calculation changed")

    tracks = list(board.GetTracks())
    vias = [item for item in tracks if isinstance(item, pcbnew.PCB_VIA)]
    segments = [item for item in tracks
                if isinstance(item, pcbnew.PCB_TRACK) and not isinstance(item, pcbnew.PCB_VIA)]
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
        "named_nets": len([net for net in board.GetNetInfo().NetsByNetcode().values()
                           if net.GetNetname()]),
        "track_segments": len(segments),
        "vias": len(vias),
        "minimum_track_width_mm": min_track_mm,
        "minimum_via_drill_mm": min_via_drill_mm,
        "erc_violations": erc_violations,
        "drc_violations": len(drc["violations"]),
        "unconnected_items": len(drc["unconnected_items"]),
        "audio_route_lengths_mm": {
            name: round(lengths.get(name, 0.0), 3)
            for name in ("DAC_LP", "DAC_LN", "DAC_RP", "DAC_RN",
                         "L_BAL_P_FILT", "L_BAL_N_FILT", "R_BAL_P_FILT", "R_BAL_N_FILT")
        },
        "release_gates": [
            "PCM5242 critical-register readback under asserted hardware mute",
            "loaded THD+N, dynamic range, channel balance, crosstalk, and reconstruction response",
            "power-up, power-down, brownout, unplug, and external-supervisor mute sequencing",
            "enclosure XLR/RCA connector mechanics, pin-1/chassis treatment, and harness qualification",
            "IEC ESD/EFT and RF-immunity qualification of provisional output clamps",
            "fabricator stackup, impedance/return-current, DFM, thermal, and assembly review",
        ],
    }
    rendered = json.dumps(stats, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    print("PASS: PCM5242 DAC/line-output Rev-A EVT board invariants verified")


if __name__ == "__main__":
    main()
