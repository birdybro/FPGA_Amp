#!/usr/bin/env python3
"""Run reproducible out-of-context XC7 structural synthesis for the tube core."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def locate(name: str) -> Path | None:
    found = shutil.which(name)
    if found:
        return Path(found)
    local = REPOSITORY_ROOT / ".tools" / "root" / "usr" / "bin" / name
    return local if local.exists() else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--top",
        choices=(
            "triode_12ax7",
            "chord_corrector_v1",
            "network_rhs_v1",
            "network_kcl_v1",
            "v1_solver_mono",
        ),
        default="triode_12ax7",
    )
    args = parser.parse_args()
    yosys = locate("yosys")
    abc = locate("abc")
    if yosys is None or abc is None:
        print("ERROR: yosys/abc unavailable; run `make tools`", file=sys.stderr)
        return 2
    results = REPOSITORY_ROOT / "reference" / "results"
    results.mkdir(parents=True, exist_ok=True)
    sources = {
        "triode_12ax7": ["rtl/tube/triode_12ax7.sv"],
        "chord_corrector_v1": ["rtl/circuit/chord_corrector_v1.sv"],
        "network_rhs_v1": ["rtl/circuit/network_rhs_v1.sv"],
        "network_kcl_v1": ["rtl/circuit/network_kcl_v1.sv"],
        "v1_solver_mono": [
            "rtl/tube/triode_12ax7.sv",
            "rtl/circuit/network_rhs_v1.sv",
            "rtl/circuit/network_kcl_v1.sv",
            "rtl/circuit/chord_corrector_v1.sv",
            "rtl/phono/v1_solver_mono.sv",
        ],
    }[args.top]
    log_path = results / f"yosys_xc7_{args.top}.log"

    # The packaged Yosys has an absolute system ABC default. Stopping before
    # map_luts and invoking the identical documented steps with -exe keeps the
    # non-root bootstrap reproducible.
    script = "; ".join(
        [
            f"read_verilog -sv {' '.join(sources)}",
            f"synth_xilinx -family xc7 -top {args.top} -noiopad -noclkbuf -run begin:map_luts",
            "opt_expr -mux_undef -noclkinv",
            f"abc -exe {abc} -luts 2:2,3,6:5,10,20",
            "clean",
            "techmap -map +/xilinx/ff_map.v",
            "xilinx_srl -fixed -minlen 3",
            "techmap -map +/xilinx/lut_map.v -map +/xilinx/cells_map.v -D LUT_WIDTH=6",
            "xilinx_dffopt",
            "opt_lut_ins -tech xilinx",
            "clean",
            "hierarchy -check",
            "stat -tech xilinx",
            "check -noinit",
        ]
    )
    environment = os.environ.copy()
    local_library = REPOSITORY_ROOT / ".tools" / "root" / "usr" / "lib"
    if local_library.exists():
        environment["LD_LIBRARY_PATH"] = str(local_library)
    completed = subprocess.run(
        [str(yosys), "-Q", "-p", script],
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
        return completed.returncode

    local_section = completed.stdout.split(f"=== {args.top} ===", 1)[1].split(
        "=== design hierarchy ===", 1
    )[0]
    hierarchy_section = completed.stdout.split("=== design hierarchy ===", 1)[1].split(
        "Executing CHECK", 1
    )[0]
    section = (
        hierarchy_section
        if "Count including submodules" in hierarchy_section
        else local_section
    )

    def count(cell: str) -> int:
        match = re.search(rf"^\s*(\d+)\s+{re.escape(cell)}\s*$", section, re.MULTILINE)
        return int(match.group(1)) if match else 0

    lc_match = re.search(r"Estimated number of LCs:\s+(\d+)", section)
    warning_match = re.search(r"Warnings:\s+(\d+) unique", completed.stdout)
    summary = {
        "flow": "Yosys out-of-context synth_xilinx XC7; no place/route",
        "top": args.top,
        "yosys": subprocess.check_output([str(yosys), "-V"], text=True).strip(),
        "estimated_logic_cells": int(lc_match.group(1)) if lc_match else None,
        "lut_by_size": {f"LUT{size}": count(f"LUT{size}") for size in range(2, 7)},
        "flip_flops": {"FDRE": count("FDRE"), "FDSE": count("FDSE")},
        "dsp48e1": count("DSP48E1"),
        "ramb18e1": count("RAMB18E1"),
        "carry4": count("CARRY4"),
        "muxf7": count("MUXF7"),
        "check_problems": 0 if "Found and reported 0 problems." in completed.stdout else None,
        "yosys_warning_count": int(warning_match.group(1)) if warning_match else 0,
        "warning_note": "Warnings are Xilinx primitive output-port resize notices from Yosys techmap; see full log.",
        "fmax_mhz": None,
        "timing_note": "Fmax requires a named part plus vendor place-and-route and is not claimed here.",
    }
    summary_path = results / f"synthesis_{args.top}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
