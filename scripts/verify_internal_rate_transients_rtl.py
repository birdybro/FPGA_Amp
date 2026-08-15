#!/usr/bin/env python3
"""Prove long 384/768 kHz transient streams bit-exact in RTL.

The numerical rate comparison lives in ``study_internal_sample_rate.py``. This
script does not reinterpret that result; it verifies that the complete RTL at
each rate reproduces the corresponding fixed model for the record-pop and the
accepted-range overload trajectory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.stream import compose_fixed_wide_stream  # noqa: E402


EXTERNAL_SAMPLE_RATE_HZ = 48_000.0
Q24_SCALE = float(1 << 24)


def _input_q24(values_v: np.ndarray) -> np.ndarray:
    unbounded = np.rint(np.asarray(values_v, dtype=np.float64) * Q24_SCALE)
    if np.any((unbounded < -(1 << 31)) | (unbounded > (1 << 31) - 1)):
        raise RuntimeError("transient stimulus exceeds signed Q8.24")
    return unbounded.astype(np.int64)


def _stimuli() -> dict[str, np.ndarray]:
    pop_count = 4_096
    pop_index = np.arange(pop_count, dtype=np.float64)
    pop = 0.005 * np.sin(
        2.0 * np.pi * 1_000.0 * pop_index / EXTERNAL_SAMPLE_RATE_HZ
    )
    pop[1_024] += 0.020
    pop[1_025] -= 0.012

    recovery_count = 8_192
    recovery_index = np.arange(recovery_count, dtype=np.float64)
    recovery = 0.005 * np.sin(
        2.0 * np.pi * 1_000.0 * recovery_index / EXTERNAL_SAMPLE_RATE_HZ
    )
    recovery[480:720] = 0.500 * np.sin(
        2.0
        * np.pi
        * 1_000.0
        * recovery_index[480:720]
        / EXTERNAL_SAMPLE_RATE_HZ
    )
    return {
        "synthetic_record_pop": pop,
        "accepted_range_overload_recovery": recovery,
    }


def _write_vectors(path: Path, inputs: np.ndarray, outputs: np.ndarray) -> None:
    with path.open("w", encoding="ascii") as handle:
        for value in inputs:
            handle.write(f"{int(value)}\n")
        handle.write("EXPECTED\n")
        for value in outputs:
            handle.write(f"{int(value)}\n")


def _load_capture(path: Path, count: int) -> np.ndarray:
    captured = np.atleast_2d(np.loadtxt(path, dtype=np.int64))
    if captured.shape != (count, 2):
        raise RuntimeError(f"expected {count} captured rows, received {captured.shape}")
    if not np.array_equal(captured[:, 0], np.arange(count, dtype=np.int64)):
        raise RuntimeError("captured output indices are not contiguous")
    return captured[:, 1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verilator", default="verilator")
    args = parser.parse_args()

    work = ROOT / "build" / "internal_rate_transient_rtl"
    work.mkdir(parents=True, exist_ok=True)
    measurements: list[dict[str, object]] = []
    total_outputs = 0
    total_updates = 0
    for factor in (8, 16):
        internal_sample_rate_hz = int(factor * EXTERNAL_SAMPLE_RATE_HZ)
        simulator_built = False
        for name, stimulus_v in _stimuli().items():
            print(
                f"generating {name} fixed trajectory at {internal_sample_rate_hz} Hz",
                flush=True,
            )
            input_q24 = _input_q24(stimulus_v)
            fixed = compose_fixed_wide_stream(
                input_q24,
                trapezoidal=True,
                banked=True,
                terminal_correction=True,
                internal_sample_rate_hz=internal_sample_rate_hz,
            )
            diagnostics = fixed.diagnostic_counts
            if sum(diagnostics.values()) != 0:
                raise RuntimeError(
                    f"{name} {factor}x fixed diagnostics are nonzero: {diagnostics}"
                )
            stem = f"{name}_{internal_sample_rate_hz // 1000}khz"
            vector_path = work / f"{stem}_vectors.txt"
            capture_path = work / f"{stem}_capture.txt"
            _write_vectors(vector_path, input_q24, fixed.output_q24)
            command = [
                sys.executable,
                "scripts/run_wide_stream_rtl.py",
                "--verilator",
                args.verilator,
                "--skip-generate",
                "--trapezoidal",
                "--banked",
                "--terminal-correction",
                "--sample-rate-hz",
                str(internal_sample_rate_hz),
                "--vectors-file",
                str(vector_path.relative_to(ROOT)),
                "--vector-count",
                str(input_q24.size),
                "--capture-file",
                str(capture_path.relative_to(ROOT)),
            ]
            if simulator_built:
                command.append("--run-only")
            subprocess.run(command, cwd=ROOT, check=True)
            simulator_built = True
            captured_q24 = _load_capture(capture_path, input_q24.size)
            if not np.array_equal(captured_q24, fixed.output_q24):
                difference = np.flatnonzero(captured_q24 != fixed.output_q24)
                raise RuntimeError(
                    f"{stem} capture differs at output {int(difference[0])}"
                )
            total_outputs += int(input_q24.size)
            total_updates += factor * int(input_q24.size)
            measurements.append(
                {
                    "name": name,
                    "internal_sample_rate_hz": internal_sample_rate_hz,
                    "external_output_count": int(input_q24.size),
                    "nonlinear_update_count": factor * int(input_q24.size),
                    "rtl_fixed_bit_exact": True,
                    "solver_latency_clocks": 127,
                    "maximum_solver_residual_q44": int(
                        fixed.circuit.max_residual_q44_observed
                    ),
                    "maximum_solver_residual_a": float(
                        fixed.circuit.max_residual_q44_observed / float(1 << 44)
                    ),
                    "diagnostics": diagnostics,
                    "maximum_absolute_output_v": float(
                        np.max(np.abs(captured_q24.astype(np.float64) / Q24_SCALE))
                    ),
                }
            )

    report = {
        "model": "12ax7_passive_riaa_v1",
        "implementation": "captured complete SystemVerilog streams",
        "category": "FPGA approximation verification; no rate promotion",
        "external_sample_rate_hz": int(EXTERNAL_SAMPLE_RATE_HZ),
        "total_external_outputs": total_outputs,
        "total_nonlinear_updates": total_updates,
        "all_rtl_fixed_bit_exact": all(
            bool(item["rtl_fixed_bit_exact"]) for item in measurements
        ),
        "measurements": measurements,
        "interpretation": (
            "This proves implementation equivalence for both rate-specific "
            "trajectories. The separate fixed A/B pop discrepancy remains and "
            "continues to block 8x promotion."
        ),
    }
    for path in (
        ROOT / "model" / "generated" / "internal_rate_transient_rtl_summary.json",
        ROOT / "reference" / "results" / "internal_rate_transient_rtl.json",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
