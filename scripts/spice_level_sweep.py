#!/usr/bin/env python3
"""Run reproducible 1 kHz V1 SPICE level sweeps and extract harmonics."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def locate_ngspice() -> Path | None:
    system = shutil.which("ngspice")
    if system:
        return Path(system)
    local = REPOSITORY_ROOT / ".tools" / "root" / "usr" / "bin" / "ngspice"
    return local if local.exists() else None


def fit_harmonics(time_s: np.ndarray, waveform: np.ndarray) -> tuple[float, float, list[float]]:
    columns = [np.ones_like(time_s)]
    for harmonic in range(1, 11):
        angle = 2.0 * np.pi * 1000.0 * harmonic * time_s
        columns.extend((np.sin(angle), np.cos(angle)))
    coefficients, *_ = np.linalg.lstsq(np.column_stack(columns), waveform, rcond=None)
    peak = [
        float(np.hypot(coefficients[2 * harmonic - 1], coefficients[2 * harmonic]))
        for harmonic in range(1, 11)
    ]
    thd = float(np.sqrt(np.sum(np.square(peak[1:]))) / peak[0])
    return peak[0], thd, peak


def main() -> int:
    executable = locate_ngspice()
    if executable is None:
        print("ERROR: ngspice unavailable; run `make tools`", file=sys.stderr)
        return 2
    source = (
        REPOSITORY_ROOT / "reference" / "spice" / "v1_reference.cir"
    ).read_text(encoding="utf-8")
    workspace = REPOSITORY_ROOT / "build" / "spice_level_sweep"
    workspace.mkdir(parents=True, exist_ok=True)
    results = REPOSITORY_ROOT / "reference" / "results"
    results.mkdir(parents=True, exist_ok=True)
    levels_peak_v = (
        0.0005,
        0.001,
        0.0025,
        0.005,
        0.010,
        0.020,
        0.050,
        0.100,
        0.200,
        0.500,
        1.000,
        1.100,
        1.250,
        1.500,
        2.000,
        5.000,
    )
    measurements: list[dict[str, object]] = []
    for index, level in enumerate(levels_peak_v):
        csv_relative = f"reference/results/spice_level_{index:02d}.csv"
        netlist_text = source.replace(
            "SIN(0 5m 1k)", f"SIN(0 {level:.12g} 1k)"
        ).replace(
            "reference/results/spice_tran_1khz_5mv.csv", csv_relative
        )
        netlist_path = workspace / f"level_{index:02d}.cir"
        netlist_path.write_text(netlist_text, encoding="utf-8")
        log_path = workspace / f"level_{index:02d}.log"
        completed = subprocess.run(
            [str(executable), "-b", "-o", str(log_path), str(netlist_path)],
            cwd=REPOSITORY_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if completed.returncode:
            print(log_path.read_text(encoding="utf-8", errors="replace"), file=sys.stderr)
            return completed.returncode
        data = np.loadtxt(REPOSITORY_ROOT / csv_relative, skiprows=1)
        selection = data[:, 0] >= 0.020
        fundamental_peak, thd, harmonic_peak = fit_harmonics(
            data[selection, 0], data[selection, -1]
        )
        measurements.append(
            {
                "input_peak_v": level,
                "input_rms_v": level / np.sqrt(2.0),
                "output_fundamental_peak_v": fundamental_peak,
                "fundamental_gain_db": float(20.0 * np.log10(fundamental_peak / level)),
                "thd_percent_h2_to_h10": 100.0 * thd,
                "harmonic_peak_v_h1_to_h10": harmonic_peak,
            }
        )
        (REPOSITORY_ROOT / csv_relative).unlink()

    small_signal_gain_db = float(measurements[0]["fundamental_gain_db"])
    for measurement in measurements:
        measurement["gain_compression_db"] = (
            float(measurement["fundamental_gain_db"]) - small_signal_gain_db
        )
    compression_levels = [
        float(entry["input_peak_v"])
        for entry in measurements
        if float(entry["gain_compression_db"]) <= -1.0
    ]
    report = {
        "engine": "ngspice",
        "stimulus": "1 kHz sine at cartridge source; AT-VM95E R/L and load retained",
        "analysis_window_s": [0.020, 0.030],
        "harmonics": "least-squares sine/cosine fit, H2-H10",
        "small_signal_gain_db": small_signal_gain_db,
        "first_tested_level_at_or_beyond_1db_compression_peak_v": (
            compression_levels[0] if compression_levels else None
        ),
        "measurements": measurements,
    }
    output = results / "spice_level_sweep.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
