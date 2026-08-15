#!/usr/bin/env python3
"""Validate a board artifact and non-destructively probe open programming."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BITSTREAM = (
    ROOT
    / "build/openxc7/xc7a200tsbg484-1/phono_audio_top_xc7/routed"
    / "phono_audio_top_xc7.bit"
)
BOARD_NAME = "nexysVideo"
EXPECTED_PART = "xc7a200tsbg484-1"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_artifact(bitstream: Path, manifest: Path) -> dict[str, object]:
    if not bitstream.is_file():
        raise ValueError(f"missing bitstream: {bitstream}")
    if not manifest.is_file():
        raise ValueError(f"missing bitstream manifest: {manifest}")
    try:
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid bitstream manifest JSON: {error}") from error

    actual_bytes = bitstream.stat().st_size
    actual_sha256 = file_sha256(bitstream)
    checks = {
        "part_matches": metadata.get("part") == EXPECTED_PART,
        "size_matches": metadata.get("bitstream_bytes") == actual_bytes,
        "sha256_matches": metadata.get("bitstream_sha256") == actual_sha256,
        "bitread_crc_validation": metadata.get("bitread_crc_validation") is True,
        "configuration_words_present": (
            isinstance(metadata.get("bitread_configuration_words"), int)
            and metadata["bitread_configuration_words"] > 0
        ),
        "configuration_frames_present": (
            isinstance(metadata.get("bitread_configuration_frames"), int)
            and metadata["bitread_configuration_frames"] > 0
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"bitstream artifact validation failed: {failed}")
    return {
        "bitstream": str(bitstream),
        "manifest": str(manifest),
        "bytes": actual_bytes,
        "sha256": actual_sha256,
        "part": metadata["part"],
        "bitread_configuration_words": metadata[
            "bitread_configuration_words"
        ],
        "bitread_configuration_frames": metadata[
            "bitread_configuration_frames"
        ],
        "checks": checks,
    }


def _run_probe(command: list[str], timeout_seconds: int = 30) -> dict[str, object]:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        output = completed.stdout[-8192:]
        return {
            "command": command,
            "returncode": completed.returncode,
            "output": output,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        return {
            "command": command,
            "returncode": None,
            "output": output[-8192:],
            "timed_out": True,
        }


def inspect_programmer(name: str, probe_hardware: bool) -> dict[str, object]:
    executable = shutil.which(name)
    if executable is None:
        return {
            "requested": name,
            "available": False,
            "board_profile": BOARD_NAME,
            "board_profile_present": None,
            "hardware_probe": None,
        }

    version = _run_probe([executable, "--version"])
    boards = _run_probe([executable, "--list-boards"])
    board_profile_present = any(
        line.split() and line.split()[0] == BOARD_NAME
        for line in str(boards["output"]).splitlines()
    )
    hardware_probe = (
        _run_probe([executable, "-b", BOARD_NAME, "--detect"])
        if probe_hardware and board_profile_present
        else None
    )
    return {
        "requested": name,
        "path": executable,
        "available": True,
        "version": version,
        "board_profile": BOARD_NAME,
        "board_profile_present": board_profile_present,
        "hardware_probe": hardware_probe,
    }


def build_report(
    bitstream: Path,
    manifest: Path,
    programmer: str,
    probe_hardware: bool,
) -> dict[str, object]:
    artifact = validate_artifact(bitstream, manifest)
    programmer_report = inspect_programmer(programmer, probe_hardware)
    probe = programmer_report.get("hardware_probe")
    hardware_detected = (
        isinstance(probe, dict)
        and probe.get("returncode") == 0
        and not probe.get("timed_out")
    )
    return {
        "schema_version": 1,
        "operation": "non-programming hardware preflight",
        "artifact": artifact,
        "programmer": programmer_report,
        "artifact_ready": True,
        "hardware_detected": hardware_detected,
        "sram_program_command": [
            programmer,
            "-b",
            BOARD_NAME,
            str(bitstream),
        ],
        "programming_performed": False,
        "hardware_validated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bitstream", type=Path, default=DEFAULT_BITSTREAM)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--programmer", default="openFPGALoader")
    parser.add_argument("--probe-hardware", action="store_true")
    parser.add_argument("--require-hardware", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    bitstream = args.bitstream.resolve()
    manifest = (
        args.manifest.resolve()
        if args.manifest is not None
        else bitstream.with_suffix(".bit.json")
    )
    try:
        report = build_report(
            bitstream,
            manifest,
            args.programmer,
            args.probe_hardware or args.require_hardware,
        )
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if args.output is not None:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if args.require_hardware and not report["hardware_detected"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
