#!/usr/bin/env python3
"""Convert a routed XC7 FASM artifact into frames and a configuration bitstream."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOT = REPOSITORY_ROOT / ".tools" / "root" / "usr"
PRJXRAY_SOURCE = REPOSITORY_ROOT / ".tools" / "src" / "prjxray"
PRJXRAY_DATABASE = REPOSITORY_ROOT / ".tools" / "src" / "prjxray-db" / "artix7"
OPENXC7_PYTHON = REPOSITORY_ROOT / ".tools" / "openxc7-venv" / "bin" / "python"
FASM2FRAMES = PRJXRAY_SOURCE / "utils" / "fasm2frames.py"
XC7FRAMES2BIT = LOCAL_ROOT / "bin" / "xc7frames2bit"
BITREAD = LOCAL_ROOT / "bin" / "bitread"
DEFAULT_PART = "xc7a200tsbg484-1"


def file_sha256(path: Path) -> str:
    """Return the lowercase SHA-256 digest of an artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def line_count(path: Path) -> int:
    """Count newline-terminated records without retaining a large artifact."""

    count = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            count += chunk.count(b"\n")
    return count


def git_revision(checkout: Path) -> str | None:
    """Return an exact checkout revision when the source tree is available."""

    completed = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def default_output_paths(fasm: Path) -> tuple[Path, Path, Path]:
    """Return frame, bitstream, and report paths beside a FASM input."""

    return (
        fasm.with_suffix(".frm"),
        fasm.with_suffix(".bit"),
        fasm.with_suffix(".bit.json"),
    )


def command_environment() -> dict[str, str]:
    """Expose the pinned Project X-Ray Python modules to its utility script."""

    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH")
    source = str(PRJXRAY_SOURCE)
    environment["PYTHONPATH"] = f"{source}:{existing}" if existing else source
    local_library = LOCAL_ROOT / "lib"
    if local_library.exists():
        existing_library = environment.get("LD_LIBRARY_PATH")
        environment["LD_LIBRARY_PATH"] = (
            f"{local_library}:{existing_library}"
            if existing_library
            else str(local_library)
        )
    return environment


def relative_to_repository(path: Path) -> str:
    """Return a readable artifact name without requiring it to be in-tree."""

    try:
        return str(path.relative_to(REPOSITORY_ROOT))
    except ValueError:
        return str(path)


def normalize_bitstream_timestamp(path: Path, source_date_epoch: int) -> str:
    """Replace variable `.bit` date/time metadata with a reproducible UTC value."""

    data = bytearray(path.read_bytes())
    if data[:13] != bytes(
        (0x00, 0x09, 0x0F, 0xF0, 0x0F, 0xF0, 0x0F, 0xF0, 0x0F, 0xF0, 0, 0, 1)
    ):
        raise ValueError("unrecognized Xilinx .bit header prefix")

    fields: dict[str, tuple[int, int]] = {}
    position = 13
    for expected_tag in "abcd":
        if position + 3 > len(data) or data[position] != ord(expected_tag):
            raise ValueError(f"missing Xilinx .bit header field {expected_tag!r}")
        length = int.from_bytes(data[position + 1 : position + 3], "big")
        start = position + 3
        end = start + length
        if end > len(data):
            raise ValueError(f"truncated Xilinx .bit header field {expected_tag!r}")
        fields[expected_tag] = (start, end)
        position = end
    if position + 5 > len(data) or data[position] != ord("e"):
        raise ValueError("missing Xilinx .bit payload-length field")

    timestamp = datetime.fromtimestamp(source_date_epoch, timezone.utc)
    replacements = {
        "c": timestamp.strftime("%Y/%m/%d").encode("ascii") + b"\0",
        "d": timestamp.strftime("%H:%M:%S").encode("ascii") + b"\0",
    }
    for tag, replacement in replacements.items():
        start, end = fields[tag]
        if len(replacement) != end - start:
            raise ValueError(f"unexpected Xilinx .bit field {tag!r} length")
        data[start:end] = replacement
    path.write_bytes(data)
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_bitread_measurements(output: str) -> tuple[int, int, int]:
    """Extract emitted bytes, configuration words, and frame count."""

    patterns = (
        r"Bitstream size: (\d+) bytes",
        r"Config size: (\d+) words",
        r"Number of configuration frames: (\d+)",
    )
    values = []
    for pattern in patterns:
        match = re.search(pattern, output)
        if match is None:
            raise ValueError("bitread output is missing measured configuration data")
        values.append(int(match.group(1)))
    return values[0], values[1], values[2]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Convert nextpnr XC7 FASM through Project X-Ray frames into a "
            "configuration bitstream. This generates an artifact; it does not "
            "program or validate hardware."
        )
    )
    parser.add_argument("--fasm", type=Path, required=True)
    parser.add_argument("--part", default=DEFAULT_PART)
    parser.add_argument("--frames", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=0,
        help="UTC timestamp stored in reproducible .bit metadata (default: 0)",
    )
    args = parser.parse_args()

    fasm = args.fasm if args.fasm.is_absolute() else REPOSITORY_ROOT / args.fasm
    if not fasm.is_file():
        parser.error(f"FASM input does not exist: {fasm}")

    default_frames, default_output, default_summary = default_output_paths(fasm)
    frames = args.frames or default_frames
    output = args.output or default_output
    summary = args.summary or default_summary
    frames = frames if frames.is_absolute() else REPOSITORY_ROOT / frames
    output = output if output.is_absolute() else REPOSITORY_ROOT / output
    summary = summary if summary.is_absolute() else REPOSITORY_ROOT / summary

    part_yaml = PRJXRAY_DATABASE / args.part / "part.yaml"
    required = (OPENXC7_PYTHON, FASM2FRAMES, XC7FRAMES2BIT, BITREAD, part_yaml)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print(
            "ERROR: missing open XC7 bitstream tool/data: " + ", ".join(missing)
            + "; run `make tools-openxc7`",
            file=sys.stderr,
        )
        return 2

    for path in (frames, output, summary):
        path.parent.mkdir(parents=True, exist_ok=True)
    frames.unlink(missing_ok=True)
    output.unlink(missing_ok=True)
    summary.unlink(missing_ok=True)

    environment = command_environment()
    assemble = subprocess.run(
        [
            str(OPENXC7_PYTHON),
            str(FASM2FRAMES),
            "--db-root",
            str(PRJXRAY_DATABASE),
            "--part",
            args.part,
            str(fasm),
            str(frames),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
    )
    if assemble.returncode != 0 or not frames.is_file():
        return assemble.returncode or 1

    emit = subprocess.run(
        [
            str(XC7FRAMES2BIT),
            "--part_name",
            args.part,
            "--part_file",
            str(part_yaml),
            "--frm_file",
            relative_to_repository(frames),
            "--output_file",
            str(output),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
    )
    if emit.returncode != 0 or not output.is_file():
        return emit.returncode or 1

    try:
        normalized_timestamp = normalize_bitstream_timestamp(
            output, args.source_date_epoch
        )
    except (OSError, OverflowError, ValueError) as error:
        print(f"ERROR: cannot normalize bitstream metadata: {error}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="fpga_amp_bitread_") as directory:
        readback = Path(directory) / "readback.bits"
        audit = subprocess.run(
            [
                str(BITREAD),
                "-C",
                "--part_file",
                str(part_yaml),
                "-o",
                str(readback),
                str(output),
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if audit.returncode != 0 or not readback.is_file():
            if audit.stdout:
                print(audit.stdout, file=sys.stderr, end="")
            print("ERROR: bitread could not validate the bitstream", file=sys.stderr)
            return audit.returncode or 1
    try:
        audited_bytes, configuration_words, configuration_frames = (
            parse_bitread_measurements(audit.stdout)
        )
    except ValueError as error:
        print(f"ERROR: cannot parse bitread validation: {error}", file=sys.stderr)
        return 1
    if audited_bytes != output.stat().st_size:
        print("ERROR: bitread reported an inconsistent bitstream size", file=sys.stderr)
        return 1

    result = {
        "flow": "Project X-Ray fasm2frames + xc7frames2bit",
        "part": args.part,
        "fasm": relative_to_repository(fasm),
        "fasm_bytes": fasm.stat().st_size,
        "fasm_sha256": file_sha256(fasm),
        "frames": relative_to_repository(frames),
        "frames_bytes": frames.stat().st_size,
        "frame_records": line_count(frames),
        "frames_sha256": file_sha256(frames),
        "bitstream": relative_to_repository(output),
        "bitstream_bytes": output.stat().st_size,
        "bitstream_sha256": file_sha256(output),
        "bitstream_header_timestamp_utc": normalized_timestamp,
        "bitread_crc_validation": True,
        "bitread_configuration_words": configuration_words,
        "bitread_configuration_frames": configuration_frames,
        "prjxray_revision": git_revision(PRJXRAY_SOURCE),
        "prjxray_database_revision": git_revision(PRJXRAY_DATABASE.parent),
        "bitstream_generated": True,
        "hardware_programmed": False,
        "hardware_validated": False,
    }
    summary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
