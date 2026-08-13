#!/usr/bin/env python3
"""Prove and classify the factorized-tube cutoff-domain expansion."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.factorized_tube import (  # noqa: E402
    FixedFactorizedKoren12AX7,
    _round_shift,
)
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedWideStateBankedChordV1CircuitModel,
)


SAMPLE_RATE_HZ = 768_000.0
FREQUENCY_HZ = 1_000.0
NOMINAL_PEAK_V = 0.005
BURST_PEAK_V = 1.5
BURST_START_S = 0.004
BURST_END_S = 0.008
DURATION_S = 0.012
INTEGRATION_METHODS = ("backward_euler", "trapezoidal")
REASONS = (
    "v_gk_below_plate_domain",
    "v_gk_above_plate_domain",
    "v_pk_below_table",
    "v_pk_above_table",
    "transformed_below_table",
    "transformed_above_table",
    "e1_below_table",
    "e1_above_table",
)


class TrackingFactorizedTube(FixedFactorizedKoren12AX7):
    """Unchanged evaluator with exact fixed intermediate-range telemetry."""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.evaluation_count = 0
        self.reported_clip_count = 0
        self.reason_count = {name: 0 for name in REASONS}
        self.grid_current_lower_clamp_count = 0
        self.grid_current_upper_clamp_count = 0
        self.minimum = {
            "v_gk_v": float("inf"),
            "v_pk_v": float("inf"),
            "transformed": float("inf"),
            "e1_v": float("inf"),
        }
        self.maximum = {name: -float("inf") for name in self.minimum}
        self.clip_minimum = {name: float("inf") for name in self.minimum}
        self.clip_maximum = {name: -float("inf") for name in self.minimum}
        self.status_mismatch_count = 0

    def _fixed_intermediates(
        self, v_gk_q: int, v_pk_q: int
    ) -> tuple[dict[str, float], dict[str, bool], bool, bool]:
        vg_low_q = self._fixed_limit(self.v_gk_min_v, self.v_gk_fractional_bits)
        vg_high_q = self._fixed_limit(self.v_gk_max_v, self.v_gk_fractional_bits)
        grid_low_q = self._fixed_limit(
            self.grid_v_gk_min_v, self.v_gk_fractional_bits
        )
        vp_low_q = self._fixed_limit(self.plate_min_v, self.v_pk_fractional_bits)
        vp_high_q = self._fixed_limit(self.plate_max_v, self.v_pk_fractional_bits)
        plate_coordinate = self._coordinate(
            v_pk_q, vp_low_q, vp_high_q, self.reciprocal_points
        )
        reciprocal_q32 = self._hermite(
            self.reciprocal_value_q32,
            self.reciprocal_slope_q32,
            plate_coordinate,
        )
        transformed_q30 = int(round((1.0 / self.tube.mu) * (1 << 30)))
        transformed_q30 += _round_shift(
            v_gk_q * reciprocal_q32,
            self.v_gk_fractional_bits
            + self.reciprocal_fractional_bits
            - self.transformed_fractional_bits,
        )
        transformed_low_q = self._fixed_limit(
            self.transformed_min, self.transformed_fractional_bits
        )
        transformed_high_q = self._fixed_limit(
            self.transformed_max, self.transformed_fractional_bits
        )
        softplus_coordinate = self._coordinate(
            transformed_q30,
            transformed_low_q,
            transformed_high_q,
            self.softplus_points,
        )
        softplus_q32 = self._hermite(
            self.softplus_value_q32,
            self.softplus_slope_q32,
            softplus_coordinate,
        )
        e1_q20 = _round_shift(
            max(v_pk_q, 0) * softplus_q32,
            self.v_pk_fractional_bits
            + self.softplus_fractional_bits
            - self.e1_fractional_bits,
        )
        e1_low_q = self._fixed_limit(self.e1_min_v, self.e1_fractional_bits)
        e1_high_q = self._fixed_limit(self.e1_max_v, self.e1_fractional_bits)
        values = {
            "v_gk_v": v_gk_q / float(1 << self.v_gk_fractional_bits),
            "v_pk_v": v_pk_q / float(1 << self.v_pk_fractional_bits),
            "transformed": transformed_q30
            / float(1 << self.transformed_fractional_bits),
            "e1_v": e1_q20 / float(1 << self.e1_fractional_bits),
        }
        status = {
            "v_gk_below_plate_domain": v_gk_q < vg_low_q,
            "v_gk_above_plate_domain": v_gk_q > vg_high_q,
            "v_pk_below_table": v_pk_q < vp_low_q,
            "v_pk_above_table": v_pk_q > vp_high_q,
            "transformed_below_table": transformed_q30 < transformed_low_q,
            "transformed_above_table": transformed_q30 > transformed_high_q,
            "e1_below_table": e1_q20 < e1_low_q,
            "e1_above_table": e1_q20 > e1_high_q,
        }
        return values, status, v_gk_q < grid_low_q, v_gk_q > vg_high_q

    def evaluate_fixed(self, v_gk_q: int, v_pk_q: int) -> tuple[int, int, bool]:
        values, status, grid_low, grid_high = self._fixed_intermediates(
            v_gk_q, v_pk_q
        )
        plate_q31, grid_q31, clipped = super().evaluate_fixed(v_gk_q, v_pk_q)
        derived_clip = any(status.values())
        self.evaluation_count += 1
        self.reported_clip_count += int(clipped)
        self.status_mismatch_count += int(clipped != derived_clip)
        self.grid_current_lower_clamp_count += int(grid_low)
        self.grid_current_upper_clamp_count += int(grid_high)
        for name, active in status.items():
            self.reason_count[name] += int(active)
        for name, value in values.items():
            self.minimum[name] = min(self.minimum[name], value)
            self.maximum[name] = max(self.maximum[name], value)
            if clipped:
                self.clip_minimum[name] = min(self.clip_minimum[name], value)
                self.clip_maximum[name] = max(self.clip_maximum[name], value)
        return plate_q31, grid_q31, clipped

    @staticmethod
    def _finite_or_none(values: dict[str, float]) -> dict[str, float | None]:
        return {
            name: value if np.isfinite(value) else None
            for name, value in values.items()
        }

    def report(self) -> dict[str, object]:
        return {
            "accepted_ranges": {
                "plate_law_v_gk_v": [self.v_gk_min_v, self.v_gk_max_v],
                "grid_current_lookup_v_gk_v": [
                    self.grid_v_gk_min_v,
                    self.v_gk_max_v,
                ],
            },
            "evaluation_count": self.evaluation_count,
            "reported_clip_evaluation_count": self.reported_clip_count,
            "reason_count": self.reason_count,
            "grid_current_lower_clamp_count": self.grid_current_lower_clamp_count,
            "grid_current_upper_clamp_count": self.grid_current_upper_clamp_count,
            "status_mismatch_count": self.status_mismatch_count,
            "all_evaluations": {
                "minimum": self._finite_or_none(self.minimum),
                "maximum": self._finite_or_none(self.maximum),
            },
            "clipped_evaluations": {
                "minimum": self._finite_or_none(self.clip_minimum),
                "maximum": self._finite_or_none(self.clip_maximum),
            },
        }


def input_trajectory() -> np.ndarray:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    amplitude = np.full(time_s.size, NOMINAL_PEAK_V)
    amplitude[(time_s >= BURST_START_S) & (time_s < BURST_END_S)] = BURST_PEAK_V
    return (
        np.rint(
            amplitude
            * np.sin(2.0 * np.pi * FREQUENCY_HZ * time_s)
            * float(1 << 24)
        ).astype(np.int64)
        / float(1 << 24)
    )


def run_variant(
    integration_method: str, plate_v_gk_min_v: float
) -> tuple[np.ndarray, FixedWideStateBankedChordV1CircuitModel, TrackingFactorizedTube]:
    tube = TrackingFactorizedTube(v_gk_min_v=plate_v_gk_min_v)
    model = FixedWideStateBankedChordV1CircuitModel(
        SAMPLE_RATE_HZ,
        tube_lut=tube,
        integration_method=integration_method,
    )
    output = model.process(
        input_trajectory(), max_iterations=3, residual_limit_a=2.0e-6
    )
    return output, model, tube


def run_case(integration_method: str) -> dict[str, object]:
    baseline_output, baseline_model, baseline_tube = run_variant(
        integration_method, -5.0
    )
    expanded_output, expanded_model, expanded_tube = run_variant(
        integration_method, -8.0
    )
    difference = expanded_output - baseline_output

    def variant_report(
        model: FixedWideStateBankedChordV1CircuitModel,
        tube: TrackingFactorizedTube,
        output: np.ndarray,
    ) -> dict[str, object]:
        return {
            "output_finite": bool(np.all(np.isfinite(output))),
            "solver_range_clip_count": model.lut_clip_count,
            "residual_limit_exceedance_count": model.nonconvergence_count,
            "tube": tube.report(),
        }

    return {
        "integration_method": integration_method,
        "baseline_minus_5_v": variant_report(
            baseline_model, baseline_tube, baseline_output
        ),
        "expanded_minus_8_v": variant_report(
            expanded_model, expanded_tube, expanded_output
        ),
        "output_equivalence": {
            "bit_exact": bool(np.array_equal(expanded_output, baseline_output)),
            "maximum_absolute_difference_v": float(np.max(np.abs(difference))),
            "rms_difference_v": float(np.sqrt(np.mean(np.square(difference)))),
        },
    }


def main() -> int:
    measurements: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(run_case, method): method
            for method in INTEGRATION_METHODS
        }
        for future in as_completed(futures):
            result = future.result()
            measurements.append(result)
            baseline = result["baseline_minus_5_v"]["tube"]
            expanded = result["expanded_minus_8_v"]["tube"]
            print(
                f"{result['integration_method']}: "
                f"baseline clip={baseline['reported_clip_evaluation_count']}, "
                f"expanded clip={expanded['reported_clip_evaluation_count']}, "
                f"exact={result['output_equivalence']['bit_exact']}",
                flush=True,
            )
    measurements.sort(key=lambda item: str(item["integration_method"]))
    variants = tuple(
        item[name]
        for item in measurements
        for name in ("baseline_minus_5_v", "expanded_minus_8_v")
    )
    baselines = tuple(item["baseline_minus_5_v"] for item in measurements)
    expanded = tuple(item["expanded_minus_8_v"] for item in measurements)
    gates = {
        "reason_classifier_matches_evaluator": all(
            int(item["tube"]["status_mismatch_count"]) == 0 for item in variants
        ),
        "all_outputs_finite": all(bool(item["output_finite"]) for item in variants),
        "baseline_events_are_only_low_plate_domain": all(
            int(item["tube"]["reported_clip_evaluation_count"]) > 0
            and int(item["tube"]["reason_count"]["v_gk_below_plate_domain"])
            == int(item["tube"]["reported_clip_evaluation_count"])
            and sum(
                int(count)
                for reason, count in item["tube"]["reason_count"].items()
                if reason != "v_gk_below_plate_domain"
            )
            == 0
            for item in baselines
        ),
        "expanded_domain_has_no_range_events": all(
            int(item["tube"]["reported_clip_evaluation_count"]) == 0
            and int(item["solver_range_clip_count"]) == 0
            for item in expanded
        ),
        "grid_current_lower_clamp_is_exercised": all(
            int(item["tube"]["grid_current_lower_clamp_count"]) > 0
            for item in expanded
        ),
        "domain_expansion_is_output_bit_exact": all(
            bool(item["output_equivalence"]["bit_exact"])
            for item in measurements
        ),
    }
    report = {
        "model": "12ax7_passive_riaa_v1",
        "study": "factorized plate-law cutoff-domain expansion audit",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "stimulus": {
            "frequency_hz": FREQUENCY_HZ,
            "nominal_peak_v": NOMINAL_PEAK_V,
            "burst_peak_v": BURST_PEAK_V,
            "burst_start_s": BURST_START_S,
            "burst_end_s": BURST_END_S,
            "duration_s": DURATION_S,
            "input_format": "Q8.24",
        },
        "factor_table_ranges": {
            "v_pk_v": [0.0, 400.0],
            "transformed": [-0.30, 0.08],
            "e1_v": [0.0, 6.0],
        },
        "interpretation": (
            "The plate law evaluates Vgk directly; only grid current uses the "
            "-5 V lookup boundary. Below -5 V that lookup clamps to its "
            "negative-grid leakage floor. Expanding the accepted plate-law "
            "domain to -8 V changes diagnostics only, not current or audio."
        ),
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "measurements": measurements,
    }
    generated = ROOT / "model" / "generated" / "factorized_domain_audit.json"
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    reference = ROOT / "reference" / "results" / "factorized_domain_audit.json"
    reference.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_gates_pass"]:
        raise RuntimeError("factorized domain audit failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
