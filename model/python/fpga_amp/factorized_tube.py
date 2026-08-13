"""Factorized 1-D LUT approximation of the Koren triode equation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from .tube import Koren12AX7


FloatArray = NDArray[np.float64]


def _round_shift(value: int, shift: int) -> int:
    """Round an integer product with the same add-half rule used by RTL."""

    if shift < 0:
        return value << -shift
    if shift == 0:
        return value
    return (value + (1 << (shift - 1))) >> shift


@dataclass
class FactorizedKoren12AX7:
    """Evaluate the Koren plate law through three linearly interpolated tables.

    This keeps the physical Koren factorization visible instead of sampling the
    final two-dimensional current surface. It is a floating architecture study,
    not yet the fixed/RTL numerical contract.
    """

    reciprocal_points: int = 512
    softplus_points: int = 1024
    power_points: int = 2048
    plate_min_v: float = 0.0
    plate_max_v: float = 400.0
    transformed_min: float = -0.30
    transformed_max: float = 0.08
    e1_min_v: float = 0.0
    e1_max_v: float = 6.0
    interpolation: str = "linear"
    tube: Koren12AX7 = Koren12AX7()

    def __post_init__(self) -> None:
        self.plate_axis = np.linspace(
            self.plate_min_v, self.plate_max_v, self.reciprocal_points
        )
        self.reciprocal_table = 1.0 / np.sqrt(
            self.tube.kvb + np.square(self.plate_axis)
        )
        self.reciprocal_derivative = -self.plate_axis * np.power(
            self.tube.kvb + np.square(self.plate_axis), -1.5
        )
        self.transformed_axis = np.linspace(
            self.transformed_min, self.transformed_max, self.softplus_points
        )
        argument = self.tube.kp * self.transformed_axis
        softplus = np.maximum(argument, 0.0) + np.log1p(np.exp(-np.abs(argument)))
        self.softplus_table = softplus / self.tube.kp
        positive = argument >= 0.0
        self.softplus_derivative = np.empty_like(argument)
        self.softplus_derivative[positive] = 1.0 / (
            1.0 + np.exp(-argument[positive])
        )
        exp_argument = np.exp(argument[~positive])
        self.softplus_derivative[~positive] = exp_argument / (1.0 + exp_argument)
        self.e1_axis = np.linspace(self.e1_min_v, self.e1_max_v, self.power_points)
        self.power_table = (
            2.0 * np.power(self.e1_axis, self.tube.ex) / self.tube.kg1
        )
        self.power_derivative = (
            2.0
            * self.tube.ex
            * np.power(self.e1_axis, self.tube.ex - 1.0)
            / self.tube.kg1
        )
        if self.interpolation not in ("linear", "hermite"):
            raise ValueError(f"unsupported interpolation: {self.interpolation}")

    @property
    def raw_table_bits_q31(self) -> int:
        table_count = 2 if self.interpolation == "hermite" else 1
        return 32 * table_count * (
            self.reciprocal_points + self.softplus_points + self.power_points
        )

    def _lookup(
        self,
        values: FloatArray,
        axis: FloatArray,
        table: FloatArray,
        derivative: FloatArray,
    ) -> FloatArray:
        if self.interpolation == "linear":
            return np.interp(values, axis, table)
        spacing = float(axis[1] - axis[0])
        coordinate = (np.clip(values, axis[0], axis[-1]) - axis[0]) / spacing
        lower = np.floor(coordinate).astype(np.int64)
        lower = np.minimum(lower, axis.size - 2)
        fraction = coordinate - lower
        fraction_2 = np.square(fraction)
        fraction_3 = fraction_2 * fraction
        h00 = 2.0 * fraction_3 - 3.0 * fraction_2 + 1.0
        h10 = fraction_3 - 2.0 * fraction_2 + fraction
        h01 = -2.0 * fraction_3 + 3.0 * fraction_2
        h11 = fraction_3 - fraction_2
        return (
            h00 * table[lower]
            + h10 * spacing * derivative[lower]
            + h01 * table[lower + 1]
            + h11 * spacing * derivative[lower + 1]
        )

    def plate_current(self, v_gk: ArrayLike, v_pk: ArrayLike) -> FloatArray:
        grid = np.asarray(v_gk, dtype=np.float64)
        plate = np.maximum(np.asarray(v_pk, dtype=np.float64), 0.0)
        reciprocal = self._lookup(
            plate,
            self.plate_axis,
            self.reciprocal_table,
            self.reciprocal_derivative,
        )
        transformed = 1.0 / self.tube.mu + grid * reciprocal
        softplus = self._lookup(
            transformed,
            self.transformed_axis,
            self.softplus_table,
            self.softplus_derivative,
        )
        e1 = plate * softplus
        current = self._lookup(
            e1, self.e1_axis, self.power_table, self.power_derivative
        )
        return np.where(plate > 0.0, current, 0.0)

    def grid_current(self, v_gk: ArrayLike) -> FloatArray:
        # Grid current remains the existing independently verified 1-D branch.
        return self.tube.grid_current(v_gk)


@dataclass
class FixedFactorizedKoren12AX7:
    """Bit-accurate fixed-point contract for the factorized Koren plate law.

    Each nonlinear function is represented by value and derivative-times-step
    tables. Cubic Hermite interpolation uses a Q0.16 coordinate and a Horner
    sequence, which maps directly to three multiply/round operations per table.
    The external voltage/current formats remain identical to ``TubeLUT`` so the
    circuit solver can compare the implementations without any other changes.
    """

    reciprocal_points: int = 512
    softplus_points: int = 1024
    power_points: int = 2048
    grid_points: int = 128
    plate_min_v: float = 0.0
    plate_max_v: float = 400.0
    transformed_min: float = -0.30
    transformed_max: float = 0.08
    e1_min_v: float = 0.0
    e1_max_v: float = 6.0
    v_gk_min_v: float = -5.0
    v_gk_max_v: float = 1.0
    v_gk_fractional_bits: int = 24
    v_pk_fractional_bits: int = 20
    current_fractional_bits: int = 31
    coordinate_fractional_bits: int = 16
    scale_fractional_bits: int = 24
    reciprocal_fractional_bits: int = 32
    transformed_fractional_bits: int = 30
    softplus_fractional_bits: int = 32
    e1_fractional_bits: int = 20
    tube: Koren12AX7 = Koren12AX7()

    def __post_init__(self) -> None:
        floating = FactorizedKoren12AX7(
            reciprocal_points=self.reciprocal_points,
            softplus_points=self.softplus_points,
            power_points=self.power_points,
            plate_min_v=self.plate_min_v,
            plate_max_v=self.plate_max_v,
            transformed_min=self.transformed_min,
            transformed_max=self.transformed_max,
            e1_min_v=self.e1_min_v,
            e1_max_v=self.e1_max_v,
            interpolation="hermite",
            tube=self.tube,
        )
        reciprocal_step = float(floating.plate_axis[1] - floating.plate_axis[0])
        softplus_step = float(
            floating.transformed_axis[1] - floating.transformed_axis[0]
        )
        power_step = float(floating.e1_axis[1] - floating.e1_axis[0])
        self.reciprocal_value_q32 = self._quantize(
            floating.reciprocal_table, self.reciprocal_fractional_bits
        )
        self.reciprocal_slope_q32 = self._quantize(
            floating.reciprocal_derivative * reciprocal_step,
            self.reciprocal_fractional_bits,
        )
        self.softplus_value_q32 = self._quantize(
            floating.softplus_table, self.softplus_fractional_bits
        )
        self.softplus_slope_q32 = self._quantize(
            floating.softplus_derivative * softplus_step,
            self.softplus_fractional_bits,
        )
        self.power_value_q31 = self._quantize(
            floating.power_table, self.current_fractional_bits
        )
        self.power_slope_q31 = self._quantize(
            floating.power_derivative * power_step,
            self.current_fractional_bits,
        )
        grid_axis = np.linspace(self.v_gk_min_v, self.v_gk_max_v, self.grid_points)
        self.grid_value_q31 = self._quantize(
            self.tube.grid_current(grid_axis), self.current_fractional_bits
        )

    @staticmethod
    def _quantize(values: ArrayLike, fractional_bits: int) -> NDArray[np.int64]:
        scaled = np.rint(
            np.asarray(values, dtype=np.float64) * (1 << fractional_bits)
        )
        return scaled.astype(np.int64)

    @property
    def raw_table_bits(self) -> int:
        return 32 * (
            2 * (self.reciprocal_points + self.softplus_points + self.power_points)
            + self.grid_points
        )

    @staticmethod
    def _fixed_limit(value: float, fractional_bits: int) -> int:
        return int(round(value * (1 << fractional_bits)))

    def _coordinate(
        self,
        value_q: int,
        low_q: int,
        high_q: int,
        points: int,
    ) -> int:
        clamped = min(max(value_q, low_q), high_q)
        numerator = (
            (points - 1)
            << (self.coordinate_fractional_bits + self.scale_fractional_bits)
        )
        scale_q = int(round(numerator / (high_q - low_q)))
        coordinate = _round_shift(
            (clamped - low_q) * scale_q, self.scale_fractional_bits
        )
        return min(coordinate, (points - 1) << self.coordinate_fractional_bits)

    def _split_coordinate(self, coordinate: int, points: int) -> tuple[int, int]:
        index = coordinate >> self.coordinate_fractional_bits
        fraction = coordinate & ((1 << self.coordinate_fractional_bits) - 1)
        if index >= points - 1:
            return points - 2, (1 << self.coordinate_fractional_bits) - 1
        return index, fraction

    def _hermite(
        self,
        value: NDArray[np.int64],
        slope: NDArray[np.int64],
        coordinate: int,
    ) -> int:
        index, fraction = self._split_coordinate(coordinate, int(value.size))
        y0 = int(value[index])
        y1 = int(value[index + 1])
        m0 = int(slope[index])
        m1 = int(slope[index + 1])
        delta = y1 - y0
        coefficient_2 = 3 * delta - 2 * m0 - m1
        coefficient_3 = -2 * delta + m0 + m1
        result = _round_shift(
            coefficient_3 * fraction, self.coordinate_fractional_bits
        ) + coefficient_2
        result = _round_shift(
            result * fraction, self.coordinate_fractional_bits
        ) + m0
        return _round_shift(
            result * fraction, self.coordinate_fractional_bits
        ) + y0

    def _linear(
        self, value: NDArray[np.int64], coordinate: int
    ) -> int:
        index, fraction = self._split_coordinate(coordinate, int(value.size))
        one = 1 << self.coordinate_fractional_bits
        return _round_shift(
            int(value[index]) * (one - fraction)
            + int(value[index + 1]) * fraction,
            self.coordinate_fractional_bits,
        )

    def evaluate_fixed(self, v_gk_q: int, v_pk_q: int) -> tuple[int, int, bool]:
        vg_low_q = self._fixed_limit(self.v_gk_min_v, self.v_gk_fractional_bits)
        vg_high_q = self._fixed_limit(self.v_gk_max_v, self.v_gk_fractional_bits)
        vp_low_q = self._fixed_limit(self.plate_min_v, self.v_pk_fractional_bits)
        vp_high_q = self._fixed_limit(self.plate_max_v, self.v_pk_fractional_bits)
        clipped = not (
            vg_low_q <= v_gk_q <= vg_high_q and vp_low_q <= v_pk_q <= vp_high_q
        )

        plate_coordinate = self._coordinate(
            v_pk_q, vp_low_q, vp_high_q, self.reciprocal_points
        )
        reciprocal_q32 = self._hermite(
            self.reciprocal_value_q32,
            self.reciprocal_slope_q32,
            plate_coordinate,
        )
        transformed_q30 = int(round((1.0 / self.tube.mu) * (1 << 30)))
        transformed_q30 += _round_shift(
            v_gk_q * reciprocal_q32,
            self.v_gk_fractional_bits
            + self.reciprocal_fractional_bits
            - self.transformed_fractional_bits,
        )
        transformed_low_q = self._fixed_limit(
            self.transformed_min, self.transformed_fractional_bits
        )
        transformed_high_q = self._fixed_limit(
            self.transformed_max, self.transformed_fractional_bits
        )
        clipped = clipped or not (
            transformed_low_q <= transformed_q30 <= transformed_high_q
        )
        softplus_coordinate = self._coordinate(
            transformed_q30,
            transformed_low_q,
            transformed_high_q,
            self.softplus_points,
        )
        softplus_q32 = self._hermite(
            self.softplus_value_q32,
            self.softplus_slope_q32,
            softplus_coordinate,
        )
        e1_q20 = _round_shift(
            max(v_pk_q, 0) * softplus_q32,
            self.v_pk_fractional_bits
            + self.softplus_fractional_bits
            - self.e1_fractional_bits,
        )
        e1_low_q = self._fixed_limit(self.e1_min_v, self.e1_fractional_bits)
        e1_high_q = self._fixed_limit(self.e1_max_v, self.e1_fractional_bits)
        clipped = clipped or not (e1_low_q <= e1_q20 <= e1_high_q)
        power_coordinate = self._coordinate(
            e1_q20, e1_low_q, e1_high_q, self.power_points
        )
        plate_q31 = self._hermite(
            self.power_value_q31, self.power_slope_q31, power_coordinate
        )
        if v_pk_q <= 0:
            plate_q31 = 0

        grid_coordinate = self._coordinate(
            v_gk_q, vg_low_q, vg_high_q, self.grid_points
        )
        grid_q31 = self._linear(self.grid_value_q31, grid_coordinate)
        current_min = -(1 << 31)
        current_max = (1 << 31) - 1
        plate_q31 = min(max(plate_q31, 0), current_max)
        grid_q31 = min(max(grid_q31, current_min), current_max)
        return plate_q31, grid_q31, clipped

    def evaluate(self, v_gk: float, v_pk: float) -> tuple[float, float, bool]:
        v_gk_q = int(round(v_gk * (1 << self.v_gk_fractional_bits)))
        v_pk_q = int(round(v_pk * (1 << self.v_pk_fractional_bits)))
        plate_q31, grid_q31, clipped = self.evaluate_fixed(v_gk_q, v_pk_q)
        scale = float(1 << self.current_fractional_bits)
        return plate_q31 / scale, grid_q31 / scale, clipped
