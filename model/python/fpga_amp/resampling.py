"""Deterministic 16x half-band interpolation and decimation reference."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray


FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]


@dataclass(frozen=True)
class HalfbandStage:
    input_rate_hz: int
    taps: int
    kaiser_beta: float

    @property
    def output_rate_hz(self) -> int:
        return 2 * self.input_rate_hz

    @property
    def coefficients(self) -> FloatArray:
        if self.taps % 4 != 3:
            raise ValueError("half-band tap count must be 4m+3")
        center = (self.taps - 1) // 2
        offset = np.arange(self.taps, dtype=np.int64) - center
        coefficients = 0.5 * np.sinc(0.5 * offset) * np.kaiser(
            self.taps, self.kaiser_beta
        )
        coefficients[(offset % 2) == 0] = 0.0
        coefficients[center] = 0.5
        # Preserve the exact half-band center coefficient. Scale only the
        # off-center taps so their sum is exactly the other half of DC gain.
        off_center_sum = np.sum(coefficients) - coefficients[center]
        coefficients *= 0.5 / off_center_sum
        coefficients[center] = 0.5
        return coefficients

    @property
    def nonzero_taps(self) -> int:
        return int(np.count_nonzero(np.abs(self.coefficients) > 1.0e-18))


# Stage 1 has the narrowest physical transition: 20 kHz passband and the first
# 48 kHz image beginning at 28 kHz. Later stages exploit their wider transitions.
DEFAULT_STAGES = (
    HalfbandStage(48_000, 79, 9.5),
    HalfbandStage(96_000, 31, 9.5),
    HalfbandStage(192_000, 19, 8.6),
    HalfbandStage(384_000, 19, 8.6),
)


def interpolate_2x(samples: ArrayLike, coefficients: ArrayLike) -> FloatArray:
    """Return the causal full convolution of a zero-stuffed 2x stream.

    The factor of two restores constant/low-frequency amplitude after zero
    insertion. Full convolution retains latency/tail evidence for verification.
    """

    values = np.asarray(samples, dtype=np.float64)
    kernel = np.asarray(coefficients, dtype=np.float64)
    stuffed = np.zeros(2 * values.size, dtype=np.float64)
    stuffed[::2] = values
    return np.convolve(stuffed, 2.0 * kernel, mode="full")


def decimate_2x(samples: ArrayLike, coefficients: ArrayLike) -> FloatArray:
    """Filter causally and retain the even output phase."""

    values = np.asarray(samples, dtype=np.float64)
    kernel = np.asarray(coefficients, dtype=np.float64)
    return np.convolve(values, kernel, mode="full")[::2]


def interpolate_16x(
    samples: ArrayLike, stages: tuple[HalfbandStage, ...] = DEFAULT_STAGES
) -> FloatArray:
    output = np.asarray(samples, dtype=np.float64)
    for stage in stages:
        output = interpolate_2x(output, stage.coefficients)
    return output


def decimate_16x(
    samples: ArrayLike, stages: tuple[HalfbandStage, ...] = DEFAULT_STAGES
) -> FloatArray:
    output = np.asarray(samples, dtype=np.float64)
    for stage in reversed(stages):
        output = decimate_2x(output, stage.coefficients)
    return output


def interpolation_delay_internal_samples(
    stages: tuple[HalfbandStage, ...] = DEFAULT_STAGES,
) -> int:
    final_rate = stages[-1].output_rate_hz
    return sum(
        ((stage.taps - 1) // 2) * (final_rate // stage.output_rate_hz)
        for stage in stages
    )


def quantized_coefficients_q23(stage: HalfbandStage) -> IntArray:
    return np.rint(stage.coefficients * (1 << 23)).astype(np.int64)


def _fixed_fir(
    samples_q24: IntArray,
    coefficients_q23: IntArray,
    interpolation_gain: bool,
) -> tuple[IntArray, int]:
    accumulator = np.convolve(
        np.asarray(samples_q24, dtype=np.int64),
        np.asarray(coefficients_q23, dtype=np.int64),
        mode="full",
    )
    if interpolation_gain:
        accumulator *= 2
    # Add-half/arithmetic-shift is the same signed rounding convention as the
    # tube and circuit fixed models.
    rounded = (accumulator + (1 << 22)) >> 23
    low = -(1 << 31)
    high = (1 << 31) - 1
    saturation_count = int(np.count_nonzero((rounded < low) | (rounded > high)))
    return np.clip(rounded, low, high).astype(np.int64), saturation_count


def interpolate_2x_fixed_q24(
    samples_q24: IntArray, coefficients_q23: IntArray
) -> tuple[IntArray, int]:
    values = np.asarray(samples_q24, dtype=np.int64)
    stuffed = np.zeros(2 * values.size, dtype=np.int64)
    stuffed[::2] = values
    return _fixed_fir(stuffed, coefficients_q23, interpolation_gain=True)


def decimate_2x_fixed_q24(
    samples_q24: IntArray, coefficients_q23: IntArray
) -> tuple[IntArray, int]:
    filtered, saturation_count = _fixed_fir(
        np.asarray(samples_q24, dtype=np.int64),
        coefficients_q23,
        interpolation_gain=False,
    )
    return filtered[::2], saturation_count


def interpolate_16x_fixed_q24(
    samples_q24: IntArray,
    stages: tuple[HalfbandStage, ...] = DEFAULT_STAGES,
) -> tuple[IntArray, int]:
    output = np.asarray(samples_q24, dtype=np.int64)
    saturation_count = 0
    for stage in stages:
        output, count = interpolate_2x_fixed_q24(
            output, quantized_coefficients_q23(stage)
        )
        saturation_count += count
    return output, saturation_count


def decimate_16x_fixed_q24(
    samples_q24: IntArray,
    stages: tuple[HalfbandStage, ...] = DEFAULT_STAGES,
) -> tuple[IntArray, int]:
    output = np.asarray(samples_q24, dtype=np.int64)
    saturation_count = 0
    for stage in reversed(stages):
        output, count = decimate_2x_fixed_q24(
            output, quantized_coefficients_q23(stage)
        )
        saturation_count += count
    return output, saturation_count
