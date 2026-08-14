#!/usr/bin/env python3
"""Prove converter-boundary rounding, clipping, and diagnostic contracts."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCAL_YOSYS = REPOSITORY_ROOT / ".tools" / "root" / "usr" / "bin" / "yosys"
LOCAL_LIBRARY = REPOSITORY_ROOT / ".tools" / "root" / "usr" / "lib"
PREPARE = (
    "read_verilog -formal -D FORMAL -sv "
    "rtl/io/pcm24_to_q8_24.sv "
    "rtl/io/q8_24_to_pcm24.sv "
    "sim/formal/audio_sample_calibration_formal.sv; "
    "prep -top audio_sample_calibration_formal; "
    "flatten; "
    "async2sync; "
    "formalff -clk2ff; "
    "opt_clean"
)


def resolve_yosys(requested: str) -> Path | None:
    resolved = shutil.which(requested)
    if resolved is not None:
        return Path(resolved)
    candidate = Path(requested)
    if candidate.is_file():
        return candidate.resolve()
    if requested == "yosys" and LOCAL_YOSYS.is_file():
        return LOCAL_YOSYS
    return None


def run_yosys(yosys: Path, command: str, log_path: Path) -> str:
    environment = os.environ.copy()
    using_local_tools = yosys.resolve().is_relative_to(LOCAL_YOSYS.parent.resolve())
    if using_local_tools and LOCAL_LIBRARY.is_dir():
        existing = environment.get("LD_LIBRARY_PATH")
        environment["LD_LIBRARY_PATH"] = (
            f"{LOCAL_LIBRARY}:{existing}" if existing else str(LOCAL_LIBRARY)
        )
    completed = subprocess.run(
        [str(yosys), "-Q", "-p", command],
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    log_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode:
        print(completed.stdout, file=sys.stderr)
        raise RuntimeError(f"Yosys failed; see {log_path}")
    return completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yosys", default="yosys")
    args = parser.parse_args()

    yosys = resolve_yosys(args.yosys)
    if yosys is None:
        print("ERROR: Yosys unavailable", file=sys.stderr)
        return 2

    build = REPOSITORY_ROOT / "build" / "formal_audio_sample_calibration"
    build.mkdir(parents=True, exist_ok=True)

    proof_command = (
        f"{PREPARE}; "
        "sat -prove-asserts -set-assumes -set-init-zero "
        "-seq 4 -tempinduct -verify -timeout 30"
    )
    try:
        proof = run_yosys(yosys, proof_command, build / "proof.log")
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if "Induction step proven: SUCCESS!" not in proof:
        print("ERROR: calibration arithmetic induction did not pass", file=sys.stderr)
        return 1
    induction_matches = re.findall(r"\[induction step (\d+)\]", proof)
    induction_depth = induction_matches[-1] if induction_matches else "unknown"

    reachability_command = (
        f"{PREPARE}; "
        "sat -set-assumes -set-init-zero -seq 5 "
        "-set-at 5 pcm_endpoint_count 1 -set-at 5 saturation_count 1 "
        "-set-at 5 input_configuration_error_sticky 1 "
        "-set-at 5 output_configuration_error_sticky 1 "
        "-show pcm_endpoint_count -show saturation_count "
        "-show input_configuration_error_sticky "
        "-show output_configuration_error_sticky"
    )
    try:
        reachability = run_yosys(
            yosys, reachability_command, build / "reachability.log"
        )
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if "SAT solving finished - model found:" not in reachability:
        print("ERROR: calibration endpoint/saturation witness missing", file=sys.stderr)
        return 1

    print(
        "PASS: converter calibration 12-property temporal induction depth "
        f"{induction_depth}; endpoint/saturation/invalid witness found"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
