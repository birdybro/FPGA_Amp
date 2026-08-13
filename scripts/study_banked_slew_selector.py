#!/usr/bin/env python3
"""Test a stage-two Vgk-slew-qualified shallow cutoff-bank selector."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

from characterize_banked_solver_accuracy import (  # noqa: E402
    BURST_END_S,
    BURST_START_S,
    DURATION_S,
    FREQUENCY_HZ,
    NOMINAL_PEAK_V,
    SAMPLE_RATE_HZ,
    input_trajectory_q24,
    waveform_metrics,
)
from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedWideStateBankedChordV1CircuitModel,
)
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


LEVELS_PEAK_V = (0.500, 1.000, 1.500)
INTEGRATION_METHODS = ("backward_euler", "trapezoidal")
BANKED_MODEL = FixedWideStateBankedChordV1CircuitModel
SHALLOW_UPPER_V_GK_V = (
    BANKED_MODEL.SHALLOW_SLEW_UPPER_V_GK_V
)
V_GK_SLEW_THRESHOLD_V_PER_SAMPLE = (
    BANKED_MODEL.SHALLOW_SLEW_THRESHOLD_V_PER_SAMPLE
)
BACKWARD_EULER_EXTRA_REPRESENTATIVE = (
    BANKED_MODEL.BACKWARD_EULER_SLEW_JACOBIAN_REPRESENTATIVE
)


class LegacyVgkOnlyBankedModel(FixedWideStateBankedChordV1CircuitModel):
    """Preserve the pre-slew selector for exact A/B comparison."""

    def _select_chord_bank(self) -> int:
        v_gk_q32 = self._previous_v_gk2_q32()
        self.previous_selector_v_gk2_q32 = v_gk_q32
        for bank_index, (upper_v, _, _) in enumerate(
            self.cutoff_jacobian_regimes
        ):
            if v_gk_q32 < int(round(upper_v * (1 << 32))):
                return bank_index
        return len(self.chord_inverse_banks_q)


def run_case(integration_method: str, level_peak_v: float) -> dict[str, object]:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    input_q24 = input_trajectory_q24(level_peak_v)
    stimulus = input_q24.astype(np.float64) / float(1 << 24)
    masks = {
        "burst": (time_s >= BURST_START_S) & (time_s < BURST_END_S),
        "complete_post_burst": time_s >= BURST_END_S,
        "final_10ms": time_s >= DURATION_S - 0.010,
    }
    reference_model = V1CircuitModel(
        SAMPLE_RATE_HZ, integration_method=integration_method
    )
    reference = reference_model.process(
        stimulus, max_iterations=8, tolerance_a=1.0e-12
    )

    current_model = LegacyVgkOnlyBankedModel(
        SAMPLE_RATE_HZ,
        tube_lut=FixedFactorizedKoren12AX7(),
        integration_method=integration_method,
    )
    current = np.empty_like(stimulus)
    shallow_slew_q32: list[int] = []
    failing_shallow_slew_q32: list[int] = []
    residual_limit_q44 = int(round(2.0e-6 * (1 << 44)))
    shallow_lower_q32 = int(
        round(current_model.cutoff_jacobian_regimes[-1][0] * (1 << 32))
    )
    shallow_upper_q32 = int(round(SHALLOW_UPPER_V_GK_V * (1 << 32)))
    for index, sample in enumerate(stimulus):
        v_gk_q32 = current_model._previous_v_gk2_q32()
        slew_q32 = abs(
            v_gk_q32 - current_model.previous_selector_v_gk2_q32
        )
        in_shallow_arc = shallow_lower_q32 <= v_gk_q32 < shallow_upper_q32
        current[index] = current_model.process_sample(
            float(sample), max_iterations=3, residual_limit_a=2.0e-6
        )
        if in_shallow_arc:
            shallow_slew_q32.append(slew_q32)
            if current_model.last_residual_q44 > residual_limit_q44:
                failing_shallow_slew_q32.append(slew_q32)
    candidate_model = FixedWideStateBankedChordV1CircuitModel(
        SAMPLE_RATE_HZ,
        tube_lut=FixedFactorizedKoren12AX7(),
        integration_method=integration_method,
    )
    candidate = candidate_model.process(
        stimulus, max_iterations=3, residual_limit_a=2.0e-6
    )

    def solver_report(
        model: FixedWideStateBankedChordV1CircuitModel,
        output: np.ndarray,
    ) -> dict[str, object]:
        report: dict[str, object] = {
            "output_finite": bool(np.all(np.isfinite(output))),
            "maximum_residual_a": model.max_residual_q44_observed
            / float(1 << 44),
            "residual_limit_exceedance_count": model.nonconvergence_count,
            "saturation_count": model.saturation_count,
            "range_clip_count": model.lut_clip_count,
            "correction_scale_fallback_count": (
                model.correction_scale_fallback_count
            ),
            "bank_selection_count": model.chord_bank_selection_count,
            "windows": {
                name: waveform_metrics(output, reference, mask)
                for name, mask in masks.items()
            },
        }
        if not isinstance(model, LegacyVgkOnlyBankedModel):
            report["slew_qualified_selection_count"] = (
                model.slew_qualified_selection_count
            )
            report["coefficient_min"] = min(
                int(value)
                for bank in model.chord_inverse_banks_q
                for value in bank.flat
            )
            report["coefficient_max"] = max(
                int(value)
                for bank in model.chord_inverse_banks_q
                for value in bank.flat
            )
        return report

    difference = candidate - current
    return {
        "integration_method": integration_method,
        "burst_input_peak_v": level_peak_v,
        "analytical_nonconvergence_count": reference_model.nonconvergence_count,
        "current": solver_report(current_model, current),
        "legacy_selector_trace": {
            "shallow_arc_sample_count": len(shallow_slew_q32),
            "shallow_arc_failure_count": len(failing_shallow_slew_q32),
            "maximum_shallow_arc_absolute_v_gk_delta_v_per_sample": (
                max(shallow_slew_q32) / float(1 << 32)
                if shallow_slew_q32
                else None
            ),
            "minimum_failing_shallow_arc_absolute_v_gk_delta_v_per_sample": (
                min(failing_shallow_slew_q32) / float(1 << 32)
                if failing_shallow_slew_q32
                else None
            ),
            "maximum_failing_shallow_arc_absolute_v_gk_delta_v_per_sample": (
                max(failing_shallow_slew_q32) / float(1 << 32)
                if failing_shallow_slew_q32
                else None
            ),
        },
        "candidate": solver_report(candidate_model, candidate),
        "candidate_vs_current": {
            "complete_record_bit_exact": bool(
                np.array_equal(candidate, current)
            ),
            "windows": {
                name: {
                    "bit_exact": bool(
                        np.array_equal(candidate[mask], current[mask])
                    ),
                    "raw_difference_rms_v": float(
                        np.sqrt(np.mean(np.square(difference[mask])))
                    ),
                    "maximum_absolute_difference_v": float(
                        np.max(np.abs(difference[mask]))
                    ),
                }
                for name, mask in masks.items()
            },
        },
    }


def main() -> int:
    jobs = [
        (method, level)
        for method in INTEGRATION_METHODS
        for level in LEVELS_PEAK_V
    ]
    measurements: list[dict[str, object]] = []
    workers = min(len(jobs), max(1, min(os.cpu_count() or 1, 6)))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_case, *job): job for job in jobs}
        for future in as_completed(futures):
            result = future.result()
            measurements.append(result)
            candidate = result["candidate"]
            burst = candidate["windows"]["burst"]
            print(
                f"{result['integration_method']} "
                f"{result['burst_input_peak_v']:.1f} V: "
                f"fail={candidate['residual_limit_exceedance_count']}, "
                f"burst={burst['raw_normalized_error_db']:.2f} dB, "
                f"selected={candidate['slew_qualified_selection_count']}",
                flush=True,
            )
    measurements.sort(
        key=lambda item: (
            str(item["integration_method"]),
            float(item["burst_input_peak_v"]),
        )
    )
    gates = {
        "analytical_newton_converged": all(
            int(item["analytical_nonconvergence_count"]) == 0
            for item in measurements
        ),
        "candidate_outputs_finite": all(
            bool(item["candidate"]["output_finite"])
            for item in measurements
        ),
        "through_one_volt_is_bit_exact_to_current_selector": all(
            bool(item["candidate_vs_current"]["complete_record_bit_exact"])
            for item in measurements
            if item["burst_input_peak_v"] <= 1.0
        ),
        "candidate_coefficients_fit_signed_18_bits": all(
            -(1 << 17) <= int(item["candidate"]["coefficient_min"])
            and int(item["candidate"]["coefficient_max"]) < (1 << 17)
            for item in measurements
        ),
        "slew_qualifier_inactive_through_one_volt": all(
            int(item["candidate"]["slew_qualified_selection_count"]) == 0
            for item in measurements
            if item["burst_input_peak_v"] <= 1.0
        ),
        "slew_qualifier_exercised_at_one_point_five_volts": all(
            int(item["candidate"]["slew_qualified_selection_count"]) > 0
            for item in measurements
            if item["burst_input_peak_v"] == 1.5
        ),
        "accepted_shallow_arc_stays_below_slew_threshold": all(
            float(
                item["legacy_selector_trace"][
                    "maximum_shallow_arc_absolute_v_gk_delta_v_per_sample"
                ]
            ) < V_GK_SLEW_THRESHOLD_V_PER_SAMPLE
            for item in measurements
            if item["burst_input_peak_v"] <= 1.0
            and item["legacy_selector_trace"][
                "maximum_shallow_arc_absolute_v_gk_delta_v_per_sample"
            ] is not None
        ),
        "one_point_five_volt_legacy_failures_are_slew_separated": all(
            int(item["legacy_selector_trace"]["shallow_arc_failure_count"])
            == int(item["current"]["residual_limit_exceedance_count"])
            and float(
                item["legacy_selector_trace"][
                    "minimum_failing_shallow_arc_absolute_v_gk_delta_v_per_sample"
                ]
            ) > V_GK_SLEW_THRESHOLD_V_PER_SAMPLE
            for item in measurements
            if item["burst_input_peak_v"] == 1.5
        ),
    }
    solver_acceptance = all(
        int(item["candidate"][key]) == 0
        for item in measurements
        for key in (
            "residual_limit_exceedance_count",
            "saturation_count",
            "range_clip_count",
            "correction_scale_fallback_count",
        )
    )
    no_burst_error_regression = all(
        float(item["candidate"]["windows"]["burst"]["raw_normalized_error_db"])
        <= float(item["current"]["windows"]["burst"]["raw_normalized_error_db"])
        for item in measurements
    )
    no_accepted_final_window_error_regression = all(
        float(
            item["candidate"]["windows"]["final_10ms"][
                "raw_normalized_error_db"
            ]
        )
        <= float(
            item["current"]["windows"]["final_10ms"][
                "raw_normalized_error_db"
            ]
        )
        for item in measurements
        if item["burst_input_peak_v"] <= 1.0
    )
    acceptance = {
        "solver_diagnostics_clean": solver_acceptance,
        "no_raw_burst_error_regression": no_burst_error_regression,
        "no_accepted_final_window_error_regression": (
            no_accepted_final_window_error_regression
        ),
    }
    acceptance["selected_for_implementation"] = (
        all(gates.values()) and all(acceptance.values())
    )
    report = {
        "model": "12ax7_passive_riaa_v1",
        "study": "stage-two Vgk-slew-qualified shallow cutoff selector",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "stimulus": {
            "frequency_hz": FREQUENCY_HZ,
            "nominal_peak_v": NOMINAL_PEAK_V,
            "burst_start_s": BURST_START_S,
            "burst_end_s": BURST_END_S,
            "duration_s": DURATION_S,
            "burst_levels_peak_v": list(LEVELS_PEAK_V),
            "input_format": "Q8.24",
        },
        "candidate": {
            "v_gk_slew_threshold_v_per_sample": (
                V_GK_SLEW_THRESHOLD_V_PER_SAMPLE
            ),
            "shallow_upper_v_gk_v": SHALLOW_UPPER_V_GK_V,
            "backward_euler_extra_representative_v_gk_vpk_v": list(
                BACKWARD_EULER_EXTRA_REPRESENTATIVE
            ),
            "trapezoidal_reuses_existing_shallow_bank": True,
        },
        "gates": gates,
        "all_gates_pass": acceptance["selected_for_implementation"],
        "acceptance": acceptance,
        "measurements": measurements,
    }
    generated = ROOT / "model" / "generated" / "banked_slew_selector_study.json"
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    reference = ROOT / "reference" / "results" / "banked_slew_selector_study.json"
    reference.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not acceptance["selected_for_implementation"]:
        raise RuntimeError("banked slew-selector study failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
