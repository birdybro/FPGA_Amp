#!/usr/bin/env python3
"""Directly measure severe floating-model recovery through 850 ms."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

from characterize_overload_recovery import (  # noqa: E402
    sliding_rms,
    sustained_recovery_s,
)
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


SAMPLE_RATE_HZ = 768_000.0
FREQUENCY_HZ = 1_000.0
NOMINAL_PEAK_V = 0.005
BURST_START_S = 0.010
BURST_END_S = 0.015
DURATION_S = 0.850
LEVELS_PEAK_V = (NOMINAL_PEAK_V, 1.000, 1.500)
ENVELOPE_CHECKPOINTS_S = (0.250, 0.300, 0.400, 0.500, 0.600, 0.700, 0.800, 0.850)


def _run_level(level_peak_v: float) -> tuple[float, np.ndarray, int]:
    """Worker entry point; each process owns an independent circuit state."""

    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    amplitude = np.full(time_s.size, NOMINAL_PEAK_V)
    amplitude[(time_s >= BURST_START_S) & (time_s < BURST_END_S)] = level_peak_v
    stimulus = amplitude * np.sin(2.0 * np.pi * FREQUENCY_HZ * time_s)
    model = V1CircuitModel(
        SAMPLE_RATE_HZ, integration_method="trapezoidal"
    )
    output = model.process(
        stimulus, max_iterations=8, tolerance_a=1.0e-12
    )
    return level_peak_v, output, model.nonconvergence_count


def _late_time_behavior(envelope: np.ndarray) -> dict[str, object]:
    """Measure cancellation and rebound instead of imposing one exponential."""

    window_samples = int(round(0.001 * SAMPLE_RATE_HZ))
    end_time_s = (
        np.arange(envelope.size, dtype=np.float64) + window_samples - 1
    ) / SAMPLE_RATE_HZ
    first = int(np.searchsorted(end_time_s, 0.250))
    minimum_relative = int(np.argmin(envelope[first:]))
    minimum_index = first + minimum_relative
    maximum_relative = int(np.argmax(envelope[minimum_index:]))
    maximum_index = minimum_index + maximum_relative
    return {
        "search_start_s_absolute": 0.250,
        "minimum_time_s_absolute": float(end_time_s[minimum_index]),
        "minimum_time_s_after_burst": float(
            end_time_s[minimum_index] - BURST_END_S
        ),
        "minimum_deviation_rms_v": float(envelope[minimum_index]),
        "subsequent_maximum_time_s_absolute": float(end_time_s[maximum_index]),
        "subsequent_maximum_time_s_after_burst": float(
            end_time_s[maximum_index] - BURST_END_S
        ),
        "subsequent_maximum_deviation_rms_v": float(envelope[maximum_index]),
        "rebound_ratio": float(
            envelope[maximum_index] / envelope[minimum_index]
        ),
        "interpretation": (
            "non-monotonic cancellation between at least two circuit-state modes"
        ),
    }


def main() -> int:
    with ProcessPoolExecutor(max_workers=len(LEVELS_PEAK_V)) as executor:
        results = list(executor.map(_run_level, LEVELS_PEAK_V))
    outputs = {level: output for level, output, _ in results}
    failures = {level: count for level, _, count in results}

    sample_count = int(round(DURATION_S * SAMPLE_RATE_HZ))
    post_index = int(round(BURST_END_S * SAMPLE_RATE_HZ))
    window_samples = int(round(0.001 * SAMPLE_RATE_HZ))
    final_window = slice(sample_count - int(0.010 * SAMPLE_RATE_HZ), None)
    control = outputs[NOMINAL_PEAK_V]
    nominal_output_rms = float(
        np.sqrt(np.mean(np.square(control[final_window])))
    )
    thresholds = {
        "ten_percent_nominal_output_rms": 0.10 * nominal_output_rms,
        "one_percent_nominal_output_rms": 0.01 * nominal_output_rms,
        "one_millivolt_rms": 0.001,
    }
    prior = json.loads(
        (ROOT / "model" / "generated" / "long_overload_recovery_summary.json")
        .read_text(encoding="utf-8")
    )
    prediction_by_level = {
        float(measurement["burst_input_peak_v"]): measurement[
            "dominant_exponential_fit"
        ]["projected_recovery_s_after_burst"]
        for measurement in prior["measurements"]
    }

    measurements: list[dict[str, object]] = []
    for level_peak_v in LEVELS_PEAK_V[1:]:
        residual = outputs[level_peak_v] - control
        envelope = sliding_rms(residual, window_samples)
        measured = {
            name: sustained_recovery_s(residual, threshold, post_index)
            for name, threshold in thresholds.items()
        }
        predicted = prediction_by_level[level_peak_v]
        prediction_error = {
            name: (
                None
                if measured[name] is None or predicted[name] is None
                else float(measured[name]) - float(predicted[name])
            )
            for name in thresholds
        }
        envelope_checkpoints = {}
        for absolute_time_s in ENVELOPE_CHECKPOINTS_S:
            envelope_index = min(
                envelope.size - 1,
                int(round(absolute_time_s * SAMPLE_RATE_HZ)) - window_samples,
            )
            envelope_checkpoints[f"{absolute_time_s:g}"] = float(
                envelope[envelope_index]
            )
        measurement = {
            "burst_input_peak_v": level_peak_v,
            "nonconvergence_count": failures[level_peak_v],
            "peak_post_burst_deviation_v": float(
                np.max(np.abs(residual[post_index:]))
            ),
            "measured_recovery_s_after_burst": measured,
            "prior_projected_recovery_s_after_burst": predicted,
            "measured_minus_projected_s": prediction_error,
            "one_ms_deviation_rms_v_at_absolute_time_s": envelope_checkpoints,
            "final_10ms_deviation_rms_v": float(
                np.sqrt(np.mean(np.square(residual[final_window])))
            ),
            "late_time_behavior": _late_time_behavior(envelope),
        }
        measurements.append(measurement)
        recovery_text = "/".join(
            "none" if measured[name] is None else f"{float(measured[name]):.6f}"
            for name in thresholds
        )
        print(
            f"{level_peak_v:5.3f} V peak: 10%/1%/1mV recovery "
            f"{recovery_text} s",
            flush=True,
        )

    report = {
        "model": "12ax7_passive_riaa_v1",
        "implementation": "floating nonlinear nodal circuit model",
        "integration_method": "trapezoidal",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "stimulus": {
            "frequency_hz": FREQUENCY_HZ,
            "nominal_peak_v": NOMINAL_PEAK_V,
            "burst_start_s": BURST_START_S,
            "burst_end_s": BURST_END_S,
            "duration_s": DURATION_S,
            "post_burst_observation_s": DURATION_S - BURST_END_S,
            "burst_levels_peak_v": list(LEVELS_PEAK_V[1:]),
        },
        "nominal_output_rms_v": nominal_output_rms,
        "recovery_thresholds_v_rms": thresholds,
        "recovery_definition": (
            "last 1 ms sliding-RMS threshold crossing relative to a nominal "
            "undisturbed trajectory"
        ),
        "prior_projection_source": (
            "model/generated/long_overload_recovery_summary.json"
        ),
        "control_nonconvergence_count": failures[NOMINAL_PEAK_V],
        "measurements": measurements,
        "fixed_rtl_scope": (
            "This directly measures the floating physical-model trajectory. "
            "Known fixed-solver residual/range failures prohibit an RTL accuracy "
            "claim at these input levels."
        ),
        "prior_projection_assessment": (
            "The 50--240 ms single-exponential fit is falsified at late time: "
            "several projected crossings occur within this record but are not "
            "measured. The envelope falls and then rebounds, demonstrating "
            "opposing modes rather than one dominant recovery exponential."
        ),
    }
    summary = (
        ROOT / "model" / "generated" / "severe_overload_recovery_summary.json"
    )
    summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result = ROOT / "reference" / "results" / "severe_overload_recovery.json"
    result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if any(failures.values()):
        raise RuntimeError("severe floating recovery failed to converge")
    one_volt = measurements[0]["measured_recovery_s_after_burst"]
    if not 0.260 <= float(one_volt["ten_percent_nominal_output_rms"]) <= 0.280:
        raise RuntimeError("1.0 V 10%-recovery time left its measured bound")
    if one_volt["one_percent_nominal_output_rms"] is not None:
        raise RuntimeError("unexpected 1.0 V 1%-recovery inside 835 ms")
    severe = measurements[1]["measured_recovery_s_after_burst"]
    if any(value is not None for value in severe.values()):
        raise RuntimeError("unexpected 1.5 V recovery inside 835 ms")
    if any(
        float(measurement["late_time_behavior"]["rebound_ratio"]) <= 2.0
        for measurement in measurements
    ):
        raise RuntimeError("expected severe-recovery cancellation/rebound is absent")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
