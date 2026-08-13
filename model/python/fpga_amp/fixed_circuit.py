"""Bit-accurate candidate for the fixed-coefficient V1 chord solver."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .fixed import TubeLUT
from .v1_circuit import V1CircuitModel


IntArray = NDArray[np.int64]


class LUTTubeAdapter:
    """Expose the fixed LUT through the floating circuit's tube API for DC init."""

    def __init__(self, lut: TubeLUT):
        self.lut = lut

    def plate_current(self, v_gk: object, v_pk: object) -> NDArray[np.float64]:
        grid = np.asarray(v_gk, dtype=np.float64)
        plate = np.asarray(v_pk, dtype=np.float64)
        shape = np.broadcast_shapes(grid.shape, plate.shape)
        grid = np.broadcast_to(grid, shape)
        plate = np.broadcast_to(plate, shape)
        output = np.empty(shape, dtype=np.float64)
        for index in np.ndindex(shape):
            output[index] = self.lut.evaluate(float(grid[index]), float(plate[index]))[0]
        return output

    def grid_current(self, v_gk: object) -> NDArray[np.float64]:
        grid = np.asarray(v_gk, dtype=np.float64)
        output = np.empty_like(grid)
        for index in np.ndindex(grid.shape):
            output[index] = self.lut.evaluate(float(grid[index]), 100.0)[1]
        return output


def round_shift(value: int, shift: int) -> int:
    """Match add-half then arithmetic-shift rounding used by the RTL contract."""

    if shift < 0:
        return value << -shift
    if shift == 0:
        return value
    return (value + (1 << (shift - 1))) >> shift


def saturate_signed(value: int, width: int) -> tuple[int, bool]:
    low = -(1 << (width - 1))
    high = (1 << (width - 1)) - 1
    clipped = value < low or value > high
    return min(max(value, low), high), clipped


@dataclass
class FixedCapacitor:
    node_a: int | None
    node_b: int | None
    conductance_q47: int
    previous_voltage_q20: int


class FixedChordV1CircuitModel:
    """Three-pass fixed V1 candidate using the exact fixed tube LUT.

    All operations between state boundaries are Python integers. This defines a
    candidate RTL arithmetic sequence; it does not claim that the circuit RTL
    has been implemented yet.
    """

    VOLTAGE_FRACTIONAL_BITS = np.asarray(
        [24, 20, 24, 20, 24, 24, 20, 24, 20], dtype=np.int64
    )
    VOLTAGE_WIDTH = 32
    CONDUCTANCE_FRACTIONAL_BITS = 47
    RESIDUAL_FRACTIONAL_BITS = 44
    CAPACITOR_STATE_FRACTIONAL_BITS = 20

    def __init__(
        self,
        sample_rate_hz: float = 768_000.0,
        inverse_fractional_bits: int = 1,
        correction_residual_fractional_bits: int = 30,
        correction_residual_width: int = 25,
        tube_lut: TubeLUT | None = None,
    ):
        self.sample_rate_hz = float(sample_rate_hz)
        self.inverse_fractional_bits = int(inverse_fractional_bits)
        self.correction_residual_fractional_bits = int(
            correction_residual_fractional_bits
        )
        self.correction_residual_width = int(correction_residual_width)
        self.reference = V1CircuitModel(sample_rate_hz)
        self.node = self.reference.node
        self.node_count = self.reference.node_count
        self.tube_lut = tube_lut or TubeLUT()
        if self.tube_lut.plate_table is None or self.tube_lut.grid_table is None:
            self.tube_lut.generate()
        initial_reference = V1CircuitModel(
            sample_rate_hz,
            tube=LUTTubeAdapter(self.tube_lut),  # type: ignore[arg-type]
            dc_tolerance_a=1.1e-9,
        )

        dynamic_matrix, _ = self.reference._linear_system(0.0, dynamic=True)
        g_scale = 1 << self.CONDUCTANCE_FRACTIONAL_BITS
        self.matrix_q47 = np.rint(dynamic_matrix * g_scale).astype(np.int64)
        self.input_conductance_q47 = int(round(self.reference.input_conductance * g_scale))
        residual_scale = 1 << self.RESIDUAL_FRACTIONAL_BITS
        self.fixed_rhs_q44 = np.rint(
            self.reference.fixed_rhs * residual_scale
        ).astype(np.int64)
        inverse_scale = 1 << self.inverse_fractional_bits
        self.chord_inverse_q = np.rint(
            self.reference.chord_inverse * inverse_scale
        ).astype(np.int64)

        self.voltage_q = np.asarray(
            [
                int(round(initial_reference.voltage[index] * (1 << int(frac))))
                for index, frac in enumerate(self.VOLTAGE_FRACTIONAL_BITS)
            ],
            dtype=np.int64,
        )
        self.capacitors: list[FixedCapacitor] = []
        for branch in initial_reference.capacitors:
            conductance_q47 = int(
                round(
                    branch.capacitance_f
                    * self.sample_rate_hz
                    * (1 << self.CONDUCTANCE_FRACTIONAL_BITS)
                )
            )
            previous_q20 = int(
                round(
                    branch.previous_voltage_v
                    * (1 << self.CAPACITOR_STATE_FRACTIONAL_BITS)
                )
            )
            self.capacitors.append(
                FixedCapacitor(
                    branch.node_a,
                    branch.node_b,
                    conductance_q47,
                    previous_q20,
                )
            )
        self.nonconvergence_count = 0
        self.saturation_count = 0
        self.lut_clip_count = 0
        self.max_iterations_observed = 0
        self.last_residual_q44 = 0
        self.max_residual_q44_observed = 0

    @staticmethod
    def _convert_fraction(value: int, source_fraction: int, target_fraction: int) -> int:
        return round_shift(value, source_fraction - target_fraction)

    def _linear_product_current_q44(
        self, coefficient_q47: int, voltage_q: int, voltage_fraction: int
    ) -> int:
        return round_shift(
            coefficient_q47 * voltage_q,
            self.CONDUCTANCE_FRACTIONAL_BITS
            + voltage_fraction
            - self.RESIDUAL_FRACTIONAL_BITS,
        )

    def _rhs_q44(self, input_q24: int) -> list[int]:
        rhs = [int(value) for value in self.fixed_rhs_q44]
        rhs[self.node["g1"]] += self._linear_product_current_q44(
            self.input_conductance_q47, input_q24, 24
        )
        for capacitor in self.capacitors:
            history_current = self._linear_product_current_q44(
                capacitor.conductance_q47,
                capacitor.previous_voltage_q20,
                self.CAPACITOR_STATE_FRACTIONAL_BITS,
            )
            if capacitor.node_a is not None:
                rhs[capacitor.node_a] += history_current
            if capacitor.node_b is not None:
                rhs[capacitor.node_b] -= history_current
        return rhs

    def _tube_current_q44(self, voltage_q: IntArray) -> tuple[list[int], bool]:
        current = [0] * self.node_count
        clipped_any = False
        for grid_name, plate_name, cathode_name in (
            ("g1", "p1", "k1"),
            ("g2", "p2", "k2"),
        ):
            grid = self.node[grid_name]
            plate = self.node[plate_name]
            cathode = self.node[cathode_name]
            vgk_q24 = int(voltage_q[grid]) - self._convert_fraction(
                int(voltage_q[cathode]),
                int(self.VOLTAGE_FRACTIONAL_BITS[cathode]),
                24,
            )
            vpk_q20 = int(voltage_q[plate]) - self._convert_fraction(
                int(voltage_q[cathode]),
                int(self.VOLTAGE_FRACTIONAL_BITS[cathode]),
                20,
            )
            plate_q31, grid_q31, clipped = self.tube_lut.evaluate_fixed(vgk_q24, vpk_q20)
            clipped_any = clipped_any or clipped
            plate_q44 = plate_q31 << 13
            grid_q44 = grid_q31 << 13
            current[plate] += plate_q44
            current[cathode] -= plate_q44 + grid_q44
            current[grid] += grid_q44
        return current, clipped_any

    def _residual_q44(self, voltage_q: IntArray, rhs_q44: list[int]) -> list[int]:
        residual = [-value for value in rhs_q44]
        for row in range(self.node_count):
            for column in range(self.node_count):
                residual[row] += self._linear_product_current_q44(
                    int(self.matrix_q47[row, column]),
                    int(voltage_q[column]),
                    int(self.VOLTAGE_FRACTIONAL_BITS[column]),
                )
        tube_current, clipped = self._tube_current_q44(voltage_q)
        if clipped:
            self.lut_clip_count += 1
        return [linear + nonlinear for linear, nonlinear in zip(residual, tube_current)]

    def _apply_correction(self, residual_q44: list[int]) -> None:
        next_voltage = self.voltage_q.copy()
        product_fraction = (
            self.inverse_fractional_bits
            + self.correction_residual_fractional_bits
        )
        correction_residual: list[int] = []
        for value in residual_q44:
            converted = round_shift(
                value,
                self.RESIDUAL_FRACTIONAL_BITS
                - self.correction_residual_fractional_bits,
            )
            converted, clipped = saturate_signed(
                converted, self.correction_residual_width
            )
            correction_residual.append(converted)
            self.saturation_count += int(clipped)
        for row in range(self.node_count):
            accumulator = 0
            for column in range(self.node_count):
                accumulator += (
                    int(self.chord_inverse_q[row, column])
                    * correction_residual[column]
                )
            correction_q = round_shift(
                accumulator,
                product_fraction - int(self.VOLTAGE_FRACTIONAL_BITS[row]),
            )
            updated, clipped = saturate_signed(
                int(self.voltage_q[row]) - correction_q, self.VOLTAGE_WIDTH
            )
            next_voltage[row] = updated
            self.saturation_count += int(clipped)
        self.voltage_q = next_voltage

    def _update_capacitors(self) -> None:
        for capacitor in self.capacitors:
            voltage_a = 0
            voltage_b = 0
            if capacitor.node_a is not None:
                voltage_a = self._convert_fraction(
                    int(self.voltage_q[capacitor.node_a]),
                    int(self.VOLTAGE_FRACTIONAL_BITS[capacitor.node_a]),
                    self.CAPACITOR_STATE_FRACTIONAL_BITS,
                )
            if capacitor.node_b is not None:
                voltage_b = self._convert_fraction(
                    int(self.voltage_q[capacitor.node_b]),
                    int(self.VOLTAGE_FRACTIONAL_BITS[capacitor.node_b]),
                    self.CAPACITOR_STATE_FRACTIONAL_BITS,
                )
            capacitor.previous_voltage_q20 = voltage_a - voltage_b

    def process_sample(
        self,
        input_v: float,
        max_iterations: int = 3,
        residual_limit_a: float = 2.0e-6,
    ) -> float:
        input_q24, input_clipped = saturate_signed(int(round(input_v * (1 << 24))), 32)
        self.saturation_count += int(input_clipped)
        rhs = self._rhs_q44(input_q24)
        tolerance_q44 = max(1, int(round(residual_limit_a * (1 << 44))))
        for iteration in range(1, max_iterations + 1):
            residual = self._residual_q44(self.voltage_q, rhs)
            self._apply_correction(residual)
        residual = self._residual_q44(self.voltage_q, rhs)
        self.last_residual_q44 = max(abs(value) for value in residual)
        self.max_residual_q44_observed = max(
            self.max_residual_q44_observed, self.last_residual_q44
        )
        if self.last_residual_q44 > tolerance_q44:
            self.nonconvergence_count += 1
        self.max_iterations_observed = max(self.max_iterations_observed, iteration)
        self._update_capacitors()
        out = self.node["out"]
        return float(self.voltage_q[out]) / (1 << int(self.VOLTAGE_FRACTIONAL_BITS[out]))

    def process(self, samples: NDArray[np.float64], **kwargs: float | int) -> NDArray[np.float64]:
        values = np.asarray(samples, dtype=np.float64)
        output = np.empty_like(values)
        for index, sample in np.ndenumerate(values):
            output[index] = self.process_sample(float(sample), **kwargs)
        return output

    @property
    def nodes(self) -> dict[str, float]:
        return {
            name: float(self.voltage_q[index])
            / (1 << int(self.VOLTAGE_FRACTIONAL_BITS[index]))
            for name, index in self.node.items()
        }
