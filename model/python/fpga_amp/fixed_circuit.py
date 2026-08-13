"""Bit-accurate candidate for the fixed-coefficient V1 chord solver."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from .fixed import TubeLUT
from .v1_circuit import V1CircuitModel


IntArray = NDArray[np.int64]


class FixedTubeApproximation(Protocol):
    """Numerical interface shared by the 2-D and factorized tube models."""

    def evaluate_fixed(self, v_gk_q: int, v_pk_q: int) -> tuple[int, int, bool]: ...

    def evaluate(self, v_gk: float, v_pk: float) -> tuple[float, float, bool]: ...


class LUTTubeAdapter:
    """Expose the fixed LUT through the floating circuit's tube API for DC init."""

    def __init__(self, lut: FixedTubeApproximation):
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
    previous_current_q44: int = 0


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
    CAPACITOR_CURRENT_WIDTH = 48

    def __init__(
        self,
        sample_rate_hz: float = 768_000.0,
        inverse_fractional_bits: int = 1,
        correction_residual_fractional_bits: int | Sequence[int] = 30,
        correction_residual_width: int = 25,
        tube_lut: FixedTubeApproximation | None = None,
        voltage_fractional_bits: Sequence[int] | None = None,
        output_fractional_bits: int | None = None,
        voltage_width: int | None = None,
        capacitor_state_fractional_bits: int | None = None,
        branch_capacitor_stamp: bool = False,
        adaptive_correction_scaling: bool = False,
        integration_method: str = "backward_euler",
        terminal_correction: bool = False,
    ):
        self.sample_rate_hz = float(sample_rate_hz)
        self.integration_method = integration_method
        self.VOLTAGE_FRACTIONAL_BITS = self.VOLTAGE_FRACTIONAL_BITS.copy()
        if voltage_fractional_bits is not None:
            if len(voltage_fractional_bits) != len(self.VOLTAGE_FRACTIONAL_BITS):
                raise ValueError("one voltage format is required for each node")
            self.VOLTAGE_FRACTIONAL_BITS = np.asarray(
                voltage_fractional_bits, dtype=np.int64
            )
        if output_fractional_bits is not None:
            self.VOLTAGE_FRACTIONAL_BITS[-1] = int(output_fractional_bits)
        if voltage_width is not None:
            self.VOLTAGE_WIDTH = int(voltage_width)
        if capacitor_state_fractional_bits is not None:
            self.CAPACITOR_STATE_FRACTIONAL_BITS = int(
                capacitor_state_fractional_bits
            )
        self.branch_capacitor_stamp = bool(branch_capacitor_stamp)
        if integration_method == "trapezoidal" and not self.branch_capacitor_stamp:
            raise ValueError(
                "fixed trapezoidal integration requires explicit capacitor branches"
            )
        self.adaptive_correction_scaling = bool(adaptive_correction_scaling)
        self.terminal_correction = bool(terminal_correction)
        self.inverse_fractional_bits = int(inverse_fractional_bits)
        if isinstance(correction_residual_fractional_bits, Sequence):
            self.correction_residual_fractional_bits = tuple(
                int(value) for value in correction_residual_fractional_bits
            )
            if not self.correction_residual_fractional_bits:
                raise ValueError("correction residual schedule must not be empty")
        else:
            self.correction_residual_fractional_bits = (
                int(correction_residual_fractional_bits),
            )
        self.correction_residual_width = int(correction_residual_width)
        self.reference = V1CircuitModel(
            sample_rate_hz, integration_method=integration_method
        )
        self.node = self.reference.node
        self.node_count = self.reference.node_count
        if tube_lut is None:
            default_lut = TubeLUT()
            default_lut.generate()
            self.tube_lut: FixedTubeApproximation = default_lut
        else:
            self.tube_lut = tube_lut
        initial_reference = V1CircuitModel(
            sample_rate_hz,
            tube=LUTTubeAdapter(self.tube_lut),  # type: ignore[arg-type]
            dc_tolerance_a=1.1e-9,
            integration_method=integration_method,
        )

        dynamic_matrix, _ = self.reference._linear_system(0.0, dynamic=True)
        network_matrix = (
            self.reference.conductance
            if self.branch_capacitor_stamp
            else dynamic_matrix
        )
        g_scale = 1 << self.CONDUCTANCE_FRACTIONAL_BITS
        self.matrix_q47 = np.rint(network_matrix * g_scale).astype(np.int64)
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
                    * (2.0 if integration_method == "trapezoidal" else 1.0)
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
        self.max_abs_capacitor_current_q44 = [0] * len(self.capacitors)
        self.saturation_count = 0
        if self.branch_capacitor_stamp:
            # Make every companion branch initially quiescent in the candidate
            # fixed domain.  This avoids importing float-state subtraction error.
            self._update_capacitors()
            for capacitor in self.capacitors:
                capacitor.previous_current_q44 = 0
        self.nonconvergence_count = 0
        self.lut_clip_count = 0
        self.max_iterations_observed = 0
        self.last_residual_q44 = 0
        self.max_residual_q44_observed = 0
        self.correction_scale_fallback_count = 0
        self.minimum_correction_residual_fractional_bits: int | None = None

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
        if not self.branch_capacitor_stamp:
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
            vgk_q24 = self._convert_fraction(
                int(voltage_q[grid]),
                int(self.VOLTAGE_FRACTIONAL_BITS[grid]),
                24,
            ) - self._convert_fraction(
                int(voltage_q[cathode]),
                int(self.VOLTAGE_FRACTIONAL_BITS[cathode]),
                24,
            )
            vpk_q20 = self._convert_fraction(
                int(voltage_q[plate]),
                int(self.VOLTAGE_FRACTIONAL_BITS[plate]),
                20,
            ) - self._convert_fraction(
                int(voltage_q[cathode]),
                int(self.VOLTAGE_FRACTIONAL_BITS[cathode]),
                20,
            )
            vgk_q24, vgk_saturated = saturate_signed(vgk_q24, 32)
            vpk_q20, vpk_saturated = saturate_signed(vpk_q20, 32)
            plate_q31, grid_q31, clipped = self.tube_lut.evaluate_fixed(vgk_q24, vpk_q20)
            clipped_any = (
                clipped_any or vgk_saturated or vpk_saturated or clipped
            )
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
        if self.branch_capacitor_stamp:
            for capacitor in self.capacitors:
                voltage_a = 0
                voltage_b = 0
                if capacitor.node_a is not None:
                    voltage_a = self._convert_fraction(
                        int(voltage_q[capacitor.node_a]),
                        int(self.VOLTAGE_FRACTIONAL_BITS[capacitor.node_a]),
                        self.CAPACITOR_STATE_FRACTIONAL_BITS,
                    )
                if capacitor.node_b is not None:
                    voltage_b = self._convert_fraction(
                        int(voltage_q[capacitor.node_b]),
                        int(self.VOLTAGE_FRACTIONAL_BITS[capacitor.node_b]),
                        self.CAPACITOR_STATE_FRACTIONAL_BITS,
                    )
                delta_voltage = (
                    voltage_a
                    - voltage_b
                    - capacitor.previous_voltage_q20
                )
                branch_current = self._linear_product_current_q44(
                    capacitor.conductance_q47,
                    delta_voltage,
                    self.CAPACITOR_STATE_FRACTIONAL_BITS,
                )
                if self.integration_method == "trapezoidal":
                    branch_current -= capacitor.previous_current_q44
                if capacitor.node_a is not None:
                    residual[capacitor.node_a] += branch_current
                if capacitor.node_b is not None:
                    residual[capacitor.node_b] -= branch_current
        tube_current, clipped = self._tube_current_q44(voltage_q)
        if clipped:
            self.lut_clip_count += 1
        return [linear + nonlinear for linear, nonlinear in zip(residual, tube_current)]

    def _apply_correction(
        self, residual_q44: list[int], residual_fractional_bits: int
    ) -> None:
        next_voltage = self.voltage_q.copy()
        product_fraction = (
            self.inverse_fractional_bits
            + residual_fractional_bits
        )
        correction_residual: list[int] = []
        for value in residual_q44:
            converted = round_shift(
                value,
                self.RESIDUAL_FRACTIONAL_BITS
                - residual_fractional_bits,
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

    def _select_correction_fraction(
        self, residual_q44: list[int], requested_fractional_bits: int
    ) -> int:
        if not self.adaptive_correction_scaling:
            return requested_fractional_bits
        candidates = sorted(
            {
                value
                for value in self.correction_residual_fractional_bits
                if value <= requested_fractional_bits
            },
            reverse=True,
        )
        if not candidates:
            raise ValueError("correction schedule has no usable residual format")
        selected = candidates[-1]
        for candidate in candidates:
            selected = candidate
            shift = self.RESIDUAL_FRACTIONAL_BITS - selected
            if all(
                not saturate_signed(
                    round_shift(value, shift), self.correction_residual_width
                )[1]
                for value in residual_q44
            ):
                break
        if selected != requested_fractional_bits:
            self.correction_scale_fallback_count += 1
            if self.minimum_correction_residual_fractional_bits is None:
                self.minimum_correction_residual_fractional_bits = selected
            else:
                self.minimum_correction_residual_fractional_bits = min(
                    self.minimum_correction_residual_fractional_bits, selected
                )
        return selected

    def _update_capacitors(self) -> None:
        for capacitor_index, capacitor in enumerate(self.capacitors):
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
            updated, clipped = saturate_signed(
                voltage_a - voltage_b, self.VOLTAGE_WIDTH
            )
            if self.integration_method == "trapezoidal":
                branch_current = self._linear_product_current_q44(
                    capacitor.conductance_q47,
                    updated - capacitor.previous_voltage_q20,
                    self.CAPACITOR_STATE_FRACTIONAL_BITS,
                ) - capacitor.previous_current_q44
                branch_current, current_clipped = saturate_signed(
                    branch_current, self.CAPACITOR_CURRENT_WIDTH
                )
                capacitor.previous_current_q44 = branch_current
                self.max_abs_capacitor_current_q44[capacitor_index] = max(
                    self.max_abs_capacitor_current_q44[capacitor_index],
                    abs(branch_current),
                )
                self.saturation_count += int(current_clipped)
            capacitor.previous_voltage_q20 = updated
            self.saturation_count += int(clipped)

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
            residual_fractional_bits = self.correction_residual_fractional_bits[
                min(iteration - 1, len(self.correction_residual_fractional_bits) - 1)
            ]
            residual_fractional_bits = self._select_correction_fraction(
                residual, residual_fractional_bits
            )
            self._apply_correction(residual, residual_fractional_bits)
        residual = self._residual_q44(self.voltage_q, rhs)
        self.last_residual_q44 = max(abs(value) for value in residual)
        self.max_residual_q44_observed = max(
            self.max_residual_q44_observed, self.last_residual_q44
        )
        if self.last_residual_q44 > tolerance_q44:
            self.nonconvergence_count += 1
        self.max_iterations_observed = max(self.max_iterations_observed, iteration)
        # The RTL can reuse this already-computed diagnostic residual for one
        # terminal chord update.  Deliberately do not recompute the residual:
        # last_residual_q44 and nonconvergence_count describe the state before
        # the terminal update, while the output and capacitor histories commit
        # the corrected state.  A conventional N+1-pass solver produces the
        # same persistent state but serializes another nonlinear residual pass.
        if self.terminal_correction:
            residual_fractional_bits = self.correction_residual_fractional_bits[
                min(
                    max_iterations,
                    len(self.correction_residual_fractional_bits) - 1,
                )
            ]
            residual_fractional_bits = self._select_correction_fraction(
                residual, residual_fractional_bits
            )
            self._apply_correction(residual, residual_fractional_bits)
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


class FixedWideStateV1CircuitModel(FixedChordV1CircuitModel):
    """Measured 40-bit node/Q30-history candidate with branch capacitor KCL.

    This remains a Python architecture candidate, not the accepted RTL
    contract.  Wider internal nodes retain the historical circuit's measured
    large-signal range while resolving slow decay.
    """

    def __init__(self, *args: object, **kwargs: object):
        kwargs.setdefault(
            "voltage_fractional_bits", (32, 28, 32, 28, 32, 32, 28, 32, 32)
        )
        kwargs.setdefault("voltage_width", 40)
        kwargs.setdefault("capacitor_state_fractional_bits", 30)
        kwargs.setdefault("branch_capacitor_stamp", True)
        # The first correction retains the established 3.9 mA range.  Once it
        # removes the large transient, later passes trade range for the current
        # resolution needed by the 2.21 Mohm output node.
        kwargs.setdefault("correction_residual_fractional_bits", (30, 34, 40))
        kwargs.setdefault("adaptive_correction_scaling", True)
        super().__init__(*args, **kwargs)


class FixedWideStateBankedChordV1CircuitModel(FixedWideStateV1CircuitModel):
    """Wide candidate with physically derived second-stage cutoff Jacobians.

    The bank is selected once from the previous sample's stage-two Vgk and its
    sample-to-sample slew, then held for all three chord corrections. This keeps
    the real-time schedule fixed while replacing the DC Jacobian only in cutoff
    regions where its measured residual contraction fails.
    """

    # Selection upper bound, representative Vgk, representative Vpk, all volts.
    # Points follow the analytical 1 V trajectory through the second-stage
    # cutoff arc. Stage one remains at its nominal operating point.
    BACKWARD_EULER_CUTOFF_JACOBIAN_REGIMES = (
        (-3.25, -3.50, 284.0),
        (-2.75, -3.00, 270.0),
    )
    TRAPEZOIDAL_CUTOFF_JACOBIAN_REGIMES = (
        (-4.00, -4.25, 293.0),
        (-3.50, -3.75, 289.0),
        (-3.00, -3.25, 278.0),
        (-2.75, -2.75, 261.0),
    )
    BACKWARD_EULER_SLEW_JACOBIAN_REPRESENTATIVE = (-2.25, 261.0)
    SHALLOW_SLEW_UPPER_V_GK_V = -2.50
    SHALLOW_SLEW_THRESHOLD_V_PER_SAMPLE = 0.020

    def __init__(self, *args: object, **kwargs: object):
        super().__init__(*args, **kwargs)
        self.cutoff_jacobian_regimes = (
            self.TRAPEZOIDAL_CUTOFF_JACOBIAN_REGIMES
            if self.integration_method == "trapezoidal"
            else self.BACKWARD_EULER_CUTOFF_JACOBIAN_REGIMES
        )
        self.nominal_chord_inverse_q = self.chord_inverse_q.copy()
        self.chord_inverse_banks_q: list[NDArray[np.int64]] = []
        for _, v_gk_v, v_pk_v in self.cutoff_jacobian_regimes:
            self.chord_inverse_banks_q.append(
                self._chord_inverse_at(v_gk_v, v_pk_v)
            )
        if self.integration_method == "backward_euler":
            self.chord_inverse_banks_q.append(
                self._chord_inverse_at(
                    *self.BACKWARD_EULER_SLEW_JACOBIAN_REPRESENTATIVE
                )
            )
        self.chord_bank_selection_count = [0] * (
            len(self.chord_inverse_banks_q) + 1
        )
        self.slew_qualified_selection_count = 0
        self.previous_selector_v_gk2_q32 = self._previous_v_gk2_q32()

    def _chord_inverse_at(
        self, v_gk_v: float, v_pk_v: float
    ) -> NDArray[np.int64]:
        voltage = self.reference.voltage.copy()
        grid = self.node["g2"]
        plate = self.node["p2"]
        cathode = self.node["k2"]
        voltage[grid] = voltage[cathode] + v_gk_v
        voltage[plate] = voltage[cathode] + v_pk_v
        jacobian, _ = self.reference._linear_system(0.0, dynamic=True)
        residual = np.zeros(self.node_count, dtype=np.float64)
        self.reference._tube_stamp(
            residual, jacobian, voltage, "g1", "p1", "k1"
        )
        self.reference._tube_stamp(
            residual, jacobian, voltage, "g2", "p2", "k2"
        )
        inverse_scale = 1 << self.inverse_fractional_bits
        return np.rint(np.linalg.inv(jacobian) * inverse_scale).astype(np.int64)

    def _previous_v_gk2_q32(self) -> int:
        grid = self.node["g2"]
        cathode = self.node["k2"]
        grid_q32 = self._convert_fraction(
            int(self.voltage_q[grid]),
            int(self.VOLTAGE_FRACTIONAL_BITS[grid]),
            32,
        )
        cathode_q32 = self._convert_fraction(
            int(self.voltage_q[cathode]),
            int(self.VOLTAGE_FRACTIONAL_BITS[cathode]),
            32,
        )
        return grid_q32 - cathode_q32

    def _select_chord_bank(self) -> int:
        v_gk_q32 = self._previous_v_gk2_q32()
        slew_q32 = abs(v_gk_q32 - self.previous_selector_v_gk2_q32)
        self.previous_selector_v_gk2_q32 = v_gk_q32
        for bank_index, (upper_v, _, _) in enumerate(
            self.cutoff_jacobian_regimes
        ):
            if v_gk_q32 < int(round(upper_v * (1 << 32))):
                return bank_index
        if (
            v_gk_q32
            < int(round(self.SHALLOW_SLEW_UPPER_V_GK_V * (1 << 32)))
            and slew_q32
            > int(round(self.SHALLOW_SLEW_THRESHOLD_V_PER_SAMPLE * (1 << 32)))
        ):
            self.slew_qualified_selection_count += 1
            return len(self.chord_inverse_banks_q) - 1
        return len(self.chord_inverse_banks_q)

    def process_sample(
        self,
        input_v: float,
        max_iterations: int = 3,
        residual_limit_a: float = 2.0e-6,
    ) -> float:
        bank_index = self._select_chord_bank()
        self.chord_bank_selection_count[bank_index] += 1
        if bank_index < len(self.chord_inverse_banks_q):
            self.chord_inverse_q = self.chord_inverse_banks_q[bank_index]
        else:
            self.chord_inverse_q = self.nominal_chord_inverse_q
        return super().process_sample(
            input_v,
            max_iterations=max_iterations,
            residual_limit_a=residual_limit_a,
        )


class FixedWideStateTrapezoidalV1CircuitModel(FixedWideStateV1CircuitModel):
    """Wide factorized candidate with Q4.44 trapezoidal current history."""

    def __init__(self, *args: object, **kwargs: object):
        kwargs.setdefault("integration_method", "trapezoidal")
        super().__init__(*args, **kwargs)
