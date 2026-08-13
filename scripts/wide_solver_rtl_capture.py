#!/usr/bin/env python3
"""Shared bit-exact vector generation and capture for the wide V1 solver."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys

import numpy as np
from numpy.typing import NDArray


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedWideStateBankedChordV1CircuitModel,
    FixedWideStateTrapezoidalV1CircuitModel,
    FixedWideStateV1CircuitModel,
)


@dataclass
class WideSolverRTLCapture:
    """Captured output and the exact fixed reference used by the testbench."""

    rtl_output_q32: NDArray[np.int64]
    fixed_output_q32: NDArray[np.int64]
    fixed_model: FixedWideStateV1CircuitModel
    maximum_grid_current_a: NDArray[np.float64]


def capture_wide_solver_rtl(
    input_q24: NDArray[np.int64],
    run_stem: str,
    verilator: str = "verilator",
    trapezoidal: bool = False,
    banked: bool = False,
    terminal_correction: bool = False,
) -> WideSolverRTLCapture:
    """Run one persistent input trajectory through fixed Python and RTL.

    The vector contains all nine nodes, ten capacitor voltage histories, the ten
    current histories in trapezoidal mode, and cumulative diagnostics after
    every sample. The self-checking testbench therefore proves more than the
    two-column output capture returned here.
    """

    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_"
    if not run_stem or any(character not in allowed for character in run_stem):
        raise ValueError(
            "run_stem must contain only lowercase letters, digits, or underscore"
        )
    samples = np.asarray(input_q24, dtype=np.int64)
    if samples.ndim != 1 or samples.size == 0:
        raise ValueError("input_q24 must be a non-empty one-dimensional array")
    if trapezoidal and terminal_correction:
        raise ValueError("terminal correction currently supports backward Euler only")

    tube = FixedFactorizedKoren12AX7()
    if banked:
        fixed = FixedWideStateBankedChordV1CircuitModel(
            tube_lut=tube,
            integration_method=(
                "trapezoidal" if trapezoidal else "backward_euler"
            ),
            terminal_correction=terminal_correction,
        )
    else:
        model_type = (
            FixedWideStateTrapezoidalV1CircuitModel
            if trapezoidal
            else FixedWideStateV1CircuitModel
        )
        fixed = model_type(tube_lut=tube, terminal_correction=terminal_correction)
    output_q32 = np.empty(samples.size, dtype=np.int64)
    maximum_grid_current_q31 = np.zeros(2, dtype=np.int64)
    vector_path = ROOT / "sim" / "vectors" / "generated" / f"{run_stem}.txt"
    vector_path.parent.mkdir(parents=True, exist_ok=True)
    with vector_path.open("w", encoding="ascii") as handle:
        for index, sample in enumerate(samples):
            fixed.process_sample(int(sample) / float(1 << 24))
            output_q32[index] = int(fixed.voltage_q[fixed.node["out"]])
            for tube_index, (grid_name, cathode_name) in enumerate(
                (("g1", "k1"), ("g2", "k2"))
            ):
                grid = fixed.node[grid_name]
                cathode = fixed.node[cathode_name]
                v_gk_q24 = fixed._convert_fraction(
                    int(fixed.voltage_q[grid]),
                    int(fixed.VOLTAGE_FRACTIONAL_BITS[grid]),
                    24,
                ) - fixed._convert_fraction(
                    int(fixed.voltage_q[cathode]),
                    int(fixed.VOLTAGE_FRACTIONAL_BITS[cathode]),
                    24,
                )
                _, grid_current_q31, _ = tube.evaluate_fixed(v_gk_q24, 100 << 20)
                maximum_grid_current_q31[tube_index] = max(
                    maximum_grid_current_q31[tube_index], grid_current_q31
                )
            fields = [
                int(sample),
                *[int(value) for value in fixed.voltage_q],
                *[int(cap.previous_voltage_q20) for cap in fixed.capacitors],
                *(
                    [int(cap.previous_current_q44) for cap in fixed.capacitors]
                    if trapezoidal
                    else []
                ),
                fixed.last_residual_q44,
                fixed.saturation_count,
                fixed.lut_clip_count,
                fixed.nonconvergence_count,
                fixed.correction_scale_fallback_count,
                fixed.minimum_correction_residual_fractional_bits or 0,
            ]
            handle.write(" ".join(str(value) for value in fields) + "\n")

    capture_path = ROOT / "build" / f"{run_stem}_capture.txt"
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "scripts/run_wide_solver_rtl.py",
        "--verilator",
        verilator,
        "--skip-generate",
        "--vectors-file",
        str(vector_path.relative_to(ROOT)),
        "--capture-file",
        str(capture_path.relative_to(ROOT)),
    ]
    if trapezoidal:
        command.append("--trapezoidal")
    if banked:
        command.append("--banked")
    if terminal_correction:
        command.append("--terminal-correction")
    subprocess.run(
        command,
        cwd=ROOT,
        check=True,
    )
    captured = np.atleast_2d(np.loadtxt(capture_path, dtype=np.int64))
    if captured.shape != (samples.size, 2):
        raise RuntimeError(
            f"expected {samples.size} captured samples, got {captured.shape}"
        )
    if not np.array_equal(captured[:, 0], np.arange(samples.size)):
        raise RuntimeError("RTL capture indices are not contiguous")
    if not np.array_equal(captured[:, 1], output_q32):
        differing = np.flatnonzero(captured[:, 1] != output_q32)
        raise RuntimeError(
            f"captured RTL output differs from fixed Python at sample {int(differing[0])}"
        )
    return WideSolverRTLCapture(
        rtl_output_q32=captured[:, 1],
        fixed_output_q32=output_q32,
        fixed_model=fixed,
        maximum_grid_current_a=maximum_grid_current_q31.astype(np.float64)
        / float(1 << 31),
    )
