#!/usr/bin/env python3
"""Summarize major solver hierarchy placement from nextpnr JSON."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re


BEL_COORDINATE = re.compile(r"X(\d+)Y(\d+)")
RESOURCE_TYPES = (
    "SLICE_LUTX",
    "SLICE_FFX",
    "CARRY4",
    "DSP48E1_DSP48E1",
    "RAMB18E1_RAMB18E1",
    "RAMB36E1_RAMB36E1",
)
HARD_BLOCK_TYPES = {
    "DSP48E1_DSP48E1",
    "RAMB18E1_RAMB18E1",
    "RAMB36E1_RAMB36E1",
}


def hierarchy_group(raw_name: str) -> str:
    """Classify flattened cells without depending on generated numeric names."""

    name = raw_name.replace("\\", "")
    if "generate_parallel_tube.generate_hermite_tube.tube_engine" in name:
        return "tube_2_parallel"
    if "generate_hermite_tube.tube_engine" in name:
        return "tube_1_primary"
    for token, group in (
        ("kcl_engine", "kcl"),
        ("chord_engine", "chord"),
        ("terminal_current_engine", "terminal_current"),
        ("rhs_engine", "rhs"),
    ):
        if token in name:
            return group
    if "harness.solver.core" in name or "harness.solver" in name:
        return "solver_control_and_state"
    return "harness_and_constants"


def bounding_box(points: list[tuple[int, int]]) -> dict[str, object] | None:
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "minimum": [min(xs), min(ys)],
        "maximum": [max(xs), max(ys)],
        "span": [max(xs) - min(xs), max(ys) - min(ys)],
        "centroid": [
            round(sum(xs) / len(xs), 2),
            round(sum(ys) / len(ys), 2),
        ],
        "placed_cells": len(points),
    }


def summarize(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    modules = payload.get("modules", {})
    if len(modules) != 1:
        raise ValueError(
            f"expected one flattened placed module, found {len(modules)}"
        )
    module = next(iter(modules.values()))
    cells = module.get("cells", {})
    grouped: dict[str, dict[str, object]] = {}
    for name, cell in cells.items():
        group = hierarchy_group(name)
        state = grouped.setdefault(
            group,
            {
                "resources": Counter(),
                "points": [],
                "hard_block_points": [],
            },
        )
        cell_type = cell.get("type", "unknown")
        if cell_type in RESOURCE_TYPES:
            state["resources"][cell_type] += 1
        bel = cell.get("attributes", {}).get("NEXTPNR_BEL", "")
        match = BEL_COORDINATE.search(bel)
        if match:
            point = (int(match.group(1)), int(match.group(2)))
            state["points"].append(point)
            if cell_type in HARD_BLOCK_TYPES:
                state["hard_block_points"].append(point)

    groups = {}
    for name in sorted(grouped):
        state = grouped[name]
        groups[name] = {
            "resources": {
                resource: state["resources"].get(resource, 0)
                for resource in RESOURCE_TYPES
            },
            "placement": bounding_box(state["points"]),
            "hard_block_placement": bounding_box(state["hard_block_points"]),
        }
    return {
        "source": str(path),
        "cell_count": len(cells),
        "groups": groups,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("placed_json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = summarize(args.placed_json)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
