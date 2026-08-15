#!/usr/bin/env python3
"""Generate the Rev-A PCM5242 DAC and protected line-output KiCad project."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pcbnew

from design import calculate


ROOT = Path(__file__).resolve().parent
NAME = "dac_line_output_eval"
MM = pcbnew.FromMM
CORE_PATH = ROOT.parent / "front_panel_motor_eval_rev_a" / "generate.py"
SPEC = importlib.util.spec_from_file_location("fpga_amp_kicad_core_dac", CORE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import generator core from {CORE_PATH}")
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)
Part = core.Part


def part(ref: str, value: str, footprint: str, nets: dict[str, str],
         xy: tuple[float, float], rotation: float = 0.0,
         description: str = "") -> Part:
    return Part(ref, value, footprint, nets, xy, rotation, description)


PARTS: list[Part] = [
    part("J1", "DAC_AUDIO", "Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical", {
        "1": "DAC_SCK_IN", "2": "GND", "3": "DAC_BCK_IN", "4": "GND",
        "5": "DAC_LRCK_IN", "6": "GND", "7": "DAC_DIN_IN", "8": "GND",
        "9": "+3V3D", "10": "GND",
    }, (8.0, 18.0), 90.0, "24.576MHz SCK, 3.072MHz BCK, 48kHz LRCK, 24-bit I2S from digital board"),
    part("J2", "DAC_CONTROL", "Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical", {
        "1": "+3V3D", "2": "GND", "3": "I2C_SCL_IN", "4": "I2C_SDA_IN",
        "5": "DAC_SOFT_UNMUTE_CTL", "6": "LINE_RELAY_EN_CTL",
        "7": "OB_PRESENT_N", "8": "HARD_MUTE_N", "9": "GND", "10": "GND",
    }, (8.0, 38.0), 90.0, "Low-speed control; DAC and relay paths fail muted"),
    part("J3", "POWER_INPUT", "Connector_PinHeader_2.54mm:PinHeader_2x04_P2.54mm_Vertical", {
        "1": "+3V7A_IN", "2": "GND", "3": "+3V7D_IN", "4": "GND",
        "5": "+5V_RELAY", "6": "GND", "7": "CHASSIS", "8": "GND",
    }, (8.0, 58.0), 90.0, "Separate analog, digital, relay, chassis, and return feeds from power board"),
    part("J4", "BALANCED_PANEL_HARNESS_EVT", "Connector_JST:JST_XH_B8B-XH-A_1x08_P2.50mm_Vertical", {
        "1": "L_BAL_P_OUT", "2": "L_BAL_N_OUT", "3": "CHASSIS", "4": "GND",
        "5": "R_BAL_P_OUT", "6": "R_BAL_N_OUT", "7": "CHASSIS", "8": "GND",
    }, (108.0, 34.0), 90.0, "EVT harness to enclosure XLRs; XLR pin 1 bonds to chassis at connector"),
    part("J5", "RCA_PANEL_HARNESS_EVT", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical", {
        "1": "L_RCA_OUT", "2": "GND", "3": "R_RCA_OUT",
    }, (108.0, 50.0), 90.0, "EVT harness to isolated RCA output jacks"),
    part("U1", "PCM5242RHBR", "Package_DFN_QFN:Texas_RHB0032E_VQFN-32-1EP_5x5mm_P0.5mm_EP3.45x3.45mm_ThermalVias", {
        "1": "DAC_XSMT_PIN", "2": "DAC_LDOO", "3": "GND", "4": "+3V3D",
        "5": "+3V3A", "6": "CP_FLY_P", "7": "GND", "8": "CP_FLY_N",
        "9": "DAC_VNEG", "10": "DAC_LP", "11": "DAC_LN", "12": "DAC_RN",
        "13": "DAC_RP", "14": "+3V3A", "15": "GND", "17": "I2C_SDA",
        "18": "I2C_SCL", "22": "GND", "23": "GND", "24": "+3V3D",
        "26": "DAC_SCK", "27": "DAC_BCK", "28": "DAC_DIN", "31": "DAC_LRCK",
        "32": "GND", "33": "GND",
    }, (49.0, 34.0), 90.0, "Stereo DirectPath DAC; I2C mode, slave clocks, external SCK, VREF output mode"),
    part("U2", "TPS7A2033PDBVR_ANALOG", "Package_TO_SOT_SMD:SOT-23-5", {
        "1": "+3V7A_IN", "2": "GND", "3": "+3V7A_IN", "5": "+3V3A_RAW",
    }, (41.0, 62.0), 0.0, "Low-noise analog/charge-pump 3.3V post-regulator"),
    part("U3", "TPS7A2033PDBVR_DIGITAL", "Package_TO_SOT_SMD:SOT-23-5", {
        "1": "+3V7D_IN", "2": "GND", "3": "+3V7D_IN", "5": "+3V3D",
    }, (55.0, 62.0), 0.0, "Low-noise digital 3.3V post-regulator"),
    part("U4", "SN74LVC1G08DBVR_RELAY_INTERLOCK", "Package_TO_SOT_SMD:SOT-23-5", {
        "1": "LINE_RELAY_EN_CTL", "2": "HARD_MUTE_N", "3": "GND",
        "4": "LINE_RELAY_EN_SAFE", "5": "+3V3D",
    }, (29.0, 55.0), 0.0,
         "Hardware AND: controller and independent supervisor must both release line relays"),
    part("U5", "SN74LVC1G08DBVR_XSMT_INTERLOCK", "Package_TO_SOT_SMD:SOT-23-5", {
        "1": "DAC_SOFT_UNMUTE_CTL", "2": "HARD_MUTE_N", "3": "GND",
        "4": "DAC_XSMT_SAFE", "5": "+3V3D",
    }, (29.0, 34.0), 0.0,
         "Hardware AND: controller and independent supervisor must both release DAC XSMT"),
]


def add_passive(ref: str, value: str, footprint: str, a: str, b: str,
                xy: tuple[float, float], rotation: float = 0.0,
                description: str = "") -> None:
    PARTS.append(part(ref, value, footprint, {"1": a, "2": b}, xy, rotation, description))


# Digital clocks and explicit fail-muted controls.
for ref, source, sink, xy in [
    ("R1", "DAC_SCK_IN", "DAC_SCK", (31.0, 20.0)),
    ("R2", "DAC_BCK_IN", "DAC_BCK", (31.0, 23.0)),
    ("R3", "DAC_LRCK_IN", "DAC_LRCK", (31.0, 26.0)),
    ("R4", "DAC_DIN_IN", "DAC_DIN", (31.0, 29.0)),
]:
    add_passive(ref, "0R_LINK", "Resistor_SMD:R_0402_1005Metric", source, sink, xy,
                description="Receiver-side link; source damping belongs on digital board")
add_passive("R5", "1k", "Resistor_SMD:R_0603_1608Metric", "DAC_XSMT_SAFE", "DAC_XSMT_PIN", (36.0, 35.0))
add_passive("R6", "100k_FAIL_MUTE", "Resistor_SMD:R_0603_1608Metric", "DAC_XSMT_PIN", "GND", (39.0, 38.0), 90.0)
add_passive("C1", "10nF_X7R", "Capacitor_SMD:C_0603_1608Metric", "DAC_XSMT_PIN", "GND", (42.0, 38.0), 90.0)
add_passive("R7", "4.7k", "Resistor_SMD:R_0603_1608Metric", "+3V3D", "I2C_SCL", (31.0, 43.0), 90.0)
add_passive("R8", "4.7k", "Resistor_SMD:R_0603_1608Metric", "+3V3D", "I2C_SDA", (35.0, 43.0), 90.0)
add_passive("R9", "0R_LINK", "Resistor_SMD:R_0603_1608Metric", "I2C_SCL_IN", "I2C_SCL", (24.0, 43.0))
add_passive("R10", "0R_LINK", "Resistor_SMD:R_0603_1608Metric", "I2C_SDA_IN", "I2C_SDA", (24.0, 47.0))
add_passive("R11", "10k", "Resistor_SMD:R_0603_1608Metric", "OB_PRESENT_N", "GND", (17.0, 49.0), 90.0)
add_passive("R12", "100k_FAIL_MUTE", "Resistor_SMD:R_0603_1608Metric", "LINE_RELAY_EN_CTL", "GND", (20.0, 52.0), 90.0)
add_passive("R13", "100k_FAIL_MUTE", "Resistor_SMD:R_0603_1608Metric", "HARD_MUTE_N", "GND", (23.0, 52.0), 90.0,
            description="Independent supervisor release defaults low if disconnected")
add_passive("R14", "100k_FAIL_MUTE", "Resistor_SMD:R_0603_1608Metric", "DAC_SOFT_UNMUTE_CTL", "GND", (22.0, 33.0), 90.0)
add_passive("C11", "100nF_X7R", "Capacitor_SMD:C_0402_1005Metric", "+3V3D", "GND", (32.0, 56.0), 90.0,
            description="U4 local bypass")
add_passive("C12", "100nF_X7R", "Capacitor_SMD:C_0402_1005Metric", "+3V3D", "GND", (32.0, 33.0), 90.0,
            description="U5 local bypass")

# PCM5242 supply and charge-pump network, following the data sheet/EVM.
for ref, value, a, b, xy, footprint in [
    ("C2", "100nF_X7R_LDOO", "DAC_LDOO", "GND", (45.0, 27.0), "Capacitor_SMD:C_0402_1005Metric"),
    ("C3", "2.2uF_X7R_FLY", "CP_FLY_P", "CP_FLY_N", (49.0, 27.0), "Capacitor_SMD:C_0603_1608Metric"),
    ("C4", "2.2uF_X7R_VNEG", "DAC_VNEG", "GND", (54.0, 27.0), "Capacitor_SMD:C_0603_1608Metric"),
    ("C5", "100nF_X7R_AVDD", "+3V3A", "GND", (45.0, 41.0), "Capacitor_SMD:C_0402_1005Metric"),
    ("C6", "10uF_X5R_AVDD", "+3V3A", "GND", (49.0, 43.0), "Capacitor_SMD:C_0805_2012Metric"),
    ("C7", "100nF_X7R_CPVDD", "+3V3A", "GND", (54.0, 41.0), "Capacitor_SMD:C_0402_1005Metric"),
    ("C8", "2.2uF_X7R_CPVDD", "+3V3A", "GND", (58.0, 43.0), "Capacitor_SMD:C_0603_1608Metric"),
    ("C9", "100nF_X7R_DVDD", "+3V3D", "GND", (43.0, 22.0), "Capacitor_SMD:C_0402_1005Metric"),
    ("C10", "10uF_X5R_DVDD", "+3V3D", "GND", (47.0, 20.0), "Capacitor_SMD:C_0805_2012Metric"),
]:
    add_passive(ref, value, footprint, a, b, xy)

# Separate differential and RCA reconstruction branches preserve their official
# reference networks and allow all outputs to fail open through signal relays.
for ref, source, filtered, xy in [
    ("R20", "DAC_LP", "L_BAL_P_FILT", (63.0, 19.0)),
    ("R21", "DAC_LN", "L_BAL_N_FILT", (63.0, 24.0)),
    ("R22", "DAC_RP", "R_BAL_P_FILT", (63.0, 38.0)),
    ("R23", "DAC_RN", "R_BAL_N_FILT", (63.0, 43.0)),
    ("R24", "DAC_LP", "L_RCA_FILT", (63.0, 50.0)),
    ("R25", "DAC_RP", "R_RCA_FILT", (63.0, 55.0)),
]:
    add_passive(ref, "499R_0.1%", "Resistor_SMD:R_0805_2012Metric", source, filtered, xy)
add_passive("C20", "1nF_C0G_DIFF", "Capacitor_SMD:C_0603_1608Metric", "L_BAL_P_FILT", "L_BAL_N_FILT", (69.0, 22.0), 90.0)
add_passive("C21", "1nF_C0G_DIFF", "Capacitor_SMD:C_0603_1608Metric", "R_BAL_P_FILT", "R_BAL_N_FILT", (69.0, 41.0), 90.0)
add_passive("C22", "2.2nF_C0G_SE", "Capacitor_SMD:C_0603_1608Metric", "L_RCA_FILT", "GND", (69.0, 50.0), 90.0)
add_passive("C23", "2.2nF_C0G_SE", "Capacitor_SMD:C_0603_1608Metric", "R_RCA_FILT", "GND", (69.0, 55.0), 90.0)

# Omron G6K-2F-Y coil 1/8; NO contacts 3-4 and 6-5. Unpowered is hard mute.
for index, nets, xy, description in [
    (1, {"1": "+5V_RELAY", "3": "L_BAL_P_FILT", "4": "L_BAL_P_OUT", "5": "L_BAL_N_OUT", "6": "L_BAL_N_FILT", "8": "K1_COIL_LOW"}, (82.0, 22.0), "Left balanced normally-open hard mute"),
    (2, {"1": "+5V_RELAY", "3": "R_BAL_P_FILT", "4": "R_BAL_P_OUT", "5": "R_BAL_N_OUT", "6": "R_BAL_N_FILT", "8": "K2_COIL_LOW"}, (82.0, 41.0), "Right balanced normally-open hard mute"),
    (3, {"1": "+5V_RELAY", "3": "L_RCA_FILT", "4": "L_RCA_OUT", "5": "R_RCA_OUT", "6": "R_RCA_FILT", "8": "K3_COIL_LOW"}, (82.0, 55.0), "Stereo RCA normally-open hard mute"),
]:
    PARTS.append(part(f"K{index}", f"G6K-2F-Y-5V_FAIL_OPEN_{index}", "Relay_SMD:Relay_DPDT_Omron_G6K-2F-Y", nets, xy, description=description))
    driver_x = 68.0 + index * 7.0
    PARTS.append(part(f"Q{index}", "MMBT3904", "Package_TO_SOT_SMD:SOT-23", {
        "1": f"K{index}_BASE", "2": "GND", "3": f"K{index}_COIL_LOW",
    }, (driver_x, 67.0), description="Independent low-side relay driver"))
    add_passive(f"R{30 + index}", "2.2k", "Resistor_SMD:R_0603_1608Metric", "LINE_RELAY_EN_SAFE", f"K{index}_BASE", (driver_x, 63.0))
    add_passive(f"R{33 + index}", "100k", "Resistor_SMD:R_0603_1608Metric", f"K{index}_BASE", "GND", (driver_x, 71.0))
    add_passive(f"D{index}", "1N4148W_FLYBACK", "Diode_SMD:D_SOD-123", "+5V_RELAY", f"K{index}_COIL_LOW", (91.0 + index * 5.0, 63.0))

# Output connector ESD candidates clamp to chassis after the current-limiting
# networks and relays. Bidirectional behavior and enclosure discharge path must
# still be physically qualified.
for index, net in enumerate(["L_BAL_P_OUT", "L_BAL_N_OUT", "R_BAL_P_OUT", "R_BAL_N_OUT", "L_RCA_OUT", "R_RCA_OUT"], 4):
    add_passive(f"D{index}", "PESD5V0X1BCL_EVT", "Diode_SMD:D_SOD-882", "CHASSIS", net, (98.0, 13.0 + (index - 4) * 8.0), 90.0,
                "EVT bidirectional line-output ESD candidate; qualify to IEC test plan")

# Post-regulators and their required local capacitance.
add_passive("R40", "1R_ANALOG_ISOLATION", "Resistor_SMD:R_0805_2012Metric", "+3V3A_RAW", "+3V3A", (47.0, 59.0))
for ref, value, rail, xy in [
    ("C30", "1uF_X7R_LDO_IN", "+3V7A_IN", (36.0, 66.0)),
    ("C31", "2.2uF_X7R_LDO_OUT", "+3V3A_RAW", (44.0, 67.0)),
    ("C32", "10uF_X5R_ANALOG_BULK", "+3V3A", (49.0, 67.0)),
    ("C33", "1uF_X7R_LDO_IN", "+3V7D_IN", (51.0, 66.0)),
    ("C34", "2.2uF_X7R_LDO_OUT", "+3V3D", (58.0, 67.0)),
    ("C35", "10uF_X5R_DIGITAL_BULK", "+3V3D", (63.0, 67.0)),
    ("C36", "10uF_X5R_RELAY_BULK", "+5V_RELAY", (69.0, 67.0)),
]:
    add_passive(ref, value, "Capacitor_SMD:C_0805_2012Metric", rail, "GND", xy, 90.0)

# The power-board/chassis star owns the DC bond; these are measurement options.
add_passive("R50", "DNP_0R_CHASSIS_BOND", "Resistor_SMD:R_1206_3216Metric", "CHASSIS", "GND", (17.0, 62.0), description="DNP; populate only from complete chassis grounding review")
add_passive("C50", "DNP_4.7nF_CHASSIS", "Capacitor_SMD:C_1206_3216Metric", "CHASSIS", "GND", (22.0, 62.0), description="DNP; safety/EMC population requires rated part and review")

for index, (net, xy) in enumerate([
    ("+3V3A", (45.0, 54.0)), ("+3V3D", (52.0, 54.0)),
    ("DAC_XSMT_PIN", (39.0, 32.0)), ("LINE_RELAY_EN_SAFE", (70.0, 61.0)),
    ("L_RCA_OUT", (100.0, 48.0)), ("R_RCA_OUT", (100.0, 54.0)),
    ("CHASSIS", (16.0, 68.0)), ("GND", (26.0, 68.0)),
], 1):
    PARTS.append(part(f"TP{index}", net, "TestPoint:TestPoint_Pad_D1.0mm", {"1": net}, xy,
                      description="Local EVT pogo point"))


def library_path(footprint: str) -> tuple[str, str]:
    library, name = footprint.split(":", 1)
    return f"/usr/share/kicad/footprints/{library}.pretty", name


def add_outline(board: pcbnew.BOARD) -> None:
    corners = [(2.0, 2.0), (114.0, 2.0), (114.0, 74.0), (2.0, 74.0), (2.0, 2.0)]
    for start, end in zip(corners, corners[1:]):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetWidth(MM(0.1))
        edge.SetStart(pcbnew.VECTOR2I(MM(start[0]), MM(start[1])))
        edge.SetEnd(pcbnew.VECTOR2I(MM(end[0]), MM(end[1])))
        board.Add(edge)


def add_text(board: pcbnew.BOARD, text: str, xy: tuple[float, float], size: float = 0.8) -> None:
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetPosition(pcbnew.VECTOR2I(MM(xy[0]), MM(xy[1])))
    item.SetLayer(pcbnew.F_SilkS)
    item.SetTextHeight(MM(size))
    item.SetTextWidth(MM(size))
    item.SetTextThickness(MM(0.15))
    board.Add(item)


def add_zone(board: pcbnew.BOARD, net: pcbnew.NETINFO_ITEM, layer: int) -> None:
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    zone.SetNet(net)
    zone.SetLocalClearance(MM(0.25))
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in [(2.5, 2.5), (113.5, 2.5), (113.5, 73.5), (2.5, 73.5)]:
        outline.Append(MM(x), MM(y))
    board.Add(zone)


def write_board() -> Path:
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    board.SetLayerName(pcbnew.In1_Cu, "GND")
    board.SetLayerName(pcbnew.In2_Cu, "POWER_SIG")
    default = board.GetAllNetClasses()["Default"]
    default.SetClearance(MM(0.20))
    default.SetTrackWidth(MM(0.25))
    default.SetViaDiameter(MM(0.70))
    default.SetViaDrill(MM(0.35))
    board.GetDesignSettings().m_TrackMinWidth = MM(0.15)
    board.GetDesignSettings().m_MinClearance = MM(0.15)
    board.GetDesignSettings().m_MinThroughDrill = MM(0.20)

    net_names = sorted({net for component in PARTS for net in component.nets.values()})
    nets: dict[str, pcbnew.NETINFO_ITEM] = {}
    for name in net_names:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        nets[name] = net

    for component in PARTS:
        directory, footprint_name = library_path(component.footprint)
        footprint = pcbnew.FootprintLoad(directory, footprint_name)
        if footprint is None:
            raise RuntimeError(f"cannot load {component.footprint}")
        footprint.SetReference(component.ref)
        footprint.SetValue(component.value)
        if "DNP" in component.value:
            footprint.SetDNP(True)
        footprint.Reference().SetLayer(pcbnew.F_Fab)
        footprint.Value().SetLayer(pcbnew.F_Fab)
        footprint.SetPosition(pcbnew.VECTOR2I(MM(component.xy[0]), MM(component.xy[1])))
        footprint.SetOrientationDegrees(component.rotation)
        for pad_number, net_name in component.nets.items():
            pads = [pad for pad in footprint.Pads() if pad.GetNumber() == pad_number]
            if not pads:
                raise RuntimeError(f"{component.ref}: {component.footprint} lacks pad {pad_number}")
            for pad in pads:
                pad.SetNet(nets[net_name])
        board.Add(footprint)

    footprints = {item.GetReference(): item for item in board.GetFootprints()}
    for pad in footprints["U1"].Pads():
        if pad.GetNumber() == "33":
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    for ref, xy in [("H1", (6.0, 6.0)), ("H2", (110.0, 6.0)), ("H3", (6.0, 70.0)), ("H4", (110.0, 70.0))]:
        footprint = pcbnew.FootprintLoad("/usr/share/kicad/footprints/MountingHole.pretty", "MountingHole_3.2mm_M3")
        footprint.SetReference(ref)
        footprint.SetValue("M3_CHASSIS_STANDOFF")
        footprint.Reference().SetLayer(pcbnew.F_Fab)
        footprint.Value().SetLayer(pcbnew.F_Fab)
        footprint.SetPosition(pcbnew.VECTOR2I(MM(xy[0]), MM(xy[1])))
        board.Add(footprint)

    add_outline(board)
    add_text(board, "FPGA AMP - PCM5242 DAC / LINE OUTPUT REV A EVT", (58.0, 72.0))
    add_text(board, "NOT FAB RELEASED - MEASURE THD+N / MUTE / ESD", (58.0, 69.5))
    add_text(board, "DIGITAL / CONTROL", (18.0, 10.0))
    add_text(board, "PCM5242 / CLOCKS", (49.0, 10.0))
    add_text(board, "FAIL-OPEN RELAYS", (82.0, 10.0))
    add_text(board, "DEFAULT: XSMT LOW + RELAYS OPEN", (58.0, 6.0))
    add_zone(board, nets["GND"], pcbnew.In1_Cu)
    add_zone(board, nets["GND"], pcbnew.B_Cu)
    path = ROOT / f"{NAME}.kicad_pcb"
    pcbnew.SaveBoard(str(path), board)
    return path


def write_schematic() -> Path:
    core.ROOT = ROOT
    core.NAME = NAME
    core.PARTS = PARTS
    root_uuid = core.uid("dac-line-schematic-root")
    lines = [
        "(kicad_sch", "  (version 20250114)", "  (generator \"fpga_amp_generate\")",
        "  (generator_version \"1.0\")", f"  (uuid {core.q(root_uuid)})", "  (paper \"A0\")",
        "  (title_block (title \"FPGA Amp PCM5242 DAC / line-output EVT\") (date \"2026-08-15\") (rev \"A / EVT\") (company \"FPGA_Amp\")",
        "    (comment 1 \"48k slave I2S; external 24.576MHz SCK; I2C unity reference configuration\")",
        "    (comment 2 \"4Vrms balanced / 2Vrms RCA targets; dual fail-low hardware mute interlocks\")",
        "    (comment 3 \"NOT PRODUCTION RELEASED OR PHYSICALLY VALIDATED\")",
        "    (comment 4 \"Generated from generate.py and design.py\"))", "  (lib_symbols",
    ]
    lines.extend("    " + core.native_symbol_definition(component).replace("\n", "\n    ") for component in PARTS)
    lines.append("  )")
    instances: list[str] = []
    labels: list[str] = []
    wires: list[str] = []
    for index, component in enumerate(PARTS):
        instance, component_labels, component_wires = core.native_symbol_instance(component, index, root_uuid)
        instances.append(instance)
        labels.extend(component_labels)
        wires.extend(component_wires)
    lines.extend("  " + wire.replace("\n", "\n  ") for wire in wires)
    lines.extend("  " + label.replace("\n", "\n  ") for label in labels)
    lines.extend("  " + instance.replace("\n", "\n  ") for instance in instances)
    lines.extend(["  (sheet_instances (path \"/\" (page \"1\")))", "  (embedded_fonts no)", ")", ""])
    path = ROOT / f"{NAME}.kicad_sch"
    path.write_text("\n".join(lines), encoding="utf-8")

    library = ["(kicad_symbol_lib", "  (version 20241209)", "  (generator \"kicad_symbol_editor\")", "  (generator_version \"9.0\")"]
    for component in PARTS:
        definition = core.native_symbol_definition(component).replace(
            core.q("FPGA_Amp:" + core.sym_name(component)), core.q(core.sym_name(component)), 1)
        library.append("  " + definition.replace("\n", "\n  "))
    library.extend([")", ""])
    (ROOT / f"{NAME}.kicad_sym").write_text("\n".join(library), encoding="utf-8")
    (ROOT / "sym-lib-table").write_text(
        '(sym_lib_table\n  (version 7)\n  (lib (name "FPGA_Amp")(type "KiCad")'
        f'(uri "${{KIPRJMOD}}/{NAME}.kicad_sym")(options "")(descr "Generated DAC line board symbols"))\n)\n',
        encoding="utf-8")
    return path


def write_project_and_bom() -> None:
    project = {
        "board": {}, "boards": [], "cvpcb": {}, "erc": {}, "libraries": {},
        "meta": {"filename": f"{NAME}.kicad_pro", "version": 1},
        "net_settings": {"classes": [{"name": "Default", "clearance": 0.20,
            "track_width": 0.25, "via_diameter": 0.70, "via_drill": 0.35}],
            "meta": {"version": 3}},
        "pcbnew": {}, "schematic": {}, "sheets": [], "text_variables": {},
    }
    (ROOT / f"{NAME}.kicad_pro").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")
    rows = ["Reference,Value,Footprint,Description"]
    for component in PARTS:
        rows.append(",".join([component.ref, component.value, component.footprint,
                              component.description.replace(",", ";")]))
    (ROOT / "bom.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (ROOT / "design_calculations.json").write_text(
        json.dumps(calculate(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    if shutil.which("kicad-cli") is None:
        raise SystemExit("kicad-cli is required")
    write_schematic()
    write_project_and_bom()
    board = write_board()
    print(f"generated {board}")
    print(f"parts={len(PARTS)} nets={len({net for component in PARTS for net in component.nets.values()})} layers=4")


if __name__ == "__main__":
    main()
