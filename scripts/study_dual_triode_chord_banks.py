#!/usr/bin/env python3
"""Test chord banks derived from both triodes' physical operating points.

The accepted bank changes only the stage-two tube Jacobian while leaving stage
one at DC.  This study derives alternative fixed matrices from medians of the
full-Newton trajectory.  Matrix selection and the 127-clock solver schedule are
unchanged; the alternatives therefore isolate coefficient choice from solver
latency.
"""

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
BASELINE_POLICY = "stage2_only_baseline"


def _sample_start_bank(v_gk2_v: float) -> int:
    regimes = (
        FixedWideStateBankedChordV1CircuitModel
        .TRAPEZOIDAL_CUTOFF_JACOBIAN_REGIMES
    )
    for bank_index, (upper_v, _, _) in enumerate(regimes):
        if v_gk2_v < upper_v:
            return bank_index
    return len(regimes)


def profile_reference(level_peak_v: float) -> dict[str, object]:
    """Run full Newton and capture the sample-start tube operating points."""

    input_q24 = input_trajectory_q24(level_peak_v)
    stimulus = input_q24.astype(np.float64) / float(1 << 24)
    model = V1CircuitModel(SAMPLE_RATE_HZ, integration_method="trapezoidal")
    output = np.empty_like(stimulus)
    all_points: list[list[list[float]]] = [[] for _ in range(4)]
    burst_points: list[list[list[float]]] = [[] for _ in range(4)]
    burst_start = int(round(BURST_START_S * SAMPLE_RATE_HZ))
    burst_end = int(round(BURST_END_S * SAMPLE_RATE_HZ))

    for sample_index, input_v in enumerate(stimulus):
        nodes = model.nodes
        point = [
            nodes["g1"] - nodes["k1"],
            nodes["p1"] - nodes["k1"],
            nodes["g2"] - nodes["k2"],
            nodes["p2"] - nodes["k2"],
        ]
        bank_index = _sample_start_bank(point[2])
        if bank_index < len(all_points):
            all_points[bank_index].append(point)
            if burst_start <= sample_index < burst_end:
                burst_points[bank_index].append(point)
        output[sample_index] = model.process_sample(
            float(input_v), max_iterations=8, tolerance_a=1.0e-12
        )

    return {
        "burst_input_peak_v": level_peak_v,
        "reference_output": output,
        "analytical_nonconvergence_count": model.nonconvergence_count,
        "all_points": [np.asarray(points) for points in all_points],
        "burst_points": [np.asarray(points) for points in burst_points],
    }


def _median_representatives(
    profiles: list[dict[str, object]],
    point_key: str,
) -> list[tuple[float, float, float, float]]:
    representatives: list[tuple[float, float, float, float]] = []
    for bank_index in range(4):
        points = np.concatenate(
            [profile[point_key][bank_index] for profile in profiles], axis=0
        )
        median = np.median(points, axis=0)
        representatives.append(tuple(float(value) for value in median))
    return representatives


def _representative_metadata(
    profiles: list[dict[str, object]],
    point_key: str,
    representatives: list[tuple[float, float, float, float]],
) -> list[dict[str, object]]:
    metadata: list[dict[str, object]] = []
    for bank_index, representative in enumerate(representatives):
        points = np.concatenate(
            [profile[point_key][bank_index] for profile in profiles], axis=0
        )
        metadata.append(
            {
                "bank_index": bank_index,
                "sample_count": int(points.shape[0]),
                "median_vgk1_vpk1_vgk2_vpk2_v": list(representative),
                "p10_vgk1_v": float(np.percentile(points[:, 0], 10.0)),
                "p90_vgk1_v": float(np.percentile(points[:, 0], 90.0)),
            }
        )
    return metadata


def _split_representatives(
    profiles: list[dict[str, object]],
    point_key: str,
    thresholds_v: list[float],
) -> list[tuple[float, float, float, float]]:
    representatives: list[tuple[float, float, float, float]] = []
    for bank_index, threshold_v in enumerate(thresholds_v):
        points = np.concatenate(
            [profile[point_key][bank_index] for profile in profiles], axis=0
        )
        for stage_one_below_threshold in (True, False):
            selected = points[(points[:, 0] < threshold_v) == stage_one_below_threshold]
            if selected.size == 0:
                raise RuntimeError(
                    f"empty stage-one partition for cutoff bank {bank_index}"
                )
            median = np.median(selected, axis=0)
            representatives.append(tuple(float(value) for value in median))
    return representatives


def _full_operating_point_inverse(
    model: FixedWideStateBankedChordV1CircuitModel,
    v_gk1_v: float,
    v_pk1_v: float,
    v_gk2_v: float,
    v_pk2_v: float,
) -> np.ndarray:
    voltage = model.reference.voltage.copy()
    for stage, v_gk_v, v_pk_v in (
        (1, v_gk1_v, v_pk1_v),
        (2, v_gk2_v, v_pk2_v),
    ):
        grid = model.node[f"g{stage}"]
        plate = model.node[f"p{stage}"]
        cathode = model.node[f"k{stage}"]
        voltage[grid] = voltage[cathode] + v_gk_v
        voltage[plate] = voltage[cathode] + v_pk_v
    jacobian, _ = model.reference._linear_system(0.0, dynamic=True)
    residual = np.zeros(model.node_count, dtype=np.float64)
    model.reference._tube_stamp(
        residual, jacobian, voltage, "g1", "p1", "k1"
    )
    model.reference._tube_stamp(
        residual, jacobian, voltage, "g2", "p2", "k2"
    )
    inverse_scale = 1 << model.inverse_fractional_bits
    return np.rint(np.linalg.inv(jacobian) * inverse_scale).astype(np.int64)


class FullOperatingPointBankedCircuit(
    FixedWideStateBankedChordV1CircuitModel
):
    """Research candidate replacing each cutoff bank's two tube derivatives."""

    def __init__(
        self,
        *args: object,
        representatives: list[tuple[float, float, float, float]],
        **kwargs: object,
    ):
        super().__init__(*args, **kwargs)
        if len(representatives) != len(self.chord_inverse_banks_q):
            raise ValueError("one full operating point is required per cutoff bank")
        self.chord_inverse_banks_q = [
            _full_operating_point_inverse(self, *point)
            for point in representatives
        ]


class StageOneSplitBankedCircuit(FixedWideStateBankedChordV1CircuitModel):
    """Split each stage-two cutoff region by sample-start stage-one Vgk."""

    def __init__(
        self,
        *args: object,
        representatives: list[tuple[float, float, float, float]],
        thresholds_v: list[float],
        **kwargs: object,
    ):
        super().__init__(*args, **kwargs)
        stage_two_bank_count = len(self.cutoff_jacobian_regimes)
        if len(thresholds_v) != stage_two_bank_count:
            raise ValueError("one stage-one threshold is required per cutoff bank")
        if len(representatives) != 2 * stage_two_bank_count:
            raise ValueError("two full operating points are required per cutoff bank")
        self.stage_one_thresholds_q32 = [
            int(round(value * (1 << 32))) for value in thresholds_v
        ]
        self.chord_inverse_banks_q = [
            _full_operating_point_inverse(self, *point)
            for point in representatives
        ]
        self.chord_bank_selection_count = [0] * (
            len(self.chord_inverse_banks_q) + 1
        )

    def _previous_v_gk1_q32(self) -> int:
        grid = self.node["g1"]
        cathode = self.node["k1"]
        grid_q32 = self._convert_fraction(
            int(self.voltage_q[grid]),
            int(self.VOLTAGE_FRACTIONAL_BITS[grid]),
            32,
        )
        cathode_q32 = self._convert_fraction(
            int(self.voltage_q[cathode]),
            int(self.VOLTAGE_FRACTIONAL_BITS[cathode]),
            32,
        )
        return grid_q32 - cathode_q32

    def _select_chord_bank(self) -> int:
        v_gk2_q32 = self._previous_v_gk2_q32()
        for stage_two_bank, (upper_v, _, _) in enumerate(
            self.cutoff_jacobian_regimes
        ):
            if v_gk2_q32 < int(round(upper_v * (1 << 32))):
                stage_one_branch = int(
                    self._previous_v_gk1_q32()
                    >= self.stage_one_thresholds_q32[stage_two_bank]
                )
                return 2 * stage_two_bank + stage_one_branch
        return len(self.chord_inverse_banks_q)


def run_level_candidates(
    profile: dict[str, object],
    policies: dict[str, object],
) -> dict[str, object]:
    level_peak_v = float(profile["burst_input_peak_v"])
    stimulus = input_trajectory_q24(level_peak_v).astype(np.float64) / float(
        1 << 24
    )
    reference = np.asarray(profile["reference_output"])
    time_s = np.arange(stimulus.size) / SAMPLE_RATE_HZ
    masks = {
        "burst": (time_s >= BURST_START_S) & (time_s < BURST_END_S),
        "complete_post_burst": time_s >= BURST_END_S,
        "final_10ms": time_s >= DURATION_S - 0.010,
    }
    cases: list[dict[str, object]] = []
    for policy_name, specification in policies.items():
        common_arguments = {
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "tube_lut": FixedFactorizedKoren12AX7(),
            "integration_method": "trapezoidal",
            "terminal_correction": True,
        }
        if specification is None:
            model = FixedWideStateBankedChordV1CircuitModel(**common_arguments)
        elif isinstance(specification, dict):
            model = StageOneSplitBankedCircuit(
                **common_arguments,
                representatives=specification["representatives"],
                thresholds_v=specification["thresholds_v"],
            )
        else:
            model = FullOperatingPointBankedCircuit(
                **common_arguments, representatives=specification
            )
        output = model.process(
            stimulus, max_iterations=3, residual_limit_a=2.0e-6
        )
        cases.append(
            {
                "policy": policy_name,
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
    return {"burst_input_peak_v": level_peak_v, "cases": cases}


def main() -> int:
    workers = min(len(LEVELS_PEAK_V), max(1, os.cpu_count() or 1))
    profiles: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(profile_reference, level): level
            for level in LEVELS_PEAK_V
        }
        for future in as_completed(futures):
            profile = future.result()
            profiles.append(profile)
            print(
                f"profiled {profile['burst_input_peak_v']:.1f} V full Newton",
                flush=True,
            )
    profiles.sort(key=lambda item: float(item["burst_input_peak_v"]))

    one_volt = [profiles[0]]
    one_point_five_volt = [profiles[1]]
    combined_all_points = [
        np.concatenate(
            [profile["all_points"][bank_index] for profile in profiles], axis=0
        )
        for bank_index in range(4)
    ]
    dc_model = V1CircuitModel(
        SAMPLE_RATE_HZ, integration_method="trapezoidal"
    )
    dc_v_gk1 = dc_model.nodes["g1"] - dc_model.nodes["k1"]
    dc_thresholds = [dc_v_gk1] * 4
    bank_median_thresholds = [
        float(np.median(points[:, 0])) for points in combined_all_points
    ]
    policies: dict[str, object] = {
        BASELINE_POLICY: None,
        "combined_all_sample_median": _median_representatives(
            profiles, "all_points"
        ),
        "combined_burst_median": _median_representatives(
            profiles, "burst_points"
        ),
        "one_volt_burst_median": _median_representatives(
            one_volt, "burst_points"
        ),
        "one_point_five_volt_burst_median": _median_representatives(
            one_point_five_volt, "burst_points"
        ),
        "stage_one_dc_split": {
            "thresholds_v": dc_thresholds,
            "representatives": _split_representatives(
                profiles, "all_points", dc_thresholds
            ),
        },
        "stage_one_bank_median_split": {
            "thresholds_v": bank_median_thresholds,
            "representatives": _split_representatives(
                profiles, "all_points", bank_median_thresholds
            ),
        },
    }

    measurements: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(run_level_candidates, profile, policies): float(
                profile["burst_input_peak_v"]
            )
            for profile in profiles
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

    def measured_case(level_peak_v: float, policy_name: str) -> dict[str, object]:
        measurement = next(
            item
            for item in measurements
            if float(item["burst_input_peak_v"]) == level_peak_v
        )
        return next(
            case for case in measurement["cases"] if case["policy"] == policy_name
        )

    diagnostic_keys = (
        "residual_limit_exceedance_count",
        "saturation_count",
        "range_clip_count",
        "correction_scale_fallback_count",
    )
    gates = {
        "analytical_newton_converged": all(
            int(profile["analytical_nonconvergence_count"]) == 0
            for profile in profiles
        ),
        "baseline_and_unsplit_candidates_diagnostic_clean": all(
            int(case[key]) == 0
            for measurement in measurements
            for case in measurement["cases"]
            if not str(case["policy"]).startswith("stage_one_")
            for key in diagnostic_keys
        ),
        "stage_one_split_rejection_reproduced_at_1p5_v": all(
            int(measured_case(1.5, policy)["residual_limit_exceedance_count"])
            > 0
            and float(
                measured_case(1.5, policy)["windows"]["burst"][
                    "raw_error_rms_v"
                ]
            )
            > float(
                measured_case(1.5, BASELINE_POLICY)["windows"]["burst"][
                    "raw_error_rms_v"
                ]
            )
            for policy in (
                "stage_one_dc_split",
                "stage_one_bank_median_split",
            )
        ),
    }
    report = {
        "model": "12ax7_passive_riaa_v1",
        "study": "schedule-neutral full-operating-point chord banks",
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
        "representative_units": ["Vgk1_V", "Vpk1_V", "Vgk2_V", "Vpk2_V"],
        "representatives": {
            policy_name: specification
            for policy_name, specification in policies.items()
            if specification is not None
        },
        "representative_distributions": {
            "combined_all_samples": _representative_metadata(
                profiles,
                "all_points",
                policies["combined_all_sample_median"],
            ),
            "combined_burst": _representative_metadata(
                profiles,
                "burst_points",
                policies["combined_burst_median"],
            ),
        },
        "schedule_projection": {
            "baseline_solver_clocks": 127,
            "candidate_solver_clocks": 127,
            "reason": (
                "only precomputed Q17.1 inverse-matrix coefficients change; "
                "the selector, residual passes, and correction passes do not"
            ),
            "resource_and_timing_not_resynthesized": True,
        },
        "decision": {
            "accepted_for_production": False,
            "reason": (
                "no unsplit full-operating-point set improves both overload "
                "levels and recovery; both stage-one split variants create "
                "58 preterminal residual-limit misses at 1.5 V and roughly "
                "double burst error"
            ),
        },
        "alignment": {"gain": False, "dc": False, "delay": False},
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "measurements": measurements,
    }
    generated = ROOT / "model" / "generated" / "dual_triode_chord_banks.json"
    generated.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    reference = ROOT / "reference" / "results" / "dual_triode_chord_banks.json"
    reference.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_gates_pass"]:
        raise RuntimeError("dual-triode chord-bank study gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
