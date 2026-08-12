#!/usr/bin/env python3
"""Generate deterministic tube memories, RTL vectors, and an error report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.fixed import TubeLUT  # noqa: E402
from fpga_amp.tube import Koren12AX7  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0x12A7)
    parser.add_argument("--vectors", type=int, default=4096)
    parser.add_argument("--output", type=Path, default=REPOSITORY_ROOT / "model" / "generated")
    args = parser.parse_args()

    tube = Koren12AX7()
    lut = TubeLUT()
    lut.generate(tube)
    plate_path, grid_path = lut.write_memories(args.output)

    rng = np.random.default_rng(args.seed)
    vg = rng.uniform(lut.v_gk_min_v, lut.v_gk_max_v, args.vectors)
    vp = rng.uniform(lut.v_pk_min_v, lut.v_pk_max_v, args.vectors)
    reference = tube.plate_current(vg, vp)
    approximate = np.empty(args.vectors)

    vector_dir = REPOSITORY_ROOT / "sim" / "vectors" / "generated"
    vector_dir.mkdir(parents=True, exist_ok=True)
    vector_path = vector_dir / "triode_random.txt"
    with vector_path.open("w", encoding="ascii") as handle:
        handle.write("# vg_q24 vp_q20 ip_q31 ig_q31 clipped\n")
        for index, (v_grid, v_plate) in enumerate(zip(vg, vp, strict=True)):
            vg_q = int(round(v_grid * (1 << lut.v_gk_fractional_bits)))
            vp_q = int(round(v_plate * (1 << lut.v_pk_fractional_bits)))
            ip_q, ig_q, clipped = lut.evaluate_fixed(vg_q, vp_q)
            approximate[index] = ip_q / float(1 << lut.current_fractional_bits)
            handle.write(f"{vg_q} {vp_q} {ip_q} {ig_q} {int(clipped)}\n")

    error = approximate - reference
    # A much larger independent error probe prevents the compact RTL vector
    # set from under-reporting the difficult positive-grid/low-plate corner.
    error_vg = rng.uniform(lut.v_gk_min_v, lut.v_gk_max_v, 100_000)
    error_vp = rng.uniform(lut.v_pk_min_v, lut.v_pk_max_v, 100_000)
    error_reference = tube.plate_current(error_vg, error_vp)
    error_approximate = np.asarray(
        [
            lut.evaluate(float(v_grid), float(v_plate))[0]
            for v_grid, v_plate in zip(error_vg, error_vp, strict=True)
        ]
    )
    error_probe = error_approximate - error_reference
    active = error_reference > 1.0e-6
    report = {
        "algorithm": "128x256 uniform LUT with bit-accurate bilinear interpolation",
        "seed": args.seed,
        "random_vectors": args.vectors,
        "ranges": {"v_gk_v": [-5.0, 1.0], "v_pk_v": [0.0, 400.0]},
        "formats": {"v_gk": "Q8.24", "v_pk": "Q12.20", "i_p": "Q0.31"},
        "error_probe_vectors": 100000,
        "mean_absolute_error_a": float(np.mean(np.abs(error_probe))),
        "rms_error_a": float(np.sqrt(np.mean(np.square(error_probe)))),
        "worst_absolute_error_a": float(np.max(np.abs(error_probe))),
        "worst_relative_error_active": float(
            np.max(np.abs(error_probe[active]) / error_reference[active])
        ),
        "plate_memory_bits": lut.grid_points * lut.plate_points * 32,
        "grid_memory_bits": lut.grid_points * 32,
        "vg_scale_q24": lut.vg_scale_q,
        "vp_scale_q24": lut.vp_scale_q,
        "outputs": [
            str(plate_path.relative_to(REPOSITORY_ROOT)),
            str(grid_path.relative_to(REPOSITORY_ROOT)),
            str(vector_path.relative_to(REPOSITORY_ROOT)),
        ],
    }
    report_path = args.output / "12ax7_lut_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
