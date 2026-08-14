"""Bit-accurate PCM24/physical-voltage calibration boundary.

The V1 circuit consumes and produces signed Q8.24 volts.  Audio converters
instead exchange dimensionless signed PCM24 codes.  These helpers define the
exact integer maps used by the RTL without selecting an ADC, analog gain, DAC,
or line-output full scale.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


PCM24_MIN = -(1 << 23)
PCM24_MAX = (1 << 23) - 1
Q24_MIN = -(1 << 31)
Q24_MAX = (1 << 31) - 1


def quantize_positive_q8_24(value: float, name: str = "coefficient") -> int:
    """Quantize a finite positive calibration coefficient to signed Q8.24."""

    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    quantized = math.floor(value * (1 << 24) + 0.5)
    if not 1 <= quantized <= Q24_MAX:
        raise ValueError(f"{name} is outside positive signed Q8.24 range")
    return quantized


def input_full_scale_coefficient_q24(
    adc_full_scale_peak_volts: float,
    measured_frontend_gain: float,
) -> int:
    """Return input-referred peak volts at PCM full scale in signed Q8.24."""

    if not math.isfinite(measured_frontend_gain) or measured_frontend_gain <= 0.0:
        raise ValueError("measured_frontend_gain must be finite and positive")
    return quantize_positive_q8_24(
        adc_full_scale_peak_volts / measured_frontend_gain,
        "input_full_scale_peak_volts",
    )


def output_reciprocal_coefficient_q24(dac_full_scale_peak_volts: float) -> int:
    """Return reciprocal DAC peak volts in signed Q8.24 per volt."""

    if not math.isfinite(dac_full_scale_peak_volts) or dac_full_scale_peak_volts <= 0.0:
        raise ValueError("dac_full_scale_peak_volts must be finite and positive")
    return quantize_positive_q8_24(
        1.0 / dac_full_scale_peak_volts,
        "reciprocal_dac_full_scale_per_volt",
    )


def round_shift_symmetric(value: int, shift: int) -> int:
    """Round an integer right shift to nearest, with exact ties away from zero."""

    if shift < 0:
        return value << -shift
    if shift == 0:
        return value
    half = 1 << (shift - 1)
    return (value + (half if value >= 0 else half - 1)) >> shift


def _require_signed(value: int, width: int, name: str) -> None:
    minimum = -(1 << (width - 1))
    maximum = (1 << (width - 1)) - 1
    if not minimum <= value <= maximum:
        raise ValueError(f"{name}={value} is outside signed {width}-bit range")


@dataclass(frozen=True)
class InputCalibrationResult:
    sample_q24: int
    pcm_endpoint: bool
    configuration_error: bool


@dataclass(frozen=True)
class OutputCalibrationResult:
    sample_pcm24: int
    saturated: bool
    configuration_error: bool


def pcm24_to_q8_24(
    sample_pcm24: int,
    full_scale_peak_volts_q24: int,
) -> InputCalibrationResult:
    """Map PCM24 to Q8.24 physical volts.

    ``full_scale_peak_volts_q24`` is the physical model-input peak voltage that
    corresponds to the negative PCM full-scale magnitude.  It includes the
    measured analog-front-end gain and ADC full scale; it is not a circuit-model
    tuning parameter.
    """

    _require_signed(sample_pcm24, 24, "sample_pcm24")
    _require_signed(full_scale_peak_volts_q24, 32, "full_scale_peak_volts_q24")
    endpoint = sample_pcm24 in (PCM24_MIN, PCM24_MAX)
    if full_scale_peak_volts_q24 <= 0:
        return InputCalibrationResult(0, endpoint, True)
    sample_q24 = round_shift_symmetric(
        sample_pcm24 * full_scale_peak_volts_q24,
        23,
    )
    # A positive signed-32 coefficient and signed-24 input prove this result is
    # inside signed Q8.24.  Keep the assertion beside the executable contract.
    assert Q24_MIN <= sample_q24 <= Q24_MAX
    return InputCalibrationResult(sample_q24, endpoint, False)


def q8_24_to_pcm24(
    sample_q24: int,
    reciprocal_full_scale_per_volt_q24: int,
) -> OutputCalibrationResult:
    """Map Q8.24 physical volts to saturating PCM24.

    The coefficient is ``1 / DAC_full_scale_peak_volts`` in signed Q8.24.  It
    is precomputed by the control plane so synthesizable logic contains no
    divider.  Exact positive full scale saturates by one code because signed
    PCM24 has an asymmetric endpoint; exact negative full scale is representable.
    """

    _require_signed(sample_q24, 32, "sample_q24")
    _require_signed(
        reciprocal_full_scale_per_volt_q24,
        32,
        "reciprocal_full_scale_per_volt_q24",
    )
    if reciprocal_full_scale_per_volt_q24 <= 0:
        return OutputCalibrationResult(0, False, True)
    unbounded = round_shift_symmetric(
        sample_q24 * reciprocal_full_scale_per_volt_q24,
        25,
    )
    saturated = unbounded < PCM24_MIN or unbounded > PCM24_MAX
    bounded = min(max(unbounded, PCM24_MIN), PCM24_MAX)
    return OutputCalibrationResult(bounded, saturated, False)
