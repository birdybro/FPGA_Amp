#!/usr/bin/env python3
"""Verify the frozen Nexys Video audio-top wiring and pin contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RTL = ROOT / "fpga/nexys_video/phono_audio_top_xc7.sv"
DEFAULT_XDC = ROOT / "fpga/nexys_video/phono_audio_top_xc7.xdc"
DEFAULT_OUTPUT = ROOT / "model/generated/nexys_video_audio_top_contract.json"

EXPECTED_PINS = {
    "clk_100mhz": ("R4", "LVCMOS33"),
    "cpu_resetn": ("G4", "LVCMOS15"),
    "force_mute_switch": ("E22", "LVCMOS12"),
    "codec_mclk": ("U6", "LVCMOS33"),
    "codec_bclk": ("T5", "LVCMOS33"),
    "codec_lrclk": ("U5", "LVCMOS33"),
    "codec_adc_serial_data": ("T4", "LVCMOS33"),
    "codec_dac_serial_data": ("W6", "LVCMOS33"),
    "codec_i2c_scl": ("W5", "LVCMOS33"),
    "codec_i2c_sda": ("V5", "LVCMOS33"),
    "spi_cs_n": ("AB22", "LVCMOS33"),
    "spi_sclk": ("AB21", "LVCMOS33"),
    "spi_mosi": ("AB20", "LVCMOS33"),
    "spi_miso": ("AB18", "LVCMOS33"),
    "led_clocks_locked": ("T14", "LVCMOS25"),
    "led_codec_configured": ("T15", "LVCMOS25"),
    "led_codec_error": ("T16", "LVCMOS25"),
    "led_output_muted": ("U16", "LVCMOS25"),
}


def _property_map(text: str, property_name: str) -> dict[str, str]:
    matches = re.findall(
        rf"set_property\s+{property_name}\s+(\S+)\s+"
        rf"\[get_ports\s+(\S+)\]",
        text,
    )
    result: dict[str, str] = {}
    for value, port in matches:
        if port in result:
            raise ValueError(f"duplicate {property_name} for port {port}")
        result[port] = value
    return result


def _require(pattern: str, text: str, message: str) -> None:
    if re.search(pattern, text, flags=re.DOTALL) is None:
        raise ValueError(message)


def verify_top(
    rtl_path: Path = DEFAULT_RTL,
    xdc_path: Path = DEFAULT_XDC,
) -> dict[str, object]:
    source = rtl_path.read_text(encoding="utf-8")
    constraints = xdc_path.read_text(encoding="utf-8")
    locs = _property_map(constraints, "LOC")
    standards = _property_map(constraints, "IOSTANDARD")
    actual_pins = {
        port: (locs.get(port), standards.get(port)) for port in EXPECTED_PINS
    }
    if actual_pins != EXPECTED_PINS:
        differences = {
            port: {"actual": actual_pins[port], "expected": expected}
            for port, expected in EXPECTED_PINS.items()
            if actual_pins[port] != expected
        }
        raise ValueError(f"board pin contract mismatch: {differences}")
    extras = (set(locs) | set(standards)) - set(EXPECTED_PINS)
    if extras:
        raise ValueError(f"unexpected constrained ports: {sorted(extras)}")

    _require(
        r"create_clock\s+-period\s+10(?:\.0+)?\s+"
        r"\[get_ports\s+clk_100mhz\]",
        constraints,
        "missing 100 MHz board-input clock constraint",
    )
    bclk_match = re.search(
        r"create_clock\s+-period\s+([0-9.]+)\s+"
        r"\[get_nets\s+audio_and_control\.i2s_bclk\]",
        constraints,
    )
    if bclk_match is None:
        raise ValueError("missing internal shared-BCLK timing constraint")
    bclk_period_ns = float(bclk_match.group(1))
    expected_bclk_period_ns = 1e9 / 3_072_000
    if abs(bclk_period_ns - expected_bclk_period_ns) > 1e-6:
        raise ValueError(
            f"BCLK period mismatch: {bclk_period_ns} ns, "
            f"expected {expected_bclk_period_ns:.9f} ns"
        )

    requirements = (
        (r"board_reset\s*=\s*!cpu_resetn\s*;", "active-low reset is not inverted"),
        (
            r"audio_rst_n\s*=\s*fabric_rst_n\s*&&\s*codec_configured\s*;",
            "audio reset is not gated by complete codec configuration",
        ),
        (
            r"\.force_mute\s*\(\s*force_mute_switch\s*\|\|\s*"
            r"!codec_configured\s*\)",
            "forced mute does not fail closed before codec configuration",
        ),
        (r"audio_clock_synth_xc7\s+clock_synth\s*\(", "missing clock leaf"),
        (
            r"audio_serial_clock_master_xc7\s+serial_clocks\s*\(",
            "missing serial-clock/reset leaf",
        ),
        (r"adau1761_codec_init\s+codec_initializer\s*\(", "missing codec initializer"),
        (
            r"codec_shared_i2s_guard\s+shared_serial_guard\s*\(",
            "missing shared-LRCLK/zero-data guard",
        ),
        (
            r"phono_i2s_spi_top\s*#\s*\(.*?"
            r"\.MODEL_SAMPLE_RATE_HZ\s*\(\s*384000\s*\).*?"
            r"\.FABRIC_CLOCKS_PER_48K_INPUT\s*\(\s*1024\s*\).*?"
            r"\.CLOCK_MONITOR_WINDOW_FABRIC_CLOCKS\s*\(\s*16384\s*\)",
            "phono hierarchy does not select the checked 384 kHz schedule",
        ),
        (
            r"assign\s+codec_i2c_scl\s*=\s*codec_scl_drive_low\s*\?\s*"
            r"1'b0\s*:\s*1'bz\s*;",
            "I2C SCL is not open drain",
        ),
        (
            r"assign\s+codec_i2c_sda\s*=\s*codec_sda_drive_low\s*\?\s*"
            r"1'b0\s*:\s*1'bz\s*;",
            "I2C SDA is not open drain",
        ),
    )
    for pattern, message in requirements:
        _require(pattern, source, message)

    return {
        "schema_version": 1,
        "rtl": str(rtl_path.relative_to(ROOT)),
        "rtl_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "constraints": str(xdc_path.relative_to(ROOT)),
        "constraints_sha256": hashlib.sha256(
            constraints.encode("utf-8")
        ).hexdigest(),
        "board": "Digilent Nexys Video Rev. A",
        "part": "xc7a200tsbg484-1",
        "pin_count": len(EXPECTED_PINS),
        "pins": {
            port: {"loc": loc, "iostandard": standard}
            for port, (loc, standard) in EXPECTED_PINS.items()
        },
        "clock_constraints": {
            "input_hz": 100_000_000,
            "bclk_hz": 3_072_000,
            "bclk_period_ns": bclk_period_ns,
        },
        "audio_profile": {
            "external_sample_rate_hz": 48_000,
            "model_sample_rate_hz": 384_000,
            "fabric_clocks_per_input": 1_024,
        },
        "validation": {
            "active_low_reset_checked": True,
            "fail_closed_audio_release_checked": True,
            "single_shared_lrclk_guard_checked": True,
            "open_drain_i2c_checked": True,
            "scope": (
                "Static RTL/XDC composition contract only; simulation, open "
                "place/route, bitstream generation, and hardware are separate gates."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rtl", type=Path, default=DEFAULT_RTL)
    parser.add_argument("--xdc", type=Path, default=DEFAULT_XDC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    report = verify_top(args.rtl.resolve(), args.xdc.resolve())
    if not args.check_only:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
