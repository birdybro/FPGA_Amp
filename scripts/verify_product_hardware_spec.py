#!/usr/bin/env python3
"""Validate the product hardware requirement ledger and Markdown traceability."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = ROOT / "hardware" / "product_v1" / "requirements.json"

REQUIREMENT_ID = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]{3}$")
INTERFACE_ID = re.compile(r"^IF-[A-Z0-9-]+$")
CLASSIFICATIONS = {"reference", "modern", "infrastructure", "safety", "regulatory"}
PRIORITIES = {"must", "should", "may"}
STATUSES = {"frozen", "provisional", "gate"}
VERIFICATION_METHODS = {
    "inspection",
    "analysis",
    "simulation",
    "test",
    "demonstration",
    "certification",
}
REQUIRED_FROZEN_INVARIANTS = {
    "SYS-002": "reference-model boundary",
    "EARC-002": "two-channel LPCM",
    "EARC-004": "unavailable compressed or multichannel decoding",
    "VOL-002": "out of the analog audio path",
    "UI-004": "physical mute and standby",
    "SAFE-001": "independent analog output mute",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read valid JSON from {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("requirements root must be a JSON object")
    return value


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def validate(requirements_path: Path = DEFAULT_REQUIREMENTS) -> dict[str, Any]:
    data = _load_json(requirements_path)
    if data.get("schema_version") != 1:
        raise ValueError("schema_version must be exactly 1")

    document_value = _require_nonempty_string(data.get("document"), "document")
    document_path = Path(document_value)
    if not document_path.is_absolute():
        document_path = ROOT / document_path
    try:
        document = document_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"cannot read specification document {document_path}: {error}") from error

    board_set = data.get("board_set")
    if not isinstance(board_set, list) or len(board_set) < 2:
        raise ValueError("board_set must contain at least two board records")
    board_ids: set[str] = set()
    for index, board in enumerate(board_set):
        if not isinstance(board, dict):
            raise ValueError(f"board_set[{index}] must be an object")
        board_id = _require_nonempty_string(board.get("id"), f"board_set[{index}].id")
        if board_id in board_ids:
            raise ValueError(f"duplicate board id {board_id}")
        board_ids.add(board_id)
        _require_nonempty_string(board.get("name"), f"board {board_id}.name")
        _require_nonempty_string(board.get("purpose"), f"board {board_id}.purpose")

    interfaces = data.get("interfaces")
    if not isinstance(interfaces, list) or not interfaces:
        raise ValueError("interfaces must be a non-empty list")
    interface_ids: set[str] = set()
    interface_records: dict[str, dict[str, Any]] = {}
    for index, interface in enumerate(interfaces):
        if not isinstance(interface, dict):
            raise ValueError(f"interfaces[{index}] must be an object")
        interface_id = _require_nonempty_string(interface.get("id"), f"interfaces[{index}].id")
        if not INTERFACE_ID.fullmatch(interface_id):
            raise ValueError(f"invalid interface id {interface_id}")
        if interface_id in interface_ids:
            raise ValueError(f"duplicate interface id {interface_id}")
        interface_ids.add(interface_id)
        interface_records[interface_id] = interface
        for endpoint in ("from", "to"):
            board_id = _require_nonempty_string(
                interface.get(endpoint), f"interface {interface_id}.{endpoint}"
            )
            if board_id not in board_ids:
                raise ValueError(
                    f"interface {interface_id} references unknown {endpoint} board {board_id}"
                )
        signals = interface.get("signals")
        if not isinstance(signals, list) or not signals or not all(
            isinstance(signal, str) and signal for signal in signals
        ):
            raise ValueError(f"interface {interface_id}.signals must be non-empty strings")
        if len(signals) != len(set(signals)):
            raise ValueError(f"interface {interface_id} contains duplicate signals")
        _require_nonempty_string(interface.get("clock_owner"), f"interface {interface_id}.clock_owner")
        _require_nonempty_string(interface.get("electrical"), f"interface {interface_id}.electrical")
        for field in ("minimum_connector_contacts", "ground_contacts", "reserved_contacts"):
            value = interface.get(field)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"interface {interface_id}.{field} must be a non-negative integer")
        if interface["minimum_connector_contacts"] == 0:
            raise ValueError(f"interface {interface_id} must budget connector contacts")

    budget_value = _require_nonempty_string(data.get("interface_budget"), "interface_budget")
    budget_path = Path(budget_value)
    if not budget_path.is_absolute():
        budget_path = ROOT / budget_path
    try:
        with budget_path.open(newline="", encoding="utf-8") as stream:
            budget_rows = list(csv.DictReader(stream))
    except OSError as error:
        raise ValueError(f"cannot read interface budget {budget_path}: {error}") from error
    expected_columns = {
        "interface_id",
        "signal",
        "driver",
        "receiver",
        "electrical",
        "clock_domain",
        "pins",
        "notes",
    }
    if not budget_rows or set(budget_rows[0]) != expected_columns:
        raise ValueError(f"interface budget columns must be exactly {sorted(expected_columns)}")
    budget_signals: dict[str, set[str]] = {interface_id: set() for interface_id in interface_ids}
    budget_pin_counts = {interface_id: 0 for interface_id in interface_ids}
    for index, row in enumerate(budget_rows, start=2):
        interface_id = row["interface_id"]
        if interface_id not in interface_ids:
            raise ValueError(f"interface budget row {index} references unknown interface {interface_id}")
        signal = _require_nonempty_string(row["signal"], f"interface budget row {index}.signal")
        if signal in budget_signals[interface_id]:
            raise ValueError(f"interface budget repeats {interface_id} signal {signal}")
        budget_signals[interface_id].add(signal)
        for field in ("driver", "receiver", "electrical", "clock_domain", "notes"):
            _require_nonempty_string(row[field], f"interface budget row {index}.{field}")
        try:
            pins = int(row["pins"])
        except ValueError as error:
            raise ValueError(f"interface budget row {index}.pins must be an integer") from error
        if pins <= 0:
            raise ValueError(f"interface budget row {index}.pins must be positive")
        budget_pin_counts[interface_id] += pins

    for interface_id, interface in interface_records.items():
        expected_signals = set(interface["signals"])
        if budget_signals[interface_id] != expected_signals:
            raise ValueError(
                f"interface budget signals differ for {interface_id}: expected "
                f"{sorted(expected_signals)}, got {sorted(budget_signals[interface_id])}"
            )
        used_contacts = (
            budget_pin_counts[interface_id]
            + interface["ground_contacts"]
            + interface["reserved_contacts"]
        )
        if used_contacts > interface["minimum_connector_contacts"]:
            raise ValueError(
                f"interface {interface_id} budgets {used_contacts} contacts but connector has "
                f"{interface['minimum_connector_contacts']}"
            )

    requirements = data.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("requirements must be a non-empty list")

    requirement_ids: set[str] = set()
    records: dict[str, dict[str, Any]] = {}
    covered_boards: set[str] = set()
    class_counts = {classification: 0 for classification in CLASSIFICATIONS}
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            raise ValueError(f"requirements[{index}] must be an object")
        requirement_id = _require_nonempty_string(
            requirement.get("id"), f"requirements[{index}].id"
        )
        if not REQUIREMENT_ID.fullmatch(requirement_id):
            raise ValueError(f"invalid requirement id {requirement_id}")
        if requirement_id in requirement_ids:
            raise ValueError(f"duplicate requirement id {requirement_id}")
        requirement_ids.add(requirement_id)
        records[requirement_id] = requirement

        _require_nonempty_string(requirement.get("title"), f"requirement {requirement_id}.title")
        _require_nonempty_string(
            requirement.get("rationale"), f"requirement {requirement_id}.rationale"
        )
        classification = requirement.get("classification")
        if classification not in CLASSIFICATIONS:
            raise ValueError(
                f"requirement {requirement_id} has invalid classification {classification!r}"
            )
        class_counts[classification] += 1
        if requirement.get("priority") not in PRIORITIES:
            raise ValueError(f"requirement {requirement_id} has invalid priority")
        if requirement.get("status") not in STATUSES:
            raise ValueError(f"requirement {requirement_id} has invalid status")

        boards = requirement.get("boards")
        if not isinstance(boards, list) or not boards:
            raise ValueError(f"requirement {requirement_id}.boards must be a non-empty list")
        if len(boards) != len(set(boards)):
            raise ValueError(f"requirement {requirement_id} contains duplicate boards")
        unknown_boards = set(boards) - board_ids
        if unknown_boards:
            raise ValueError(
                f"requirement {requirement_id} references unknown boards {sorted(unknown_boards)}"
            )
        covered_boards.update(boards)

        verification = requirement.get("verification")
        if not isinstance(verification, list) or not verification:
            raise ValueError(
                f"requirement {requirement_id}.verification must be a non-empty list"
            )
        unknown_methods = set(verification) - VERIFICATION_METHODS
        if unknown_methods:
            raise ValueError(
                f"requirement {requirement_id} has invalid verification methods "
                f"{sorted(unknown_methods)}"
            )
        if len(verification) != len(set(verification)):
            raise ValueError(f"requirement {requirement_id} repeats verification methods")

        if requirement_id not in document:
            raise ValueError(
                f"requirement {requirement_id} is absent from traceability document {document_path}"
            )

    if covered_boards != board_ids:
        raise ValueError(f"boards without requirements: {sorted(board_ids - covered_boards)}")
    missing_classes = sorted(
        classification for classification, count in class_counts.items() if count == 0
    )
    if missing_classes:
        raise ValueError(f"unused classifications: {missing_classes}")

    for requirement_id, expected_title_fragment in REQUIRED_FROZEN_INVARIANTS.items():
        requirement = records.get(requirement_id)
        if requirement is None:
            raise ValueError(f"missing required invariant {requirement_id}")
        if requirement.get("status") != "frozen" or requirement.get("priority") != "must":
            raise ValueError(f"invariant {requirement_id} must remain frozen and mandatory")
        title = str(requirement.get("title", "")).lower()
        if expected_title_fragment.lower() not in title:
            raise ValueError(
                f"invariant {requirement_id} title must retain {expected_title_fragment!r}"
            )

    if "hardware/product_v1/requirements.json" not in document:
        raise ValueError("specification must link its machine-readable requirements")

    status_counts = {
        status: sum(1 for requirement in requirements if requirement["status"] == status)
        for status in sorted(STATUSES)
    }
    priority_counts = {
        priority: sum(1 for requirement in requirements if requirement["priority"] == priority)
        for priority in sorted(PRIORITIES)
    }
    return {
        "schema_version": 1,
        "requirements": len(requirements),
        "boards": len(board_set),
        "interfaces": len(interfaces),
        "interface_signal_rows": len(budget_rows),
        "classification_counts": dict(sorted(class_counts.items())),
        "priority_counts": priority_counts,
        "status_counts": status_counts,
        "document": str(document_path.relative_to(ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requirements", nargs="?", type=Path, default=DEFAULT_REQUIREMENTS)
    args = parser.parse_args()
    try:
        report = validate(args.requirements)
    except ValueError as error:
        parser.exit(1, f"hardware specification validation failed: {error}\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
