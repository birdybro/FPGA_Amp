"""Independent mathematical RIAA replay reference."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


T1_S = 3180.0e-6
T2_S = 318.0e-6
T3_S = 75.0e-6
REFERENCE_HZ = 1000.0


def _unnormalized(frequency_hz: ArrayLike) -> NDArray[np.complex128]:
    frequency = np.asarray(frequency_hz, dtype=np.float64)
    s = 2j * np.pi * frequency
    return (1.0 + s * T2_S) / ((1.0 + s * T1_S) * (1.0 + s * T3_S))


def riaa_replay(frequency_hz: ArrayLike) -> NDArray[np.complex128]:
    """Return the canonical replay transfer normalized to unity at 1 kHz."""

    normalization = abs(_unnormalized(REFERENCE_HZ))
    return _unnormalized(frequency_hz) / normalization


def riaa_db(frequency_hz: ArrayLike) -> NDArray[np.float64]:
    return 20.0 * np.log10(np.abs(riaa_replay(frequency_hz)))

