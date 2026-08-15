#!/usr/bin/env python3
"""Fail if the Rev-A STM32 front-panel allocation conflicts or drifts.

The allowed alternate-function rows below are a task-specific extract from
STMicroelectronics STM32_open_pin_data, STM32H753ZITx.xml, release matching
STM32CubeMX 6.18.0, upstream commit 7d1f1514ed5583ec5007ad91236b4e1d377295b1.
They are intentionally checked independently from pin_assignment.csv.
"""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parent

# Fixed package position truth for every assigned I/O. Power/special pins are
# checked in generate.py. A wrong package variant must therefore fail early.
PACKAGE_POSITIONS = {
    "PE2": 1, "PE3": 2, "PC14": 8, "PC15": 9,
    "PF0": 10, "PF1": 11, "PF2": 12, "PF3": 13, "PF4": 14, "PF5": 15,
    "PF6": 18, "PF7": 19, "PF8": 20, "PF9": 21, "PF10": 22,
    "PH0": 23, "PH1": 24, "PC0": 26, "PC1": 27, "PC2_C": 28, "PC3_C": 29,
    "PA0": 34, "PA1": 35, "PA2": 36, "PA3": 37, "PA4": 40, "PA5": 41,
    "PA6": 42, "PA7": 43, "PC4": 44, "PC5": 45, "PB0": 46, "PB1": 47,
    "PB2": 48, "PF11": 49, "PF12": 50, "PF13": 53, "PF14": 54,
    "PF15": 55, "PG0": 56, "PG1": 57, "PE7": 58, "PE8": 59, "PE9": 60,
    "PE10": 63, "PE11": 64, "PE12": 65, "PE13": 66, "PE14": 67,
    "PE15": 68, "PB10": 69, "PB11": 70, "PB12": 73, "PB13": 74,
    "PB14": 75, "PB15": 76, "PD8": 77, "PD9": 78, "PD10": 79,
    "PD11": 80, "PD12": 81, "PD13": 82, "PD14": 85, "PD15": 86,
    "PG2": 87, "PG3": 88, "PG4": 89, "PG5": 90, "PG6": 91, "PG7": 92,
    "PG8": 93, "PC6": 96, "PC7": 97, "PC8": 98, "PC9": 99,
    "PA8": 100, "PA9": 101, "PA11": 103, "PA13": 105, "PA14": 109,
    "PC10": 111, "PC11": 112, "PC12": 113, "PD0": 114, "PD1": 115,
    "PD2": 116, "PD3": 117, "PD4": 118, "PD5": 119, "PD6": 122,
    "PD7": 123, "PG9": 124, "PG10": 125, "PG11": 126, "PG12": 127,
    "PG13": 128, "PG14": 129, "PG15": 132, "PB3": 133, "PB4": 134,
    "PB5": 135, "PB6": 136, "PB8": 139, "PB9": 140, "PE0": 141,
    "PE1": 142,
}

REQUIRED_PREFIX = {"sdram": "FMC_", "flash": "QUADSPI_"}


def main() -> None:
    with (ROOT / "pin_assignment.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("pin assignment is empty")

    errors: list[str] = []
    used_pins: dict[str, str] = {}
    used_pads: dict[int, str] = {}
    used_signals: set[str] = set()
    for row in rows:
        signal = row["signal"]
        pin = row["mcu_pin"]
        pad = int(row["pad"])
        af = row["alternate_function"]
        expected_pad = PACKAGE_POSITIONS.get(pin)
        if expected_pad != pad:
            errors.append(f"{signal}: {pin} package pad {pad}, expected {expected_pad}")
        if pin in used_pins:
            errors.append(f"{signal}: {pin} already used by {used_pins[pin]}")
        if pad in used_pads:
            errors.append(f"{signal}: pad {pad} already used by {used_pads[pad]}")
        if signal in used_signals:
            errors.append(f"duplicate logical signal {signal}")
        prefix = "LTDC_" if signal.startswith("LCD_") and signal not in {"LCD_STBY_N"} else REQUIRED_PREFIX.get(row["group"])
        if prefix and not af.startswith(prefix):
            errors.append(f"{signal}: {row['group']} function must start with {prefix}, got {af}")
        used_pins[pin] = signal
        used_pads[pad] = signal
        used_signals.add(signal)

    required = {
        "LCD_CLK", "LCD_DE", "LCD_HSYNC", "LCD_VSYNC",
        "SDRAM_CLK", "SDRAM_CKE", "SDRAM_CS_N", "SDRAM_RAS_N",
        "SDRAM_CAS_N", "SDRAM_WE_N", "QSPI_CLK", "QSPI_CS_N",
        "DB_SPI_SCK", "FORCE_MUTE_N", "MOTOR_PWM", "BACKLIGHT_PWM",
    }
    missing = sorted(required - used_signals)
    if missing:
        errors.append("missing required signals: " + ", ".join(missing))
    if errors:
        raise SystemExit("\n".join(errors))

    print(f"pin assignment OK: {len(rows)} signals, {len(used_pins)} unique MCU pins")
    print("package=STM32H753ZIT6 LQFP144; direct Ethernet unavailable in Rev A allocation")


if __name__ == "__main__":
    main()
