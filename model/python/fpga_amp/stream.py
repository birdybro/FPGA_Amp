"""Composed 48 kHz V1 phono-stream fixed references at 384/768 kHz.

The helpers in this module preserve the scheduling visible at the RTL stream
boundary. They keep interpolation, the measured rate-specific RTL pipeline
offset, nonlinear circuit, output rounding, and decimation as separate arrays
so each source of approximation error can be measured.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .factorized_tube import FixedFactorizedKoren12AX7
from .fixed_circuit import (
    FixedWideStateBankedChordV1CircuitModel,
    FixedWideStateTrapezoidalV1CircuitModel,
    FixedWideStateV1CircuitModel,
    round_shift,
    saturate_signed,
)
from .resampling import (
    DEFAULT_STAGES,
    EIGHT_X_STAGES,
    decimate_16x,
    decimate_16x_fixed_q24,
    interpolate_16x,
    interpolate_16x_fixed_q24,
    interpolation_delay_internal_samples,
)
from .v1_circuit import V1CircuitModel


IntArray = NDArray[np.int64]
FloatArray = NDArray[np.float64]

EXTERNAL_SAMPLE_RATE_HZ = 48_000.0
INTERNAL_SAMPLE_RATE_HZ = 768_000.0
INTERPOLATOR_PIPELINE_DELAY_INTERNAL_SAMPLES = 18
EIGHT_X_INTERPOLATOR_PIPELINE_DELAY_INTERNAL_SAMPLES = 8
CONVERTER_GROUP_DELAY_EXTERNAL_SAMPLES = (
    2 * interpolation_delay_internal_samples()
    + INTERPOLATOR_PIPELINE_DELAY_INTERNAL_SAMPLES
) / 16.0


@dataclass(frozen=True)
class FixedWideStreamResult:
    """Bit-accurate complete-stream result and its diagnostic sources."""

    internal_input_q24: IntArray
    circuit_output_q24: IntArray
    output_q24: IntArray
    interpolation_saturation_count: int
    output_conversion_saturation_count: int
    decimation_saturation_count: int
    circuit: FixedWideStateV1CircuitModel
    internal_sample_rate_hz: int
    oversampling_factor: int
    interpolator_pipeline_delay_internal_samples: int

    @property
    def diagnostic_counts(self) -> dict[str, int]:
        return {
            "interpolation_saturation_count": self.interpolation_saturation_count,
            "output_conversion_saturation_count": (
                self.output_conversion_saturation_count
            ),
            "decimation_saturation_count": self.decimation_saturation_count,
            "solver_saturation_count": self.circuit.saturation_count,
            "solver_range_clip_count": self.circuit.lut_clip_count,
            "solver_residual_limit_exceedance_count": (
                self.circuit.nonconvergence_count
            ),
            "solver_correction_scale_fallback_count": (
                self.circuit.correction_scale_fallback_count
            ),
        }


@dataclass(frozen=True)
class FloatingStreamResult:
    """Floating-point composed stream using the physical circuit solver."""

    internal_input_v: FloatArray
    circuit_output_v: FloatArray
    output_v: FloatArray
    circuit: V1CircuitModel


def _scheduled_internal(
    values: NDArray,
    output_count: int,
    *,
    oversampling_factor: int = 16,
    pipeline_delay_internal_samples: int = (
        INTERPOLATOR_PIPELINE_DELAY_INTERNAL_SAMPLES
    ),
) -> NDArray:
    """Apply the measured RTL interpolator offset and sample-window truncation."""

    return np.concatenate(
        (
            np.zeros(
                pipeline_delay_internal_samples,
                dtype=values.dtype,
            ),
            values,
        )
    )[: oversampling_factor * output_count]


def compose_fixed_wide_stream(
    input_q24: IntArray,
    *,
    trapezoidal: bool = False,
    banked: bool = False,
    terminal_correction: bool = False,
    internal_sample_rate_hz: int = 768_000,
) -> FixedWideStreamResult:
    """Run the exact fixed arithmetic used by the complete wide RTL stream."""

    if terminal_correction and not banked:
        raise ValueError("terminal correction requires the banked chord solver")
    if internal_sample_rate_hz == 768_000:
        stages = DEFAULT_STAGES
        oversampling_factor = 16
        pipeline_delay = INTERPOLATOR_PIPELINE_DELAY_INTERNAL_SAMPLES
    elif internal_sample_rate_hz == 384_000:
        stages = EIGHT_X_STAGES
        oversampling_factor = 8
        pipeline_delay = EIGHT_X_INTERPOLATOR_PIPELINE_DELAY_INTERNAL_SAMPLES
    else:
        raise ValueError("internal sample rate must be 384000 or 768000 Hz")
    inputs = np.asarray(input_q24, dtype=np.int64)
    interpolated_q24, interpolation_saturations = interpolate_16x_fixed_q24(
        inputs, stages=stages
    )
    internal_q24 = _scheduled_internal(
        interpolated_q24,
        inputs.size,
        oversampling_factor=oversampling_factor,
        pipeline_delay_internal_samples=pipeline_delay,
    )
    tube = FixedFactorizedKoren12AX7()
    circuit: FixedWideStateV1CircuitModel
    if banked:
        circuit = FixedWideStateBankedChordV1CircuitModel(
            sample_rate_hz=internal_sample_rate_hz,
            tube_lut=tube,
            integration_method=(
                "trapezoidal" if trapezoidal else "backward_euler"
            ),
            terminal_correction=terminal_correction,
        )
    elif trapezoidal:
        circuit = FixedWideStateTrapezoidalV1CircuitModel(
            sample_rate_hz=internal_sample_rate_hz,
            tube_lut=tube,
            terminal_correction=terminal_correction,
        )
    else:
        circuit = FixedWideStateV1CircuitModel(
            sample_rate_hz=internal_sample_rate_hz,
            tube_lut=tube,
            terminal_correction=terminal_correction,
        )

    circuit_output_q24 = np.empty(internal_q24.size, dtype=np.int64)
    conversion_saturations = 0
    for index, sample_q24 in enumerate(internal_q24):
        circuit.process_sample(int(sample_q24) / float(1 << 24))
        converted = round_shift(
            int(circuit.voltage_q[circuit.node["out"]]), 8
        )
        circuit_output_q24[index], clipped = saturate_signed(converted, 32)
        conversion_saturations += int(clipped)

    output_q24, decimation_saturations = decimate_16x_fixed_q24(
        circuit_output_q24, stages=stages
    )
    return FixedWideStreamResult(
        internal_input_q24=internal_q24,
        circuit_output_q24=circuit_output_q24,
        output_q24=output_q24[: inputs.size],
        interpolation_saturation_count=interpolation_saturations,
        output_conversion_saturation_count=conversion_saturations,
        decimation_saturation_count=decimation_saturations,
        circuit=circuit,
        internal_sample_rate_hz=internal_sample_rate_hz,
        oversampling_factor=oversampling_factor,
        interpolator_pipeline_delay_internal_samples=pipeline_delay,
    )


def compose_floating_stream(
    input_q24: IntArray,
    *,
    integration_method: str = "backward_euler",
) -> FloatingStreamResult:
    """Run the end-to-end floating reference from the same quantized input."""

    inputs = np.asarray(input_q24, dtype=np.int64)
    input_v = inputs.astype(np.float64) / float(1 << 24)
    internal_v = _scheduled_internal(interpolate_16x(input_v), inputs.size)
    circuit = V1CircuitModel(
        INTERNAL_SAMPLE_RATE_HZ,
        integration_method=integration_method,
    )
    circuit_output_v = circuit.process(
        internal_v, max_iterations=8, tolerance_a=1.0e-12
    )
    output_v = decimate_16x(circuit_output_v)[: inputs.size]
    return FloatingStreamResult(
        internal_input_v=internal_v,
        circuit_output_v=circuit_output_v,
        output_v=output_v,
        circuit=circuit,
    )


def compose_fixed_converter_only(input_q24: IntArray) -> tuple[IntArray, int]:
    """Run the scheduled fixed converters with an identity internal system."""

    inputs = np.asarray(input_q24, dtype=np.int64)
    interpolated_q24, interpolation_saturations = interpolate_16x_fixed_q24(
        inputs
    )
    internal_q24 = _scheduled_internal(interpolated_q24, inputs.size)
    output_q24, decimation_saturations = decimate_16x_fixed_q24(internal_q24)
    return (
        output_q24[: inputs.size],
        interpolation_saturations + decimation_saturations,
    )


def compose_floating_converter_only(input_q24: IntArray) -> FloatArray:
    """Run the float converters with an identity internal system."""

    inputs = np.asarray(input_q24, dtype=np.int64)
    input_v = inputs.astype(np.float64) / float(1 << 24)
    internal_v = _scheduled_internal(interpolate_16x(input_v), inputs.size)
    return decimate_16x(internal_v)[: inputs.size]
