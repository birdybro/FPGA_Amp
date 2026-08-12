#!/usr/bin/env python3
"""Regenerate mathematical reports and optional engineering plots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.cartridge import CartridgeModel  # noqa: E402
from fpga_amp.fixed import TubeLUT  # noqa: E402
from fpga_amp.riaa import riaa_db  # noqa: E402
from fpga_amp.tube import Koren12AX7  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    results = REPOSITORY_ROOT / "reference" / "results"
    results.mkdir(parents=True, exist_ok=True)

    tube = Koren12AX7()
    cartridge = CartridgeModel()
    standard = np.loadtxt(
        REPOSITORY_ROOT / "reference" / "vectors" / "riaa_e1_1978.csv", delimiter=","
    )
    standard_error = riaa_db(standard[:, 0]) - standard[:, 1]
    digitized = np.loadtxt(
        REPOSITORY_ROOT / "reference" / "tube_data" / "ge_12ax7_digitized.csv",
        delimiter=",",
    )
    predicted_ma = 1000.0 * tube.plate_current(digitized[:, 0], digitized[:, 1])
    curve_error_ma = predicted_ma - digitized[:, 2]
    frequency = np.geomspace(10.0, 100_000.0, 2000)
    cartridge_magnitude = np.abs(cartridge.transfer(frequency))

    lut = TubeLUT()
    lut.generate(tube)
    rng = np.random.default_rng(0x12A7)
    vg = rng.uniform(-5.0, 1.0, 4096)
    vp = rng.uniform(0.0, 400.0, 4096)
    lut_error = np.asarray(
        [lut.evaluate(float(g), float(p))[0] for g, p in zip(vg, vp, strict=True)]
    ) - tube.plate_current(vg, vp)

    report = {
        "ideal_riaa_vs_1978_table_max_error_db": float(np.max(np.abs(standard_error))),
        "ge_curve_digitization_uncertainty_ma": 0.05,
        "koren_vs_ge_digitized_rms_error_ma": float(
            np.sqrt(np.mean(np.square(curve_error_ma)))
        ),
        "koren_vs_ge_digitized_worst_error_ma": float(np.max(np.abs(curve_error_ma))),
        "cartridge_undamped_lc_resonance_hz": cartridge.undamped_resonance_hz,
        "cartridge_loaded_peak_hz": float(frequency[np.argmax(cartridge_magnitude)]),
        "cartridge_loaded_peak_db": float(20.0 * np.log10(np.max(cartridge_magnitude))),
        "tube_lut_mean_absolute_error_a": float(np.mean(np.abs(lut_error))),
        "tube_lut_worst_absolute_error_a": float(np.max(np.abs(lut_error))),
        "tube_bias": {
            "stage1": tube.solve_cathode_bias(300.0, 121_000.0, 1_210.0),
            "stage2": tube.solve_cathode_bias(300.0, 100_000.0, 1_210.0),
        },
    }
    report_path = results / "mathematical_reference.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

    if args.plots:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.figure(figsize=(8, 5))
        plt.semilogx(frequency, riaa_db(frequency), label="Ideal RIAA E-1")
        plt.scatter(standard[:, 0], standard[:, 1], s=12, label="1978 tabulation")
        plt.xlabel("Frequency (Hz)")
        plt.ylabel("Replay response relative to 1 kHz (dB)")
        plt.grid(True, which="both", alpha=0.3)
        plt.legend()
        plt.tight_layout()
        plt.savefig(results / "ideal_riaa.png", dpi=150)
        plt.close()

        plt.figure(figsize=(8, 5))
        plate_axis = np.linspace(0.0, 450.0, 500)
        for grid_v in np.arange(0.0, -3.01, -0.5):
            plt.plot(
                plate_axis,
                1000.0 * tube.plate_current(grid_v, plate_axis),
                label=f"Vgk={grid_v:g} V",
            )
        plt.scatter(digitized[:, 1], digitized[:, 2], c="black", s=10, label="GE digitized")
        plt.xlim(0, 450)
        plt.ylim(0, 4.0)
        plt.xlabel("Plate-to-cathode voltage (V)")
        plt.ylabel("Plate current (mA)")
        plt.grid(True, alpha=0.3)
        plt.legend(ncol=2, fontsize=8)
        plt.tight_layout()
        plt.savefig(results / "12ax7_curves.png", dpi=150)
        plt.close()

        plt.figure(figsize=(8, 5))
        plt.semilogx(frequency, 20.0 * np.log10(cartridge_magnitude))
        plt.xlabel("Frequency (Hz)")
        plt.ylabel("Cartridge terminal / source voltage (dB)")
        plt.title("AT-VM95E nominal R/L into 47.5 kΩ || 150 pF")
        plt.grid(True, which="both", alpha=0.3)
        plt.tight_layout()
        plt.savefig(results / "cartridge_loading.png", dpi=150)
        plt.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

