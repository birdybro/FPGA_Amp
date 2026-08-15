#!/usr/bin/env python3
"""Run the open Yosys/nextpnr-Himbaechel XC7 timing flow."""

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
    "parallel_deep_pipelined_solver_pnr_harness",
    "parallel_max_pipelined_solver_pnr_harness",
    "parallel_diagnostic_pipelined_solver_pnr_harness",
    "parallel_decoupled_diagnostic_pipelined_solver_pnr_harness",
    "parallel_shared_capacitor_decoupled_diagnostic_pipelined_solver_pnr_harness",
    "parallel_shared_capacitor_terminal_decoupled_diagnostic_pipelined_solver_pnr_harness",
    "parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness",
    "terminal_current_pnr_harness",
    "half_parallel_terminal_current_pnr_harness",
    "kcl_pnr_harness",
    "pipelined_kcl_pnr_harness",
    "deep_pipelined_kcl_pnr_harness",
    "max_pipelined_kcl_pnr_harness",
    "diagnostic_pipelined_kcl_pnr_harness",
    "decoupled_diagnostic_pipelined_kcl_pnr_harness",
    "shared_capacitor_decoupled_diagnostic_pipelined_kcl_pnr_harness",
    "chord_pnr_harness",
    "pipelined_chord_pnr_harness",
    "stream_384khz_pnr_harness",
    "stream_384khz_49mhz_pnr_harness",
)
RUN_TAG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def chipdb_device_name(part: str) -> str:
    """Return the density name used by nextpnr's generated XC7 chipdb."""

    match = re.match(r"^(xc7(?:a\d+t|s\d+|z\d+))", part)
    if match is None:
        raise ValueError(f"cannot derive an XC7 chipdb density from part {part!r}")
    return match.group(1)


def validated_run_tag(tag: str) -> str:
    """Return a filesystem-safe experiment tag or raise an argparse error."""

    if RUN_TAG_PATTERN.fullmatch(tag) is None:
        raise argparse.ArgumentTypeError(
            "run tag must be 1-64 lowercase letters, digits, underscores, or "
            "hyphens and must start with a letter or digit"
        )
    return tag


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


def measured_report_summary(
    report: Path,
    *,
    log: Path | None = None,
    placement_requested: bool = True,
    route_requested: bool = True,
) -> dict[str, object]:
    """Extract stable, compact evidence from a nextpnr JSON report."""

    if not report.exists():
        return {
            "pack_completed": False,
            "placement_completed": False,
            "route_completed": False,
            "timing_pass": None,
            "clock_fmax_mhz": {},
            "utilization": {},
        }
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "pack_completed": False,
            "placement_completed": False,
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
    if not clocks and log is not None and log.exists():
        placement_pattern = re.compile(
            r"Max frequency for clock '([^']+)': ([0-9.]+) MHz "
            r"\((?:PASS|FAIL) at ([0-9.]+) MHz\)"
        )
        matches = placement_pattern.findall(log.read_text(encoding="utf-8"))
        clocks = {
            name: {"achieved": float(achieved), "constraint": float(constraint)}
            for name, achieved, constraint in matches
        }
    timing_pass = (
        all(
            values["achieved"] is not None
            and values["constraint"] is not None
            and values["achieved"] >= values["constraint"]
            for values in clocks.values()
        )
        if clocks
        else None
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
        "pack_completed": True,
        "placement_completed": placement_requested,
        "route_completed": route_requested,
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
    parser.add_argument(
        "--placer",
        choices=("heap", "sa", "static"),
        default="heap",
        help="nextpnr placement algorithm (default: heap)",
    )
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument(
        "--run-tag",
        type=validated_run_tag,
        help=(
            "retain this experiment in a tagged output subdirectory and "
            "summary instead of replacing the untagged artifacts"
        ),
    )
    parser.add_argument(
        "--placer-heap-timingweight",
        type=int,
        default=10,
        help="nextpnr heap-placer timing weight (upstream default: 10)",
    )
    parser.add_argument(
        "--placer-heap-cell-placement-timeout",
        type=int,
        default=8,
        help=(
            "nextpnr heap-placer cell-placement timeout divisor "
            "(upstream default: 8; smaller values allow more attempts)"
        ),
    )
    parser.add_argument("--yosys", default="yosys")
    parser.add_argument("--nextpnr", default="nextpnr-himbaechel")
    parser.add_argument(
        "--pre-place-script",
        type=Path,
        help="nextpnr Python hook to run after packing and before placement",
    )
    soft_kcl_mapping = parser.add_mutually_exclusive_group()
    soft_kcl_mapping.add_argument(
        "--soft-kcl-multipliers",
        action="store_true",
        help="map the KCL engine's eleven multipliers to LUT logic",
    )
    soft_kcl_mapping.add_argument(
        "--soft-kcl-capacitor-multipliers",
        action="store_true",
        help="map only the KCL engine's two capacitor multipliers to LUT logic",
    )
    parser.add_argument(
        "--timing-allow-fail",
        action="store_true",
        help="finish routing and emit a report even when the timing target fails",
    )
    stop_stage = parser.add_mutually_exclusive_group()
    stop_stage.add_argument("--synth-only", action="store_true")
    stop_stage.add_argument(
        "--pack-only",
        action="store_true",
        help=(
            "pack and emit an exact utilization report without running the "
            "placer; use this for candidates whose placement is impractical"
        ),
    )
    stop_stage.add_argument(
        "--place-only",
        action="store_true",
        help=(
            "pack/place and emit a detailed timing report without routing; "
            "use this to diagnose candidates with a large placement miss"
        ),
    )
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()

    try:
        chipdb_density = chipdb_device_name(args.device)
    except ValueError as error:
        parser.error(str(error))

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

    chipdb = (
        LOCAL_ROOT
        / "share"
        / "nextpnr"
        / "himbaechel"
        / "xilinx"
        / f"chipdb-{chipdb_density}.bin"
    )
    probe = {
        "flow": "Yosys + nextpnr-himbaechel Xilinx + Project X-Ray database",
        "device": args.device,
        "timing_grade": "DEFAULT",
        "timing_grade_limit": (
            "The experimental backend does not currently distinguish the "
            "selected device's -1 speed grade."
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
    pre_place_script = args.pre_place_script
    if pre_place_script is not None:
        if not pre_place_script.is_absolute():
            pre_place_script = REPOSITORY_ROOT / pre_place_script
        if not pre_place_script.exists():
            print(
                f"ERROR: missing pre-place script: {pre_place_script}",
                file=sys.stderr,
            )
            return 2

    device_tag = "" if args.device == DEFAULT_DEVICE else f"_{args.device}"
    output_dir = REPOSITORY_ROOT / "build" / "openxc7"
    if args.device != DEFAULT_DEVICE:
        output_dir = output_dir / args.device
    output_dir = output_dir / args.top
    if args.run_tag is not None:
        output_dir = output_dir / args.run_tag
    output_dir.mkdir(parents=True, exist_ok=True)
    netlist = output_dir / f"{args.top}.json"
    fasm = output_dir / f"{args.top}.fasm"
    placed_netlist = output_dir / f"{args.top}_placed.json"
    packed_netlist = output_dir / f"{args.top}_packed.json"
    if args.pack_only:
        stage_tag = "_pack"
        implementation_stage = "packing"
        implementation_artifact = packed_netlist
    elif args.place_only:
        stage_tag = "_place"
        implementation_stage = "placement"
        implementation_artifact = placed_netlist
    else:
        stage_tag = ""
        implementation_stage = "route"
        implementation_artifact = fasm
    report = output_dir / f"{args.top}_nextpnr{stage_tag}_report.json"
    log = output_dir / f"{args.top}_nextpnr{stage_tag}.log"
    for stale_artifact in (report, log, implementation_artifact):
        stale_artifact.unlink(missing_ok=True)

    synthesis_command = [
        sys.executable,
        str(REPOSITORY_ROOT / "scripts" / "run_synthesis.py"),
        "--top",
        args.top,
        "--pnr-json",
        str(netlist),
    ]
    if args.run_tag is not None:
        synthesis_command.extend(["--result-tag", args.run_tag])
    if args.soft_kcl_multipliers:
        synthesis_command.extend(
            ["--soft-multiplier-module", "network_kcl_v1_wide"]
        )
    elif args.soft_kcl_capacitor_multipliers:
        synthesis_command.append("--soft-kcl-capacitor-multipliers")
    synthesis = subprocess.run(
        synthesis_command,
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
        "--placer",
        args.placer,
        "--router",
        args.router,
        "--seed",
        str(args.seed),
        "--threads",
        str(args.threads),
        "--placer-heap-timingweight",
        str(args.placer_heap_timingweight),
        "--placer-heap-cell-placement-timeout",
        str(args.placer_heap_cell_placement_timeout),
        "--report",
        str(report),
        "--detailed-timing-report",
        "--log",
        str(log),
        "-o",
        f"xdc={xdc}",
    ]
    if args.pack_only:
        command.extend(["--pack-only", "--write", str(packed_netlist)])
    elif args.place_only:
        command.extend(["--no-route", "--write", str(placed_netlist)])
    else:
        command.extend(["-o", f"fasm={fasm}"])
    if pre_place_script is not None:
        command.extend(["--pre-place", str(pre_place_script)])
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
        "placer": args.placer,
        "router": args.router,
        "seed": args.seed,
        "threads": args.threads,
        "run_tag": args.run_tag,
        "placer_heap_timingweight": args.placer_heap_timingweight,
        "placer_heap_cell_placement_timeout": (
            args.placer_heap_cell_placement_timeout
        ),
        "implementation_stage": implementation_stage,
        "nextpnr_returncode": placed.returncode,
        "netlist": str(netlist.relative_to(REPOSITORY_ROOT)),
        "packed_netlist": (
            str(packed_netlist.relative_to(REPOSITORY_ROOT))
            if packed_netlist.exists()
            else None
        ),
        "placed_netlist": (
            str(placed_netlist.relative_to(REPOSITORY_ROOT))
            if placed_netlist.exists()
            else None
        ),
        "constraints": str(xdc.relative_to(REPOSITORY_ROOT)),
        "pre_place_script": (
            str(pre_place_script.relative_to(REPOSITORY_ROOT))
            if pre_place_script is not None
            else None
        ),
        "soft_kcl_multipliers": args.soft_kcl_multipliers,
        "soft_kcl_capacitor_multipliers": (
            args.soft_kcl_capacitor_multipliers
        ),
        "fasm": (
            str(fasm.relative_to(REPOSITORY_ROOT))
            if not args.pack_only and not args.place_only and fasm.exists()
            else None
        ),
        "report": str(report.relative_to(REPOSITORY_ROOT)) if report.exists() else None,
        "log": str(log.relative_to(REPOSITORY_ROOT)),
        "bitstream_generated": False,
        "hardware_ready": False,
    } | measured_report_summary(
        report,
        log=log,
        placement_requested=not args.pack_only,
        route_requested=not args.pack_only and not args.place_only,
    )
    run_tag = f"_{args.run_tag}" if args.run_tag is not None else ""
    summary_path = (
        REPOSITORY_ROOT
        / "reference"
        / "results"
        / f"openxc7_{args.top}{device_tag}{run_tag}{stage_tag}_summary.json"
    )
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return placed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
