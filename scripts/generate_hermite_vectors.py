#!/usr/bin/env python3
"""Generate deterministic bit-exact vectors for the Q0.16 Hermite kernel."""

from __future__ import annotations

import argparse
from pathlib import Path
import random
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "model" / "python"))

from fpga_amp.factorized_tube import hermite_q16_fixed  # noqa: E402


BOUNDARY_VECTORS = (
    (0, 0, 0, 0, 0),
    (0, 0, 0, 0, 0xFFFF),
    (1, 2, 0, 0, 0),
    (1, 2, 0, 0, 0x8000),
    (1, 2, 0, 0, 0xFFFF),
    (-1, -2, 0, 0, 0x8000),
    (0x7FFFFFFF, -0x80000000, 0x7FFFFFFF, -0x80000000, 0),
    (0x7FFFFFFF, -0x80000000, 0x7FFFFFFF, -0x80000000, 1),
    (0x7FFFFFFF, -0x80000000, 0x7FFFFFFF, -0x80000000, 0x7FFF),
    (0x7FFFFFFF, -0x80000000, 0x7FFFFFFF, -0x80000000, 0xFFFF),
    (-0x80000000, 0x7FFFFFFF, -0x80000000, 0x7FFFFFFF, 0xFFFF),
    (123456789, -987654321, 314159265, -271828182, 0x1234),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=0x12A7C0DE)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("sim/vectors/generated/hermite_q16_random.txt"),
    )
    args = parser.parse_args()
    if args.vectors < len(BOUNDARY_VECTORS):
        parser.error(f"--vectors must be at least {len(BOUNDARY_VECTORS)}")

    rng = random.Random(args.seed)
    vectors = list(BOUNDARY_VECTORS)
    while len(vectors) < args.vectors:
        vectors.append(
            (
                rng.randint(-(1 << 31), (1 << 31) - 1),
                rng.randint(-(1 << 31), (1 << 31) - 1),
                rng.randint(-(1 << 31), (1 << 31) - 1),
                rng.randint(-(1 << 31), (1 << 31) - 1),
                rng.randint(0, 0xFFFF),
            )
        )

    output = args.output if args.output.is_absolute() else REPOSITORY_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="ascii") as handle:
        handle.write("# y0 y1 m0 m1 fraction result\n")
        for y0, y1, m0, m1, fraction in vectors:
            result = hermite_q16_fixed(y0, y1, m0, m1, fraction)
            handle.write(f"{y0} {y1} {m0} {m1} {fraction} {result}\n")
    print(f"wrote {len(vectors)} deterministic vectors to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
