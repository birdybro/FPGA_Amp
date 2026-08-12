#!/usr/bin/env python3
"""Run the V1 ngspice reference and extract a compact measured summary."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.riaa import riaa_db  # noqa: E402


def locate_tool(requested: str) -> str | None:
    found = shutil.which(requested)
    if found:
        return found
    local = REPOSITORY_ROOT / ".tools" / "root" / "usr" / "bin" / requested
    return str(local) if local.exists() else None


def load_wrdata(path: Path) -> tuple[list[str], np.ndarray]:
    with path.open("r", encoding="utf-8") as handle:
        rows = [row for row in csv.reader(handle, delimiter=" ") if row]
    # csv with a literal delimiter retains empty fields; normalize whitespace.
    normalized = [[field for field in row if field] for row in rows]
    names = normalized[0]
    data = np.asarray(normalized[1:], dtype=np.float64)
    return names, data


def column(names: list[str], data: np.ndarray, suffix: str) -> np.ndarray:
    for index, name in enumerate(names):
        if name.lower().endswith(suffix.lower()):
            return data[:, index]
    raise KeyError(f"no column ending in {suffix!r}; columns={names}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ngspice", default="ngspice")
    parser.add_argument("--require-tool", action="store_true")
    args = parser.parse_args()

    executable = locate_tool(args.ngspice)
    if executable is None:
        message = "ngspice unavailable; run `make tools` or install ngspice"
        if args.require_tool:
            print(message, file=sys.stderr)
            return 2
        print(f"SKIP: {message}")
        return 0

    results = REPOSITORY_ROOT / "reference" / "results"
    results.mkdir(parents=True, exist_ok=True)
    log_path = results / "ngspice.log"
    netlist = REPOSITORY_ROOT / "reference" / "spice" / "v1_reference.cir"
    completed = subprocess.run(
        [executable, "-b", "-o", str(log_path), str(netlist)],
        cwd=REPOSITORY_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode:
        print(completed.stdout, file=sys.stderr)
        print(log_path.read_text(encoding="utf-8", errors="replace"), file=sys.stderr)
        return completed.returncode

    op_names, op_data = load_wrdata(results / "spice_op.csv")
    ac_names, ac_data = load_wrdata(results / "spice_ac.csv")
    frequency = ac_data[:, 0]
    circuit_gain = column(ac_names, ac_data, "circuit_gain_db")
    overall_gain = column(ac_names, ac_data, "overall_gain_db")
    phase = column(ac_names, ac_data, "gain_phase_deg")
    cartridge_loading = column(ac_names, ac_data, "input_db")
    ideal = riaa_db(frequency)
    audio_band = (frequency >= 20.0) & (frequency <= 20_000.0)
    gain_1k = float(np.interp(1000.0, frequency, circuit_gain))
    overall_gain_1k = float(np.interp(1000.0, frequency, overall_gain))
    physical_relative = circuit_gain - gain_1k
    error = physical_relative - ideal

    op_values = op_data[0]
    summary = {
        "tool": log_path.read_text(encoding="utf-8", errors="replace").splitlines()[0:8],
        "dc": {name: float(value) for name, value in zip(op_names[1:], op_values[1:], strict=True)},
        "ac": {
            "gain_db_at_1khz": gain_1k,
            "overall_cartridge_to_output_gain_db_at_1khz": overall_gain_1k,
            "cartridge_loading_db_at_20khz": float(
                np.interp(20_000.0, frequency, cartridge_loading)
            ),
            "phase_deg_at_1khz": float(np.interp(1000.0, frequency, phase)),
            "riaa_error_min_db_20hz_20khz": float(np.min(error[audio_band])),
            "riaa_error_max_db_20hz_20khz": float(np.max(error[audio_band])),
            "riaa_error_rms_db_20hz_20khz": float(
                np.sqrt(np.mean(np.square(error[audio_band])))
            ),
            "points_10hz_100khz": int(frequency.size),
        },
    }
    summary_path = results / "spice_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
