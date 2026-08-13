#!/usr/bin/env python3
"""Generate factorized 12AX7 ROMs, exact RTL vectors, and metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.tube import Koren12AX7  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0xFAC701)
    parser.add_argument("--vectors", type=int, default=4096)
    parser.add_argument(
        "--output", type=Path, default=REPOSITORY_ROOT / "model" / "generated"
    )
    args = parser.parse_args()

    factorized = FixedFactorizedKoren12AX7()
    memory_paths = factorized.write_memories(args.output)
    rng = np.random.default_rng(args.seed)
    random_grid = rng.integers(
        factorized._fixed_limit(-5.0, 24),
        factorized._fixed_limit(1.0, 24) + 1,
        args.vectors,
        dtype=np.int64,
    )
    random_plate = rng.integers(
        factorized._fixed_limit(0.0, 20),
        factorized._fixed_limit(400.0, 20) + 1,
        args.vectors,
        dtype=np.int64,
    )
    directed = np.asarray(
        [
            (-6 << 24, -1 << 20),
            (-5 << 24, 0),
            (-5 << 24, 400 << 20),
            (-1 << 24, 150 << 20),
            (0, 0),
            (0, 100 << 20),
            (1 << 24, 400 << 20),
            (2 << 24, 401 << 20),
            (-(1 << 31), 0),
            ((1 << 31) - 1, (1 << 31) - 1),
            (0, -(1 << 31)),
        ],
        dtype=np.int64,
    )
    grid_q24 = np.concatenate((directed[:, 0], random_grid))
    plate_q20 = np.concatenate((directed[:, 1], random_plate))

    vector_dir = REPOSITORY_ROOT / "sim" / "vectors" / "generated"
    vector_dir.mkdir(parents=True, exist_ok=True)
    vector_path = vector_dir / "triode_factorized_random.txt"
    approximate = np.empty(grid_q24.size)
    clip_count = 0
    with vector_path.open("w", encoding="ascii") as handle:
        handle.write("# vg_q24 vp_q20 ip_q31 ig_q31 clipped\n")
        for index, (grid, plate) in enumerate(
            zip(grid_q24, plate_q20, strict=True)
        ):
            ip_q31, ig_q31, clipped = factorized.evaluate_fixed(
                int(grid), int(plate)
            )
            approximate[index] = ip_q31 / (1 << 31)
            clip_count += int(clipped)
            handle.write(
                f"{grid} {plate} {ip_q31} {ig_q31} {int(clipped)}\n"
            )

    in_range = (
        (grid_q24 >= (-5 << 24))
        & (grid_q24 <= (1 << 24))
        & (plate_q20 >= 0)
        & (plate_q20 <= (400 << 20))
    )
    reference = Koren12AX7().plate_current(
        grid_q24[in_range] / (1 << 24), plate_q20[in_range] / (1 << 20)
    )
    error = approximate[in_range] - reference
    report = {
        "algorithm": "three value/slope 1-D LUTs with fixed cubic Hermite interpolation",
        "seed": args.seed,
        "random_vectors": args.vectors,
        "directed_vectors": int(directed.shape[0]),
        "total_vectors": int(grid_q24.size),
        "expected_clip_vectors": clip_count,
        "latency_clocks": 8,
        "raw_table_bits": factorized.raw_table_bits,
        "raw_ramb18_equivalents": factorized.raw_table_bits / 18_432.0,
        "mean_absolute_error_a": float(np.mean(np.abs(error))),
        "rms_error_a": float(np.sqrt(np.mean(np.square(error)))),
        "worst_absolute_error_a": float(np.max(np.abs(error))),
        "outputs": [
            *(str(path.relative_to(REPOSITORY_ROOT)) for path in memory_paths),
            str(vector_path.relative_to(REPOSITORY_ROOT)),
        ],
    }
    report_path = args.output / "12ax7_factorized_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
