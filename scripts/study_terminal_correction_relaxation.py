#!/usr/bin/env python3
"""Sweep schedule-neutral rational scaling of the terminal chord residual."""

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


LEVELS_PEAK_V = (1.0, 1.5)
TERMINAL_POLICIES = (
    ("all_1_over_2", 1, 2, False),
    ("all_3_over_4", 3, 4, False),
    ("baseline_1_over_1", 1, 1, False),
    ("all_5_over_4", 5, 4, False),
    ("all_3_over_2", 3, 2, False),
    ("all_2_over_1", 2, 1, False),
    ("cutoff_5_over_4", 5, 4, True),
    ("cutoff_3_over_2", 3, 2, True),
    ("cutoff_2_over_1", 2, 1, True),
)


def _symmetric_scale(value: int, numerator: int, denominator: int) -> int:
    magnitude = (abs(value) * numerator + denominator // 2) // denominator
    return -magnitude if value < 0 else magnitude


class RelaxedTerminalCircuit(FixedWideStateBankedChordV1CircuitModel):
    """Research variant scaling only the already available terminal residual."""

    def __init__(
        self,
        *args: object,
        terminal_scale: tuple[int, int],
        cutoff_only: bool,
        **kwargs: object,
    ):
        numerator, denominator = terminal_scale
        if numerator <= 0 or denominator <= 0:
            raise ValueError("terminal scale must be positive")
        self.terminal_scale = (numerator, denominator)
        self.cutoff_only = bool(cutoff_only)
        self.correction_number = 0
        self.sample_start_bank = 0
        super().__init__(*args, **kwargs)

    def _select_chord_bank(self) -> int:
        bank_index = super()._select_chord_bank()
        self.sample_start_bank = bank_index
        return bank_index

    def _apply_correction(
        self, residual_q44: list[int], residual_fractional_bits: int
    ) -> None:
        self.correction_number += 1
        cutoff_active = self.sample_start_bank < len(self.chord_inverse_banks_q)
        if self.correction_number == 4 and (
            not self.cutoff_only or cutoff_active
        ):
            numerator, denominator = self.terminal_scale
            residual_q44 = [
                _symmetric_scale(value, numerator, denominator)
                for value in residual_q44
            ]
        super()._apply_correction(residual_q44, residual_fractional_bits)

    def process_sample(
        self,
        input_v: float,
        max_iterations: int = 3,
        residual_limit_a: float = 2.0e-6,
    ) -> float:
        self.correction_number = 0
        return super().process_sample(
            input_v,
            max_iterations=max_iterations,
            residual_limit_a=residual_limit_a,
        )


def run_level(level_peak_v: float) -> dict[str, object]:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    stimulus = input_trajectory_q24(level_peak_v).astype(np.float64) / float(
        1 << 24
    )
    masks = {
        "burst": (time_s >= BURST_START_S) & (time_s < BURST_END_S),
        "complete_post_burst": time_s >= BURST_END_S,
        "final_10ms": time_s >= DURATION_S - 0.010,
    }
    reference_model = V1CircuitModel(
        SAMPLE_RATE_HZ, integration_method="trapezoidal"
    )
    reference = reference_model.process(
        stimulus, max_iterations=8, tolerance_a=1.0e-12
    )
    cases: list[dict[str, object]] = []
    for policy_name, numerator, denominator, cutoff_only in TERMINAL_POLICIES:
        model = RelaxedTerminalCircuit(
            SAMPLE_RATE_HZ,
            tube_lut=FixedFactorizedKoren12AX7(),
            integration_method="trapezoidal",
            terminal_correction=True,
            terminal_scale=(numerator, denominator),
            cutoff_only=cutoff_only,
        )
        output = model.process(
            stimulus, max_iterations=3, residual_limit_a=2.0e-6
        )
        cases.append(
            {
                "policy": policy_name,
                "terminal_residual_scale": numerator / denominator,
                "integer_numerator": numerator,
                "integer_denominator": denominator,
                "cutoff_banks_only": cutoff_only,
                "windows": {
                    name: waveform_metrics(output, reference, mask)
                    for name, mask in masks.items()
                },
                "maximum_preterminal_residual_a": (
                    model.max_residual_q44_observed / float(1 << 44)
                ),
                "residual_limit_exceedance_count": model.nonconvergence_count,
                "saturation_count": model.saturation_count,
                "range_clip_count": model.lut_clip_count,
                "correction_scale_fallback_count": (
                    model.correction_scale_fallback_count
                ),
                "bank_selection_count": model.chord_bank_selection_count,
            }
        )
    return {
        "burst_input_peak_v": level_peak_v,
        "analytical_nonconvergence_count": reference_model.nonconvergence_count,
        "cases": cases,
    }


def main() -> int:
    measurements: list[dict[str, object]] = []
    workers = min(len(LEVELS_PEAK_V), max(1, os.cpu_count() or 1))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(run_level, level): level for level in LEVELS_PEAK_V
        }
        for future in as_completed(futures):
            result = future.result()
            measurements.append(result)
            print(f"{result['burst_input_peak_v']:.1f} V", flush=True)
            for case in result["cases"]:
                print(
                    f"  {case['policy']}: burst="
                    f"{case['windows']['burst']['raw_error_rms_v'] * 1e3:.3f} mV, "
                    f"final="
                    f"{case['windows']['final_10ms']['raw_error_rms_v'] * 1e3:.3f} mV",
                    flush=True,
                )
    measurements.sort(key=lambda item: float(item["burst_input_peak_v"]))
    gates = {
        "analytical_newton_converged": all(
            int(item["analytical_nonconvergence_count"]) == 0
            for item in measurements
        ),
        "all_fixed_candidates_diagnostic_clean": all(
            int(case[key]) == 0
            for item in measurements
            for case in item["cases"]
            for key in (
                "residual_limit_exceedance_count",
                "saturation_count",
                "range_clip_count",
                "correction_scale_fallback_count",
            )
        ),
    }
    report = {
        "model": "12ax7_passive_riaa_v1",
        "study": "schedule-neutral terminal chord-residual relaxation",
        "integration_method": "trapezoidal",
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
        "terminal_policies": [
            {
                "name": name,
                "numerator": numerator,
                "denominator": denominator,
                "value": numerator / denominator,
                "cutoff_banks_only": cutoff_only,
            }
            for name, numerator, denominator, cutoff_only in TERMINAL_POLICIES
        ],
        "schedule_projection": {
            "baseline_solver_clocks": 127,
            "candidate_solver_clocks": 127,
            "implementation": (
                "small-integer shift/add scaling of the existing Q44 terminal "
                "residual before Q40 chord conversion; no pass is added"
            ),
            "timing_not_proven": True,
        },
        "alignment": {"gain": False, "dc": False, "delay": False},
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "measurements": measurements,
    }
    generated = (
        ROOT / "model" / "generated" / "terminal_correction_relaxation.json"
    )
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    reference = (
        ROOT / "reference" / "results" / "terminal_correction_relaxation.json"
    )
    reference.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_gates_pass"]:
        raise RuntimeError("terminal correction-relaxation study gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
