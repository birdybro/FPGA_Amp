#!/usr/bin/env python3
"""Compare tube LUT resolution, error, and raw storage cost."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.fixed import TubeLUT  # noqa: E402
from fpga_amp.tube import Koren12AX7  # noqa: E402


def main() -> int:
    tube = Koren12AX7()
    rng = np.random.default_rng(0x51A7)
    vg = rng.uniform(-5.0, 1.0, 50_000)
    vp = rng.uniform(0.0, 400.0, 50_000)
    reference = tube.plate_current(vg, vp)
    operating = (vp >= 20.0) & (vg <= 0.0)
    reports: list[dict[str, float | int | str]] = []
    for grid_points, plate_points in ((64, 128), (128, 256), (256, 256), (128, 512)):
        lut = TubeLUT(grid_points=grid_points, plate_points=plate_points)
        lut.generate(tube)
        approximate = np.asarray(
            [lut.evaluate(float(g), float(p))[0] for g, p in zip(vg, vp, strict=True)]
        )
        error = approximate - reference
        reports.append(
            {
                "grid_points": grid_points,
                "plate_points": plate_points,
                "plate_storage_bits": grid_points * plate_points * 32,
                "mean_absolute_error_a": float(np.mean(np.abs(error))),
                "rms_error_a": float(np.sqrt(np.mean(np.square(error)))),
                "worst_absolute_error_a": float(np.max(np.abs(error))),
                "worst_absolute_error_operating_region_a": float(
                    np.max(np.abs(error[operating]))
                ),
            }
        )
    result = {
        "probe_vectors": int(vg.size),
        "operating_region_definition": "v_pk >= 20 V and v_gk <= 0 V",
        "architectural_note": "raw bits exclude BRAM aspect-ratio/packing overhead",
        "resolutions": reports,
    }
    output = REPOSITORY_ROOT / "reference" / "results" / "lut_resolution_study.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

