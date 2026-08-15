#!/usr/bin/env python3
"""Generate the Rev-A shielded MM phono/ADC KiCad project.

The native schematic and placed four-layer PCB share one explicit component
and net table.  The output is an EVT artifact: it is concrete enough for ERC,
DRC, routing, and bench review, but enclosure connectors and ESD performance
remain qualification gates.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pcbnew

from design import calculate


ROOT = Path(__file__).resolve().parent
NAME = "phono_adc_eval"
MM = pcbnew.FromMM

CORE_PATH = ROOT.parent / "front_panel_motor_eval_rev_a" / "generate.py"
SPEC = importlib.util.spec_from_file_location("fpga_amp_kicad_core_phono", CORE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import generator core from {CORE_PATH}")
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)
Part = core.Part


def part(
    ref: str,
    value: str,
    footprint: str,
    nets: dict[str, str],
    xy: tuple[float, float],
    rotation: float = 0.0,
    description: str = "",
) -> Part:
    return Part(ref, value, footprint, nets, xy, rotation, description)


PARTS: list[Part] = [
    part("J1", "ISOLATED_PANEL_RCA_HARNESS", "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical", {
        "1": "L_INPUT_RAW", "2": "GND", "3": "R_INPUT_RAW",
    }, (8.0, 24.0), 90.0, "Short shielded harness to enclosure-qualified isolated RCA jacks; connector is EVT only"),
    part("J2", "TURNTABLE_GROUND_POST", "TerminalBlock_MetzConnect:TerminalBlock_MetzConnect_360425_1x01_Horizontal_ScrewM4.0_Boxed", {
        "1": "CHASSIS",
    }, (8.0, 45.0), 90.0, "EVT screw terminal; production binding post is chassis-mounted"),
    part("J3", "ADC_AUDIO", "Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical", {
        "1": "SCKI_24M576_IN", "2": "GND", "3": "ADC_BCK_OUT", "4": "GND",
        "5": "ADC_LRCK_OUT", "6": "GND", "7": "ADC_DATA_OUT", "8": "GND",
        "9": "ADC_CLIP_L", "10": "ADC_CLIP_R",
    }, (123.0, 23.0), 0.0, "Clock/data harness to digital board; PCM4202 is the 48 kHz I2S master"),
    part("J4", "POWER_INPUT", "Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Vertical", {
        "1": "+15V5_IN", "2": "GND", "3": "-15V5_IN", "4": "GND",
        "5": "+5V7_IN", "6": "GND", "7": "+3V7_IN", "8": "GND",
        "9": "+5V_RELAY", "10": "GND", "12": "GND",
    }, (116.0, 80.0), 90.0, "Separately supplied analog, digital, and relay rails from product power board"),
    part("J5", "ADC_CONTROL", "Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical", {
        "1": "+3V3D", "2": "GND", "3": "ADC_RESET_N", "4": "GAIN_BANK_CTL",
        "5": "GAIN_RANGE_CTL", "6": "CAP_47PF_CTL", "7": "CAP_100PF_CTL",
        "8": "AB_PRESENT_N", "9": "GND", "10": "GND",
    }, (123.0, 47.0), 0.0, "Low-speed controls; all selection controls default low"),
    part("U1", "TPS7A39DSCR", "Package_SON:Texas_DSC0010J_ThermalVias", {
        "1": "+15V5_IN", "2": "+15V5_IN", "3": "LDO_NR", "4": "GND", "5": "-15V5_IN",
        "6": "-12VA", "7": "LDO_FBN", "8": "LDO_BUF", "9": "LDO_FBP", "10": "+12VA", "11": "GND",
    }, (73.0, 79.0), 0.0, "Dual low-noise post-regulator; ±12 V nominal from separately supplied ±15.5 V"),
    part("U2", "TPS7A2050PDBVR", "Package_TO_SOT_SMD:SOT-23-5", {
        "1": "+5V7_IN", "2": "GND", "3": "+5V7_IN", "5": "+5VA",
    }, (91.0, 79.0), 0.0, "Low-noise +5 V ADC analog post-regulator"),
    part("U3", "TPS7A2033PDBVR", "Package_TO_SOT_SMD:SOT-23-5", {
        "1": "+3V7_IN", "2": "GND", "3": "+3V7_IN", "5": "+3V3D",
    }, (101.0, 79.0), 0.0, "Low-noise +3.3 V ADC digital post-regulator"),
    part("U4", "OPA1656IDR", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", {
        "1": "L_GAIN_OUT", "2": "L_GAIN_N", "3": "L_INPUT", "4": "-12VA",
        "5": "R_INPUT", "6": "R_GAIN_N", "7": "R_GAIN_OUT", "8": "+12VA",
    }, (64.0, 34.0), 0.0, "Dual JFET-input flat gain stage; 2.9 nV/rtHz at 10 kHz, 6 fA/rtHz at 1 kHz"),
    part("U5", "OPA1632DR", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", {
        "1": "L_DRV_IN_N", "2": "L_VCOM_BUF", "3": "+12VA", "4": "L_DRV_OUT_P",
        "5": "L_DRV_OUT_N", "6": "-12VA", "7": "GND", "8": "L_DRV_IN_P",
    }, (83.0, 22.0), 0.0, "Left fully differential PCM4202 driver; enabled by grounding EN with bipolar supplies"),
    part("U6", "OPA1632DR", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", {
        "1": "R_DRV_IN_N", "2": "R_VCOM_BUF", "3": "+12VA", "4": "R_DRV_OUT_P",
        "5": "R_DRV_OUT_N", "6": "-12VA", "7": "GND", "8": "R_DRV_IN_P",
    }, (83.0, 45.0), 0.0, "Right fully differential PCM4202 driver; enabled by grounding EN with bipolar supplies"),
    part("U7", "PCM4202DBR", "Package_SO:SSOP-28_5.3x10.2mm_P0.65mm", {
        "1": "VREF_L", "2": "GND", "3": "VCOM_L", "4": "ADC_L_IN_P", "5": "ADC_L_IN_N",
        "6": "+3V3D", "7": "GND", "8": "GND", "9": "+3V3D", "10": "GND", "11": "GND",
        "12": "+3V3D", "13": "GND", "14": "+3V3D", "15": "ADC_DATA_SRC", "16": "ADC_BCK_SRC",
        "17": "ADC_LRCK_SRC", "18": "SCKI_24M576", "19": "ADC_RESET_N", "20": "ADC_CLIP_R",
        "21": "ADC_CLIP_L", "22": "+5VA", "23": "GND", "24": "ADC_R_IN_N", "25": "ADC_R_IN_P",
        "26": "VCOM_R", "27": "GND", "28": "VREF_R",
    }, (105.0, 34.0), 90.0, "Stereo 24-bit ADC; 48 kHz master/I2S, 512fS SCKI, internal HPF disabled"),
    part("U8", "OPA1656IDR", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", {
        "1": "L_VCOM_BUF", "2": "L_VCOM_BUF", "3": "VCOM_L", "4": "-12VA",
        "5": "VCOM_R", "6": "R_VCOM_BUF", "7": "R_VCOM_BUF", "8": "+12VA",
    }, (96.0, 52.0), 0.0, "Dual voltage follower required because PCM4202 VCOM cannot drive OPA1632 VOCM directly"),
]


def add_passive(
    ref: str,
    value: str,
    footprint: str,
    a: str,
    b: str,
    xy: tuple[float, float],
    rotation: float = 0.0,
    description: str = "",
) -> None:
    PARTS.append(part(ref, value, footprint, {"1": a, "2": b}, xy, rotation, description))


# Cartridge entry: the specified 47.5 kilohm load is after the small series RF/ESD resistor.
add_passive("R1", "100R_0.1%", "Resistor_SMD:R_0805_2012Metric", "L_INPUT_RAW", "L_INPUT", (16.0, 21.0))
add_passive("R2", "100R_0.1%", "Resistor_SMD:R_0805_2012Metric", "R_INPUT_RAW", "R_INPUT", (16.0, 28.0))
add_passive("R3", "47.5k_0.1%_25ppm", "Resistor_SMD:R_0805_2012Metric", "L_INPUT", "GND", (22.0, 21.0), 90.0)
add_passive("R4", "47.5k_0.1%_25ppm", "Resistor_SMD:R_0805_2012Metric", "R_INPUT", "GND", (22.0, 28.0), 90.0)
add_passive("D1", "PESD5V0X1BCL_EVT", "Diode_SMD:D_SOD-882", "GND", "L_INPUT", (19.0, 18.0), 90.0,
            "0.49 pF nominal bidirectional ESD candidate; fit only after leakage/noise review")
add_passive("D2", "PESD5V0X1BCL_EVT", "Diode_SMD:D_SOD-882", "GND", "R_INPUT", (19.0, 31.0), 90.0,
            "0.49 pF nominal bidirectional ESD candidate; fit only after leakage/noise review")
add_passive("C1", "47pF_C0G_1%", "Capacitor_SMD:C_0603_1608Metric", "L_CAP47", "GND", (38.0, 14.0))
add_passive("C2", "47pF_C0G_1%", "Capacitor_SMD:C_0603_1608Metric", "R_CAP47", "GND", (38.0, 17.0))
add_passive("C3", "100pF_C0G_1%", "Capacitor_SMD:C_0603_1608Metric", "L_CAP100", "GND", (38.0, 56.0))
add_passive("C4", "100pF_C0G_1%", "Capacitor_SMD:C_0603_1608Metric", "R_CAP100", "GND", (38.0, 60.0))
add_passive("C5", "DNP_22pF_C0G_RF", "Capacitor_SMD:C_0603_1608Metric", "L_INPUT", "GND", (26.0, 22.0), 90.0,
            "DNP; populate only from RF injection data and include in measured cartridge load")
add_passive("C6", "DNP_22pF_C0G_RF", "Capacitor_SMD:C_0603_1608Metric", "R_INPUT", "GND", (26.0, 28.0), 90.0,
            "DNP; populate only from RF injection data and include in measured cartridge load")

# Omron G6K-2F-Y: coil 1/8; pole A NC/common/NO 2/3/4; pole B NO/common/NC 5/6/7.
PARTS.extend([
    part("K1", "G6K-2F-Y-5V_GAIN_BANK", "Relay_SMD:Relay_DPDT_Omron_G6K-2F-Y", {
        "1": "+5V_RELAY", "2": "L_GAIN26", "3": "L_GAIN_N", "4": "L_GAIN_ALT",
        "5": "R_GAIN_ALT", "6": "R_GAIN_N", "7": "R_GAIN26", "8": "K1_COIL_LOW",
    }, (43.0, 28.0), 0.0, "Default NC is 26 dB; energized delegates both channels to K2"),
    part("K2", "G6K-2F-Y-5V_GAIN_RANGE", "Relay_SMD:Relay_DPDT_Omron_G6K-2F-Y", {
        "1": "+5V_RELAY", "2": "L_GAIN20", "3": "L_GAIN_ALT", "4": "L_GAIN32",
        "5": "R_GAIN32", "6": "R_GAIN_ALT", "7": "R_GAIN20", "8": "K2_COIL_LOW",
    }, (43.0, 42.0), 0.0, "NC selects 20 dB and NO selects 32 dB only while K1 is energized"),
    part("K3", "G6K-2F-Y-5V_CAP47", "Relay_SMD:Relay_DPDT_Omron_G6K-2F-Y", {
        "1": "+5V_RELAY", "3": "L_INPUT", "4": "L_CAP47",
        "5": "R_CAP47", "6": "R_INPUT", "8": "K3_COIL_LOW",
    }, (31.0, 14.5), 0.0, "Normally open 47 pF C0G load increment for both channels"),
    part("K4", "G6K-2F-Y-5V_CAP100", "Relay_SMD:Relay_DPDT_Omron_G6K-2F-Y", {
        "1": "+5V_RELAY", "3": "L_INPUT", "4": "L_CAP100",
        "5": "R_CAP100", "6": "R_INPUT", "8": "K4_COIL_LOW",
    }, (31.0, 58.0), 0.0, "Normally open 100 pF C0G load increment for both channels"),
])

# Flat non-inverting gain network.  Contact resistance is outside the high-impedance input path.
add_passive("R5", "19.1k_0.1%", "Resistor_SMD:R_0805_2012Metric", "L_GAIN_OUT", "L_GAIN_N", (59.0, 28.0))
add_passive("R6", "19.1k_0.1%", "Resistor_SMD:R_0805_2012Metric", "R_GAIN_OUT", "R_GAIN_N", (59.0, 41.0))
for ref, value, branch, xy in [
    ("R7", "1.00k_0.1%", "L_GAIN26", (50.0, 24.0)), ("R8", "1.00k_0.1%", "R_GAIN26", (50.0, 27.0)),
    ("R9", "2.12k_0.1%", "L_GAIN20", (50.0, 36.0)), ("R10", "2.12k_0.1%", "R_GAIN20", (50.0, 39.0)),
    ("R11", "492R_0.1%", "L_GAIN32", (50.0, 45.0)), ("R12", "492R_0.1%", "R_GAIN32", (50.0, 48.0)),
]:
    add_passive(ref, value, "Resistor_SMD:R_0805_2012Metric", branch, "GND", xy)

# Unity-gain single-ended to differential conversion and PCM4202 charge reservoir/filter.
for prefix, gain_out, in_p, in_n, out_p, out_n, adc_p, adc_n, y, rbase, cbase in [
    ("L", "L_GAIN_OUT", "L_DRV_IN_P", "L_DRV_IN_N", "L_DRV_OUT_P", "L_DRV_OUT_N", "ADC_L_IN_P", "ADC_L_IN_N", 22.0, 20, 20),
    ("R", "R_GAIN_OUT", "R_DRV_IN_P", "R_DRV_IN_N", "R_DRV_OUT_P", "R_DRV_OUT_N", "ADC_R_IN_P", "ADC_R_IN_N", 45.0, 30, 30),
]:
    add_passive(f"R{rbase}", "316R_0.1%", "Resistor_SMD:R_0603_1608Metric", gain_out, in_p, (71.0, y - 2.0))
    add_passive(f"R{rbase + 1}", "316R_0.1%", "Resistor_SMD:R_0603_1608Metric", "GND", in_n, (71.0, y + 2.0))
    add_passive(f"R{rbase + 2}", "316R_0.1%", "Resistor_SMD:R_0603_1608Metric", out_n, in_p, (78.0, y - 4.0))
    add_passive(f"R{rbase + 3}", "316R_0.1%", "Resistor_SMD:R_0603_1608Metric", out_p, in_n, (78.0, y + 4.0))
    add_passive(f"C{cbase}", "1nF_C0G", "Capacitor_SMD:C_0603_1608Metric", out_n, in_p, (81.0, y - 4.0))
    add_passive(f"C{cbase + 1}", "1nF_C0G", "Capacitor_SMD:C_0603_1608Metric", out_p, in_n, (81.0, y + 4.0))
    add_passive(f"R{rbase + 4}", "40.2R_0.1%", "Resistor_SMD:R_0603_1608Metric", out_p, adc_p, (90.0, y - 2.0))
    add_passive(f"R{rbase + 5}", "40.2R_0.1%", "Resistor_SMD:R_0603_1608Metric", out_n, adc_n, (90.0, y + 2.0))
    add_passive(f"C{cbase + 2}", "2.7nF_C0G", "Capacitor_SMD:C_0603_1608Metric", adc_p, adc_n, (95.0, y))
    add_passive(f"C{cbase + 3}", "100pF_C0G", "Capacitor_SMD:C_0603_1608Metric", adc_p, "GND", (98.0, y - 2.0))
    add_passive(f"C{cbase + 4}", "100pF_C0G", "Capacitor_SMD:C_0603_1608Metric", adc_n, "GND", (98.0, y + 2.0))

# ADC reference, common-mode, and supply bypassing copied from the PCM4202 application requirements.
add_passive("C40", "33uF_LOW_ESR", "Capacitor_SMD:C_Elec_4x5.8", "VREF_L", "GND", (106.0, 15.0))
add_passive("C41", "100nF_X7R", "Capacitor_SMD:C_0603_1608Metric", "VREF_L", "GND", (103.0, 19.0))
add_passive("C42", "33uF_LOW_ESR", "Capacitor_SMD:C_Elec_4x5.8", "VREF_R", "GND", (108.0, 55.0))
add_passive("C43", "100nF_X7R", "Capacitor_SMD:C_0603_1608Metric", "VREF_R", "GND", (104.0, 53.0))
add_passive("C44", "100nF_X7R", "Capacitor_SMD:C_0603_1608Metric", "VCOM_L", "GND", (90.0, 49.0))
add_passive("C45", "100nF_X7R", "Capacitor_SMD:C_0603_1608Metric", "VCOM_R", "GND", (90.0, 55.0))
add_passive("C46", "33uF_LOW_ESR", "Capacitor_SMD:C_Elec_4x5.8", "+5VA", "GND", (114.0, 44.0))
add_passive("C47", "100nF_X7R", "Capacitor_SMD:C_0603_1608Metric", "+5VA", "GND", (109.0, 45.0))
add_passive("C48", "33uF_LOW_ESR", "Capacitor_SMD:C_Elec_4x5.8", "+3V3D", "GND", (114.0, 28.0))
add_passive("C49", "100nF_X7R", "Capacitor_SMD:C_0603_1608Metric", "+3V3D", "GND", (109.0, 27.0))

# Clock and serial source damping.  No data-format strap is left floating.
add_passive("R40", "22R", "Resistor_SMD:R_0402_1005Metric", "SCKI_24M576_IN", "SCKI_24M576", (114.0, 31.0))
add_passive("R41", "33R", "Resistor_SMD:R_0402_1005Metric", "ADC_BCK_SRC", "ADC_BCK_OUT", (114.0, 34.0))
add_passive("R42", "33R", "Resistor_SMD:R_0402_1005Metric", "ADC_LRCK_SRC", "ADC_LRCK_OUT", (114.0, 37.0))
add_passive("R43", "33R", "Resistor_SMD:R_0402_1005Metric", "ADC_DATA_SRC", "ADC_DATA_OUT", (114.0, 40.0))
add_passive("R44", "100k", "Resistor_SMD:R_0603_1608Metric", "ADC_RESET_N", "GND", (115.0, 48.0), 90.0,
            "External control must actively release reset; PCM4202 internal POR remains upstream")
add_passive("R45", "10k", "Resistor_SMD:R_0603_1608Metric", "AB_PRESENT_N", "GND", (116.0, 52.0))

# Relay low-side drivers and flyback clamps.  Controls default low even when the cable floats.
for index, (control, coil) in enumerate([
    ("GAIN_BANK_CTL", "K1_COIL_LOW"), ("GAIN_RANGE_CTL", "K2_COIL_LOW"),
    ("CAP_47PF_CTL", "K3_COIL_LOW"), ("CAP_100PF_CTL", "K4_COIL_LOW"),
], 1):
    x = 55.0 + (index - 1) * 7.0
    PARTS.append(part(f"Q{index}", "MMBT3904", "Package_TO_SOT_SMD:SOT-23", {
        "1": f"K{index}_BASE", "2": "GND", "3": coil,
    }, (x, 56.0), 0.0, "Relay low-side driver"))
    add_passive(f"R{50 + index}", "2.2k", "Resistor_SMD:R_0603_1608Metric", control, f"K{index}_BASE", (x, 52.0))
    add_passive(f"R{54 + index}", "100k", "Resistor_SMD:R_0603_1608Metric", f"K{index}_BASE", "GND", (x, 60.0))
    add_passive(f"D{2 + index}", "1N4148W", "Diode_SMD:D_SOD-123", "+5V_RELAY", coil, (x, 64.0))

# Local post-regulators and bypassing.
for ref, value, a, b, xy in [
    ("R60", "90.9k_0.1%", "+12VA", "LDO_FBP", (64.0, 83.0)),
    ("R61", "10.0k_0.1%", "LDO_FBP", "GND", (64.0, 87.0)),
    ("R62", "100k_0.1%", "-12VA", "LDO_FBN", (82.0, 83.0)),
    ("R63", "10.0k_0.1%", "LDO_FBN", "LDO_BUF", (82.0, 87.0)),
]:
    add_passive(ref, value, "Resistor_SMD:R_0603_1608Metric", a, b, xy)
add_passive("C60", "10nF_X7R", "Capacitor_SMD:C_0603_1608Metric", "LDO_NR", "GND", (73.0, 86.0))
add_passive("C61", "10nF_X7R", "Capacitor_SMD:C_0603_1608Metric", "+12VA", "LDO_FBP", (68.0, 82.0))
add_passive("C62", "10nF_X7R", "Capacitor_SMD:C_0603_1608Metric", "-12VA", "LDO_FBN", (78.0, 82.0))
for ref, rail, xy in [
    ("C63", "+15V5_IN", (66.0, 74.0)), ("C64", "-15V5_IN", (80.0, 74.0)),
    ("C65", "+12VA", (66.0, 78.0)), ("C66", "-12VA", (80.0, 78.0)),
]:
    add_passive(ref, "10uF_25V_X7R", "Capacitor_SMD:C_1206_3216Metric", rail, "GND", xy)
for ref, rail, xy in [
    ("C67", "+5V7_IN", (88.0, 75.0)), ("C68", "+5VA", (94.0, 75.0)),
    ("C69", "+3V7_IN", (98.0, 75.0)), ("C70", "+3V3D", (104.0, 75.0)),
]:
    add_passive(ref, "1uF_X7R", "Capacitor_SMD:C_0603_1608Metric", rail, "GND", xy)

# Op-amp rail bypass; bulk capacitors are shared locally, ceramics are per package.
for index, (rail, xy) in enumerate([
    ("+12VA", (69.0, 29.0)), ("-12VA", (69.0, 39.0)),
    ("+12VA", (77.0, 22.6)), ("-12VA", (89.0, 22.6)),
    ("+12VA", (77.0, 45.6)), ("-12VA", (89.0, 45.6)),
    ("+12VA", (103.0, 47.0)), ("-12VA", (101.0, 58.0)),
], 71):
    footprint = "Capacitor_SMD:C_0402_1005Metric" if 73 <= index <= 76 else "Capacitor_SMD:C_0603_1608Metric"
    add_passive(f"C{index}", "100nF_X7R", footprint, rail, "GND", xy)
add_passive("C79", "10uF_25V_X7R", "Capacitor_SMD:C_1206_3216Metric", "+12VA", "GND", (84.0, 64.0))
add_passive("C80", "10uF_25V_X7R", "Capacitor_SMD:C_1206_3216Metric", "-12VA", "GND", (90.0, 64.0))

# Chassis bond alternatives: direct bond is the reference build; impedance network is DNP until hum/ESD tests.
add_passive("R70", "0R_CHASSIS_BOND", "Resistor_SMD:R_1206_3216Metric", "CHASSIS", "GND", (22.0, 45.0), 0.0,
            "Reference build bonds signal return to chassis at the cartridge entry")
add_passive("R71", "DNP_10R_CHASSIS", "Resistor_SMD:R_1206_3216Metric", "CHASSIS", "GND", (22.0, 49.0), 0.0,
            "Alternative only; remove R70 before fitting")
add_passive("C81", "DNP_100nF_CHASSIS", "Capacitor_SMD:C_1206_3216Metric", "CHASSIS", "GND", (22.0, 53.0), 0.0,
            "Alternative RF bond used only with documented ground strategy")

# Local pogo points avoid the long, capacitive analog stubs that edge-mounted
# through-hole test loops would add to the cartridge and ADC input nodes.
for index, (net, xy) in enumerate([
    ("L_INPUT", (25.0, 18.5)), ("R_INPUT", (25.0, 31.5)),
    ("L_GAIN_OUT", (71.0, 33.0)), ("R_GAIN_OUT", (68.0, 45.5)),
    ("ADC_L_IN_P", (95.0, 16.0)), ("ADC_L_IN_N", (95.0, 28.0)),
    ("ADC_R_IN_P", (91.0, 39.0)), ("ADC_R_IN_N", (94.0, 47.0)),
    ("+12VA", (84.0, 68.0)), ("-12VA", (90.0, 68.0)),
    ("+5VA", (96.0, 70.0)), ("+3V3D", (106.0, 70.0)),
    ("SCKI_24M576", (118.0, 16.0)), ("ADC_BCK_OUT", (118.0, 32.0)),
    ("ADC_LRCK_OUT", (118.0, 36.0)), ("GND", (116.0, 60.0)),
], 1):
    PARTS.append(part(f"TP{index}", net, "TestPoint:TestPoint_Pad_D1.0mm", {"1": net}, xy, 0.0,
                      "Local EVT pogo point; do not extend sensitive-node routing"))


def library_path(footprint: str) -> tuple[str, str]:
    library, footprint_name = footprint.split(":", 1)
    return f"/usr/share/kicad/footprints/{library}.pretty", footprint_name


def add_outline(board: pcbnew.BOARD) -> None:
    corners = [(2.0, 2.0), (132.0, 2.0), (132.0, 92.0), (2.0, 92.0), (2.0, 2.0)]
    for start, end in zip(corners, corners[1:]):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetWidth(MM(0.1))
        edge.SetStart(pcbnew.VECTOR2I(MM(start[0]), MM(start[1])))
        edge.SetEnd(pcbnew.VECTOR2I(MM(end[0]), MM(end[1])))
        board.Add(edge)


def add_text(board: pcbnew.BOARD, text: str, xy: tuple[float, float], size: float = 1.0) -> None:
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
    for x, y in [(2.5, 2.5), (131.5, 2.5), (131.5, 91.5), (2.5, 91.5)]:
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
            matching = [pad for pad in footprint.Pads() if pad.GetNumber() == pad_number]
            if not matching:
                raise RuntimeError(f"{component.ref}: {component.footprint} lacks pad {pad_number}")
            for pad in matching:
                pad.SetNet(nets[net_name])
        board.Add(footprint)

    footprints = {item.GetReference(): item for item in board.GetFootprints()}
    for pad in footprints["U1"].Pads():
        if pad.GetNumber() == "11":
            pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    for ref, xy in [("H1", (6.0, 6.0)), ("H2", (128.0, 6.0)), ("H3", (6.0, 88.0)), ("H4", (128.0, 88.0))]:
        footprint = pcbnew.FootprintLoad("/usr/share/kicad/footprints/MountingHole.pretty", "MountingHole_3.2mm_M3")
        footprint.SetReference(ref)
        footprint.SetValue("M3_SHIELD_STANDOFF")
        footprint.Reference().SetLayer(pcbnew.F_Fab)
        footprint.Value().SetLayer(pcbnew.F_Fab)
        footprint.SetPosition(pcbnew.VECTOR2I(MM(xy[0]), MM(xy[1])))
        board.Add(footprint)

    add_outline(board)
    add_text(board, "FPGA AMP - SHIELDED MM PHONO / PCM4202 ADC REV A EVT", (67.0, 90.0), 0.8)
    add_text(board, "NOT FAB RELEASED - MEASURE INPUT C AND NOISE", (27.0, 87.0), 0.8)
    add_text(board, "CARTRIDGE ENTRY", (13.0, 12.0), 0.8)
    add_text(board, "RELAYS: DEFAULT 26dB / 0pF", (49.0, 10.0), 0.8)
    add_text(board, "PCM4202 48k MASTER / HPF OFF", (105.0, 11.0), 0.8)
    add_text(board, "STAR BOND", (22.0, 41.0), 0.8)
    add_text(board, "POWER / POST-REG", (100.0, 87.0), 0.8)
    add_zone(board, nets["GND"], pcbnew.In1_Cu)
    add_zone(board, nets["GND"], pcbnew.B_Cu)
    path = ROOT / f"{NAME}.kicad_pcb"
    pcbnew.SaveBoard(str(path), board)
    return path


def symbol_instance(component: Part, xy: tuple[float, float], root_uuid: str) -> tuple[str, list[str], list[str]]:
    x, y = xy
    symbol_uuid = core.uid(f"phono-symbol-instance:{component.ref}")
    lines = [
        "(symbol", f"  (lib_id {core.q('FPGA_Amp:' + core.sym_name(component))})",
        f"  (at {x:.2f} {y:.2f} 0) (unit 1)",
        "  (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)",
        f"  (uuid {core.q(symbol_uuid)})",
        f"  (property \"Reference\" {core.q(component.ref)} (at {x:.2f} {y - 12.7:.2f} 0) {core.effects()})",
        f"  (property \"Value\" {core.q(component.value)} (at {x:.2f} {y + 15.24:.2f} 0) {core.effects(1.0)})",
        f"  (property \"Footprint\" {core.q(component.footprint)} (at {x:.2f} {y:.2f} 0) {core.effects(hide=True)})",
        f"  (property \"Datasheet\" \"~\" (at {x:.2f} {y:.2f} 0) {core.effects(hide=True)})",
        f"  (property \"Description\" {core.q(component.description)} (at {x:.2f} {y:.2f} 0) {core.effects(hide=True)})",
    ]
    labels: list[str] = []
    wires: list[str] = []
    for number, net, x_mil, y_mil, _orientation in core.symbol_pin_layout(component):
        lines.append(f"  (pin {core.q(number)} (uuid {core.q(core.uid(f'phono-pin:{component.ref}:{number}'))}))")
        pin_x = x + x_mil * 0.0254
        label_y = y - y_mil * 0.0254
        direction = -1.0 if x_mil < 0 else 1.0
        label_x = pin_x + direction * 2.54
        wires.append(
            f"(wire (pts (xy {pin_x:.3f} {label_y:.3f}) (xy {label_x:.3f} {label_y:.3f})) "
            f"(stroke (width 0) (type default)) (uuid {core.q(core.uid(f'phono-wire:{component.ref}:{number}'))}))"
        )
        labels.append(
            f"(label {core.q(net)} (at {label_x:.3f} {label_y:.3f} 0) "
            f"{core.effects(0.8, justify='left bottom')} (uuid {core.q(core.uid(f'phono-label:{component.ref}:{number}'))}))"
        )
    lines.extend([
        "  (instances", "    (project \"\"",
        f"      (path {core.q('/' + root_uuid + '/' + symbol_uuid)} (reference {core.q(component.ref)}) (unit 1))",
        "    )", "  )", ")",
    ])
    return "\n".join(lines), labels, wires


def write_schematic() -> Path:
    root_uuid = core.uid("phono-schematic-root")
    lines = [
        "(kicad_sch", "  (version 20250114)", "  (generator \"fpga_amp_generate\")",
        "  (generator_version \"1.0\")", f"  (uuid {core.q(root_uuid)})", "  (paper \"A0\")",
        "  (title_block (title \"FPGA Amp shielded MM phono / PCM4202 ADC\") (date \"2026-08-15\") (rev \"A / EVT\") (company \"FPGA_Amp\")",
        "    (comment 1 \"47.5k load; relay 0/47/100/147pF; flat 20/26/32dB\")",
        "    (comment 2 \"PCM4202 48k master I2S; 24.576MHz SCKI; 6.144MHz BCK; HPF disabled\")",
        "    (comment 3 \"NOT PRODUCTION RELEASED OR PHYSICALLY VALIDATED\")",
        "    (comment 4 \"Generated from generate.py and design.py\"))", "  (lib_symbols",
    ]
    lines.extend("    " + definition.replace("\n", "\n    ") for definition in (core.native_symbol_definition(component) for component in PARTS))
    lines.append("  )")

    columns = [38.10, 165.10, 292.10, 419.10, 546.10, 673.10]
    cursors = [25.40] * len(columns)
    instances: list[str] = []
    labels: list[str] = []
    wires: list[str] = []
    for component in PARTS:
        pin_rows = max(1, (len(component.nets) + 1) // 2)
        body_height = max(20.32, pin_rows * 2.54)
        column = min(range(len(cursors)), key=cursors.__getitem__)
        xy = (columns[column], cursors[column] + 12.70)
        cursors[column] += body_height + 35.56
        instance, component_labels, component_wires = symbol_instance(component, xy, root_uuid)
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
            core.q("FPGA_Amp:" + core.sym_name(component)), core.q(core.sym_name(component)), 1,
        )
        library.append("  " + definition.replace("\n", "\n  "))
    library.extend([")", ""])
    (ROOT / f"{NAME}.kicad_sym").write_text("\n".join(library), encoding="utf-8")
    (ROOT / "sym-lib-table").write_text(
        '(sym_lib_table\n  (version 7)\n  (lib (name "FPGA_Amp")(type "KiCad")'
        f'(uri "${{KIPRJMOD}}/{NAME}.kicad_sym")(options "")(descr "Generated phono ADC board symbols"))\n)\n',
        encoding="utf-8",
    )
    return path


def write_project_and_bom() -> None:
    project = {
        "board": {}, "boards": [], "cvpcb": {}, "erc": {}, "libraries": {},
        "meta": {"filename": f"{NAME}.kicad_pro", "version": 1},
        "net_settings": {"classes": [{"name": "Default", "clearance": 0.20, "track_width": 0.25,
                                        "via_diameter": 0.70, "via_drill": 0.35}], "meta": {"version": 3}},
        "pcbnew": {}, "schematic": {}, "sheets": [], "text_variables": {},
    }
    (ROOT / f"{NAME}.kicad_pro").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")
    rows = ["Reference,Value,Footprint,Description"]
    for component in PARTS:
        rows.append(",".join([component.ref, component.value, component.footprint, component.description.replace(",", ";")]))
    (ROOT / "bom.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (ROOT / "design_calculations.json").write_text(json.dumps(calculate(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    if shutil.which("kicad-cli") is None:
        raise SystemExit("kicad-cli is required")
    core.ROOT = ROOT
    core.NAME = NAME
    core.PARTS = PARTS
    write_schematic()
    write_project_and_bom()
    board = write_board()
    print(f"generated {board}")
    print(f"parts={len(PARTS)} nets={len({net for component in PARTS for net in component.nets.values()})} layers=4")


if __name__ == "__main__":
    main()
