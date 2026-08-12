"""Linear electrical moving-magnet cartridge model."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray


@dataclass(frozen=True)
class CartridgeModel:
    """Thevenin source followed by winding R/L and parallel R/C loading."""

    series_resistance_ohm: float = 485.0
    series_inductance_h: float = 0.550
    load_resistance_ohm: float = 47_500.0
    load_capacitance_f: float = 150.0e-12

    def transfer(self, frequency_hz: ArrayLike) -> NDArray[np.complex128]:
        frequency = np.asarray(frequency_hz, dtype=np.float64)
        s = 2j * np.pi * frequency
        winding = self.series_resistance_ohm + s * self.series_inductance_h
        load_admittance = 1.0 / self.load_resistance_ohm + s * self.load_capacitance_f
        load = 1.0 / load_admittance
        return load / (winding + load)

    @property
    def undamped_resonance_hz(self) -> float:
        return 1.0 / (
            2.0 * np.pi * np.sqrt(self.series_inductance_h * self.load_capacitance_f)
        )

