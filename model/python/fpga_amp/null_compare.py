"""Transparent latency, gain, and residual comparison for audio streams."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


FloatArray = NDArray[np.float64]
_DIRECT_CORRELATION_MAX_MULTIPLIES = 5_000_000


@dataclass(frozen=True)
class NullComparison:
    """Comparison report plus the exact samples used for the final residual."""

    report: dict[str, object]
    reference_aligned: FloatArray
    candidate_aligned: FloatArray
    residual: FloatArray


def _as_signal(values: FloatArray, name: str) -> FloatArray:
    signal = np.asarray(values, dtype=np.float64)
    if signal.ndim != 1 or signal.size < 3:
        raise ValueError(f"{name} must be a one-dimensional signal of >=3 samples")
    if not np.all(np.isfinite(signal)):
        raise ValueError(f"{name} contains a non-finite sample")
    return signal


def _rms(values: FloatArray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def _db_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0.0:
        return -300.0 if numerator <= 0.0 else 300.0
    if numerator <= 0.0:
        return -300.0
    return float(max(-300.0, 20.0 * np.log10(numerator / denominator)))


def _integer_overlap(
    reference: FloatArray,
    candidate: FloatArray,
    lag_samples: int,
) -> tuple[FloatArray, FloatArray]:
    """Align a candidate delayed by positive ``lag_samples`` to reference."""

    if lag_samples >= 0:
        length = min(reference.size, candidate.size - lag_samples)
        if length <= 0:
            return reference[:0], candidate[:0]
        return reference[:length], candidate[lag_samples : lag_samples + length]
    start = -lag_samples
    length = min(reference.size - start, candidate.size)
    if length <= 0:
        return reference[:0], candidate[:0]
    return reference[start : start + length], candidate[:length]


def _correlation_score(reference: FloatArray, candidate: FloatArray) -> float:
    if reference.size < 3:
        return float("-inf")
    ref_zero = reference - np.mean(reference)
    candidate_zero = candidate - np.mean(candidate)
    denominator = float(np.linalg.norm(ref_zero) * np.linalg.norm(candidate_zero))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(ref_zero, candidate_zero) / denominator)


def estimate_integer_latency(
    reference: FloatArray,
    candidate: FloatArray,
    *,
    max_lag_samples: int,
) -> tuple[int, dict[int, float]]:
    """Estimate signed candidate delay with bounded normalized correlation."""

    if max_lag_samples < 0:
        raise ValueError("max lag must be non-negative")
    maximum, minimum_overlap = _latency_search_bounds(
        reference, candidate, max_lag_samples
    )
    operation_count = (2 * maximum + 1) * min(reference.size, candidate.size)
    if operation_count <= _DIRECT_CORRELATION_MAX_MULTIPLIES:
        scores = _direct_latency_scores(reference, candidate, maximum)
    else:
        scores = _fft_latency_scores(reference, candidate, maximum, minimum_overlap)
    # Prefer zero/shorter latency when several scores are exactly tied, as for
    # silence or a constant signal. Such a delay is separately marked as not
    # identifiable in the report.
    best_lag = max(scores, key=lambda lag: (scores[lag], -abs(lag), -lag))
    return best_lag, scores


def _latency_search_bounds(
    reference: FloatArray,
    candidate: FloatArray,
    max_lag_samples: int,
) -> tuple[int, int]:
    shorter = min(reference.size, candidate.size)
    # Normalized correlation becomes spuriously perfect at two- or three-point
    # edge overlaps. Retain at least half of a short fixture and at least 32
    # samples for longer streams.
    minimum_overlap = min(shorter, max(32, shorter // 2))
    maximum = min(
        max_lag_samples,
        reference.size - minimum_overlap,
        candidate.size - minimum_overlap,
    )
    return max(0, int(maximum)), int(minimum_overlap)


def _direct_latency_scores(
    reference: FloatArray,
    candidate: FloatArray,
    maximum: int,
) -> dict[int, float]:
    scores: dict[int, float] = {}
    for lag in range(-maximum, maximum + 1):
        ref_part, candidate_part = _integer_overlap(reference, candidate, lag)
        scores[lag] = _correlation_score(ref_part, candidate_part)
    return scores


def _slice_moments(prefix: FloatArray, start: int, stop: int) -> float:
    return float(prefix[stop] - prefix[start])


def _fft_latency_scores(
    reference: FloatArray,
    candidate: FloatArray,
    maximum: int,
    minimum_overlap: int,
) -> dict[int, float]:
    """Compute lag dot products by FFT and normalize each exact overlap."""

    convolution_size = reference.size + candidate.size - 1
    fft_size = 1 << (convolution_size - 1).bit_length()
    convolution = np.fft.irfft(
        np.fft.rfft(candidate, fft_size)
        * np.fft.rfft(reference[::-1], fft_size),
        fft_size,
    )[:convolution_size]
    ref_sum = np.concatenate(([0.0], np.cumsum(reference)))
    candidate_sum = np.concatenate(([0.0], np.cumsum(candidate)))
    ref_square_sum = np.concatenate(([0.0], np.cumsum(np.square(reference))))
    candidate_square_sum = np.concatenate(
        ([0.0], np.cumsum(np.square(candidate)))
    )

    scores: dict[int, float] = {}
    for lag in range(-maximum, maximum + 1):
        if lag >= 0:
            length = min(reference.size, candidate.size - lag)
            ref_start, candidate_start = 0, lag
        else:
            ref_start, candidate_start = -lag, 0
            length = min(reference.size - ref_start, candidate.size)
        if length < minimum_overlap:
            scores[lag] = -1.0
            continue
        ref_stop = ref_start + length
        candidate_stop = candidate_start + length
        sum_ref = _slice_moments(ref_sum, ref_start, ref_stop)
        sum_candidate = _slice_moments(
            candidate_sum, candidate_start, candidate_stop
        )
        centered_dot = (
            float(convolution[reference.size - 1 + lag])
            - sum_ref * sum_candidate / length
        )
        ref_energy = (
            _slice_moments(ref_square_sum, ref_start, ref_stop)
            - sum_ref * sum_ref / length
        )
        candidate_energy = (
            _slice_moments(
                candidate_square_sum, candidate_start, candidate_stop
            )
            - sum_candidate * sum_candidate / length
        )
        denominator = np.sqrt(max(0.0, ref_energy) * max(0.0, candidate_energy))
        scores[lag] = (
            float(np.clip(centered_dot / denominator, -1.0, 1.0))
            if denominator > 0.0
            else 0.0
        )
    return scores


def _parabolic_peak_offset(scores: dict[int, float], best_lag: int) -> float:
    left = scores.get(best_lag - 1)
    center = scores.get(best_lag)
    right = scores.get(best_lag + 1)
    if left is None or center is None or right is None:
        return 0.0
    denominator = left - 2.0 * center + right
    if not np.isfinite(denominator) or abs(denominator) < 1.0e-15:
        return 0.0
    offset = 0.5 * (left - right) / denominator
    return float(np.clip(offset, -0.5, 0.5))


def _fractional_overlap(
    reference: FloatArray,
    candidate: FloatArray,
    lag_samples: float,
) -> tuple[FloatArray, FloatArray]:
    """Align with labeled linear interpolation at candidate index i + lag."""

    start = max(0, int(np.ceil(-lag_samples)))
    stop = min(
        reference.size,
        int(np.floor((candidate.size - 1) - lag_samples)) + 1,
    )
    if stop - start < 3:
        raise ValueError("latency leaves fewer than three overlapping samples")
    reference_indices = np.arange(start, stop, dtype=np.int64)
    candidate_positions = reference_indices.astype(np.float64) + lag_samples
    aligned_candidate = np.interp(
        candidate_positions,
        np.arange(candidate.size, dtype=np.float64),
        candidate,
    )
    return reference[reference_indices], aligned_candidate


def _metrics(reference: FloatArray, candidate: FloatArray) -> dict[str, float | int]:
    residual = candidate - reference
    reference_rms = _rms(reference)
    candidate_rms = _rms(candidate)
    residual_rms = _rms(residual)
    reference_energy = float(np.dot(reference, reference))
    candidate_energy = float(np.dot(candidate, candidate))
    candidate_relative_gain = (
        float(np.dot(reference, candidate) / reference_energy)
        if reference_energy > 0.0
        else 0.0
    )
    gain_to_apply = (
        float(np.dot(candidate, reference) / candidate_energy)
        if candidate_energy > 0.0
        else 0.0
    )
    return {
        "sample_count": int(reference.size),
        "reference_rms": reference_rms,
        "candidate_rms": candidate_rms,
        "residual_rms": residual_rms,
        "normalized_residual_db": _db_ratio(residual_rms, reference_rms),
        "maximum_absolute_residual": float(np.max(np.abs(residual))),
        "candidate_relative_gain": candidate_relative_gain,
        "candidate_relative_gain_db": _db_ratio(abs(candidate_relative_gain), 1.0),
        "least_squares_gain_to_apply": gain_to_apply,
        "correlation_coefficient": _correlation_score(reference, candidate),
    }


def compare_signals(
    reference: FloatArray,
    candidate: FloatArray,
    *,
    max_lag_samples: int = 4096,
    align_latency: bool = True,
    fractional_delay: bool = False,
    align_gain: bool = False,
) -> NullComparison:
    """Compare signals while recording every operation applied to the residual."""

    ref = _as_signal(reference, "reference")
    test = _as_signal(candidate, "candidate")
    raw_count = min(ref.size, test.size)
    raw_ref = ref[:raw_count]
    raw_test = test[:raw_count]
    raw_metrics = _metrics(raw_ref, raw_test)

    integer_lag = 0
    fractional_offset = 0.0
    peak_correlation = _correlation_score(raw_ref, raw_test)
    latency_identifiable = bool(
        np.linalg.norm(ref - np.mean(ref)) > 0.0
        and np.linalg.norm(test - np.mean(test)) > 0.0
    )
    actual_maximum_lag = 0
    minimum_latency_overlap = raw_count
    latency_method = "disabled"
    if align_latency:
        actual_maximum_lag, minimum_latency_overlap = _latency_search_bounds(
            ref, test, max_lag_samples
        )
        operation_count = (
            (2 * actual_maximum_lag + 1) * min(ref.size, test.size)
        )
        latency_method = (
            "bounded direct normalized correlation"
            if operation_count <= _DIRECT_CORRELATION_MAX_MULTIPLIES
            else "FFT dot products with exact-overlap normalized correlation"
        )
        integer_lag, scores = estimate_integer_latency(
            ref, test, max_lag_samples=max_lag_samples
        )
        peak_correlation = scores[integer_lag]
        if fractional_delay:
            fractional_offset = _parabolic_peak_offset(scores, integer_lag)
    total_lag = float(integer_lag) + fractional_offset

    if align_latency and fractional_delay:
        aligned_ref, aligned_test = _fractional_overlap(ref, test, total_lag)
        fractional_method = "parabolic correlation peak + linear interpolation"
    elif align_latency:
        aligned_ref, aligned_test = _integer_overlap(ref, test, integer_lag)
        fractional_method = "disabled"
    else:
        aligned_ref, aligned_test = raw_ref, raw_test
        fractional_method = "disabled"
    before_gain_metrics = _metrics(aligned_ref, aligned_test)

    applied_gain = 1.0
    if align_gain:
        applied_gain = float(before_gain_metrics["least_squares_gain_to_apply"])
        aligned_test = aligned_test * applied_gain
    residual = aligned_test - aligned_ref
    final_metrics = _metrics(aligned_ref, aligned_test)

    report: dict[str, object] = {
        "conventions": {
            "residual": "candidate - reference",
            "positive_latency_samples": "candidate is delayed relative to reference",
            "gain": "scalar multiplied into candidate; no DC offset is fitted",
            "decibel_floor": -300.0,
        },
        "input": {
            "reference_sample_count": int(ref.size),
            "candidate_sample_count": int(test.size),
        },
        "transformations": {
            "integer_latency_alignment_enabled": align_latency,
            "maximum_lag_requested_samples": max_lag_samples if align_latency else 0,
            "maximum_lag_searched_samples": actual_maximum_lag,
            "minimum_latency_overlap_samples": minimum_latency_overlap,
            "latency_estimation_method": latency_method,
            "latency_identifiable": latency_identifiable,
            "estimated_integer_latency_samples": integer_lag,
            "fractional_delay_alignment_enabled": fractional_delay and align_latency,
            "estimated_fractional_latency_samples": fractional_offset,
            "estimated_total_latency_samples": total_lag,
            "fractional_delay_method": fractional_method,
            "gain_alignment_enabled": align_gain,
            "applied_candidate_gain": applied_gain,
        },
        "raw_zero_lag": raw_metrics,
        "latency_aligned_before_gain": before_gain_metrics,
        "final": final_metrics,
        "latency_peak_correlation": peak_correlation,
    }
    return NullComparison(
        report=report,
        reference_aligned=aligned_ref,
        candidate_aligned=aligned_test,
        residual=residual,
    )


def windowed_spectrum(
    reference: FloatArray,
    candidate: FloatArray,
    sample_rate_hz: float,
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    """Return Hann-windowed amplitude spectra for the aligned comparison."""

    ref = _as_signal(reference, "reference")
    test = _as_signal(candidate, "candidate")
    if ref.size != test.size:
        raise ValueError("spectrum inputs must be aligned to equal lengths")
    if sample_rate_hz <= 0.0:
        raise ValueError("sample rate must be positive")
    window = np.hanning(ref.size)
    coherent_gain = float(np.sum(window) / 2.0)
    scale = coherent_gain if coherent_gain > 0.0 else 1.0
    frequencies = np.fft.rfftfreq(ref.size, 1.0 / sample_rate_hz)
    ref_spectrum = np.abs(np.fft.rfft(ref * window)) / scale
    test_spectrum = np.abs(np.fft.rfft(test * window)) / scale
    residual_spectrum = np.abs(np.fft.rfft((test - ref) * window)) / scale
    return frequencies, ref_spectrum, test_spectrum, residual_spectrum
