#!/usr/bin/env python3
"""Run the open Yosys/nextpnr-Himbaechel XC7 timing flow."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOT = REPOSITORY_ROOT / ".tools" / "root" / "usr"
DEFAULT_DEVICE = "xc7a100tcsg324-1"
DEFAULT_FREQUENCY_MHZ = 98.304
DEFAULT_TOP = "solver_pnr_harness"
SUPPORTED_TOPS = (
    DEFAULT_TOP,
    "hermite_pnr_harness",
    "linear_tube_pnr_harness",
    "linear_solver_pnr_harness",
    "parallel_solver_pnr_harness",
    "parallel_pipelined_solver_pnr_harness",
    "terminal_current_pnr_harness",
    "kcl_pnr_harness",
    "pipelined_kcl_pnr_harness",
    "chord_pnr_harness",
    "pipelined_chord_pnr_harness",
)


def locate(name: str) -> Path | None:
    candidate = Path(name)
    if candidate.parent != Path("."):
        return candidate if candidate.exists() else None
    found = shutil.which(name)
    if found:
        return Path(found)
    local = LOCAL_ROOT / "bin" / name
    return local if local.exists() else None


def command_environment() -> dict[str, str]:
    environment = os.environ.copy()
    local_library = LOCAL_ROOT / "lib"
    if local_library.exists():
        existing = environment.get("LD_LIBRARY_PATH")
        environment["LD_LIBRARY_PATH"] = (
            f"{local_library}:{existing}" if existing else str(local_library)
        )
    return environment


def version_line(executable: Path, argument: str) -> str:
    completed = subprocess.run(
        [str(executable), argument],
        cwd=REPOSITORY_ROOT,
        env=command_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return completed.stdout.splitlines()[0] if completed.stdout else "unknown"


def measured_report_summary(report: Path) -> dict[str, object]:
    """Extract stable, compact evidence from a nextpnr JSON report."""

    if not report.exists():
        return {
            "route_completed": False,
            "timing_pass": None,
            "clock_fmax_mhz": {},
            "utilization": {},
        }
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "route_completed": False,
            "timing_pass": None,
            "clock_fmax_mhz": {},
            "utilization": {},
        }

    clocks = {
        name: {
            "achieved": values.get("achieved"),
            "constraint": values.get("constraint"),
        }
        for name, values in payload.get("fmax", {}).items()
    }
    timing_pass = bool(clocks) and all(
        values["achieved"] is not None
        and values["constraint"] is not None
        and values["achieved"] >= values["constraint"]
        for values in clocks.values()
    )
    utilization_payload = payload.get("utilization", {})
    resource_names = (
        "SLICE_LUTX",
        "SLICE_FFX",
        "CARRY4",
        "DSP48E1_DSP48E1",
        "RAMB18E1_RAMB18E1",
        "RAMB36E1_RAMB36E1",
        "BUFGCTRL",
        "PAD",
    )
    utilization = {
        name: utilization_payload[name]
        for name in resource_names
        if name in utilization_payload
    }
    return {
        "route_completed": True,
        "timing_pass": timing_pass,
        "clock_fmax_mhz": clocks,
        "utilization": utilization,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", default=DEFAULT_TOP, choices=SUPPORTED_TOPS)
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--frequency-mhz", type=float, default=DEFAULT_FREQUENCY_MHZ)
    parser.add_argument(
        "--xdc",
        type=Path,
        default=Path("fpga/arty_a7_100t/solver_pnr_harness.xdc"),
    )
    parser.add_argument("--router", choices=("router1", "router2"), default="router2")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--yosys", default="yosys")
    parser.add_argument("--nextpnr", default="nextpnr-himbaechel")
    parser.add_argument(
        "--timing-allow-fail",
        action="store_true",
        help="finish routing and emit a report even when the timing target fails",
    )
    parser.add_argument("--synth-only", action="store_true")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()

    yosys = locate(args.yosys)
    nextpnr = locate(args.nextpnr)
    if yosys is None or nextpnr is None:
        missing = []
        if yosys is None:
            missing.append(args.yosys)
        if nextpnr is None:
            missing.append(args.nextpnr)
        print(
            "ERROR: missing open FPGA tool(s): " + ", ".join(missing)
            + "; run `make tools-openxc7`",
            file=sys.stderr,
        )
        return 2

    chipdb = LOCAL_ROOT / "share" / "nextpnr" / "himbaechel" / "xilinx" / "chipdb-xc7a100t.bin"
    probe = {
        "flow": "Yosys + nextpnr-himbaechel Xilinx + Project X-Ray database",
        "device": args.device,
        "timing_grade": "DEFAULT",
        "timing_grade_limit": (
            "The experimental backend does not currently distinguish the "
            "XC7A100T-1 speed grade."
        ),
        "yosys": version_line(yosys, "-V"),
        "nextpnr": version_line(nextpnr, "--version"),
        "chipdb": str(chipdb.relative_to(REPOSITORY_ROOT)) if chipdb.exists() else None,
    }
    if args.probe:
        print(json.dumps(probe, indent=2))
        return 0

    xdc = args.xdc if args.xdc.is_absolute() else REPOSITORY_ROOT / args.xdc
    if not xdc.exists():
        print(f"ERROR: missing XDC: {xdc}", file=sys.stderr)
        return 2

    output_dir = REPOSITORY_ROOT / "build" / "openxc7" / args.top
    output_dir.mkdir(parents=True, exist_ok=True)
    netlist = output_dir / f"{args.top}.json"
    fasm = output_dir / f"{args.top}.fasm"
    report = output_dir / f"{args.top}_nextpnr_report.json"
    log = output_dir / f"{args.top}_nextpnr.log"

    synthesis = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "run_synthesis.py"),
            "--top",
            args.top,
            "--pnr-json",
            str(netlist),
        ],
        cwd=REPOSITORY_ROOT,
        env=command_environment(),
        check=False,
    )
    if synthesis.returncode or args.synth_only:
        return synthesis.returncode

    command = [
        str(nextpnr),
        "--device",
        args.device,
        "--json",
        str(netlist),
        "--freq",
        str(args.frequency_mhz),
        "--router",
        args.router,
        "--seed",
        str(args.seed),
        "--threads",
        str(args.threads),
        "--report",
        str(report),
        "--detailed-timing-report",
        "--log",
        str(log),
        "-o",
        f"xdc={xdc}",
        "-o",
        f"fasm={fasm}",
    ]
    if args.timing_allow_fail:
        command.append("--timing-allow-fail")
    placed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=command_environment(),
        check=False,
    )

    summary = probe | {
        "top": args.top,
        "target_frequency_mhz": args.frequency_mhz,
        "router": args.router,
        "seed": args.seed,
        "threads": args.threads,
        "nextpnr_returncode": placed.returncode,
        "netlist": str(netlist.relative_to(REPOSITORY_ROOT)),
        "constraints": str(xdc.relative_to(REPOSITORY_ROOT)),
        "fasm": str(fasm.relative_to(REPOSITORY_ROOT)) if fasm.exists() else None,
        "report": str(report.relative_to(REPOSITORY_ROOT)) if report.exists() else None,
        "log": str(log.relative_to(REPOSITORY_ROOT)),
        "bitstream_generated": False,
        "hardware_ready": False,
    } | measured_report_summary(report)
    summary_path = REPOSITORY_ROOT / "reference" / "results" / f"openxc7_{args.top}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return placed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
