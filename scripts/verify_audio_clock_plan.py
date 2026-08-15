#!/usr/bin/env python3
"""Verify the exact XC7 audio-clock ratios encoded in the board RTL."""

from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RTL = ROOT / "fpga/nexys_video/audio_clock_synth_xc7.sv"
DEFAULT_XDC = ROOT / "fpga/nexys_video/audio_clock_synth_xc7.xdc"
DEFAULT_OUTPUT = ROOT / "model/generated/audio_clock_plan_xc7.json"

EXPECTED = {
    "mclk_mmcm": {
        "input_hz": 100_000_000,
        "divclk_divide": Fraction(5),
        "feedback_multiply": Fraction(48),
        "output_divide": Fraction(625, 8),
        "vco_hz": 960_000_000,
        "output_hz": 12_288_000,
    },
    "fabric_mmcm": {
        "input_hz": 12_288_000,
        "divclk_divide": Fraction(1),
        "feedback_multiply": Fraction(50),
        "output_divide": Fraction(25, 2),
        "vco_hz": 614_400_000,
        "output_hz": 49_152_000,
    },
}


def _fraction(text: str) -> Fraction:
    return Fraction(text.strip())


def _instance_parameters(text: str, instance_name: str) -> dict[str, Fraction]:
    instance_marker = re.compile(rf"\)\s+{re.escape(instance_name)}\s*\(")
    match = instance_marker.search(text)
    if match is None:
        raise ValueError(f"missing MMCM instance {instance_name}")
    start = text.rfind("MMCME2_BASE #(", 0, match.start())
    if start < 0:
        raise ValueError(f"missing MMCME2_BASE declaration for {instance_name}")
    block = text[start : match.start()]
    values: dict[str, Fraction] = {}
    for parameter in ("DIVCLK_DIVIDE", "CLKFBOUT_MULT_F", "CLKOUT0_DIVIDE_F"):
        parameter_match = re.search(
            rf"\.{parameter}\s*\(\s*([0-9]+(?:\.[0-9]+)?)\s*\)", block
        )
        if parameter_match is None:
            raise ValueError(f"missing {parameter} on {instance_name}")
        values[parameter] = _fraction(parameter_match.group(1))
    return values


def _fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else str(value)


def verify_plan(
    rtl_path: Path = DEFAULT_RTL,
    xdc_path: Path = DEFAULT_XDC,
) -> dict[str, object]:
    source = rtl_path.read_text(encoding="utf-8")
    constraints = xdc_path.read_text(encoding="utf-8")
    if re.search(r"input\s+logic\s+cpu_resetn", source) is None:
        raise ValueError("clock harness must expose active-low cpu_resetn")
    if re.search(r"board_reset\s*=\s*!cpu_resetn\s*;", source) is None:
        raise ValueError("clock harness must invert active-low cpu_resetn")
    if re.search(r"\.reset\s*\(\s*board_reset\s*\)", source) is None:
        raise ValueError("clock MMCM leaf must receive active-high board_reset")
    if re.search(
        r"LOC\s+G4\s+\[get_ports\s+cpu_resetn\]", constraints
    ) is None:
        raise ValueError("G4 must be constrained as cpu_resetn")
    stages: list[dict[str, object]] = []
    preceding_output: int | None = None

    for name, expected in EXPECTED.items():
        actual = _instance_parameters(source, name)
        settings = {
            "DIVCLK_DIVIDE": actual["DIVCLK_DIVIDE"],
            "CLKFBOUT_MULT_F": actual["CLKFBOUT_MULT_F"],
            "CLKOUT0_DIVIDE_F": actual["CLKOUT0_DIVIDE_F"],
        }
        expected_settings = {
            "DIVCLK_DIVIDE": expected["divclk_divide"],
            "CLKFBOUT_MULT_F": expected["feedback_multiply"],
            "CLKOUT0_DIVIDE_F": expected["output_divide"],
        }
        if settings != expected_settings:
            raise ValueError(
                f"{name} parameter mismatch: actual={settings}, "
                f"expected={expected_settings}"
            )

        input_hz = int(expected["input_hz"])
        if preceding_output is not None and input_hz != preceding_output:
            raise ValueError(f"{name} is not chained from the preceding output")
        vco_hz = (
            Fraction(input_hz)
            * actual["CLKFBOUT_MULT_F"]
            / actual["DIVCLK_DIVIDE"]
        )
        output_hz = vco_hz / actual["CLKOUT0_DIVIDE_F"]
        if vco_hz.denominator != 1 or int(vco_hz) != expected["vco_hz"]:
            raise ValueError(f"{name} VCO mismatch: {vco_hz} Hz")
        if output_hz.denominator != 1 or int(output_hz) != expected["output_hz"]:
            raise ValueError(f"{name} output mismatch: {output_hz} Hz")
        if (actual["CLKOUT0_DIVIDE_F"] * 8).denominator != 1:
            raise ValueError(f"{name} output divide is not on a 1/8 step")

        preceding_output = int(output_hz)
        stages.append(
            {
                "instance": name,
                "input_hz": input_hz,
                "divclk_divide": _fraction_text(actual["DIVCLK_DIVIDE"]),
                "feedback_multiply": _fraction_text(
                    actual["CLKFBOUT_MULT_F"]
                ),
                "output_divide": _fraction_text(actual["CLKOUT0_DIVIDE_F"]),
                "vco_hz": int(vco_hz),
                "output_hz": int(output_hz),
            }
        )

    return {
        "schema_version": 1,
        "source": str(rtl_path.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "constraints": str(xdc_path.relative_to(ROOT)),
        "constraints_sha256": hashlib.sha256(
            constraints.encode("utf-8")
        ).hexdigest(),
        "family": "48-kHz audio",
        "codec_mclk_hz": stages[0]["output_hz"],
        "fabric_clock_hz": stages[1]["output_hz"],
        "fabric_clocks_per_384khz_sample": (
            int(stages[1]["output_hz"]) // 384_000
        ),
        "stages": stages,
        "validation": {
            "rtl_parameters_match": True,
            "ratios_are_exact": True,
            "fractional_output_divide_step": "1/8",
            "active_low_board_reset_checked": True,
            "scope": (
                "Arithmetic and RTL-parameter validation only; open P&R and "
                "physical frequency measurement are separate gates."
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

    report = verify_plan(args.rtl.resolve(), args.xdc.resolve())
    if not args.check_only:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
