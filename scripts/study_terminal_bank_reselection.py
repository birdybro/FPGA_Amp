#!/usr/bin/env python3
"""Test schedule-neutral chord-bank reselection before later corrections."""

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
STRATEGIES = ("held", "terminal", "after_first")


class ReselectingBankedCircuit(FixedWideStateBankedChordV1CircuitModel):
    """Research variant that can reselect existing banks within one sample."""

    def __init__(self, *args: object, reselection_strategy: str, **kwargs: object):
        if reselection_strategy not in STRATEGIES:
            raise ValueError(f"unknown reselection strategy {reselection_strategy}")
        self.reselection_strategy = reselection_strategy
        self.correction_number = 0
        self.reselection_count: list[int] = []
        super().__init__(*args, **kwargs)
        self.reselection_count = [0] * (len(self.chord_inverse_banks_q) + 1)

    def _current_state_bank(self) -> int:
        """Select by corrected Vgk without reusing the inter-sample slew rule."""

        v_gk_q32 = self._previous_v_gk2_q32()
        for bank_index, (upper_v, _, _) in enumerate(
            self.cutoff_jacobian_regimes
        ):
            if v_gk_q32 < int(round(upper_v * (1 << 32))):
                return bank_index
        return len(self.chord_inverse_banks_q)

    def _apply_correction(
        self, residual_q44: list[int], residual_fractional_bits: int
    ) -> None:
        self.correction_number += 1
        should_reselect = (
            self.reselection_strategy == "after_first"
            and self.correction_number > 1
        ) or (
            self.reselection_strategy == "terminal"
            and self.correction_number == 4
        )
        if should_reselect:
            bank_index = self._current_state_bank()
            self.reselection_count[bank_index] += 1
            if bank_index < len(self.chord_inverse_banks_q):
                self.chord_inverse_q = self.chord_inverse_banks_q[bank_index]
            else:
                self.chord_inverse_q = self.nominal_chord_inverse_q
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

    outputs: dict[str, np.ndarray] = {}
    cases: list[dict[str, object]] = []
    for strategy in STRATEGIES:
        model = ReselectingBankedCircuit(
            SAMPLE_RATE_HZ,
            tube_lut=FixedFactorizedKoren12AX7(),
            integration_method="trapezoidal",
            terminal_correction=True,
            reselection_strategy=strategy,
        )
        output = model.process(
            stimulus, max_iterations=3, residual_limit_a=2.0e-6
        )
        outputs[strategy] = output
        cases.append(
            {
                "strategy": strategy,
                "bank_policy": {
                    "first_correction": "sample-start held bank",
                    "later_corrections": (
                        "corrected-state Vgk bank"
                        if strategy == "after_first"
                        else "sample-start held bank"
                    ),
                    "terminal_correction": (
                        "corrected-state Vgk bank"
                        if strategy in ("terminal", "after_first")
                        else "sample-start held bank"
                    ),
                    "corrected_state_reselection_count": model.reselection_count,
                },
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
                "sample_start_bank_selection_count": (
                    model.chord_bank_selection_count
                ),
                "sample_start_slew_selection_count": (
                    model.slew_qualified_selection_count
                ),
            }
        )

    held = outputs["held"]
    for case in cases:
        strategy = str(case["strategy"])
        difference = outputs[strategy] - held
        case["difference_from_held"] = {
            name: {
                "rms_v": float(np.sqrt(np.mean(np.square(difference[mask])))),
                "maximum_absolute_v": float(np.max(np.abs(difference[mask]))),
            }
            for name, mask in masks.items()
        }
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
                    f"  {case['strategy']}: burst="
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
        "study": "schedule-neutral within-sample chord-bank reselection",
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
        "strategies": list(STRATEGIES),
        "schedule_projection": {
            "held_solver_clocks": 127,
            "reselected_solver_clocks": 127,
            "reason": (
                "reselection is a threshold mux among existing coefficient "
                "sets at the chord-engine launch; no residual or correction "
                "pass is added"
            ),
        },
        "alignment": {"gain": False, "dc": False, "delay": False},
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "measurements": measurements,
    }
    generated = ROOT / "model" / "generated" / "terminal_bank_reselection.json"
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    reference = ROOT / "reference" / "results" / "terminal_bank_reselection.json"
    reference.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_gates_pass"]:
        raise RuntimeError("terminal bank-reselection study gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
