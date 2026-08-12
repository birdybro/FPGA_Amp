"""Sample-by-sample nonlinear nodal model of the frozen V1 circuit.

This is intentionally a circuit solver: tube currents couple grid, plate, and
cathode nodes, while every physical capacitor is a companion-model branch.
The first implementation uses backward Euler for deterministic, robust state
updates. It is not an EQ biquad followed by a saturation function.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .tube import Koren12AX7


FloatArray = NDArray[np.float64]


@dataclass
class CapacitorBranch:
    node_a: int | None
    node_b: int | None
    capacitance_f: float
    previous_voltage_v: float = 0.0


class V1CircuitModel:
    """Mono Kennedy passive-RIAA stage at a fixed internal sample rate."""

    NODE_NAMES = ("g1", "p1", "k1", "eq_pre", "g2", "eq_low", "p2", "k2", "out")

    def __init__(
        self,
        sample_rate_hz: float = 768_000.0,
        tube: Koren12AX7 | None = None,
        dc_tolerance_a: float = 1.0e-12,
    ):
        self.sample_rate_hz = float(sample_rate_hz)
        self.tube = tube or Koren12AX7()
        self.node = {name: index for index, name in enumerate(self.NODE_NAMES)}
        self.node_count = len(self.NODE_NAMES)
        self.conductance = np.zeros((self.node_count, self.node_count), dtype=np.float64)
        self.fixed_rhs = np.zeros(self.node_count, dtype=np.float64)
        self.input_conductance = 0.0
        self.capacitors: list[CapacitorBranch] = []
        self._build_circuit()
        dynamic_matrix, _ = self._linear_system(0.0, dynamic=True)
        self.dynamic_inverse = np.linalg.inv(dynamic_matrix)
        self.voltage = np.zeros(self.node_count, dtype=np.float64)
        self.last_iterations = 0
        self.last_residual = float("inf")
        self.max_iterations_observed = 0
        self.nonconvergence_count = 0
        self.initialize_dc(tolerance_a=dc_tolerance_a)
        chord_jacobian = dynamic_matrix.copy()
        chord_residual = np.zeros(self.node_count, dtype=np.float64)
        self._tube_stamp(chord_residual, chord_jacobian, self.voltage, "g1", "p1", "k1")
        self._tube_stamp(chord_residual, chord_jacobian, self.voltage, "g2", "p2", "k2")
        self.chord_inverse = np.linalg.inv(chord_jacobian)

    def _stamp_conductance(self, a: int | None, b: int | None, conductance: float) -> None:
        if a is not None:
            self.conductance[a, a] += conductance
        if b is not None:
            self.conductance[b, b] += conductance
        if a is not None and b is not None:
            self.conductance[a, b] -= conductance
            self.conductance[b, a] -= conductance

    def _resistor(self, a: str | None, b: str | None, resistance_ohm: float) -> None:
        self._stamp_conductance(
            self.node[a] if a is not None else None,
            self.node[b] if b is not None else None,
            1.0 / resistance_ohm,
        )

    def _resistor_to_fixed(self, node_name: str, resistance_ohm: float, voltage_v: float) -> None:
        index = self.node[node_name]
        conductance = 1.0 / resistance_ohm
        self.conductance[index, index] += conductance
        self.fixed_rhs[index] += conductance * voltage_v

    def _capacitor(self, a: str | None, b: str | None, capacitance_f: float) -> None:
        self.capacitors.append(
            CapacitorBranch(
                self.node[a] if a is not None else None,
                self.node[b] if b is not None else None,
                capacitance_f,
            )
        )

    def _build_circuit(self) -> None:
        # Input is an ideal sampled node driving the historical 221-ohm stopper.
        self.input_conductance = 1.0 / 221.0
        self.conductance[self.node["g1"], self.node["g1"]] += self.input_conductance
        self._resistor_to_fixed("p1", 121_000.0, 300.0)
        self._resistor("k1", None, 1_210.0)
        self._resistor("eq_pre", "g2", 210_000.0)
        self._resistor("g2", "eq_low", 33_200.0)
        self._resistor("g2", None, 2.21e6)
        self._resistor_to_fixed("p2", 100_000.0, 300.0)
        self._resistor("k2", None, 1_210.0)
        self._resistor("out", None, 2.21e6)

        # Tube parasitics, then the explicit passive signal network.
        for grid, plate, cathode in (("g1", "p1", "k1"), ("g2", "p2", "k2")):
            self._capacitor(grid, cathode, 2.3e-12)
            self._capacitor(grid, plate, 2.4e-12)
            self._capacitor(plate, cathode, 0.9e-12)
        self._capacitor("p1", "eq_pre", 47.0e-9)
        self._capacitor("eq_low", None, 10.0e-9)
        self._capacitor("g2", None, 3.3e-9)
        self._capacitor("p2", "out", 470.0e-9)

    def _tube_stamp(
        self,
        residual: FloatArray,
        jacobian: FloatArray,
        voltage: FloatArray,
        grid_name: str,
        plate_name: str,
        cathode_name: str,
    ) -> None:
        grid = self.node[grid_name]
        plate = self.node[plate_name]
        cathode = self.node[cathode_name]
        vgk = voltage[grid] - voltage[cathode]
        vpk = voltage[plate] - voltage[cathode]
        ip = float(self.tube.plate_current(vgk, vpk))
        ig = float(self.tube.grid_current(vgk))

        # Numerical derivatives are local model derivatives, not solver finite
        # differencing of the full circuit. Steps are below table/input LSBs.
        delta_v = 1.0e-5
        dip_dvg = float(
            self.tube.plate_current(vgk + delta_v, vpk)
            - self.tube.plate_current(vgk - delta_v, vpk)
        ) / (2.0 * delta_v)
        dip_dvp = float(
            self.tube.plate_current(vgk, vpk + delta_v)
            - self.tube.plate_current(vgk, vpk - delta_v)
        ) / (2.0 * delta_v)
        dig_dvg = float(
            self.tube.grid_current(vgk + delta_v)
            - self.tube.grid_current(vgk - delta_v)
        ) / (2.0 * delta_v)

        residual[plate] += ip
        residual[cathode] -= ip
        residual[grid] += ig
        residual[cathode] -= ig

        plate_derivatives = {
            grid: dip_dvg,
            plate: dip_dvp,
            cathode: -(dip_dvg + dip_dvp),
        }
        for column, derivative in plate_derivatives.items():
            jacobian[plate, column] += derivative
            jacobian[cathode, column] -= derivative
        jacobian[grid, grid] += dig_dvg
        jacobian[grid, cathode] -= dig_dvg
        jacobian[cathode, grid] -= dig_dvg
        jacobian[cathode, cathode] += dig_dvg

    def _tube_current_vector(self, voltage: FloatArray) -> FloatArray:
        """Return KCL current injections for both nonlinear devices."""

        current = np.zeros(self.node_count, dtype=np.float64)
        for grid_name, plate_name, cathode_name in (
            ("g1", "p1", "k1"),
            ("g2", "p2", "k2"),
        ):
            grid = self.node[grid_name]
            plate = self.node[plate_name]
            cathode = self.node[cathode_name]
            vgk = voltage[grid] - voltage[cathode]
            vpk = voltage[plate] - voltage[cathode]
            ip = float(self.tube.plate_current(vgk, vpk))
            ig = float(self.tube.grid_current(vgk))
            current[plate] += ip
            current[cathode] -= ip + ig
            current[grid] += ig
        return current

    def _linear_system(self, input_v: float, dynamic: bool) -> tuple[FloatArray, FloatArray]:
        matrix = self.conductance.copy()
        rhs = self.fixed_rhs.copy()
        rhs[self.node["g1"]] += self.input_conductance * input_v
        if dynamic:
            for capacitor in self.capacitors:
                companion_g = capacitor.capacitance_f * self.sample_rate_hz
                self._stamp_matrix_branch(matrix, capacitor.node_a, capacitor.node_b, companion_g)
                if capacitor.node_a is not None:
                    rhs[capacitor.node_a] += companion_g * capacitor.previous_voltage_v
                if capacitor.node_b is not None:
                    rhs[capacitor.node_b] -= companion_g * capacitor.previous_voltage_v
        return matrix, rhs

    @staticmethod
    def _stamp_matrix_branch(
        matrix: FloatArray, a: int | None, b: int | None, conductance: float
    ) -> None:
        if a is not None:
            matrix[a, a] += conductance
        if b is not None:
            matrix[b, b] += conductance
        if a is not None and b is not None:
            matrix[a, b] -= conductance
            matrix[b, a] -= conductance

    def _newton(
        self,
        matrix: FloatArray,
        rhs: FloatArray,
        initial: FloatArray,
        max_iterations: int,
        tolerance_a: float,
    ) -> tuple[FloatArray, int, float, bool]:
        voltage = initial.copy()
        converged = False
        residual_norm = float("inf")
        for iteration in range(1, max_iterations + 1):
            residual = matrix @ voltage - rhs
            jacobian = matrix.copy()
            self._tube_stamp(residual, jacobian, voltage, "g1", "p1", "k1")
            self._tube_stamp(residual, jacobian, voltage, "g2", "p2", "k2")
            residual_norm = float(np.max(np.abs(residual)))
            if residual_norm <= tolerance_a:
                converged = True
                break
            correction = np.linalg.solve(jacobian, -residual)
            voltage += correction
            if float(np.max(np.abs(correction))) <= 1.0e-9:
                converged = True
                break
        return voltage, iteration, residual_norm, converged

    def _fixed_point(
        self,
        matrix: FloatArray,
        rhs: FloatArray,
        initial: FloatArray,
        max_iterations: int,
        tolerance_a: float,
        relaxation: float,
    ) -> tuple[FloatArray, int, float, bool]:
        """Solve using a constant linear inverse and relaxed tube-current updates.

        This form is deliberately evaluated as an FPGA candidate. ``matrix`` is
        constant at a fixed sample rate, so its inverse could become generated
        coefficients. It is not assumed equivalent until convergence studies
        cover the circuit's operating range.
        """

        if not 0.0 < relaxation <= 1.0:
            raise ValueError("relaxation must be in (0, 1]")
        inverse = self.dynamic_inverse
        voltage = initial.copy()
        converged = False
        residual_norm = float("inf")
        for iteration in range(1, max_iterations + 1):
            candidate = inverse @ (rhs - self._tube_current_vector(voltage))
            voltage += relaxation * (candidate - voltage)
            residual = matrix @ voltage - rhs + self._tube_current_vector(voltage)
            residual_norm = float(np.max(np.abs(residual)))
            if residual_norm <= tolerance_a:
                converged = True
                break
        return voltage, iteration, residual_norm, converged

    def _chord(
        self,
        matrix: FloatArray,
        rhs: FloatArray,
        initial: FloatArray,
        max_iterations: int,
        tolerance_a: float,
        relaxation: float,
    ) -> tuple[FloatArray, int, float, bool]:
        """Use a fixed quiescent-point Jacobian (chord/Newton iteration)."""

        if not 0.0 < relaxation <= 1.0:
            raise ValueError("relaxation must be in (0, 1]")
        voltage = initial.copy()
        converged = False
        residual_norm = float("inf")
        for iteration in range(1, max_iterations + 1):
            residual = matrix @ voltage - rhs + self._tube_current_vector(voltage)
            residual_norm = float(np.max(np.abs(residual)))
            if residual_norm <= tolerance_a:
                converged = True
                break
            voltage -= relaxation * (self.chord_inverse @ residual)
        # Report the residual of the returned point rather than the residual
        # immediately before its final correction.
        residual = matrix @ voltage - rhs + self._tube_current_vector(voltage)
        residual_norm = float(np.max(np.abs(residual)))
        converged = converged or residual_norm <= tolerance_a
        return voltage, iteration, residual_norm, converged

    def initialize_dc(self, tolerance_a: float = 1.0e-12) -> dict[str, float]:
        matrix, rhs = self._linear_system(0.0, dynamic=False)
        # Plausible stage voltages avoid the zero-plate singular corner.
        initial = np.zeros(self.node_count, dtype=np.float64)
        initial[self.node["p1"]] = 180.0
        initial[self.node["k1"]] = 1.2
        initial[self.node["p2"]] = 193.0
        initial[self.node["k2"]] = 1.3
        voltage, iterations, residual, converged = self._newton(
            matrix, rhs, initial, max_iterations=30, tolerance_a=tolerance_a
        )
        if not converged:
            raise RuntimeError(f"V1 DC solve failed: residual={residual:.3e} A")
        self.voltage = voltage
        for capacitor in self.capacitors:
            va = voltage[capacitor.node_a] if capacitor.node_a is not None else 0.0
            vb = voltage[capacitor.node_b] if capacitor.node_b is not None else 0.0
            capacitor.previous_voltage_v = float(va - vb)
        self.last_iterations = iterations
        self.last_residual = residual
        return self.nodes

    def process_sample(
        self,
        input_v: float,
        max_iterations: int = 8,
        tolerance_a: float = 1.0e-10,
        solver: str = "newton",
        relaxation: float = 1.0,
    ) -> float:
        matrix, rhs = self._linear_system(float(input_v), dynamic=True)
        if solver == "newton":
            voltage, iterations, residual, converged = self._newton(
                matrix, rhs, self.voltage, max_iterations, tolerance_a
            )
        elif solver == "fixed_point":
            voltage, iterations, residual, converged = self._fixed_point(
                matrix,
                rhs,
                self.voltage,
                max_iterations,
                tolerance_a,
                relaxation,
            )
        elif solver == "chord":
            voltage, iterations, residual, converged = self._chord(
                matrix,
                rhs,
                self.voltage,
                max_iterations,
                tolerance_a,
                relaxation,
            )
        else:
            raise ValueError(f"unsupported nonlinear solver: {solver}")
        self.last_iterations = iterations
        self.last_residual = residual
        self.max_iterations_observed = max(self.max_iterations_observed, iterations)
        if not converged:
            self.nonconvergence_count += 1
        self.voltage = voltage
        for capacitor in self.capacitors:
            va = voltage[capacitor.node_a] if capacitor.node_a is not None else 0.0
            vb = voltage[capacitor.node_b] if capacitor.node_b is not None else 0.0
            capacitor.previous_voltage_v = float(va - vb)
        return float(voltage[self.node["out"]])

    def process(self, samples: FloatArray, **kwargs: float | int) -> FloatArray:
        output = np.empty_like(np.asarray(samples, dtype=np.float64))
        for index, sample in np.ndenumerate(np.asarray(samples, dtype=np.float64)):
            output[index] = self.process_sample(float(sample), **kwargs)
        return output

    @property
    def nodes(self) -> dict[str, float]:
        return {name: float(self.voltage[index]) for name, index in self.node.items()}
