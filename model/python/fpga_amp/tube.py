"""Koren 12AX7 large-signal current model.

Plate current follows Norman Koren's improved triode equation. Grid current
matches the static diode plus series-RGI branch in Koren's published SPICE
subcircuit. Capacitances remain circuit elements rather than being hidden in
these static current functions.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from numpy.typing import ArrayLike, NDArray


FloatArray = NDArray[np.float64]


def _softplus(value: FloatArray) -> FloatArray:
    return np.maximum(value, 0.0) + np.log1p(np.exp(-np.abs(value)))


@dataclass(frozen=True)
class Koren12AX7:
    """Nominal Koren 12AX7 parameters, in volts, amperes, and ohms."""

    mu: float = 100.0
    ex: float = 1.4
    kg1: float = 1060.0
    kp: float = 600.0
    kvb: float = 300.0
    rgi_ohm: float = 2000.0
    grid_diode_is_a: float = 1.0e-9
    grid_diode_n: float = 1.0
    grid_diode_temperature_c: float = 27.0

    def plate_current(self, v_gk: ArrayLike, v_pk: ArrayLike) -> FloatArray:
        """Return plate current for external grid/cathode and plate/cathode volts."""

        vg = np.asarray(v_gk, dtype=np.float64)
        vp = np.maximum(np.asarray(v_pk, dtype=np.float64), 0.0)
        argument = self.kp * (
            1.0 / self.mu + vg / np.sqrt(self.kvb + np.square(vp))
        )
        e1 = (vp / self.kp) * _softplus(argument)
        # Koren's (1 + sgn(E1)) term is two for positive E1 and zero below it.
        current = 2.0 * np.power(np.maximum(e1, 0.0), self.ex) / self.kg1
        return np.where(vp > 0.0, current, 0.0)

    @property
    def thermal_voltage_v(self) -> float:
        boltzmann_over_q = 8.617333262145e-5
        return boltzmann_over_q * (self.grid_diode_temperature_c + 273.15)

    def grid_current(self, v_gk: ArrayLike) -> FloatArray:
        """Return external-grid current through Koren's RGI/diode branch.

        The implicit diode equation is solved with bounded Newton iterations.
        Negative-grid leakage is retained (near -Is), matching the SPICE diode.
        """

        values = np.asarray(v_gk, dtype=np.float64)
        result = np.empty_like(values)
        vt = self.grid_diode_n * self.thermal_voltage_v
        for index, voltage in np.ndenumerate(values):
            # A safe initial value handles both cutoff and resistor-limited conduction.
            current = max((float(voltage) - 0.55) / self.rgi_ohm, 0.0)
            for _ in range(12):
                junction_v = float(voltage) - current * self.rgi_ohm
                exponent = min(max(junction_v / vt, -50.0), 40.0)
                exp_value = math.exp(exponent)
                diode_i = self.grid_diode_is_a * (exp_value - 1.0)
                residual = current - diode_i
                derivative = 1.0 + (
                    self.rgi_ohm * self.grid_diode_is_a * exp_value / vt
                )
                next_current = current - residual / derivative
                current = max(next_current, -self.grid_diode_is_a)
            result[index] = current
        return result

    def solve_cathode_bias(
        self,
        bplus_v: float,
        plate_resistance_ohm: float,
        cathode_resistance_ohm: float,
    ) -> dict[str, float]:
        """Solve an unbypassed common-cathode stage's quiescent point."""

        low_a = 0.0
        high_a = bplus_v / plate_resistance_ohm
        for _ in range(96):
            current_a = 0.5 * (low_a + high_a)
            cathode_v = current_a * cathode_resistance_ohm
            plate_v = bplus_v - current_a * plate_resistance_ohm
            predicted = float(self.plate_current(-cathode_v, plate_v - cathode_v))
            if predicted > current_a:
                low_a = current_a
            else:
                high_a = current_a
        current_a = 0.5 * (low_a + high_a)
        cathode_v = current_a * cathode_resistance_ohm
        plate_v = bplus_v - current_a * plate_resistance_ohm
        return {
            "grid_v": 0.0,
            "cathode_v": cathode_v,
            "plate_v": plate_v,
            "v_gk_v": -cathode_v,
            "v_pk_v": plate_v - cathode_v,
            "plate_current_a": current_a,
        }

