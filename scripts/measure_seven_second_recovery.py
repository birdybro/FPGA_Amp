#!/usr/bin/env python3
"""Measure complete severe recovery with a validated Newton/chord handoff."""

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
DURATION_S = 7.000
NEWTON_HANDOFF_S = 0.850
OVERLAP_END_S = 0.950
LEVELS_PEAK_V = (NOMINAL_PEAK_V, 1.000, 1.500)


def _clone_state(source: V1CircuitModel) -> V1CircuitModel:
    clone = V1CircuitModel(
        SAMPLE_RATE_HZ, integration_method="trapezoidal"
    )
    clone.voltage = source.voltage.copy()
    for target_capacitor, source_capacitor in zip(
        clone.capacitors, source.capacitors, strict=True
    ):
        target_capacitor.previous_voltage_v = source_capacitor.previous_voltage_v
        target_capacitor.previous_current_a = source_capacitor.previous_current_a
    clone.nonconvergence_count = 0
    clone.max_iterations_observed = 0
    return clone


def _run_level(level_peak_v: float) -> tuple[float, np.ndarray, dict[str, object]]:
    sample_count = int(round(DURATION_S * SAMPLE_RATE_HZ))
    handoff_index = int(round(NEWTON_HANDOFF_S * SAMPLE_RATE_HZ))
    overlap_end_index = int(round(OVERLAP_END_S * SAMPLE_RATE_HZ))
    burst_start_index = int(round(BURST_START_S * SAMPLE_RATE_HZ))
    burst_end_index = int(round(BURST_END_S * SAMPLE_RATE_HZ))
    period_samples = int(round(SAMPLE_RATE_HZ / FREQUENCY_HZ))
    phase = np.arange(period_samples, dtype=np.float64)
    sine_period = np.sin(2.0 * np.pi * phase / period_samples)

    newton = V1CircuitModel(
        SAMPLE_RATE_HZ, integration_method="trapezoidal"
    )
    output = np.empty(sample_count, dtype=np.float64)
    for index in range(handoff_index):
        amplitude = (
            level_peak_v
            if burst_start_index <= index < burst_end_index
            else NOMINAL_PEAK_V
        )
        sample = amplitude * sine_period[index % period_samples]
        output[index] = newton.process_sample(
            float(sample), max_iterations=8, tolerance_a=1.0e-12
        )
    newton_failures_before_handoff = newton.nonconvergence_count
    chord = _clone_state(newton)

    overlap_error = np.empty(overlap_end_index - handoff_index, dtype=np.float64)
    for index in range(handoff_index, overlap_end_index):
        sample = NOMINAL_PEAK_V * sine_period[index % period_samples]
        reference = newton.process_sample(
            float(sample), max_iterations=8, tolerance_a=1.0e-12
        )
        output[index] = chord.process_sample(
            float(sample),
            solver="chord",
            max_iterations=2,
            tolerance_a=1.0e-12,
        )
        overlap_error[index - handoff_index] = output[index] - reference

    for index in range(overlap_end_index, sample_count):
        sample = NOMINAL_PEAK_V * sine_period[index % period_samples]
        output[index] = chord.process_sample(
            float(sample),
            solver="chord",
            max_iterations=2,
            tolerance_a=1.0e-12,
        )
    final_newton = _clone_state(chord)
    final_chord = _clone_state(chord)
    final_probe_error = np.empty(period_samples, dtype=np.float64)
    for phase_index in range(period_samples):
        sample = NOMINAL_PEAK_V * sine_period[phase_index]
        reference = final_newton.process_sample(
            float(sample), max_iterations=8, tolerance_a=1.0e-12
        )
        candidate = final_chord.process_sample(
            float(sample),
            solver="chord",
            max_iterations=2,
            tolerance_a=1.0e-12,
        )
        final_probe_error[phase_index] = candidate - reference
    diagnostics = {
        "newton_handoff_s": NEWTON_HANDOFF_S,
        "newton_overlap_end_s": OVERLAP_END_S,
        "newton_nonconvergence_count": newton.nonconvergence_count,
        "newton_nonconvergence_count_before_handoff": (
            newton_failures_before_handoff
        ),
        "chord_nonconvergence_count": chord.nonconvergence_count,
        "chord_max_iterations": 2,
        "overlap_samples": overlap_error.size,
        "overlap_error_rms_v": float(
            np.sqrt(np.mean(np.square(overlap_error)))
        ),
        "overlap_error_mean_v": float(np.mean(overlap_error)),
        "overlap_error_maximum_absolute_v": float(np.max(np.abs(overlap_error))),
        "final_probe_samples": period_samples,
        "final_probe_error_rms_v": float(
            np.sqrt(np.mean(np.square(final_probe_error)))
        ),
        "final_probe_error_maximum_absolute_v": float(
            np.max(np.abs(final_probe_error))
        ),
    }
    return level_peak_v, output, diagnostics


def main() -> int:
    with ProcessPoolExecutor(max_workers=len(LEVELS_PEAK_V)) as executor:
        results = list(executor.map(_run_level, LEVELS_PEAK_V))
    outputs = {level: output for level, output, _ in results}
    solver_diagnostics = {level: diagnostic for level, _, diagnostic in results}

    sample_count = int(round(DURATION_S * SAMPLE_RATE_HZ))
    post_index = int(round(BURST_END_S * SAMPLE_RATE_HZ))
    window_samples = int(round(0.001 * SAMPLE_RATE_HZ))
    final_window = slice(sample_count - int(round(0.010 * SAMPLE_RATE_HZ)), None)
    control = outputs[NOMINAL_PEAK_V]
    nominal_output_rms = float(
        np.sqrt(np.mean(np.square(control[final_window])))
    )
    thresholds = {
        "ten_percent_nominal_output_rms": 0.10 * nominal_output_rms,
        "one_percent_nominal_output_rms": 0.01 * nominal_output_rms,
        "one_millivolt_rms": 0.001,
    }
    modes_path = ROOT / "model" / "generated" / "linearized_mode_summary.json"
    modes = json.loads(modes_path.read_text(encoding="utf-8"))
    estimate_by_level = {
        float(item["burst_input_peak_v"]): item
        for item in modes["overload_recovery_interpretation"][
            "modal_late_recovery_estimates"
        ]
    }

    measurements: list[dict[str, object]] = []
    for level_peak_v in LEVELS_PEAK_V[1:]:
        residual = outputs[level_peak_v] - control
        envelope = sliding_rms(residual, window_samples)
        recovery = {
            name: sustained_recovery_s(residual, threshold, post_index)
            for name, threshold in thresholds.items()
        }
        checkpoints = {}
        for absolute_time_s in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0):
            index = min(
                envelope.size - 1,
                int(round(absolute_time_s * SAMPLE_RATE_HZ)) - window_samples,
            )
            checkpoints[f"{absolute_time_s:g}"] = float(envelope[index])
        estimate = estimate_by_level[level_peak_v][
            "estimated_recovery_s_after_burst"
        ]
        measurements.append(
            {
                "burst_input_peak_v": level_peak_v,
                "measured_recovery_s_after_burst": recovery,
                "modal_estimated_recovery_s_after_burst": estimate,
                "measured_minus_modal_estimate_s": {
                    name: (
                        None
                        if name not in estimate or recovery[name] is None
                        else float(recovery[name]) - float(estimate[name])
                    )
                    for name in thresholds
                },
                "one_ms_deviation_rms_v_at_absolute_time_s": checkpoints,
                "final_10ms_deviation_rms_v": float(
                    np.sqrt(np.mean(np.square(residual[final_window])))
                ),
                "solver_handoff_diagnostics": solver_diagnostics[level_peak_v],
            }
        )
        recovery_text = "/".join(
            "none" if recovery[name] is None else f"{float(recovery[name]):.6f}"
            for name in thresholds
        )
        print(
            f"{level_peak_v:5.3f} V peak: 10%/1%/1mV "
            f"{recovery_text} s",
            flush=True,
        )

    report = {
        "model": "12ax7_passive_riaa_v1",
        "implementation": "floating nonlinear nodal circuit model",
        "integration_method": "trapezoidal",
        "solver_schedule": (
            "full Newton through 850 ms, two-pass DC-chord candidate thereafter, "
            "with a simultaneous Newton comparison through 950 ms"
        ),
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
        "modal_estimate_source": str(modes_path.relative_to(ROOT)),
        "control_solver_handoff_diagnostics": solver_diagnostics[NOMINAL_PEAK_V],
        "measurements": measurements,
        "scope": (
            "This closes floating physical-model recovery timing. It does not "
            "remove the known fixed/RTL severe-overload solver limitation."
        ),
    }
    for diagnostic in solver_diagnostics.values():
        if int(diagnostic["newton_nonconvergence_count"]) or int(
            diagnostic["chord_nonconvergence_count"]
        ):
            raise RuntimeError("seven-second solver failed to converge")
        if float(diagnostic["overlap_error_maximum_absolute_v"]) > 5.0e-6:
            raise RuntimeError("Newton/chord overlap error exceeds 5 uV")
        if float(diagnostic["final_probe_error_maximum_absolute_v"]) > 5.0e-6:
            raise RuntimeError("final Newton/chord probe error exceeds 5 uV")
    for measurement in measurements:
        if any(
            value is None
            for value in measurement["measured_recovery_s_after_burst"].values()
        ):
            raise RuntimeError("seven-second record missed a recovery threshold")

    summary = ROOT / "model" / "generated" / "seven_second_recovery_summary.json"
    summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result = ROOT / "reference" / "results" / "seven_second_recovery.json"
    result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
