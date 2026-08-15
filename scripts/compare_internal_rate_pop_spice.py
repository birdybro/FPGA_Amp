#!/usr/bin/env python3
"""Compare 384/768 kHz floating pop trajectories with the ngspice circuit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.null_compare import compare_signals  # noqa: E402
from fpga_amp.resampling import (  # noqa: E402
    DEFAULT_STAGES,
    EIGHT_X_STAGES,
    decimate_16x,
)
from fpga_amp.stream import compose_floating_stream  # noqa: E402


EXTERNAL_SAMPLE_RATE_HZ = 48_000.0
FRAME_COUNT = 2_048
EVENT_SAMPLE = 512
Q24_SCALE = float(1 << 24)


def _locate_ngspice(requested: str) -> Path | None:
    system = shutil.which(requested)
    if system:
        return Path(system)
    local = ROOT / ".tools" / "root" / "usr" / "bin" / requested
    return local if local.exists() else None


def _input_q24(values_v: np.ndarray) -> np.ndarray:
    values = np.rint(np.asarray(values_v, dtype=np.float64) * Q24_SCALE)
    if np.any((values < -(1 << 31)) | (values > (1 << 31) - 1)):
        raise RuntimeError("SPICE pop stimulus exceeds signed Q8.24")
    return values.astype(np.int64)


def _write_pwl_source(path: Path, values_v: np.ndarray, sample_rate_hz: int) -> None:
    time_s = np.arange(values_v.size, dtype=np.float64) / sample_rate_hz
    with path.open("w", encoding="ascii") as handle:
        handle.write(
            f"V_SIGNAL INPUT 0 PWL({time_s[0]:.15e} {values_v[0]:.15e}\n"
        )
        for time_value, voltage in zip(time_s[1:], values_v[1:], strict=True):
            handle.write(f"+ {time_value:.15e} {voltage:.15e}\n")
        handle.write(
            f"+ {values_v.size / sample_rate_hz:.15e} {values_v[-1]:.15e})\n"
        )


def _build_netlist(
    pwl_path: Path,
    output_path: Path,
    maximum_step_s: float,
    duration_s: float,
) -> str:
    source = (ROOT / "reference" / "spice" / "v1_reference.cir").read_text(
        encoding="utf-8"
    )
    prefix, marker, _ = source.partition(".control")
    if not marker:
        raise RuntimeError("V1 SPICE source has no control block")
    source_line = "V_SIGNAL CART_SOURCE 0 DC 0 AC 1 SIN(0 5m 1k)"
    if source_line not in prefix:
        raise RuntimeError("V1 SPICE source stimulus changed")
    prefix = prefix.replace(
        source_line,
        f".include {pwl_path.as_posix()}",
    )
    for passive_line in (
        "R_CART CART_SOURCE CART_L 485",
        "L_CART CART_L INPUT 550m",
        "C_LOAD INPUT 0 150p",
        "R_INPUT INPUT 0 47.5k",
    ):
        if passive_line not in prefix:
            raise RuntimeError(f"V1 SPICE source line changed: {passive_line}")
        prefix = prefix.replace(passive_line, f"* bypassed: {passive_line}")
    return (
        prefix
        + ".control\n"
        + "set wr_singlescale\n"
        + "set wr_vecnames\n"
        + f"tran {maximum_step_s:.15e} {duration_s:.15e} 0 "
        + f"{maximum_step_s:.15e}\n"
        + f"wrdata {output_path.as_posix()} v(input) v(output)\n"
        + "quit\n"
        + ".endc\n\n.end\n"
    )


def _run_spice(
    executable: Path,
    name: str,
    values_v: np.ndarray,
    sample_rate_hz: int,
    workspace: Path,
) -> tuple[np.ndarray, dict[str, object]]:
    pwl_path = workspace / f"{name}_input.inc"
    csv_path = workspace / f"{name}_output.csv"
    netlist_path = workspace / f"{name}.cir"
    log_path = workspace / f"{name}.log"
    _write_pwl_source(pwl_path, values_v, sample_rate_hz)
    duration_s = values_v.size / sample_rate_hz
    maximum_step_s = 1.0 / (8.0 * sample_rate_hz)
    netlist_path.write_text(
        _build_netlist(
            pwl_path.relative_to(ROOT),
            csv_path.relative_to(ROOT),
            maximum_step_s,
            duration_s,
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [str(executable), "-b", "-o", str(log_path), str(netlist_path)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(log_path.read_text(encoding="utf-8", errors="replace"))
    data = np.loadtxt(csv_path, skiprows=1)
    if data.ndim != 2 or data.shape[1] != 3:
        raise RuntimeError(f"unexpected ngspice output shape {data.shape}")
    sample_times_s = np.arange(values_v.size, dtype=np.float64) / sample_rate_hz
    output_v = np.interp(sample_times_s, data[:, 0], data[:, 2])
    return output_v, {
        "raw_spice_points": int(data.shape[0]),
        "maximum_step_s": maximum_step_s,
        "duration_s": duration_s,
    }


def _metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, object]:
    comparison = compare_signals(
        reference,
        candidate,
        align_latency=False,
        align_gain=False,
    )
    return comparison.report["final"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ngspice", default="ngspice")
    args = parser.parse_args()
    executable = _locate_ngspice(args.ngspice)
    if executable is None:
        print("ERROR: ngspice unavailable; run `make tools`", file=sys.stderr)
        return 2

    index = np.arange(FRAME_COUNT, dtype=np.float64)
    control_v = 0.005 * np.sin(
        2.0 * np.pi * 1_000.0 * index / EXTERNAL_SAMPLE_RATE_HZ
    )
    pop_v = control_v.copy()
    pop_v[EVENT_SAMPLE] += 0.020
    pop_v[EVENT_SAMPLE + 1] -= 0.012
    control_q24 = _input_q24(control_v)
    pop_q24 = _input_q24(pop_v)

    workspace = ROOT / "build" / "internal_rate_pop_spice"
    workspace.mkdir(parents=True, exist_ok=True)
    measurements: list[dict[str, object]] = []
    for factor, stages in ((8, EIGHT_X_STAGES), (16, DEFAULT_STAGES)):
        sample_rate_hz = int(factor * EXTERNAL_SAMPLE_RATE_HZ)
        print(f"running {sample_rate_hz} Hz floating trajectories", flush=True)
        floating_pop = compose_floating_stream(
            pop_q24,
            integration_method="trapezoidal",
            internal_sample_rate_hz=sample_rate_hz,
        )
        floating_control = compose_floating_stream(
            control_q24,
            integration_method="trapezoidal",
            internal_sample_rate_hz=sample_rate_hz,
        )
        if (
            floating_pop.circuit.nonconvergence_count
            or floating_control.circuit.nonconvergence_count
        ):
            raise RuntimeError(f"{sample_rate_hz} Hz floating trajectory failed")
        print(f"running {sample_rate_hz} Hz ngspice pop/control", flush=True)
        spice_pop, pop_spice = _run_spice(
            executable,
            f"pop_{sample_rate_hz}",
            floating_pop.internal_input_v,
            sample_rate_hz,
            workspace,
        )
        spice_control, control_spice = _run_spice(
            executable,
            f"control_{sample_rate_hz}",
            floating_control.internal_input_v,
            sample_rate_hz,
            workspace,
        )
        model_response_internal = (
            floating_pop.circuit_output_v - floating_control.circuit_output_v
        )
        spice_response_internal = spice_pop - spice_control
        internal_start = (EVENT_SAMPLE - 64) * factor
        model_response_external = decimate_16x(
            model_response_internal, stages=stages
        )[:FRAME_COUNT]
        spice_response_external = decimate_16x(
            spice_response_internal, stages=stages
        )[:FRAME_COUNT]
        external_start = EVENT_SAMPLE - 64
        measurements.append(
            {
                "internal_sample_rate_hz": sample_rate_hz,
                "integration_method": "trapezoidal",
                "ngspice": {
                    "pop": pop_spice,
                    "control": control_spice,
                    "input_source": (
                        "ideal INPUT-node PWL from the rate-specific floating "
                        "interpolator; cartridge/load network bypassed"
                    ),
                },
                "internal_response_python_vs_spice": _metrics(
                    spice_response_internal[internal_start:],
                    model_response_internal[internal_start:],
                ),
                "external_response_python_vs_spice": _metrics(
                    spice_response_external[external_start:],
                    model_response_external[external_start:],
                ),
                "floating_nonconvergence_count": 0,
            }
        )

    report = {
        "model": "12ax7_passive_riaa_v1",
        "comparison": "rate-specific floating trapezoidal model vs ngspice",
        "external_sample_rate_hz": int(EXTERNAL_SAMPLE_RATE_HZ),
        "frame_count": FRAME_COUNT,
        "stimulus": {
            "nominal_tone_hz": 1_000,
            "nominal_tone_peak_v": 0.005,
            "event_sample": EVENT_SAMPLE,
            "event_samples_v": [0.020, -0.012],
            "input_quantization": "signed Q8.24 before interpolation",
        },
        "comparison_interval": {
            "start_external_sample": EVENT_SAMPLE - 64,
            "latency_alignment": False,
            "gain_alignment": False,
            "dc_alignment": False,
        },
        "measurements": measurements,
        "limitations": [
            "each rate is compared to SPICE driven by its own interpolated input",
            "PWL is linear between internal samples while the discrete model samples those endpoints",
            "this is numerical SPICE-model agreement, not measured tube hardware truth",
        ],
    }
    output = ROOT / "model" / "generated" / "internal_rate_pop_spice.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
