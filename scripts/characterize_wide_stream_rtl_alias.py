#!/usr/bin/env python3
"""Measure nonlinear harmonic aliasing in captured stream/decimator RTL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

from design_resampler import tone_peak  # noqa: E402
from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedWideStateV1CircuitModel,
    round_shift,
    saturate_signed,
)
from fpga_amp.resampling import (  # noqa: E402
    decimate_16x_fixed_q24,
    interpolate_16x_fixed_q24,
)


EXTERNAL_RATE_HZ = 48_000.0
INTERNAL_RATE_HZ = 768_000.0
INPUT_FREQUENCY_HZ = 15_000.0
ALIAS_FREQUENCY_HZ = 3_000.0
INTERNAL_THIRD_HARMONIC_HZ = 45_000.0
INPUT_PEAK_V = 0.500
VECTOR_COUNT = 8192
ANALYSIS_COUNT = 4096


def tone_coefficients(
    values: np.ndarray,
    sample_rate_hz: float,
    frequency_hz: float,
    start_index: int = 0,
) -> np.ndarray:
    """Return phase-coherent sine/cosine coefficients after fitting DC."""

    index = start_index + np.arange(values.size, dtype=np.float64)
    angle = 2.0 * np.pi * frequency_hz * index / sample_rate_hz
    design = np.column_stack((np.ones(values.size), np.sin(angle), np.cos(angle)))
    coefficient, *_ = np.linalg.lstsq(design, values, rcond=None)
    return np.asarray(coefficient[1:3], dtype=np.float64)


def tone_from_coefficients(
    coefficient: np.ndarray,
    sample_count: int,
    sample_rate_hz: float,
    frequency_hz: float,
) -> np.ndarray:
    index = np.arange(sample_count, dtype=np.float64)
    angle = 2.0 * np.pi * frequency_hz * index / sample_rate_hz
    return coefficient[0] * np.sin(angle) + coefficient[1] * np.cos(angle)


def coefficient_report(coefficient: np.ndarray) -> dict[str, float]:
    return {
        "sine_coefficient_v": float(coefficient[0]),
        "cosine_coefficient_v": float(coefficient[1]),
        "peak_v": float(np.hypot(*coefficient)),
        "phase_deg": float(np.degrees(np.arctan2(coefficient[1], coefficient[0]))),
    }


def relative_db(numerator: float, denominator: float) -> float:
    return float(
        20.0
        * np.log10(max(abs(numerator), 1.0e-30) / max(abs(denominator), 1.0e-30))
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verilator", default="verilator")
    args = parser.parse_args()
    external_index = np.arange(VECTOR_COUNT, dtype=np.float64)
    input_q24 = np.rint(
        INPUT_PEAK_V
        * np.sin(2.0 * np.pi * INPUT_FREQUENCY_HZ * external_index / EXTERNAL_RATE_HZ)
        * (1 << 24)
    ).astype(np.int64)

    interpolated_q24, interpolation_saturations = interpolate_16x_fixed_q24(
        input_q24
    )
    internal_q24 = np.concatenate(
        (np.zeros(18, dtype=np.int64), interpolated_q24)
    )[: 16 * VECTOR_COUNT]
    model = FixedWideStateV1CircuitModel(tube_lut=FixedFactorizedKoren12AX7())
    circuit_output_q24 = np.empty(internal_q24.size, dtype=np.int64)
    conversion_saturations = 0
    for index, sample_q24 in enumerate(internal_q24):
        model.process_sample(int(sample_q24) / float(1 << 24))
        converted = round_shift(int(model.voltage_q[model.node["out"]]), 8)
        circuit_output_q24[index], clipped = saturate_signed(converted, 32)
        conversion_saturations += int(clipped)

    expected_q24, decimation_saturations = decimate_16x_fixed_q24(
        circuit_output_q24
    )
    expected_q24 = expected_q24[:VECTOR_COUNT]
    vector_path = (
        ROOT / "sim" / "vectors" / "generated" / "wide_stream_rtl_alias.txt"
    )
    vector_path.parent.mkdir(parents=True, exist_ok=True)
    with vector_path.open("w", encoding="ascii") as handle:
        for value in input_q24:
            handle.write(f"{int(value)}\n")
        handle.write("EXPECTED\n")
        for value in expected_q24:
            handle.write(f"{int(value)}\n")

    capture_path = ROOT / "build" / "wide_stream_rtl_alias_capture.txt"
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "scripts/run_wide_stream_rtl.py",
            "--verilator",
            args.verilator,
            "--skip-generate",
            "--vectors-file",
            str(vector_path.relative_to(ROOT)),
            "--vector-count",
            str(VECTOR_COUNT),
            "--capture-file",
            str(capture_path.relative_to(ROOT)),
        ],
        cwd=ROOT,
        check=True,
    )
    captured = np.atleast_2d(np.loadtxt(capture_path, dtype=np.int64))
    if captured.shape != (VECTOR_COUNT, 2):
        raise RuntimeError(f"expected {VECTOR_COUNT} outputs, got {captured.shape}")
    if not np.array_equal(captured[:, 0], np.arange(VECTOR_COUNT)):
        raise RuntimeError("captured output indices are not contiguous")
    if not np.array_equal(captured[:, 1], expected_q24):
        differing = np.flatnonzero(captured[:, 1] != expected_q24)
        raise RuntimeError(
            f"captured stream differs from fixed at output {int(differing[0])}"
        )

    external_selected = slice(VECTOR_COUNT - ANALYSIS_COUNT, VECTOR_COUNT)
    rtl_v = captured[:, 1].astype(np.float64) / float(1 << 24)
    external_measured = rtl_v[external_selected]
    fundamental_peak_v = tone_peak(
        external_measured, EXTERNAL_RATE_HZ, INPUT_FREQUENCY_HZ
    )
    alias_peak_v = tone_peak(
        external_measured, EXTERNAL_RATE_HZ, ALIAS_FREQUENCY_HZ
    )

    internal_analysis_count = 16 * ANALYSIS_COUNT
    internal_measured = (
        circuit_output_q24[-internal_analysis_count:].astype(np.float64)
        / float(1 << 24)
    )
    internal_fundamental_peak_v = tone_peak(
        internal_measured, INTERNAL_RATE_HZ, INPUT_FREQUENCY_HZ
    )
    internal_third_peak_v = tone_peak(
        internal_measured, INTERNAL_RATE_HZ, INTERNAL_THIRD_HARMONIC_HZ
    )
    internal_3khz_peak_v = tone_peak(
        internal_measured, INTERNAL_RATE_HZ, ALIAS_FREQUENCY_HZ
    )
    internal_start_index = circuit_output_q24.size - internal_analysis_count
    external_start_index = VECTOR_COUNT - ANALYSIS_COUNT
    alias_family_hz = sorted(
        {
            frequency_hz
            for offset_hz in (ALIAS_FREQUENCY_HZ, -ALIAS_FREQUENCY_HZ)
            for multiple in range(9)
            if 0.0
            < (frequency_hz := multiple * EXTERNAL_RATE_HZ + offset_hz)
            < INTERNAL_RATE_HZ / 2.0
        }
    )
    internal_alias_coefficients = {
        frequency_hz: tone_coefficients(
            internal_measured,
            INTERNAL_RATE_HZ,
            frequency_hz,
            internal_start_index,
        )
        for frequency_hz in alias_family_hz
    }
    internal_3khz_coefficient = internal_alias_coefficients[ALIAS_FREQUENCY_HZ]
    naive_q24 = circuit_output_q24[::16][:VECTOR_COUNT]
    naive_measured = (
        naive_q24[external_selected].astype(np.float64) / float(1 << 24)
    )
    naive_alias_peak_v = tone_peak(
        naive_measured, EXTERNAL_RATE_HZ, ALIAS_FREQUENCY_HZ
    )
    naive_fundamental_peak_v = tone_peak(
        naive_measured, EXTERNAL_RATE_HZ, INPUT_FREQUENCY_HZ
    )

    # The decimator is linear apart from explicit fixed rounding. Reconstruct
    # every phase-coherent internal component that aliases to +/-3 kHz after
    # 16x downsampling, pass each through the exact fixed chain, and capture
    # their combined projection in RTL. This distinguishes the genuine in-band
    # component from the complete folded alias family.
    isolated_output_q24: dict[float, np.ndarray] = {}
    isolated_saturation_counts: dict[float, int] = {}
    isolated_combined_q24 = np.zeros(circuit_output_q24.size, dtype=np.int64)
    for frequency_hz in alias_family_hz:
        component_q24 = np.rint(
            tone_from_coefficients(
                internal_alias_coefficients[frequency_hz],
                circuit_output_q24.size,
                INTERNAL_RATE_HZ,
                frequency_hz,
            )
            * (1 << 24)
        ).astype(np.int64)
        output_q24, saturation_count = decimate_16x_fixed_q24(component_q24)
        isolated_output_q24[frequency_hz] = output_q24[:VECTOR_COUNT]
        isolated_saturation_counts[frequency_hz] = saturation_count
        if frequency_hz != ALIAS_FREQUENCY_HZ:
            isolated_combined_q24 += component_q24
    isolated_combined_output_q24, isolated_combined_saturations = (
        decimate_16x_fixed_q24(isolated_combined_q24)
    )
    isolated_combined_output_q24 = isolated_combined_output_q24[:VECTOR_COUNT]
    without_folded_q24 = circuit_output_q24 - isolated_combined_q24
    without_folded_output_q24, without_folded_saturations = decimate_16x_fixed_q24(
        without_folded_q24
    )
    without_folded_output_q24 = without_folded_output_q24[:VECTOR_COUNT]

    isolated_vector_path = (
        ROOT / "sim" / "vectors" / "generated" / "decimator_16x_alias_isolated.txt"
    )
    with isolated_vector_path.open("w", encoding="ascii") as handle:
        for value in isolated_combined_q24:
            handle.write(f"{int(value)}\n")
        handle.write("EXPECTED\n")
        for value in isolated_combined_output_q24:
            handle.write(f"{int(value)}\n")
    isolated_capture_path = (
        ROOT / "build" / "decimator_16x_alias_isolated_capture.txt"
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/run_decimator_16x_rtl.py",
            "--verilator",
            args.verilator,
            "--skip-generate",
            "--vectors-file",
            str(isolated_vector_path.relative_to(ROOT)),
            "--input-count",
            str(isolated_combined_q24.size),
            "--output-count",
            str(VECTOR_COUNT),
            "--capture-file",
            str(isolated_capture_path.relative_to(ROOT)),
        ],
        cwd=ROOT,
        check=True,
    )
    isolated_captured = np.atleast_2d(
        np.loadtxt(isolated_capture_path, dtype=np.int64)
    )
    if isolated_captured.shape != (VECTOR_COUNT, 2):
        raise RuntimeError(
            f"expected {VECTOR_COUNT} isolated outputs, got {isolated_captured.shape}"
        )
    if not np.array_equal(isolated_captured[:, 0], np.arange(VECTOR_COUNT)):
        raise RuntimeError("isolated decimator capture indices are not contiguous")
    if not np.array_equal(isolated_captured[:, 1], isolated_combined_output_q24):
        differing = np.flatnonzero(
            isolated_captured[:, 1] != isolated_combined_output_q24
        )
        raise RuntimeError(
            "isolated decimator RTL differs from fixed at output "
            f"{int(differing[0])}"
        )

    actual_3khz_coefficient = tone_coefficients(
        external_measured,
        EXTERNAL_RATE_HZ,
        ALIAS_FREQUENCY_HZ,
        external_start_index,
    )
    isolated_output_coefficients = {
        frequency_hz: tone_coefficients(
            output_q24[external_selected].astype(np.float64) / float(1 << 24),
            EXTERNAL_RATE_HZ,
            ALIAS_FREQUENCY_HZ,
            external_start_index,
        )
        for frequency_hz, output_q24 in isolated_output_q24.items()
    }
    isolated_3khz_coefficient = isolated_output_coefficients[
        ALIAS_FREQUENCY_HZ
    ]
    isolated_45khz_coefficient = isolated_output_coefficients[
        INTERNAL_THIRD_HARMONIC_HZ
    ]
    isolated_combined_coefficient = tone_coefficients(
        isolated_captured[external_selected, 1].astype(np.float64)
        / float(1 << 24),
        EXTERNAL_RATE_HZ,
        ALIAS_FREQUENCY_HZ,
        external_start_index,
    )
    folded_alias_coefficient = np.sum(
        np.stack(
            [
                coefficient
                for frequency_hz, coefficient in isolated_output_coefficients.items()
                if frequency_hz != ALIAS_FREQUENCY_HZ
            ]
        ),
        axis=0,
    )
    independent_sum_coefficient = folded_alias_coefficient
    rounding_closure_coefficient = (
        isolated_combined_coefficient - independent_sum_coefficient
    )
    without_folded_coefficient = tone_coefficients(
        without_folded_output_q24[external_selected].astype(np.float64)
        / float(1 << 24),
        EXTERNAL_RATE_HZ,
        ALIAS_FREQUENCY_HZ,
        external_start_index,
    )
    complete_minus_without_coefficient = tone_coefficients(
        (
            expected_q24[external_selected] - without_folded_output_q24[external_selected]
        ).astype(np.float64)
        / float(1 << 24),
        EXTERNAL_RATE_HZ,
        ALIAS_FREQUENCY_HZ,
        external_start_index,
    )
    subtraction_rounding_closure_coefficient = (
        complete_minus_without_coefficient - isolated_combined_coefficient
    )
    folded_45khz_peak_v = float(np.hypot(*isolated_45khz_coefficient))
    folded_alias_peak_v = float(np.hypot(*folded_alias_coefficient))
    nonfolded_3khz_peak_v = float(np.hypot(*without_folded_coefficient))
    observed_fold_effect_peak_v = float(
        np.hypot(*complete_minus_without_coefficient)
    )
    alias_family_components = []
    for frequency_hz in alias_family_hz:
        internal_coefficient = internal_alias_coefficients[frequency_hz]
        output_coefficient = isolated_output_coefficients[frequency_hz]
        input_peak_v = float(np.hypot(*internal_coefficient))
        output_peak_v = float(np.hypot(*output_coefficient))
        alias_family_components.append(
            {
                "internal_frequency_hz": frequency_hz,
                "in_band_preexisting_component": (
                    frequency_hz == ALIAS_FREQUENCY_HZ
                ),
                "internal": coefficient_report(internal_coefficient),
                "isolated_3khz_output": coefficient_report(output_coefficient),
                "decimator_attenuation_db": (
                    relative_db(output_peak_v, input_peak_v)
                    if output_peak_v > 0.0
                    else None
                ),
                "output_is_exact_zero_in_analysis_window": output_peak_v == 0.0,
                "decimation_saturation_count": isolated_saturation_counts[
                    frequency_hz
                ],
            }
        )

    # The complete tube trajectory contains a genuine 3 kHz component before
    # decimation, so its output bin cannot isolate 45 -> 3 kHz aliasing. Exercise
    # the exact RTL decimator separately with the established cubic stimulus.
    cubic_external_q24 = np.rint(
        0.8
        * np.sin(
            2.0
            * np.pi
            * INPUT_FREQUENCY_HZ
            * external_index
            / EXTERNAL_RATE_HZ
        )
        * (1 << 24)
    ).astype(np.int64)
    cubic_internal_q24, cubic_interpolation_saturations = (
        interpolate_16x_fixed_q24(cubic_external_q24)
    )
    cubic_internal_q24 = cubic_internal_q24[: 16 * VECTOR_COUNT]
    cubic_internal_v = cubic_internal_q24.astype(np.float64) / float(1 << 24)
    cubic_nonlinear_q24 = np.rint(
        (cubic_internal_v + 0.5 * np.power(cubic_internal_v, 3)) * (1 << 24)
    ).astype(np.int64)
    cubic_expected_q24, cubic_decimation_saturations = decimate_16x_fixed_q24(
        cubic_nonlinear_q24
    )
    cubic_expected_q24 = cubic_expected_q24[:VECTOR_COUNT]
    cubic_vector_path = (
        ROOT / "sim" / "vectors" / "generated" / "decimator_16x_alias.txt"
    )
    with cubic_vector_path.open("w", encoding="ascii") as handle:
        for value in cubic_nonlinear_q24:
            handle.write(f"{int(value)}\n")
        handle.write("EXPECTED\n")
        for value in cubic_expected_q24:
            handle.write(f"{int(value)}\n")
    cubic_capture_path = ROOT / "build" / "decimator_16x_alias_capture.txt"
    subprocess.run(
        [
            sys.executable,
            "scripts/run_decimator_16x_rtl.py",
            "--verilator",
            args.verilator,
            "--skip-generate",
            "--vectors-file",
            str(cubic_vector_path.relative_to(ROOT)),
            "--input-count",
            str(cubic_nonlinear_q24.size),
            "--output-count",
            str(VECTOR_COUNT),
            "--capture-file",
            str(cubic_capture_path.relative_to(ROOT)),
        ],
        cwd=ROOT,
        check=True,
    )
    cubic_captured = np.atleast_2d(
        np.loadtxt(cubic_capture_path, dtype=np.int64)
    )
    if cubic_captured.shape != (VECTOR_COUNT, 2):
        raise RuntimeError(
            f"expected {VECTOR_COUNT} decimator outputs, got {cubic_captured.shape}"
        )
    if not np.array_equal(cubic_captured[:, 0], np.arange(VECTOR_COUNT)):
        raise RuntimeError("captured decimator indices are not contiguous")
    if not np.array_equal(cubic_captured[:, 1], cubic_expected_q24):
        differing = np.flatnonzero(cubic_captured[:, 1] != cubic_expected_q24)
        raise RuntimeError(
            f"captured decimator differs from fixed at output {int(differing[0])}"
        )
    cubic_measured = (
        cubic_captured[external_selected, 1].astype(np.float64) / float(1 << 24)
    )
    cubic_fundamental_peak = tone_peak(
        cubic_measured, EXTERNAL_RATE_HZ, INPUT_FREQUENCY_HZ
    )
    cubic_alias_peak = tone_peak(
        cubic_measured, EXTERNAL_RATE_HZ, ALIAS_FREQUENCY_HZ
    )
    cubic_alias_relative_db = float(
        20.0 * np.log10(cubic_alias_peak / cubic_fundamental_peak)
    )

    report = {
        "model": "12ax7_passive_riaa_v1",
        "implementation": "captured SystemVerilog wide stream and 16x decimator",
        "stimulus": {
            "input_peak_v": INPUT_PEAK_V,
            "input_frequency_hz": INPUT_FREQUENCY_HZ,
            "external_rate_hz": EXTERNAL_RATE_HZ,
            "internal_rate_hz": INTERNAL_RATE_HZ,
            "vectors": VECTOR_COUNT,
            "analysis_vectors": ANALYSIS_COUNT,
            "quantized_input": "Q8.24",
        },
        "rtl_fixed_bit_exact": True,
        "internal_solver_output": {
            "fundamental_peak_v": internal_fundamental_peak_v,
            "preexisting_3khz_peak_v": internal_3khz_peak_v,
            "third_harmonic_frequency_hz": INTERNAL_THIRD_HARMONIC_HZ,
            "third_harmonic_peak_v": internal_third_peak_v,
            "third_harmonic_relative_db": float(
                20.0
                * np.log10(internal_third_peak_v / internal_fundamental_peak_v)
            ),
        },
        "naive_16x_downsample": {
            "fundamental_peak_v": naive_fundamental_peak_v,
            "alias_frequency_hz": ALIAS_FREQUENCY_HZ,
            "alias_peak_v": naive_alias_peak_v,
            "alias_relative_db": float(
                20.0 * np.log10(naive_alias_peak_v / naive_fundamental_peak_v)
            ),
        },
        "captured_filtered_output": {
            "fundamental_peak_v": fundamental_peak_v,
            "alias_frequency_hz": ALIAS_FREQUENCY_HZ,
            "alias_peak_v": alias_peak_v,
            "alias_relative_db": float(
                20.0 * np.log10(alias_peak_v / fundamental_peak_v)
            ),
            "observed_3khz_change_vs_naive_db": float(
                20.0 * np.log10(alias_peak_v / naive_alias_peak_v)
            ),
            "interpretation": (
                "raw bin is not an isolated alias measurement because 3 kHz "
                "exists at the internal solver output; the phase-coherent "
                "family decomposition below separates the contributions"
            ),
        },
        "phase_coherent_3khz_decomposition": {
            "method": (
                "least-squares sine/cosine projection of every internal "
                "frequency that maps to +/-3 kHz, followed by independent "
                "exact fixed decimation; the combined out-of-band projection "
                "is captured from RTL and subtracted before a second full "
                "fixed decimation"
            ),
            "alias_family_hz": alias_family_hz,
            "components": alias_family_components,
            "actual_complete_stream_3khz_output": coefficient_report(
                actual_3khz_coefficient
            ),
            "output_from_isolated_preexisting_3khz": coefficient_report(
                isolated_3khz_coefficient
            ),
            "output_from_isolated_45khz_fold": coefficient_report(
                isolated_45khz_coefficient
            ),
            "phase_sum_of_all_out_of_band_folded_components": coefficient_report(
                folded_alias_coefficient
            ),
            "output_from_combined_out_of_band_components_rtl": coefficient_report(
                isolated_combined_coefficient
            ),
            "isolated_fixed_superposition_closure": coefficient_report(
                rounding_closure_coefficient
            ),
            "output_with_out_of_band_family_removed": coefficient_report(
                without_folded_coefficient
            ),
            "complete_minus_family_removed_output": coefficient_report(
                complete_minus_without_coefficient
            ),
            "subtraction_rounding_closure": coefficient_report(
                subtraction_rounding_closure_coefficient
            ),
            "45khz_fold_is_exact_zero_in_fixed_output_window": (
                folded_45khz_peak_v == 0.0
            ),
            "aggregate_folded_alias_relative_to_output_fundamental_db": relative_db(
                folded_alias_peak_v, fundamental_peak_v
            ),
            "family_removed_3khz_to_aggregate_folded_alias_ratio_db": relative_db(
                nonfolded_3khz_peak_v, folded_alias_peak_v
            ),
            "observed_fold_effect_relative_to_output_fundamental_db": relative_db(
                observed_fold_effect_peak_v, fundamental_peak_v
            ),
            "family_removed_3khz_to_observed_fold_effect_ratio_db": relative_db(
                nonfolded_3khz_peak_v, observed_fold_effect_peak_v
            ),
            "rtl_fixed_bit_exact": True,
            "isolated_component_decimation_saturation_total": sum(
                isolated_saturation_counts.values()
            ),
            "isolated_combined_decimation_saturation_count": (
                isolated_combined_saturations
            ),
            "family_removed_decimation_saturation_count": without_folded_saturations,
        },
        "captured_cubic_decimator_test": {
            "stimulus": "interpolated 0.8-peak 15 kHz, y=x+0.5*x^3",
            "generated_internal_harmonic_hz": INTERNAL_THIRD_HARMONIC_HZ,
            "alias_frequency_hz": ALIAS_FREQUENCY_HZ,
            "fundamental_peak": cubic_fundamental_peak,
            "alias_peak": cubic_alias_peak,
            "alias_relative_db": cubic_alias_relative_db,
            "rtl_fixed_bit_exact": True,
            "interpolation_saturation_count": cubic_interpolation_saturations,
            "decimation_saturation_count": cubic_decimation_saturations,
        },
        "diagnostics": {
            "interpolation_saturation_count": interpolation_saturations,
            "output_conversion_saturation_count": conversion_saturations,
            "decimation_saturation_count": decimation_saturations,
            "solver_saturation_count": model.saturation_count,
            "solver_range_clip_count": model.lut_clip_count,
            "solver_residual_limit_exceedance_count": model.nonconvergence_count,
            "solver_correction_scale_fallback_count": (
                model.correction_scale_fallback_count
            ),
            "maximum_solver_residual_a": model.max_residual_q44_observed
            / float(1 << 44),
        },
    }
    if any(
        int(value)
        for value in report["diagnostics"].values()
        if isinstance(value, int)
    ):
        raise RuntimeError("nominal alias trajectory produced a diagnostic event")
    if cubic_interpolation_saturations or cubic_decimation_saturations:
        raise RuntimeError("cubic alias test saturated")
    if any(
        (
            *isolated_saturation_counts.values(),
            isolated_combined_saturations,
            without_folded_saturations,
        )
    ):
        raise RuntimeError("isolated alias decomposition saturated")
    if cubic_alias_relative_db >= -120.0:
        raise RuntimeError("captured decimator alias rejection is below 120 dB")
    if relative_db(observed_fold_effect_peak_v, fundamental_peak_v) >= -150.0:
        raise RuntimeError("complete-stream folded-family effect exceeds -150 dBc")
    if relative_db(nonfolded_3khz_peak_v, observed_fold_effect_peak_v) <= 90.0:
        raise RuntimeError("nonfolded 3 kHz output does not dominate by 90 dB")
    summary = ROOT / "model" / "generated" / "wide_stream_rtl_alias_summary.json"
    summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    result = ROOT / "reference" / "results" / "wide_stream_rtl_alias.json"
    result.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
