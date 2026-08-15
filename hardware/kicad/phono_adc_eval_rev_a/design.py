#!/usr/bin/env python3
"""Auditable electrical calculations for the Rev-A phono/ADC EVT board."""

from __future__ import annotations

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent

ADC_SAMPLE_RATE_HZ = 48_000.0
ADC_SYSTEM_CLOCK_HZ = 24_576_000.0
ADC_FULL_SCALE_RMS_V = 2.12
ADC_BCK_PER_FRAME = 128

GAIN_FEEDBACK_OHM = 19_100.0
GAIN_GROUND_OHM = {
    "20_db": 2_120.0,
    "26_db_default": 1_000.0,
    "32_db": 492.0,
}
DRIVER_INPUT_OHM = 316.0
DRIVER_FEEDBACK_OHM = 316.0


def calculate() -> dict[str, object]:
    driver_gain = DRIVER_FEEDBACK_OHM / DRIVER_INPUT_OHM
    gains: dict[str, object] = {}
    for name, ground_resistor in GAIN_GROUND_OHM.items():
        voltage_gain = (1.0 + GAIN_FEEDBACK_OHM / ground_resistor) * driver_gain
        stress = {}
        for input_mv_rms in (4.0, 20.0, 100.0):
            output_v_rms = voltage_gain * input_mv_rms / 1000.0
            stress[f"{input_mv_rms:g}_mv_rms"] = {
                "adc_input_v_rms": output_v_rms,
                "adc_level_dbfs": 20.0 * math.log10(output_v_rms / ADC_FULL_SCALE_RMS_V),
            }
        gains[name] = {
            "ground_resistor_ohm": ground_resistor,
            "voltage_gain": voltage_gain,
            "gain_db": 20.0 * math.log10(voltage_gain),
            "input_for_adc_full_scale_mv_rms": ADC_FULL_SCALE_RMS_V / voltage_gain * 1000.0,
            "stress": stress,
        }

    return {
        "status": "EVT calculations; not measured hardware performance",
        "adc": {
            "part": "PCM4202DBR",
            "sample_rate_hz": ADC_SAMPLE_RATE_HZ,
            "system_clock_hz": ADC_SYSTEM_CLOCK_HZ,
            "system_clock_ratio_fs": ADC_SYSTEM_CLOCK_HZ / ADC_SAMPLE_RATE_HZ,
            "bck_hz": ADC_SAMPLE_RATE_HZ * ADC_BCK_PER_FRAME,
            "bck_ratio_fs": ADC_BCK_PER_FRAME,
            "differential_full_scale_rms_v": ADC_FULL_SCALE_RMS_V,
            "straps": {
                "S/M": 0,
                "FMT1": 0,
                "FMT0": 1,
                "FS2": 0,
                "FS1": 0,
                "FS0": 1,
                "HPFD": 1,
            },
            "mode": "48 kHz single-rate master, 512 fS system clock, 24-bit I2S, HPF disabled",
        },
        "gain": {
            "stage_feedback_ohm": GAIN_FEEDBACK_OHM,
            "driver_input_ohm": DRIVER_INPUT_OHM,
            "driver_feedback_ohm": DRIVER_FEEDBACK_OHM,
            "driver_differential_gain": driver_gain,
            "settings": gains,
        },
        "input_load": {
            "resistance_ohm": 47_500.0,
            "installed_selectable_capacitance_pf": [0.0, 47.0, 100.0, 147.0],
            "warning": "total cartridge load also includes cable, connector, ESD, relay, op-amp, and PCB parasitics and must be measured",
        },
        "regulated_rails": {
            "+12VA": {"regulator": "TPS7A39", "input_nominal_v": 15.5, "output_v": 12.0},
            "-12VA": {"regulator": "TPS7A39", "input_nominal_v": -15.5, "output_v": -11.9},
            "+5VA": {"regulator": "TPS7A2050PDBVR", "input_nominal_v": 5.7, "output_v": 5.0},
            "+3V3D": {"regulator": "TPS7A2033PDBVR", "input_nominal_v": 3.7, "output_v": 3.3},
            "+5V_RELAY": {"regulator": "external PB rail", "input_nominal_v": 5.0, "output_v": 5.0},
        },
    }


def main() -> None:
    rendered = json.dumps(calculate(), indent=2, sort_keys=True) + "\n"
    (ROOT / "design_calculations.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
