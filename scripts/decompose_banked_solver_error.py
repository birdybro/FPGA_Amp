#!/usr/bin/env python3
"""Decompose banked fixed error into tube and circuit numerical layers."""

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
from fpga_amp.factorized_tube import (  # noqa: E402
    FactorizedKoren12AX7,
    FixedFactorizedKoren12AX7,
)
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedWideStateBankedChordV1CircuitModel,
)
from fpga_amp.v1_circuit import V1CircuitModel  # noqa: E402


LEVELS_PEAK_V = (1.0, 1.5)
INTEGRATION_METHODS = ("backward_euler", "trapezoidal")


class ContinuousQuantizedFactorizedTube:
    """Smoothly interpolate the fixed model's quantized table coefficients.

    This isolates stored-coefficient quantization without putting a
    discontinuous integer device law inside a floating Newton solve.
    """

    def __init__(
        self,
        fixed: FixedFactorizedKoren12AX7,
        *,
        quantize_plate: bool = True,
        quantize_grid: bool = True,
    ):
        self.fixed = fixed
        self.tube = fixed.tube
        self.floating = FactorizedKoren12AX7(interpolation="hermite")
        self.quantize_plate = quantize_plate
        self.quantize_grid = quantize_grid
        self.plate_axis = np.linspace(
            fixed.plate_min_v, fixed.plate_max_v, fixed.reciprocal_points
        )
        self.transformed_axis = np.linspace(
            fixed.transformed_min,
            fixed.transformed_max,
            fixed.softplus_points,
        )
        self.e1_axis = np.linspace(
            fixed.e1_min_v, fixed.e1_max_v, fixed.power_points
        )
        self.grid_axis = np.linspace(
            fixed.grid_v_gk_min_v, fixed.v_gk_max_v, fixed.grid_points
        )

    @staticmethod
    def _hermite(
        values: object,
        axis: np.ndarray,
        value_q: np.ndarray,
        slope_q: np.ndarray,
        fractional_bits: int,
    ) -> np.ndarray:
        query = np.asarray(values, dtype=np.float64)
        coordinate = (
            np.clip(query, axis[0], axis[-1]) - axis[0]
        ) / float(axis[1] - axis[0])
        lower = np.minimum(np.floor(coordinate).astype(np.int64), axis.size - 2)
        fraction = coordinate - lower
        fraction_2 = np.square(fraction)
        fraction_3 = fraction_2 * fraction
        scale = float(1 << fractional_bits)
        y0 = value_q[lower] / scale
        y1 = value_q[lower + 1] / scale
        m0 = slope_q[lower] / scale
        m1 = slope_q[lower + 1] / scale
        return (
            (2.0 * fraction_3 - 3.0 * fraction_2 + 1.0) * y0
            + (fraction_3 - 2.0 * fraction_2 + fraction) * m0
            + (-2.0 * fraction_3 + 3.0 * fraction_2) * y1
            + (fraction_3 - fraction_2) * m1
        )

    def plate_current(self, v_gk: object, v_pk: object) -> np.ndarray:
        if not self.quantize_plate:
            return self.floating.plate_current(v_gk, v_pk)
        grid = np.asarray(v_gk, dtype=np.float64)
        plate = np.maximum(np.asarray(v_pk, dtype=np.float64), 0.0)
        reciprocal = self._hermite(
            plate,
            self.plate_axis,
            self.fixed.reciprocal_value_q32,
            self.fixed.reciprocal_slope_q32,
            self.fixed.reciprocal_fractional_bits,
        )
        transformed = 1.0 / self.tube.mu + grid * reciprocal
        softplus = self._hermite(
            transformed,
            self.transformed_axis,
            self.fixed.softplus_value_q32,
            self.fixed.softplus_slope_q32,
            self.fixed.softplus_fractional_bits,
        )
        e1 = plate * softplus
        current = self._hermite(
            e1,
            self.e1_axis,
            self.fixed.power_value_q31,
            self.fixed.power_slope_q31,
            self.fixed.current_fractional_bits,
        )
        return np.where(plate > 0.0, current, 0.0)

    def grid_current(self, v_gk: object) -> np.ndarray:
        if not self.quantize_grid:
            return self.tube.grid_current(v_gk)
        return np.interp(
            np.asarray(v_gk, dtype=np.float64),
            self.grid_axis,
            self.fixed.grid_value_q31
            / float(1 << self.fixed.current_fractional_bits),
        )


class ContinuousQuantizedFixedInterfaceTube:
    """Expose continuous quantized coefficients through the fixed tube API.

    Inputs still use the exact Q24/Q20 circuit boundary and outputs are rounded
    to Q31, but the three Hermite functions are evaluated continuously.  A
    fixed-circuit run with this adapter therefore isolates node, capacitor,
    coefficient, and chord arithmetic from the integer Hermite datapath.
    """

    def __init__(self, fixed: FixedFactorizedKoren12AX7):
        self.fixed = fixed
        self.continuous = ContinuousQuantizedFactorizedTube(fixed)

    def evaluate_fixed(
        self, v_gk_q: int, v_pk_q: int
    ) -> tuple[int, int, bool]:
        v_gk = v_gk_q / float(1 << self.fixed.v_gk_fractional_bits)
        v_pk = v_pk_q / float(1 << self.fixed.v_pk_fractional_bits)
        scale = 1 << self.fixed.current_fractional_bits
        plate_q31 = int(
            np.rint(float(self.continuous.plate_current(v_gk, v_pk)) * scale)
        )
        grid_q31 = int(
            np.rint(float(self.continuous.grid_current(v_gk)) * scale)
        )
        current_max = (1 << 31) - 1
        plate_q31 = min(max(plate_q31, 0), current_max)
        grid_q31 = min(max(grid_q31, -(1 << 31)), current_max)
        # Reuse the production evaluator's independent external and transformed
        # domain guards, while deliberately discarding its integer currents.
        _, _, clipped = self.fixed.evaluate_fixed(v_gk_q, v_pk_q)
        return plate_q31, grid_q31, clipped

    def evaluate(self, v_gk: float, v_pk: float) -> tuple[float, float, bool]:
        v_gk_q = int(round(v_gk * (1 << self.fixed.v_gk_fractional_bits)))
        v_pk_q = int(round(v_pk * (1 << self.fixed.v_pk_fractional_bits)))
        plate_q31, grid_q31, clipped = self.evaluate_fixed(v_gk_q, v_pk_q)
        scale = float(1 << self.fixed.current_fractional_bits)
        return plate_q31 / scale, grid_q31 / scale, clipped


def run_case(integration_method: str, level_peak_v: float) -> dict[str, object]:
    time_s = np.arange(int(round(DURATION_S * SAMPLE_RATE_HZ))) / SAMPLE_RATE_HZ
    input_q24 = input_trajectory_q24(level_peak_v)
    stimulus = input_q24.astype(np.float64) / float(1 << 24)
    masks = {
        "burst": (time_s >= BURST_START_S) & (time_s < BURST_END_S),
        "complete_post_burst": time_s >= BURST_END_S,
        "final_10ms": time_s >= DURATION_S - 0.010,
    }

    analytical_model = V1CircuitModel(
        SAMPLE_RATE_HZ, integration_method=integration_method
    )
    analytical = analytical_model.process(
        stimulus, max_iterations=8, tolerance_a=1.0e-12
    )
    factorized_model = V1CircuitModel(
        SAMPLE_RATE_HZ,
        tube=FactorizedKoren12AX7(interpolation="hermite"),
        dc_tolerance_a=1.0e-10,
        integration_method=integration_method,
    )
    factorized = factorized_model.process(
        stimulus, max_iterations=8, tolerance_a=1.0e-12
    )

    fixed_tube = FixedFactorizedKoren12AX7()
    quantized_outputs: dict[str, np.ndarray] = {}
    quantized_models: dict[str, V1CircuitModel] = {}
    for name, quantize_plate, quantize_grid in (
        ("plate_coefficients_only", True, False),
        ("grid_coefficients_only", False, True),
        ("all_coefficients", True, True),
    ):
        model = V1CircuitModel(
            SAMPLE_RATE_HZ,
            tube=ContinuousQuantizedFactorizedTube(  # type: ignore[arg-type]
                fixed_tube,
                quantize_plate=quantize_plate,
                quantize_grid=quantize_grid,
            ),
            dc_tolerance_a=1.0e-10,
            integration_method=integration_method,
        )
        quantized_outputs[name] = model.process(
            stimulus, max_iterations=8, tolerance_a=1.0e-12
        )
        quantized_models[name] = model
    quantized_tables = quantized_outputs["all_coefficients"]
    continuous_evaluator_fixed_model = FixedWideStateBankedChordV1CircuitModel(
        SAMPLE_RATE_HZ,
        tube_lut=ContinuousQuantizedFixedInterfaceTube(fixed_tube),
        integration_method=integration_method,
    )
    continuous_evaluator_fixed = continuous_evaluator_fixed_model.process(
        stimulus, max_iterations=3, residual_limit_a=2.0e-6
    )
    fixed_model = FixedWideStateBankedChordV1CircuitModel(
        SAMPLE_RATE_HZ,
        tube_lut=fixed_tube,
        integration_method=integration_method,
    )
    fixed = fixed_model.process(
        stimulus, max_iterations=3, residual_limit_a=2.0e-6
    )

    layers = (
        ("factorized_tables", analytical, factorized),
        ("quantized_table_coefficients", factorized, quantized_tables),
        (
            "fixed_circuit_state_and_chord",
            quantized_tables,
            continuous_evaluator_fixed,
        ),
        (
            "integer_tube_evaluation",
            continuous_evaluator_fixed,
            fixed,
        ),
        ("total_fixed_vs_analytical", analytical, fixed),
    )
    closure = (
        (factorized - analytical)
        + (quantized_tables - factorized)
        + (continuous_evaluator_fixed - quantized_tables)
        + (fixed - continuous_evaluator_fixed)
        - (fixed - analytical)
    )
    window_results: dict[str, object] = {}
    for window_name, mask in masks.items():
        layer_metrics = {
            name: waveform_metrics(candidate, reference, mask)
            for name, reference, candidate in layers
        }
        component_names = (
            "factorized_tables",
            "quantized_table_coefficients",
            "fixed_circuit_state_and_chord",
            "integer_tube_evaluation",
        )
        dominant = max(
            component_names,
            key=lambda name: float(layer_metrics[name]["raw_error_rms_v"]),
        )
        coefficient_ab = {
            name: waveform_metrics(candidate, factorized, mask)
            for name, candidate in quantized_outputs.items()
        }
        window_results[window_name] = {
            "layers": layer_metrics,
            "coefficient_ab_vs_floating_factorized": coefficient_ab,
            "dominant_coefficient_group_by_independent_raw_rms": max(
                ("plate_coefficients_only", "grid_coefficients_only"),
                key=lambda name: float(
                    coefficient_ab[name]["raw_error_rms_v"]
                ),
            ),
            "dominant_component_by_raw_rms": dominant,
            "component_sum_closure_maximum_absolute_v": float(
                np.max(np.abs(closure[mask]))
            ),
        }

    return {
        "integration_method": integration_method,
        "burst_input_peak_v": level_peak_v,
        "windows": window_results,
        "diagnostics": {
            "analytical_nonconvergence_count": (
                analytical_model.nonconvergence_count
            ),
            "factorized_float_nonconvergence_count": (
                factorized_model.nonconvergence_count
            ),
            "quantized_table_float_nonconvergence_count": {
                name: model.nonconvergence_count
                for name, model in quantized_models.items()
            },
            "fixed_residual_limit_exceedance_count": (
                fixed_model.nonconvergence_count
            ),
            "fixed_saturation_count": fixed_model.saturation_count,
            "fixed_range_clip_count": fixed_model.lut_clip_count,
            "fixed_correction_scale_fallback_count": (
                fixed_model.correction_scale_fallback_count
            ),
            "continuous_evaluator_fixed_residual_limit_exceedance_count": (
                continuous_evaluator_fixed_model.nonconvergence_count
            ),
            "continuous_evaluator_fixed_saturation_count": (
                continuous_evaluator_fixed_model.saturation_count
            ),
            "continuous_evaluator_fixed_range_clip_count": (
                continuous_evaluator_fixed_model.lut_clip_count
            ),
            "continuous_evaluator_fixed_correction_scale_fallback_count": (
                continuous_evaluator_fixed_model.correction_scale_fallback_count
            ),
        },
    }


def main() -> int:
    jobs = [
        (method, level)
        for method in INTEGRATION_METHODS
        for level in LEVELS_PEAK_V
    ]
    measurements: list[dict[str, object]] = []
    workers = min(len(jobs), max(1, min(os.cpu_count() or 1, 4)))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_case, *job): job for job in jobs}
        for future in as_completed(futures):
            result = future.result()
            measurements.append(result)
            final = result["windows"]["final_10ms"]
            total = final["layers"]["total_fixed_vs_analytical"]
            print(
                f"{result['integration_method']} "
                f"{result['burst_input_peak_v']:.1f} V: "
                f"final={total['raw_error_rms_v'] * 1e3:.3f} mV, "
                f"dominant={final['dominant_component_by_raw_rms']}",
                flush=True,
            )
    measurements.sort(
        key=lambda item: (
            str(item["integration_method"]),
            float(item["burst_input_peak_v"]),
        )
    )
    gates = {
        "analytical_and_factorized_float_converged": all(
            int(item["diagnostics"][key]) == 0
            for item in measurements
            for key in (
                "analytical_nonconvergence_count",
                "factorized_float_nonconvergence_count",
            )
        ),
        "quantized_table_float_converged": all(
            int(count) == 0
            for item in measurements
            for count in item["diagnostics"][
                "quantized_table_float_nonconvergence_count"
            ].values()
        ),
        "banked_fixed_diagnostics_clean": all(
            int(item["diagnostics"][key]) == 0
            for item in measurements
            for key in (
                "fixed_residual_limit_exceedance_count",
                "fixed_saturation_count",
                "fixed_range_clip_count",
                "fixed_correction_scale_fallback_count",
            )
        ),
        "continuous_evaluator_fixed_diagnostics_clean": all(
            int(item["diagnostics"][key]) == 0
            for item in measurements
            for key in (
                "continuous_evaluator_fixed_residual_limit_exceedance_count",
                "continuous_evaluator_fixed_saturation_count",
                "continuous_evaluator_fixed_range_clip_count",
                "continuous_evaluator_fixed_correction_scale_fallback_count",
            )
        ),
        "component_sum_is_numerically_exact": all(
            float(window["component_sum_closure_maximum_absolute_v"])
            <= 1.0e-12
            for item in measurements
            for window in item["windows"].values()
        ),
    }
    report = {
        "model": "12ax7_passive_riaa_v1",
        "study": "banked fixed severe-overload error decomposition",
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
        "layers": [
            "analytical Koren full Newton",
            "floating cubic-Hermite factorized Koren full Newton",
            "quantized fixed-table coefficients with continuous interpolation",
            "banked fixed circuit using continuous coefficients at Q24/Q20 and Q31 interfaces",
            "bit-accurate banked fixed circuit and three-pass chord",
        ],
        "rejected_intermediate": (
            "The exact integer tube law is discontinuous in floating nodal "
            "voltage and cannot serve as a converged Newton reference; use the "
            "continuous quantized-coefficient layer above."
        ),
        "alignment": {"gain": False, "dc": False, "delay": False},
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "measurements": measurements,
    }
    generated = ROOT / "model" / "generated" / "banked_error_decomposition.json"
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    reference = ROOT / "reference" / "results" / "banked_error_decomposition.json"
    reference.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_gates_pass"]:
        raise RuntimeError("banked error decomposition gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
