"""Bit-accurate fixed-point 12AX7 LUT approximation used by RTL."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .tube import Koren12AX7


def _round_shift_nonnegative(value: int, shift: int) -> int:
    return (value + (1 << (shift - 1))) >> shift


def _quantize(values: ArrayLike, fractional_bits: int) -> NDArray[np.int64]:
    return np.rint(np.asarray(values, dtype=np.float64) * (1 << fractional_bits)).astype(
        np.int64
    )


@dataclass
class TubeLUT:
    """Uniform 2-D plate-current and 1-D grid-current tables.

    The mapping and interpolation operations deliberately use the same integer
    rounding sequence as `rtl/tube/triode_12ax7.sv`.
    """

    grid_points: int = 128
    plate_points: int = 256
    v_gk_min_v: float = -5.0
    v_gk_max_v: float = 1.0
    v_pk_min_v: float = 0.0
    v_pk_max_v: float = 400.0
    v_gk_fractional_bits: int = 24
    v_pk_fractional_bits: int = 20
    current_fractional_bits: int = 31
    coordinate_fractional_bits: int = 16
    scale_fractional_bits: int = 24
    plate_table: NDArray[np.int64] | None = None
    grid_table: NDArray[np.int64] | None = None

    def generate(self, tube: Koren12AX7 | None = None) -> None:
        tube = tube or Koren12AX7()
        grid_axis = np.linspace(self.v_gk_min_v, self.v_gk_max_v, self.grid_points)
        plate_axis = np.linspace(self.v_pk_min_v, self.v_pk_max_v, self.plate_points)
        vpk, vgk = np.meshgrid(plate_axis, grid_axis, indexing="ij")
        max_q = (1 << 31) - 1
        plate_q = _quantize(tube.plate_current(vgk, vpk), self.current_fractional_bits)
        grid_q = _quantize(tube.grid_current(grid_axis), self.current_fractional_bits)
        self.plate_table = np.clip(plate_q, 0, max_q)
        self.grid_table = np.clip(grid_q, -(1 << 31), max_q)

    @property
    def vg_min_q(self) -> int:
        return int(round(self.v_gk_min_v * (1 << self.v_gk_fractional_bits)))

    @property
    def vg_max_q(self) -> int:
        return int(round(self.v_gk_max_v * (1 << self.v_gk_fractional_bits)))

    @property
    def vp_min_q(self) -> int:
        return int(round(self.v_pk_min_v * (1 << self.v_pk_fractional_bits)))

    @property
    def vp_max_q(self) -> int:
        return int(round(self.v_pk_max_v * (1 << self.v_pk_fractional_bits)))

    @property
    def vg_scale_q(self) -> int:
        span_q = self.vg_max_q - self.vg_min_q
        numerator = (
            (self.grid_points - 1)
            << (self.coordinate_fractional_bits + self.scale_fractional_bits)
        )
        return int(round(numerator / span_q))

    @property
    def vp_scale_q(self) -> int:
        span_q = self.vp_max_q - self.vp_min_q
        numerator = (
            (self.plate_points - 1)
            << (self.coordinate_fractional_bits + self.scale_fractional_bits)
        )
        return int(round(numerator / span_q))

    def _coordinate(self, value_q: int, low_q: int, high_q: int, scale_q: int, points: int) -> int:
        clamped = min(max(value_q, low_q), high_q)
        coordinate = _round_shift_nonnegative(
            (clamped - low_q) * scale_q, self.scale_fractional_bits
        )
        return min(coordinate, (points - 1) << self.coordinate_fractional_bits)

    def _split_coordinate(self, coordinate: int, points: int) -> tuple[int, int]:
        index = coordinate >> self.coordinate_fractional_bits
        fraction = coordinate & ((1 << self.coordinate_fractional_bits) - 1)
        if index >= points - 1:
            return points - 2, (1 << self.coordinate_fractional_bits) - 1
        return index, fraction

    def evaluate_fixed(self, v_gk_q: int, v_pk_q: int) -> tuple[int, int, bool]:
        if self.plate_table is None or self.grid_table is None:
            raise RuntimeError("generate the tables before evaluating")
        clipped = not (
            self.vg_min_q <= v_gk_q <= self.vg_max_q
            and self.vp_min_q <= v_pk_q <= self.vp_max_q
        )
        vg_coord = self._coordinate(
            v_gk_q, self.vg_min_q, self.vg_max_q, self.vg_scale_q, self.grid_points
        )
        vp_coord = self._coordinate(
            v_pk_q, self.vp_min_q, self.vp_max_q, self.vp_scale_q, self.plate_points
        )
        gi, gf = self._split_coordinate(vg_coord, self.grid_points)
        pi, pf = self._split_coordinate(vp_coord, self.plate_points)
        one = 1 << self.coordinate_fractional_bits

        def lerp(a: int, b: int, fraction: int) -> int:
            return _round_shift_nonnegative(
                a * (one - fraction) + b * fraction,
                self.coordinate_fractional_bits,
            )

        x0 = lerp(int(self.plate_table[pi, gi]), int(self.plate_table[pi, gi + 1]), gf)
        x1 = lerp(
            int(self.plate_table[pi + 1, gi]),
            int(self.plate_table[pi + 1, gi + 1]),
            gf,
        )
        plate_q = lerp(x0, x1, pf)
        grid_q = lerp(int(self.grid_table[gi]), int(self.grid_table[gi + 1]), gf)
        return plate_q, grid_q, clipped

    def evaluate(self, v_gk: float, v_pk: float) -> tuple[float, float, bool]:
        vg_q = int(round(v_gk * (1 << self.v_gk_fractional_bits)))
        vp_q = int(round(v_pk * (1 << self.v_pk_fractional_bits)))
        plate_q, grid_q, clipped = self.evaluate_fixed(vg_q, vp_q)
        scale = float(1 << self.current_fractional_bits)
        return plate_q / scale, grid_q / scale, clipped

    def write_memories(self, directory: Path) -> tuple[Path, Path]:
        if self.plate_table is None or self.grid_table is None:
            raise RuntimeError("generate the tables before writing")
        directory.mkdir(parents=True, exist_ok=True)
        plate_path = directory / "12ax7_plate_128x256_q31.mem"
        grid_path = directory / "12ax7_grid_128_q31.mem"
        with plate_path.open("w", encoding="ascii") as handle:
            for value in self.plate_table.flat:
                handle.write(f"{int(value) & 0xFFFFFFFF:08x}\n")
        with grid_path.open("w", encoding="ascii") as handle:
            for value in self.grid_table:
                handle.write(f"{int(value) & 0xFFFFFFFF:08x}\n")
        return plate_path, grid_path

