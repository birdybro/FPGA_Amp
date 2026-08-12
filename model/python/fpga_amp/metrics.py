"""Small dependency-free measurement helpers."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike


def db(value: ArrayLike, floor_db: float = -300.0) -> np.ndarray:
    magnitude = np.maximum(np.abs(np.asarray(value)), 10.0 ** (floor_db / 20.0))
    return 20.0 * np.log10(magnitude)


def rms(value: ArrayLike) -> float:
    samples = np.asarray(value, dtype=np.float64)
    return float(np.sqrt(np.mean(np.square(samples))))

