#!/usr/bin/env python3
"""Generate the Rev-A front-panel controller KiCad project.

The schematic and placed six-layer PCB are generated from the same part/net
table.  This is an EVT design: electrical architecture, pin allocation, and
manufacturer-derived display FFC footprints are concrete; enclosure-dependent
connector locations remain release gates called out on the PCB and README.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parent
NAME = "front_panel_controller"
MM = pcbnew.FromMM

CORE_PATH = ROOT.parent / "front_panel_motor_eval_rev_a" / "generate.py"
SPEC = importlib.util.spec_from_file_location("fpga_amp_kicad_core", CORE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import generator core from {CORE_PATH}")
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)
Part = core.Part


def part(ref: str, value: str, footprint: str, nets: dict[str, str], xy: tuple[float, float],
         rotation: float = 0.0, description: str = "") -> Part:
    return Part(ref, value, footprint, nets, xy, rotation, description)


def load_pin_rows() -> list[dict[str, str]]:
    with (ROOT / "pin_assignment.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


PIN_ROWS = load_pin_rows()
DISPLAY_SERIES = {
    row["signal"] for row in PIN_ROWS
    if row["signal"].startswith("LCD_") and row["signal"] not in {"LCD_STBY_N"}
}
SERIES_SOURCE = DISPLAY_SERIES | {"SDRAM_CLK", "QSPI_CLK"}


def mcu_net(signal: str) -> str:
    return signal + "_MCU" if signal in SERIES_SOURCE else signal


MCU_NETS = {row["pad"]: mcu_net(row["signal"]) for row in PIN_ROWS}
MCU_NETS.update({
    "6": "+3V3", "16": "GND", "17": "+3V3", "25": "NRST",
    "30": "+3V3", "31": "GND", "32": "VREF_PLUS", "33": "VDDA",
    "38": "GND", "39": "+3V3", "51": "GND", "52": "+3V3",
    "61": "GND", "62": "+3V3", "71": "VCAP_CORE", "72": "+3V3",
    "83": "GND", "84": "+3V3", "94": "GND", "95": "+3V3",
    "106": "VCAP_CORE", "107": "GND", "108": "+3V3", "120": "GND",
    "121": "+3V3", "130": "GND", "131": "+3V3", "138": "BOOT0",
    "143": "+3V3", "144": "+3V3",
})


PARTS: list[Part] = [
    part("U1", "STM32H753ZIT6", "Package_QFP:LQFP-144_20x20mm_P0.5mm", MCU_NETS,
         (72.0, 50.0), description="480 MHz UI controller; exact Rev-A pin map in pin_assignment.csv"),
    part("U2", "IS42S16160J-6TLI_32MiB", "Package_SO:TSOP-II-54_22.2x10.16mm_P0.8mm", {
        "1": "+3V3", "2": "SDRAM_D0", "3": "+3V3", "4": "SDRAM_D1", "5": "SDRAM_D2",
        "6": "GND", "7": "SDRAM_D3", "8": "SDRAM_D4", "9": "+3V3", "10": "SDRAM_D5",
        "11": "SDRAM_D6", "12": "GND", "13": "SDRAM_D7", "14": "+3V3",
        "15": "SDRAM_LDQM", "16": "SDRAM_UDQM", "17": "SDRAM_CLK", "18": "SDRAM_CKE",
        "19": "SDRAM_A12", "20": "SDRAM_BA0", "21": "SDRAM_BA1", "22": "SDRAM_A10",
        "23": "SDRAM_A0", "24": "SDRAM_A1", "25": "SDRAM_A2", "26": "SDRAM_A3",
        "27": "+3V3", "28": "GND", "29": "SDRAM_A4", "30": "SDRAM_A5",
        "31": "SDRAM_A6", "32": "SDRAM_A7", "33": "SDRAM_A8", "34": "SDRAM_A9",
        "35": "SDRAM_A11", "36": "SDRAM_CS_N", "37": "SDRAM_RAS_N", "38": "SDRAM_CAS_N",
        "39": "SDRAM_WE_N", "41": "GND", "42": "SDRAM_D8", "43": "+3V3",
        "44": "SDRAM_D9", "45": "SDRAM_D10", "46": "GND", "47": "SDRAM_D11",
        "48": "SDRAM_D12", "49": "+3V3", "50": "SDRAM_D13", "51": "SDRAM_D14",
        "52": "GND", "53": "SDRAM_D15", "54": "GND",
    }, (108.0, 52.0), 90.0, "166 MHz x16 SDR SDRAM; 32 MiB framebuffer/work RAM"),
    part("U3", "W25Q256JVSIQ_32MiB", "Package_SO:SOIC-8_5.3x5.3mm_P1.27mm", {
        "1": "QSPI_CS_N", "2": "QSPI_IO1", "3": "QSPI_IO2", "4": "GND",
        "5": "QSPI_IO0", "6": "QSPI_CLK", "7": "QSPI_IO3", "8": "+3V3",
    }, (42.0, 50.0), description="Quad-SPI UI assets and firmware storage"),
    part("U4", "TPS62132RGTR_3V3_3A", "Package_DFN_QFN:VQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm_ThermalVias", {
        "1": "BUCK_SW", "2": "BUCK_SW", "3": "BUCK_SW", "4": "BUCK_PG", "5": "GND",
        "6": "GND", "7": "GND", "8": "GND", "9": "BUCK_SS", "10": "+12V_UI",
        "11": "+12V_UI", "12": "+12V_UI", "13": "BUCK_EN", "14": "+3V3",
        "15": "GND", "16": "GND", "17": "GND",
    }, (23.0, 24.0), description="Fixed 3.3 V 3 A synchronous buck; TPS62132, not TPS62133"),
    part("U5", "TPS61165DRVR", "Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm_ThermalVias", {
        "1": "BL_FB", "2": "BL_COMP", "3": "GND", "4": "BL_SW",
        "5": "BACKLIGHT_PWM", "6": "+12V_UI", "7": "GND",
    }, (24.0, 48.0), description="38 V boost LED driver; 60 mA nominal current"),
    part("J1", "UI_12V_INPUT", "Connector_JST:JST_VH_B2P-VH-B_1x02_P3.96mm_Vertical",
         {"1": "UI_12V_IN", "2": "GND"}, (10.0, 14.0), description="Protected 12 V input from product power board"),
    part("J2", "NHD-5.0-800480AF-ASXP-CTP_TFT", "fpga_amp:Molex_54104-4031_1x40-2MP_P0.50mm_Horizontal", {},
         (75.0, 8.0), description="40-pin 0.5 mm TFT FFC; land pattern from Molex 541041000 rev B"),
    part("J3", "NHD_CTP_6P", "fpga_amp:Molex_52271-0679_1x06-2MP_P1.00mm_Horizontal", {
        "1": "+3V3_TOUCH", "2": "GND", "3": "TOUCH_SCL", "4": "TOUCH_SDA",
        "5": "TOUCH_INT_N", "6": "TOUCH_RESET_N",
    }, (124.0, 6.5), description="6-pin 1.0 mm capacitive touch FFC; land pattern from Molex SD-52271-036 rev F"),
    part("J4", "MOTOR_VOLUME_BOARD", "Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Vertical", {
        "1": "+3V3", "2": "GND", "3": "MOTOR_PWM", "4": "MOTOR_DIR",
        "5": "MOTOR_SLEEP", "6": "MOTOR_FAULT_N", "7": "MOTOR_CURRENT_ADC",
        "8": "POT_A_ADC", "9": "POT_B_ADC", "10": "MOTOR_BOARD_ID", "11": "GND", "12": "GND",
    }, (143.0, 69.0), description="Harness to isolated motor-volume evaluation board"),
    part("J5", "DIGITAL_BOARD_CONTROL", "Connector_PinHeader_2.54mm:PinHeader_2x08_P2.54mm_Vertical", {
        "1": "+3V3", "2": "GND", "3": "DB_SPI_SCK", "4": "DB_SPI_CS_N",
        "5": "DB_SPI_MISO", "6": "DB_SPI_MOSI", "7": "DB_IRQ_N", "8": "UI_ALIVE",
        "9": "FORCE_MUTE_N", "10": "GND",
    }, (143.0, 43.0), description="Low-speed control link to FPGA/digital board; no audio samples"),
    part("J6", "PANEL_CONTROLS", "Connector_PinHeader_2.54mm:PinHeader_2x08_P2.54mm_Vertical", {
        "1": "+3V3", "2": "GND", "3": "SOURCE_ENC_A", "4": "SOURCE_ENC_B",
        "5": "SOURCE_PUSH", "6": "MODEL_ENC_A", "7": "MODEL_ENC_B", "8": "MODEL_PUSH",
        "9": "PARAM_ENC_A", "10": "PARAM_ENC_B", "11": "PARAM_PUSH", "12": "MUTE_BUTTON",
        "13": "STANDBY_BUTTON", "14": "AMBIENT_ADC", "15": "GND", "16": "GND",
    }, (9.0, 63.0), description="Panel-mounted optical encoders/buttons and ambient sensor"),
    part("J7", "CORTEX_SWD", "Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical", {
        "1": "+3V3", "2": "SWDIO", "3": "GND", "4": "SWCLK", "5": "GND",
        "6": "SWO", "9": "GND", "10": "NRST",
    }, (130.0, 80.0), description="1.27 mm Cortex debug connector"),
]

# Exact display electrical pinout. Unused RGB LSBs are grounded for RGB565.
LCD_PINS = {
    "1": "BL_FB", "2": "LCD_LED_A", "3": "GND", "4": "+3V3",
    "5": "GND", "6": "GND", "7": "GND", "8": "LCD_R3", "9": "LCD_R4",
    "10": "LCD_R5", "11": "LCD_R6", "12": "LCD_R7", "13": "GND", "14": "GND",
    "15": "LCD_G2", "16": "LCD_G3", "17": "LCD_G4", "18": "LCD_G5",
    "19": "LCD_G6", "20": "LCD_G7", "21": "GND", "22": "GND", "23": "GND",
    "24": "LCD_B3", "25": "LCD_B4", "26": "LCD_B5", "27": "LCD_B6",
    "28": "LCD_B7", "29": "GND", "30": "LCD_CLK", "31": "LCD_STBY_N",
    "32": "LCD_HSYNC", "33": "LCD_VSYNC", "34": "LCD_DE", "36": "GND",
}
PARTS[6] = part("J2", "NHD-5.0-800480AF-ASXP-CTP_TFT",
                "fpga_amp:Molex_54104-4031_1x40-2MP_P0.50mm_Horizontal",
                LCD_PINS, (75.0, 8.0), description=PARTS[6].description)


def add_passive(ref: str, value: str, footprint: str, a: str, b: str,
                xy: tuple[float, float], rotation: float = 0.0, description: str = "") -> None:
    PARTS.append(part(ref, value, footprint, {"1": a, "2": b}, xy, rotation, description))


# Input protection and 3.3 V converter support.
add_passive("F1", "1.5A_PTC", "Fuse:Fuse_1206_3216Metric", "UI_12V_IN", "+12V_UI", (19.0, 14.0),
            description="Select final hold/trip after measured UI load")
add_passive("D1", "SMBJ15A", "Diode_SMD:D_SMB", "GND", "+12V_UI", (26.0, 14.0), 90.0)
add_passive("C1", "10uF_25V_X7R", "Capacitor_SMD:C_1210_3225Metric", "+12V_UI", "GND", (32.0, 15.0), 90.0)
add_passive("C2", "100nF_25V_X7R", "Capacitor_SMD:C_0603_1608Metric", "+12V_UI", "GND", (36.0, 16.0), 90.0)
add_passive("L1", "2.2uH_4A", "Inductor_SMD:L_Bourns_SRN6045TA", "BUCK_SW", "+3V3", (31.0, 25.0))
add_passive("C3", "22uF_6V3_X7R", "Capacitor_SMD:C_1210_3225Metric", "+3V3", "GND", (38.0, 23.0), 90.0)
add_passive("C4", "22uF_6V3_X7R", "Capacitor_SMD:C_1210_3225Metric", "+3V3", "GND", (42.0, 23.0), 90.0)
add_passive("C5", "3.3nF_X7R", "Capacitor_SMD:C_0603_1608Metric", "BUCK_SS", "GND", (20.0, 29.0), 90.0)
add_passive("R1", "100k", "Resistor_SMD:R_0603_1608Metric", "+12V_UI", "BUCK_EN", (17.0, 25.0))
add_passive("R2", "100k", "Resistor_SMD:R_0603_1608Metric", "BUCK_PG", "+3V3", (31.0, 29.0))

# LCD boost LED driver: 200 mV / 3.32 ohm = 60.2 mA nominal.
add_passive("L2", "10uH_1A", "Inductor_SMD:L_Bourns-SRN4018", "+12V_UI", "BL_SW", (17.0, 43.0))
add_passive("D2", "MBR0540T1G", "Diode_SMD:D_SOD-123", "BL_SW", "LCD_LED_A", (30.0, 43.0))
add_passive("C6", "1uF_50V_X7R", "Capacitor_SMD:C_1206_3216Metric", "LCD_LED_A", "GND", (35.0, 44.0), 90.0)
add_passive("R3", "3.32R_1%", "Resistor_SMD:R_0805_2012Metric", "BL_FB", "GND", (28.0, 54.0))
add_passive("C7", "220nF_X7R", "Capacitor_SMD:C_0603_1608Metric", "BL_COMP", "GND", (20.0, 54.0))
add_passive("R4", "100k", "Resistor_SMD:R_0603_1608Metric", "BACKLIGHT_PWM", "GND", (31.0, 50.0), 90.0)

# LTDC, SDRAM clock, and QSPI clock source termination.
resistor_number = 10
display_order = sorted(DISPLAY_SERIES)
for index, signal in enumerate(display_order):
    x = 46.0 + (index % 10) * 7.0
    y = 22.0 + (index // 10) * 5.0
    add_passive(f"R{resistor_number}", "33R", "Resistor_SMD:R_0402_1005Metric",
                signal + "_MCU", signal, (x, y), description="LTDC source damping; verify by scope/SI")
    resistor_number += 1
add_passive(f"R{resistor_number}", "22R", "Resistor_SMD:R_0402_1005Metric",
            "SDRAM_CLK_MCU", "SDRAM_CLK", (94.0, 49.0), description="SDRAM clock source termination")
resistor_number += 1
add_passive(f"R{resistor_number}", "22R", "Resistor_SMD:R_0402_1005Metric",
            "QSPI_CLK_MCU", "QSPI_CLK", (50.0, 48.0), description="QSPI clock source termination")
resistor_number += 1

# MCU regulator, analog supply, oscillator, reset, and boot support.
for index in range(11):
    x = 57.0 + (index % 6) * 6.0
    y = 36.0 if index < 6 else 64.0
    add_passive(f"C{10 + index}", "100nF_X7R", "Capacitor_SMD:C_0402_1005Metric", "+3V3", "GND", (x, y),
                description="One per STM32 VDD/VDD33_USB pin; place at assigned power pin")
add_passive("C21", "4.7uF_X7R", "Capacitor_SMD:C_0805_2012Metric", "+3V3", "GND", (57.0, 67.0))
add_passive("C22", "2.2uF_LOW_ESR", "Capacitor_SMD:C_0805_2012Metric", "VCAP_CORE", "GND", (65.0, 67.0),
            description="VCAP; two capacitors total, VCAP pins connected per ST AN4938")
add_passive("C23", "2.2uF_LOW_ESR", "Capacitor_SMD:C_0805_2012Metric", "VCAP_CORE", "GND", (72.0, 67.0))
add_passive("FB1", "600R@100MHz", "Inductor_SMD:L_0603_1608Metric_Pad1.05x0.95mm_HandSolder", "+3V3", "VDDA", (48.0, 66.0))
add_passive("C24", "1uF_X7R", "Capacitor_SMD:C_0603_1608Metric", "VDDA", "GND", (45.0, 69.0))
add_passive("C25", "100nF_X7R", "Capacitor_SMD:C_0402_1005Metric", "VDDA", "GND", (48.0, 69.0))
add_passive("R40", "0R", "Resistor_SMD:R_0402_1005Metric", "VDDA", "VREF_PLUS", (51.0, 69.0))
add_passive("C26", "1uF_X7R", "Capacitor_SMD:C_0603_1608Metric", "VREF_PLUS", "GND", (54.0, 69.0))
add_passive("C27", "100nF_X7R", "Capacitor_SMD:C_0402_1005Metric", "VREF_PLUS", "GND", (57.0, 69.0))
PARTS.extend([
    part("Y1", "25MHz_10pF", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", {"1": "HSE_IN", "2": "GND", "3": "HSE_OUT", "4": "GND"}, (52.0, 41.0)),
    part("Y2", "32.768kHz_7pF", "Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm", {"1": "LSE_IN", "2": "LSE_OUT"}, (52.0, 58.0)),
])
add_passive("C28", "12pF_C0G", "Capacitor_SMD:C_0402_1005Metric", "HSE_IN", "GND", (48.0, 39.0))
add_passive("C29", "12pF_C0G", "Capacitor_SMD:C_0402_1005Metric", "HSE_OUT", "GND", (48.0, 43.0))
add_passive("C30", "10pF_C0G_DNP", "Capacitor_SMD:C_0402_1005Metric", "LSE_IN", "GND", (48.0, 57.0), description="DNP pending crystal CL calculation")
add_passive("C31", "10pF_C0G_DNP", "Capacitor_SMD:C_0402_1005Metric", "LSE_OUT", "GND", (48.0, 60.0), description="DNP pending crystal CL calculation")
add_passive("R41", "10k", "Resistor_SMD:R_0603_1608Metric", "+3V3", "NRST", (123.0, 75.0))
add_passive("C32", "100nF", "Capacitor_SMD:C_0603_1608Metric", "NRST", "GND", (126.0, 75.0))
PARTS.append(part("SW1", "RESET", "Button_Switch_SMD:Panasonic_EVQPUJ_EVQPUA", {"1": "NRST", "2": "GND"}, (118.0, 80.0)))
add_passive("R42", "100k", "Resistor_SMD:R_0603_1608Metric", "BOOT0", "GND", (112.0, 80.0))
PARTS.append(part("JP1", "BOOT0", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", {"1": "+3V3", "2": "BOOT0"}, (106.0, 81.0)))

# Touch rail and I2C/reset bias.
add_passive("FB2", "600R@100MHz", "Inductor_SMD:L_0603_1608Metric_Pad1.05x0.95mm_HandSolder", "+3V3", "+3V3_TOUCH", (116.0, 15.0))
add_passive("C33", "1uF_X7R", "Capacitor_SMD:C_0603_1608Metric", "+3V3_TOUCH", "GND", (120.0, 15.0))
add_passive("C34", "100nF_X7R", "Capacitor_SMD:C_0402_1005Metric", "+3V3_TOUCH", "GND", (124.0, 15.0))
add_passive("R43", "2.2k", "Resistor_SMD:R_0603_1608Metric", "+3V3_TOUCH", "TOUCH_SCL", (128.0, 16.0))
add_passive("R44", "2.2k", "Resistor_SMD:R_0603_1608Metric", "+3V3_TOUCH", "TOUCH_SDA", (132.0, 16.0))
add_passive("R45", "10k", "Resistor_SMD:R_0603_1608Metric", "+3V3_TOUCH", "TOUCH_INT_N", (136.0, 16.0))
add_passive("R46", "10k", "Resistor_SMD:R_0603_1608Metric", "+3V3_TOUCH", "TOUCH_RESET_N", (140.0, 16.0))

# SDRAM and flash local decoupling. Placement is deliberately near each IC.
for index in range(6):
    add_passive(f"C{40 + index}", "100nF_X7R", "Capacitor_SMD:C_0402_1005Metric", "+3V3", "GND",
                (101.0 + (index % 3) * 5.0, 65.0 + (index // 3) * 4.0), description="SDRAM VDD/VDDQ bypass")
add_passive("C46", "10uF_X7R", "Capacitor_SMD:C_0805_2012Metric", "+3V3", "GND", (116.0, 67.0))
add_passive("C47", "100nF_X7R", "Capacitor_SMD:C_0402_1005Metric", "+3V3", "GND", (40.0, 55.0))
add_passive("C48", "1uF_X7R", "Capacitor_SMD:C_0603_1608Metric", "+3V3", "GND", (43.0, 56.0))
add_passive("R47", "10k", "Resistor_SMD:R_0603_1608Metric", "+3V3", "QSPI_CS_N", (37.0, 55.0))

# Fail-safe defaults: audio mutes until the UI explicitly establishes control.
add_passive("R48", "10k", "Resistor_SMD:R_0603_1608Metric", "FORCE_MUTE_N", "GND", (135.0, 51.0),
            description="Default asserted; firmware must release mute intentionally")
add_passive("R49", "10k", "Resistor_SMD:R_0603_1608Metric", "+3V3", "DB_SPI_CS_N", (135.0, 55.0))
add_passive("R50", "10k", "Resistor_SMD:R_0603_1608Metric", "+3V3", "DB_IRQ_N", (135.0, 59.0))
add_passive("R51", "1k", "Resistor_SMD:R_0603_1608Metric", "STATUS_LED", "STATUS_LED_A", (124.0, 65.0))
PARTS.append(part("D3", "GREEN_STATUS", "LED_SMD:LED_0603_1608Metric", {"1": "GND", "2": "STATUS_LED_A"}, (130.0, 65.0)))

# Bring-up test points.
for index, net in enumerate(["+12V_UI", "+3V3", "GND", "VCAP_CORE", "VDDA", "LCD_LED_A", "BL_FB", "NRST"], 1):
    PARTS.append(part(f"TP{index}", net, "TestPoint:TestPoint_Plated_Hole_D2.0mm", {"1": net},
                      (39.0 + index * 9.0, 88.0), description="EVT bring-up test point"))


def library_path(footprint: str) -> tuple[str, str]:
    library, footprint_name = footprint.split(":", 1)
    if library == "fpga_amp":
        return str(ROOT / "fpga_amp.pretty"), footprint_name
    return f"/usr/share/kicad/footprints/{library}.pretty", footprint_name


def add_outline(board: pcbnew.BOARD) -> None:
    corners = [(2.0, 2.0), (152.0, 2.0), (152.0, 92.0), (2.0, 92.0), (2.0, 2.0)]
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
    zone.SetLocalClearance(MM(0.20))
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in [(2.5, 2.5), (151.5, 2.5), (151.5, 91.5), (2.5, 91.5)]:
        outline.Append(MM(x), MM(y))
    board.Add(zone)


def write_board() -> Path:
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    board.SetLayerName(pcbnew.In1_Cu, "GND1")
    board.SetLayerName(pcbnew.In2_Cu, "PWR")
    board.SetLayerName(pcbnew.In3_Cu, "SIG2")
    board.SetLayerName(pcbnew.In4_Cu, "GND2")
    default = board.GetAllNetClasses()["Default"]
    default.SetClearance(MM(0.18))
    default.SetTrackWidth(MM(0.20))
    default.SetViaDiameter(MM(0.60))
    default.SetViaDrill(MM(0.30))
    board.GetDesignSettings().m_TrackMinWidth = MM(0.12)
    board.GetDesignSettings().m_MinClearance = MM(0.12)
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

    # Dense two-row headers can starve an inner-plane thermal at the chosen
    # placement. Use local solid connections on these low-current ground pins
    # instead of weakening the board-wide thermal-spoke rule.
    footprints = {item.GetReference(): item for item in board.GetFootprints()}
    for reference, pad_number in (("J6", "2"), ("J7", "9")):
        pad = next(item for item in footprints[reference].Pads() if item.GetNumber() == pad_number)
        pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    for ref, xy in [("H1", (6.0, 6.0)), ("H2", (148.0, 6.0)), ("H3", (6.0, 88.0)), ("H4", (148.0, 88.0))]:
        footprint = pcbnew.FootprintLoad("/usr/share/kicad/footprints/MountingHole.pretty", "MountingHole_3.2mm_M3")
        footprint.SetReference(ref)
        footprint.SetValue("M3_CHASSIS")
        footprint.Reference().SetLayer(pcbnew.F_Fab)
        footprint.Value().SetLayer(pcbnew.F_Fab)
        footprint.SetPosition(pcbnew.VECTOR2I(MM(xy[0]), MM(xy[1])))
        board.Add(footprint)

    add_outline(board)
    add_text(board, "FPGA AMP - FRONT PANEL CONTROLLER REV A EVT", (77.0, 4.0), 1.1)
    add_text(board, "NOT FAB RELEASED", (77.0, 90.5), 1.0)
    add_text(board, "J2 TFT FFC - MOLEX 54104-4031", (75.0, 16.5), 0.8)
    add_text(board, "J3 52271-0679", (139.0, 4.0), 0.8)
    add_text(board, "J1 12V", (9.0, 8.0), 0.8)
    add_text(board, "J4 MOTOR", (132.0, 69.0), 0.8)
    add_text(board, "J5 DIGITAL", (143.0, 33.0), 0.8)
    add_text(board, "J6 PANEL", (9.0, 56.0), 0.8)
    add_zone(board, nets["GND"], pcbnew.In1_Cu)
    add_zone(board, nets["GND"], pcbnew.In4_Cu)
    add_zone(board, nets["GND"], pcbnew.B_Cu)
    path = ROOT / f"{NAME}.kicad_pcb"
    pcbnew.SaveBoard(str(path), board)
    return path


def controller_symbol_instance(component: Part, xy: tuple[float, float], root_uuid: str) -> tuple[str, list[str], list[str]]:
    """Place a generated block symbol without the small-board fixed grid."""
    x, y = xy
    symbol_uuid = core.uid(f"symbol-instance:{component.ref}")
    lines = [
        "(symbol",
        f"  (lib_id {core.q('FPGA_Amp:' + core.sym_name(component))})",
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
    for number, net, x_mil, y_mil, _orient in core.symbol_pin_layout(component):
        lines.append(f"  (pin {core.q(number)} (uuid {core.q(core.uid(f'pin:{component.ref}:{number}'))}))")
        pin_x = x + x_mil * 0.0254
        label_y = y - y_mil * 0.0254
        direction = -1.0 if x_mil < 0 else 1.0
        label_x = pin_x + direction * 2.54
        wires.append(
            f"(wire (pts (xy {pin_x:.3f} {label_y:.3f}) (xy {label_x:.3f} {label_y:.3f})) "
            f"(stroke (width 0) (type default)) (uuid {core.q(core.uid(f'wire:{component.ref}:{number}'))}))"
        )
        labels.append(
            f"(label {core.q(net)} (at {label_x:.3f} {label_y:.3f} 0) "
            f"{core.effects(0.8, justify='left bottom')} (uuid {core.q(core.uid(f'label:{component.ref}:{number}'))}))"
        )
    lines.extend([
        "  (instances", "    (project \"\"",
        f"      (path {core.q('/' + root_uuid + '/' + symbol_uuid)} (reference {core.q(component.ref)}) (unit 1))",
        "    )", "  )", ")",
    ])
    return "\n".join(lines), labels, wires


def write_controller_schematic() -> Path:
    root_uuid = core.uid("schematic-root")
    lines = [
        "(kicad_sch", "  (version 20250114)", "  (generator \"fpga_amp_generate\")",
        "  (generator_version \"1.0\")", f"  (uuid {core.q(root_uuid)})", "  (paper \"A0\")",
        "  (title_block (title \"FPGA Amp front-panel controller\") (date \"2026-08-15\") (rev \"A / EVT\") (company \"FPGA_Amp\")",
        "    (comment 1 \"STM32H753 LTDC + SDRAM + touch + physical controls\")",
        "    (comment 2 \"Six-layer Rev-A EVT; display connector footprints derived from Molex drawings\")",
        "    (comment 3 \"NOT PRODUCTION RELEASED\")",
        "    (comment 4 \"Generated from generate.py\"))", "  (lib_symbols",
    ]
    lines.extend("    " + definition.replace("\n", "\n    ") for definition in (core.native_symbol_definition(component) for component in PARTS))
    lines.append("  )")

    # Height-aware column packing prevents labels from different generated
    # block symbols from landing on top of one another and joining nets.
    x_columns = [38.10, 165.10, 292.10, 419.10, 546.10, 673.10]
    cursors = [25.40] * len(x_columns)
    instances: list[str] = []
    labels: list[str] = []
    wires: list[str] = []
    for component in PARTS:
        pin_rows = max(1, (len(component.nets) + 1) // 2)
        body_height = max(20.32, pin_rows * 2.54)
        column = min(range(len(cursors)), key=cursors.__getitem__)
        xy = (x_columns[column], cursors[column] + 12.70)
        cursors[column] += body_height + 35.56
        instance, component_labels, component_wires = controller_symbol_instance(component, xy, root_uuid)
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
        definition = core.native_symbol_definition(component).replace(core.q("FPGA_Amp:" + core.sym_name(component)), core.q(core.sym_name(component)), 1)
        library.append("  " + definition.replace("\n", "\n  "))
    library.extend([")", ""])
    (ROOT / f"{NAME}.kicad_sym").write_text("\n".join(library), encoding="utf-8")
    (ROOT / "sym-lib-table").write_text(
        '(sym_lib_table\n  (version 7)\n  (lib (name "FPGA_Amp")(type "KiCad")'
        f'(uri "${{KIPRJMOD}}/{NAME}.kicad_sym")(options "")(descr "Generated front-panel controller symbols"))\n)\n',
        encoding="utf-8",
    )
    return path


def write_schematic_and_project() -> None:
    core.ROOT = ROOT
    core.NAME = NAME
    core.PARTS = PARTS
    write_controller_schematic()
    project = {
        "board": {}, "boards": [], "cvpcb": {}, "erc": {}, "libraries": {},
        "meta": {"filename": f"{NAME}.kicad_pro", "version": 1},
        "net_settings": {"classes": [{"name": "Default", "clearance": 0.18, "track_width": 0.20,
                                        "via_diameter": 0.60, "via_drill": 0.30}], "meta": {"version": 3}},
        "pcbnew": {}, "schematic": {}, "sheets": [], "text_variables": {},
    }
    (ROOT / f"{NAME}.kicad_pro").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")
    rows = ["Reference,Value,Footprint,Description"]
    for component in PARTS:
        rows.append(",".join([component.ref, component.value, component.footprint,
                              component.description.replace(",", ";")]))
    (ROOT / "bom.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> None:
    if shutil.which("kicad-cli") is None:
        raise SystemExit("kicad-cli is required")
    import subprocess
    subprocess.run(["python3", str(ROOT / "verify_pin_assignment.py")], check=True)
    write_schematic_and_project()
    board = write_board()
    print(f"generated {board}")
    print(f"parts={len(PARTS)} nets={len({n for p in PARTS for n in p.nets.values()})} layers=6")


if __name__ == "__main__":
    main()
