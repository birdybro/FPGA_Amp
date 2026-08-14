"""Deterministic least-squares audio measurements without SciPy dependencies."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


FloatArray = NDArray[np.float64]


def _signal(values: FloatArray) -> FloatArray:
    samples = np.asarray(values, dtype=np.float64)
    if samples.ndim != 1 or samples.size < 3:
        raise ValueError("audio analysis requires a one-dimensional signal of >=3 samples")
    if not np.all(np.isfinite(samples)):
        raise ValueError("audio analysis signal contains a non-finite sample")
    return samples


def _db_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0.0:
        return -300.0 if numerator <= 0.0 else 300.0
    if numerator <= 0.0:
        return -300.0
    return float(max(-300.0, 20.0 * np.log10(numerator / denominator)))


def signal_summary(values: FloatArray) -> dict[str, float | int]:
    """Return DC, RMS, and signed/absolute peak measurements."""

    samples = _signal(values)
    return {
        "sample_count": int(samples.size),
        "mean": float(np.mean(samples)),
        "rms": float(np.sqrt(np.mean(np.square(samples)))),
        "minimum": float(np.min(samples)),
        "maximum": float(np.max(samples)),
        "maximum_absolute": float(np.max(np.abs(samples))),
    }


def fit_tones(
    values: FloatArray,
    sample_rate_hz: float,
    frequencies_hz: list[float] | tuple[float, ...],
    *,
    start_sample: int = 0,
    stop_sample: int | None = None,
) -> dict[str, object]:
    """Fit DC and arbitrary non-coherent sinusoids simultaneously."""

    samples = _signal(values)
    if sample_rate_hz <= 0.0:
        raise ValueError("sample rate must be positive")
    stop = samples.size if stop_sample is None else int(stop_sample)
    start = int(start_sample)
    if start < 0 or stop > samples.size or stop - start < 3:
        raise ValueError("invalid analysis interval")
    frequencies = [float(value) for value in frequencies_hz]
    if len(frequencies) != len(set(frequencies)):
        raise ValueError("fit frequencies must be unique")
    if any(value <= 0.0 or value >= sample_rate_hz / 2.0 for value in frequencies):
        raise ValueError("fit frequencies must be between DC and Nyquist")
    if 1 + 2 * len(frequencies) >= stop - start:
        raise ValueError("analysis interval is too short for requested tone count")

    indices = np.arange(start, stop, dtype=np.float64)
    columns: list[FloatArray] = [np.ones(indices.size, dtype=np.float64)]
    for frequency_hz in frequencies:
        phase = 2.0 * np.pi * frequency_hz * indices / sample_rate_hz
        columns.extend((np.sin(phase), np.cos(phase)))
    basis = np.column_stack(columns)
    interval = samples[start:stop]
    coefficients, *_ = np.linalg.lstsq(basis, interval, rcond=None)
    fitted = basis @ coefficients
    residual = interval - fitted
    tones: list[dict[str, float]] = []
    for tone_index, frequency_hz in enumerate(frequencies):
        sine = float(coefficients[1 + 2 * tone_index])
        cosine = float(coefficients[2 + 2 * tone_index])
        tones.append(
            {
                "frequency_hz": frequency_hz,
                "sine_coefficient": sine,
                "cosine_coefficient": cosine,
                "peak_amplitude": float(np.hypot(sine, cosine)),
                "rms_amplitude": float(np.hypot(sine, cosine) / np.sqrt(2.0)),
                "phase_deg": float(np.degrees(np.arctan2(cosine, sine))),
            }
        )
    interval_rms = float(np.sqrt(np.mean(np.square(interval))))
    residual_rms = float(np.sqrt(np.mean(np.square(residual))))
    return {
        "sample_rate_hz": sample_rate_hz,
        "start_sample": start,
        "stop_sample": stop,
        "sample_count": stop - start,
        "dc": float(coefficients[0]),
        "tones": tones,
        "interval_rms": interval_rms,
        "residual_rms": residual_rms,
        "normalized_residual_db": _db_ratio(residual_rms, interval_rms),
    }


def harmonic_analysis(
    values: FloatArray,
    sample_rate_hz: float,
    fundamental_hz: float,
    *,
    maximum_harmonic: int = 10,
    start_sample: int = 0,
    stop_sample: int | None = None,
) -> dict[str, object]:
    """Measure H1..Hn and amplitude-ratio THD by simultaneous sine fitting."""

    if maximum_harmonic < 2:
        raise ValueError("maximum harmonic must be at least two")
    if fundamental_hz <= 0.0 or fundamental_hz >= sample_rate_hz / 2.0:
        raise ValueError("fundamental must be between DC and Nyquist")
    orders = [
        order
        for order in range(1, maximum_harmonic + 1)
        if order * fundamental_hz < sample_rate_hz / 2.0
    ]
    fit = fit_tones(
        values,
        sample_rate_hz,
        [order * fundamental_hz for order in orders],
        start_sample=start_sample,
        stop_sample=stop_sample,
    )
    amplitudes = [float(tone["peak_amplitude"]) for tone in fit["tones"]]
    fundamental = amplitudes[0]
    harmonic_root_sum_square = float(np.sqrt(np.sum(np.square(amplitudes[1:]))))
    fit["fundamental_hz"] = fundamental_hz
    fit["maximum_harmonic_requested"] = maximum_harmonic
    fit["harmonic_orders_measured"] = orders
    fit["thd_ratio"] = (
        harmonic_root_sum_square / fundamental if fundamental > 0.0 else 0.0
    )
    fit["thd_percent"] = 100.0 * float(fit["thd_ratio"])
    fit["thd_db"] = _db_ratio(harmonic_root_sum_square, fundamental)
    return fit


def intermodulation_analysis(
    values: FloatArray,
    sample_rate_hz: float,
    fundamentals_hz: tuple[float, float],
    products_hz: list[float] | tuple[float, ...],
    *,
    start_sample: int = 0,
    stop_sample: int | None = None,
) -> dict[str, object]:
    """Fit two fundamentals and explicitly selected intermodulation products."""

    first, second = (float(value) for value in fundamentals_hz)
    if first == second:
        raise ValueError("two-tone fundamentals must differ")
    products = [float(value) for value in products_hz]
    requested = [first, second, *products]
    fit = fit_tones(
        values,
        sample_rate_hz,
        requested,
        start_sample=start_sample,
        stop_sample=stop_sample,
    )
    fundamental_tones = fit["tones"][:2]
    product_tones = fit["tones"][2:]
    combined_fundamental_peak = float(
        np.sqrt(
            sum(float(tone["peak_amplitude"]) ** 2 for tone in fundamental_tones)
        )
    )
    for tone in product_tones:
        tone["relative_to_combined_fundamentals_db"] = _db_ratio(
            float(tone["peak_amplitude"]), combined_fundamental_peak
        )
    fit["fundamentals_hz"] = [first, second]
    fit["products_hz"] = products
    fit["combined_fundamental_peak"] = combined_fundamental_peak
    fit["note"] = (
        "selected spectral-product amplitudes; not labeled as a standards-compliant "
        "SMPTE or CCIF scalar"
    )
    return fit


def smpte_modulation_analysis(
    values: FloatArray,
    sample_rate_hz: float,
    low_frequency_hz: float,
    high_frequency_hz: float,
    *,
    maximum_sideband_order: int = 2,
    start_sample: int = 0,
    stop_sample: int | None = None,
) -> dict[str, object]:
    """Measure the 60 Hz/7 kHz SMPTE-profile amplitude-modulation sidebands.

    For each sideband order, the lower and upper peak amplitudes are summed and
    divided by the high-frequency carrier peak.  This returns the modulation
    depth for ideal symmetric AM.  The root-sum-square of those per-order depths
    is reported as the scalar.  The frequency profile follows common RP 120
    instrumentation; this numerical fit is not a claim of a calibrated,
    standards-conformant analyzer.
    """

    low = float(low_frequency_hz)
    high = float(high_frequency_hz)
    if low <= 0.0 or high <= low or high >= sample_rate_hz / 2.0:
        raise ValueError("IMD frequencies must satisfy 0 < low < high < Nyquist")
    if maximum_sideband_order < 1:
        raise ValueError("maximum sideband order must be positive")
    sideband_frequencies: list[float] = []
    for order in range(1, maximum_sideband_order + 1):
        lower = high - order * low
        upper = high + order * low
        if lower <= 0.0 or upper >= sample_rate_hz / 2.0:
            raise ValueError("requested IMD sideband falls outside (DC, Nyquist)")
        sideband_frequencies.extend((lower, upper))

    fit = fit_tones(
        values,
        sample_rate_hz,
        [low, high, *sideband_frequencies],
        start_sample=start_sample,
        stop_sample=stop_sample,
    )
    low_tone, carrier_tone = fit["tones"][:2]
    carrier_peak = float(carrier_tone["peak_amplitude"])
    sideband_tones = fit["tones"][2:]
    sideband_pairs: list[dict[str, object]] = []
    modulation_depths: list[float] = []
    for order in range(1, maximum_sideband_order + 1):
        lower_tone = sideband_tones[2 * (order - 1)]
        upper_tone = sideband_tones[2 * (order - 1) + 1]
        lower_peak = float(lower_tone["peak_amplitude"])
        upper_peak = float(upper_tone["peak_amplitude"])
        depth = (
            (lower_peak + upper_peak) / carrier_peak
            if carrier_peak > 0.0
            else 0.0
        )
        modulation_depths.append(depth)
        sideband_pairs.append(
            {
                "order": order,
                "lower": lower_tone,
                "upper": upper_tone,
                "modulation_depth_ratio": depth,
                "modulation_depth_percent": 100.0 * depth,
            }
        )

    scalar = float(np.sqrt(np.sum(np.square(modulation_depths))))
    fit["profile"] = "SMPTE RP 120-style 60 Hz / 7 kHz, 4:1 input profile"
    fit["low_frequency_hz"] = low
    fit["high_frequency_hz"] = high
    fit["maximum_sideband_order"] = maximum_sideband_order
    fit["low_to_high_output_peak_ratio"] = (
        float(low_tone["peak_amplitude"]) / carrier_peak
        if carrier_peak > 0.0
        else 0.0
    )
    fit["sideband_pairs"] = sideband_pairs
    fit["imd_ratio"] = scalar
    fit["imd_percent"] = 100.0 * scalar
    fit["imd_db"] = _db_ratio(scalar, 1.0)
    fit["measurement_definition"] = (
        "RSS across sideband orders of (lower peak + upper peak) / 7 kHz "
        "carrier peak; ideal symmetric AM therefore reports its modulation depth"
    )
    fit["conformance_note"] = (
        "frequency/ratio profile and traceable sideband fit only; no claim of "
        "calibrated SMPTE RP 120 instrument conformance"
    )
    return fit


def sustained_recovery_analysis(
    values: FloatArray,
    sample_rate_hz: float,
    threshold_rms: float,
    start_sample: int,
    *,
    window_seconds: float = 0.001,
) -> dict[str, float | int | None]:
    """Find the final sliding-RMS threshold crossing after ``start_sample``."""

    samples = _signal(values)
    if sample_rate_hz <= 0.0 or threshold_rms <= 0.0 or window_seconds <= 0.0:
        raise ValueError("recovery rate, threshold, and window must be positive")
    start = int(start_sample)
    if start < 0 or start >= samples.size:
        raise ValueError("recovery start sample is outside the signal")
    window = int(round(window_seconds * sample_rate_hz))
    if window < 1 or window > samples.size:
        raise ValueError("recovery RMS window is outside the signal")
    squared = np.square(samples)
    cumulative = np.concatenate(([0.0], np.cumsum(squared)))
    envelope = np.sqrt((cumulative[window:] - cumulative[:-window]) / window)
    first_post = max(0, start - window + 1)
    above = np.flatnonzero(envelope[first_post:] > threshold_rms)
    recovered_envelope_index = (
        first_post if above.size == 0 else first_post + int(above[-1]) + 1
    )
    recovered_sample = recovered_envelope_index + window - 1
    recovery_seconds: float | None
    if recovered_envelope_index >= envelope.size:
        recovery_seconds = None
    else:
        recovery_seconds = max(0.0, (recovered_sample - start) / sample_rate_hz)
    return {
        "threshold_rms": float(threshold_rms),
        "window_samples": window,
        "window_seconds": window / sample_rate_hz,
        "start_sample": start,
        "recovered_sample": (
            None if recovery_seconds is None else int(recovered_sample)
        ),
        "recovery_seconds_after_start": recovery_seconds,
        "final_window_rms": float(envelope[-1]),
        "maximum_post_start_window_rms": float(np.max(envelope[first_post:])),
    }
