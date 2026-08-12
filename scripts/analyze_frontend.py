#!/usr/bin/env python3
"""Quantify V1 MM loading, noise, ADC use, and RIAA partition choices."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.riaa import riaa_replay  # noqa: E402


BOLTZMANN = 1.380649e-23
TEMPERATURE_K = 293.15


def rms_density(density: np.ndarray, frequency: np.ndarray) -> float:
    return float(np.sqrt(np.trapezoid(np.square(np.abs(density)), frequency)))


def dbfs(level_v_rms: float, full_scale_v_rms: float) -> float:
    return float(20.0 * np.log10(level_v_rms / full_scale_v_rms))


def main() -> int:
    # The calculation deliberately covers only the audio band. Flicker noise,
    # RF, mains hum, and subsonic warp are separate requirements, not hidden in
    # a single optimistic number.
    frequency = np.geomspace(20.0, 20_000.0, 200_000)
    omega = 2.0 * np.pi * frequency
    cartridge_r = 485.0
    cartridge_l = 0.550
    load_r = 47_500.0
    load_c = 150.0e-12
    z_cartridge = cartridge_r + 1j * omega * cartridge_l
    y_load = 1.0 / load_r + 1j * omega * load_c
    z_load = 1.0 / y_load
    loading = z_load / (z_cartridge + z_load)
    z_terminal = 1.0 / (1.0 / z_cartridge + y_load)

    riaa = riaa_replay(frequency)
    # Architecture B moves only the 3180/318 us bass shelf into analog. The
    # 75 us pole remains digital. This is a precise study case, not a PCB choice.
    s = 1j * omega
    analog_b = (1.0 + s * 318.0e-6) / (1.0 + s * 3180.0e-6)
    analog_b /= (1.0 + 1j * 2.0 * np.pi * 1000.0 * 318.0e-6) / (
        1.0 + 1j * 2.0 * np.pi * 1000.0 * 3180.0e-6
    )
    digital_b = riaa / analog_b

    sqrt_four_k_t = np.sqrt(4.0 * BOLTZMANN * TEMPERATURE_K)
    cartridge_density = sqrt_four_k_t * np.sqrt(cartridge_r) * loading
    load_density = sqrt_four_k_t / np.sqrt(load_r) * z_terminal

    amplifiers = {
        # Broadband typical data-sheet values. Voltage/current noise is held
        # white here; the report explicitly excludes 1/f and hum.
        "ADA4625-1": {"en_v_sqrt_hz": 3.3e-9, "in_a_sqrt_hz": 4.5e-15},
        "OPA210": {"en_v_sqrt_hz": 2.2e-9, "in_a_sqrt_hz": 400.0e-15},
        "OPA1656": {"en_v_sqrt_hz": 4.3e-9, "in_a_sqrt_hz": 6.0e-15},
    }
    noise: dict[str, object] = {
        "band_hz": [20.0, 20_000.0],
        "temperature_c": 20.0,
        "cartridge_resistance_rms_v": rms_density(cartridge_density, frequency),
        "load_resistor_rms_v": rms_density(load_density, frequency),
        "cartridge_resistance_after_riaa_rms_v": rms_density(
            cartridge_density * riaa, frequency
        ),
        "load_resistor_after_riaa_rms_v": rms_density(
            load_density * riaa, frequency
        ),
        "amplifiers": {},
    }
    analog_riaa_weighted: dict[str, float] = {}
    for name, part in amplifiers.items():
        voltage_density = np.full_like(frequency, part["en_v_sqrt_hz"])
        current_density = part["in_a_sqrt_hz"] * z_terminal
        total_density = np.sqrt(
            np.square(np.abs(cartridge_density))
            + np.square(np.abs(load_density))
            + np.square(voltage_density)
            + np.square(np.abs(current_density))
        )
        noise["amplifiers"][name] = {
            **part,
            "voltage_noise_rms_v": rms_density(voltage_density, frequency),
            "current_noise_rms_v": rms_density(current_density, frequency),
            "total_input_rms_v": rms_density(total_density, frequency),
            "snr_for_4mv_db": float(
                20.0 * np.log10(4.0e-3 / rms_density(total_density, frequency))
            ),
        }
        analog_riaa_weighted[name] = rms_density(total_density * riaa, frequency)

    adc_full_scale_v_rms = 2.0
    adc_dynamic_range_db = 119.0
    adc_integrated_noise_v = adc_full_scale_v_rms / 10.0 ** (
        adc_dynamic_range_db / 20.0
    )
    adc_density = adc_integrated_noise_v / np.sqrt(20_000.0 - 20.0)
    architecture = {
        "assumptions": {
            "adc_full_scale_differential_v_rms": adc_full_scale_v_rms,
            "adc_dynamic_range_db": adc_dynamic_range_db,
            "transient_levels_v_rms_equivalent": [0.004, 0.020, 0.100],
            "architecture_b_partition": "analog 3180/318 us shelf; digital 75 us pole",
        },
        "A_flat_26db": {
            "analog_gain_db_at_1khz": 26.0,
            "analog_gain_peak_20hz_to_20khz_db_relative_1khz": 0.0,
        },
        "B_partial_20db": {
            "analog_gain_db_at_1khz": 20.0,
            "analog_gain_peak_20hz_to_20khz_db_relative_1khz": float(
                20.0 * np.log10(np.max(np.abs(analog_b)))
            ),
        },
        "C_full_riaa_40db": {
            "analog_gain_db_at_1khz": 40.0,
            "analog_gain_peak_20hz_to_20khz_db_relative_1khz": float(
                20.0 * np.log10(np.max(np.abs(riaa)))
            ),
        },
    }
    partitions = {
        "A_flat_26db": riaa,
        "B_partial_20db": digital_b,
        "C_full_riaa_40db": np.ones_like(frequency),
    }
    for name, digital_response in partitions.items():
        entry = architecture[name]
        gain = 10.0 ** (entry["analog_gain_db_at_1khz"] / 20.0)
        entry["adc_dbfs_at_1khz"] = {
            f"{1000.0 * level:.0f}mv": dbfs(level * gain, adc_full_scale_v_rms)
            for level in (0.004, 0.020, 0.100)
        }
        entry["adc_dbfs_at_analog_peak"] = {
            f"{1000.0 * level:.0f}mv": dbfs(
                level
                * gain
                * 10.0
                ** (entry["analog_gain_peak_20hz_to_20khz_db_relative_1khz"] / 20.0),
                adc_full_scale_v_rms,
            )
            for level in (0.004, 0.020, 0.100)
        }
        entry["adc_noise_referred_to_cartridge_after_riaa_rms_v"] = rms_density(
            adc_density * digital_response / gain, frequency
        )
        best_analog = analog_riaa_weighted["ADA4625-1"]
        adc_referred = entry[
            "adc_noise_referred_to_cartridge_after_riaa_rms_v"
        ]
        entry["combined_ada4625_and_adc_after_riaa_rms_v"] = float(
            np.hypot(best_analog, adc_referred)
        )
        entry["snr_for_4mv_after_riaa_db"] = float(
            20.0
            * np.log10(
                4.0e-3 / entry["combined_ada4625_and_adc_after_riaa_rms_v"]
            )
        )

    report = {
        "scope": "Analytical 20 Hz-20 kHz estimate; excludes 1/f, hum, RF, distortion, and tolerance",
        "loading": {
            "terminal_gain_db_at_1khz": float(
                20.0 * np.log10(abs(np.interp(1000.0, frequency, loading)))
            ),
            "terminal_gain_db_at_20khz": float(
                20.0 * np.log10(abs(loading[-1]))
            ),
            "terminal_peak_db": float(20.0 * np.log10(np.max(np.abs(loading)))),
            "terminal_peak_hz": float(frequency[np.argmax(np.abs(loading))]),
        },
        "noise": noise,
        "architectures": architecture,
    }
    output = REPOSITORY_ROOT / "reference" / "results" / "frontend_analysis.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
