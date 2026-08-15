#!/usr/bin/env python3
"""Auditable electrical calculations for the Rev-A PCM5242 line-output EVT."""

from __future__ import annotations

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SAMPLE_RATE_HZ = 48_000.0
SCK_HZ = 24_576_000.0
BCK_HZ = 3_072_000.0
DAC_SINGLE_ENDED_FULL_SCALE_RMS_V = 2.1
DAC_DIFFERENTIAL_FULL_SCALE_RMS_V = 4.2
OUTPUT_RESISTOR_OHM = 499.0
RCA_CAPACITOR_F = 2.2e-9
BALANCED_CAPACITOR_F = 1.0e-9
RCA_LOAD_OHM = 10_000.0
BALANCED_LOAD_OHM = 20_000.0


def loaded_lowpass(source_r: float, load_r: float, capacitance: float, hz: float) -> complex:
    shunt = 1.0 / (1.0 / load_r + 1j * 2.0 * math.pi * hz * capacitance)
    return shunt / (source_r + shunt)


def calculate() -> dict[str, object]:
    rca_dc = RCA_LOAD_OHM / (RCA_LOAD_OHM + OUTPUT_RESISTOR_OHM)
    balanced_dc = BALANCED_LOAD_OHM / (
        BALANCED_LOAD_OHM + 2.0 * OUTPUT_RESISTOR_OHM
    )
    rca_20k = loaded_lowpass(
        OUTPUT_RESISTOR_OHM, RCA_LOAD_OHM, RCA_CAPACITOR_F, 20_000.0
    )
    balanced_20k = loaded_lowpass(
        2.0 * OUTPUT_RESISTOR_OHM,
        BALANCED_LOAD_OHM,
        BALANCED_CAPACITOR_F,
        20_000.0,
    )
    return {
        "status": "EVT calculations; not measured hardware performance",
        "converter": {
            "part": "PCM5242RHBR",
            "mode": "48 kHz slave, 24-bit I2S, external SCK, I2C control, VREF output mode",
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "sck_hz": SCK_HZ,
            "sck_ratio_fs": SCK_HZ / SAMPLE_RATE_HZ,
            "bck_hz": BCK_HZ,
            "bck_ratio_fs": BCK_HZ / SAMPLE_RATE_HZ,
            "single_ended_full_scale_rms_v_unloaded": DAC_SINGLE_ENDED_FULL_SCALE_RMS_V,
            "differential_full_scale_rms_v_unloaded": DAC_DIFFERENTIAL_FULL_SCALE_RMS_V,
        },
        "outputs": {
            "rca": {
                "series_resistance_ohm": OUTPUT_RESISTOR_OHM,
                "shunt_capacitance_f": RCA_CAPACITOR_F,
                "specified_load_ohm": RCA_LOAD_OHM,
                "full_scale_at_dc_rms_v": DAC_SINGLE_ENDED_FULL_SCALE_RMS_V * rca_dc,
                "full_scale_at_20khz_rms_v": DAC_SINGLE_ENDED_FULL_SCALE_RMS_V * abs(rca_20k),
                "relative_20khz_db": 20.0 * math.log10(abs(rca_20k) / rca_dc),
            },
            "balanced": {
                "series_resistance_per_leg_ohm": OUTPUT_RESISTOR_OHM,
                "differential_capacitance_f": BALANCED_CAPACITOR_F,
                "specified_differential_load_ohm": BALANCED_LOAD_OHM,
                "full_scale_at_dc_rms_v": DAC_DIFFERENTIAL_FULL_SCALE_RMS_V * balanced_dc,
                "full_scale_at_20khz_rms_v": DAC_DIFFERENTIAL_FULL_SCALE_RMS_V * abs(balanced_20k),
                "relative_20khz_db": 20.0 * math.log10(abs(balanced_20k) / balanced_dc),
            },
        },
        "mute_contract": {
            "reset": "XSMT pulled low and all signal relays de-energized/open",
            "unmute": "configure/read back unity path while XSMT low; energize relays; then raise XSMT",
            "mute": "drive XSMT low and wait for soft-ramp completion before dropping relays",
            "safety": "SN74LVC1G08 hardware AND gates require both controller and external supervisor release for XSMT and relay enable",
        },
        "population": {
            "dac_default_digital_volume_db": 0.0,
            "dac_minidsp_creative_processing": "disabled in reference mode",
            "relay_count": 3,
            "line_outputs": ["stereo balanced harness", "stereo RCA harness"],
        },
    }


def main() -> None:
    rendered = json.dumps(calculate(), indent=2, sort_keys=True) + "\n"
    (ROOT / "design_calculations.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
