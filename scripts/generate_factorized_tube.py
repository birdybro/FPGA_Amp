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

from fpga_amp.factorized_tube import (  # noqa: E402
    FixedFactorizedKoren12AX7,
    FixedLinearFactorizedKoren12AX7,
)
from fpga_amp.tube import Koren12AX7  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0xFAC701)
    parser.add_argument("--vectors", type=int, default=4096)
    parser.add_argument(
        "--linear",
        action="store_true",
        help="generate the measured value-only linear timing candidate",
    )
    parser.add_argument(
        "--output", type=Path, default=REPOSITORY_ROOT / "model" / "generated"
    )
    args = parser.parse_args()

    factorized = (
        FixedLinearFactorizedKoren12AX7()
        if args.linear
        else FixedFactorizedKoren12AX7()
    )
    memory_paths = factorized.write_memories(args.output)
    rng = np.random.default_rng(args.seed)
    random_grid = rng.integers(
        factorized._fixed_limit(factorized.v_gk_min_v, 24),
        factorized._fixed_limit(factorized.v_gk_max_v, 24) + 1,
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
            (-9 << 24, 300 << 20),
            (-8 << 24, 300 << 20),
            (-7 << 24, 295 << 20),
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
    vector_path = vector_dir / (
        "triode_factorized_linear_random.txt"
        if args.linear
        else "triode_factorized_random.txt"
    )
    approximate = np.empty(grid_q24.size)
    clipped_flags = np.empty(grid_q24.size, dtype=np.bool_)
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
            clipped_flags[index] = clipped
            clip_count += int(clipped)
            handle.write(
                f"{grid} {plate} {ip_q31} {ig_q31} {int(clipped)}\n"
            )

    externally_in_range = (
        (grid_q24 >= factorized._fixed_limit(factorized.v_gk_min_v, 24))
        & (grid_q24 <= factorized._fixed_limit(factorized.v_gk_max_v, 24))
        & (plate_q20 >= factorized._fixed_limit(factorized.plate_min_v, 20))
        & (plate_q20 <= factorized._fixed_limit(factorized.plate_max_v, 20))
    )
    in_range = externally_in_range & ~clipped_flags
    accuracy_grid_q24 = grid_q24[in_range]
    accuracy_plate_q20 = plate_q20[in_range]
    accuracy_approximate = approximate[in_range]
    if args.linear:
        # The latency candidate was selected from a much denser deterministic
        # probe than the RTL vector set. Reproduce that error evidence every
        # time its tables are generated rather than reporting a lucky 4k draw.
        accuracy_rng = np.random.default_rng(args.seed ^ 0x1A11E4)
        accuracy_grid_q24 = accuracy_rng.integers(
            factorized._fixed_limit(factorized.v_gk_min_v, 24),
            factorized._fixed_limit(factorized.v_gk_max_v, 24) + 1,
            100_000,
            dtype=np.int64,
        )
        accuracy_plate_q20 = accuracy_rng.integers(
            factorized._fixed_limit(factorized.plate_min_v, 20),
            factorized._fixed_limit(factorized.plate_max_v, 20) + 1,
            100_000,
            dtype=np.int64,
        )
        accuracy_values: list[float] = []
        retained_grid: list[int] = []
        retained_plate: list[int] = []
        for grid, plate in zip(
            accuracy_grid_q24, accuracy_plate_q20, strict=True
        ):
            plate_q31, _, clipped = factorized.evaluate_fixed(
                int(grid), int(plate)
            )
            if not clipped:
                retained_grid.append(int(grid))
                retained_plate.append(int(plate))
                accuracy_values.append(plate_q31 / (1 << 31))
        accuracy_grid_q24 = np.asarray(retained_grid, dtype=np.int64)
        accuracy_plate_q20 = np.asarray(retained_plate, dtype=np.int64)
        accuracy_approximate = np.asarray(accuracy_values)
    reference = Koren12AX7().plate_current(
        accuracy_grid_q24 / (1 << 24), accuracy_plate_q20 / (1 << 20)
    )
    error = accuracy_approximate - reference
    grid_probe_v = np.linspace(
        factorized.grid_v_gk_min_v,
        factorized.v_gk_max_v,
        200_001,
    )
    grid_coordinate_q16 = [
        factorized._coordinate(
            factorized._fixed_limit(float(value), 24),
            factorized._fixed_limit(factorized.grid_v_gk_min_v, 24),
            factorized._fixed_limit(factorized.v_gk_max_v, 24),
            factorized.grid_points,
        )
        for value in grid_probe_v
    ]
    fixed_grid_current = np.asarray(
        [
            factorized._linear(factorized.grid_value_q31, coordinate)
            / float(1 << 31)
            for coordinate in grid_coordinate_q16
        ]
    )
    grid_error = fixed_grid_current - Koren12AX7().grid_current(grid_probe_v)
    report = {
        "algorithm": (
            "three value-only 1-D LUTs with fixed linear interpolation"
            if args.linear
            else "three value/slope 1-D LUTs with fixed cubic Hermite interpolation"
        ),
        "seed": args.seed,
        "random_vectors": args.vectors,
        "directed_vectors": int(directed.shape[0]),
        "total_vectors": int(grid_q24.size),
        "accuracy_vectors_inside_all_factor_domains": int(error.size),
        "ranges": {
            "plate_law_v_gk_v": [
                factorized.v_gk_min_v,
                factorized.v_gk_max_v,
            ],
            "grid_current_lookup_v_gk_v": [
                factorized.grid_v_gk_min_v,
                factorized.v_gk_max_v,
            ],
            "v_pk_v": [factorized.plate_min_v, factorized.plate_max_v],
            "transformed": [
                factorized.transformed_min,
                factorized.transformed_max,
            ],
            "e1_v": [factorized.e1_min_v, factorized.e1_max_v],
        },
        "expected_clip_vectors": clip_count,
        "latency_clocks": 8,
        "raw_table_bits": factorized.raw_table_bits,
        "raw_ramb18_equivalents": factorized.raw_table_bits / 18_432.0,
        "grid_current_points": factorized.grid_points,
        "grid_current_storage_bits": factorized.grid_points * 32,
        "grid_current_maximum_absolute_error_a": float(
            np.max(np.abs(grid_error))
        ),
        "grid_current_active_region_rms_error_a": float(
            np.sqrt(np.mean(np.square(grid_error[grid_probe_v >= 0.0])))
        ),
        "mean_absolute_error_a": float(np.mean(np.abs(error))),
        "rms_error_a": float(np.sqrt(np.mean(np.square(error)))),
        "worst_absolute_error_a": float(np.max(np.abs(error))),
        "outputs": [
            *(str(path.relative_to(REPOSITORY_ROOT)) for path in memory_paths),
            str(vector_path.relative_to(REPOSITORY_ROOT)),
        ],
    }
    report_path = args.output / (
        "12ax7_factorized_linear_report.json"
        if args.linear
        else "12ax7_factorized_report.json"
    )
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
