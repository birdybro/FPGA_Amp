#!/usr/bin/env python3
"""Prove integer width bounds for the accepted wide network datapath.

The calculation uses conservative independent intervals for every declared
state/input bit pattern and the frozen generated circuit constants. It does not
infer safety from observed audio trajectories. Deliberate state/correction
saturators are reported separately from products and sums that must never wrap.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model" / "python"))

from fpga_amp.factorized_tube import FixedFactorizedKoren12AX7  # noqa: E402
from fpga_amp.fixed_circuit import (  # noqa: E402
    FixedWideStateTrapezoidalV1CircuitModel,
    FixedWideStateV1CircuitModel,
)


@dataclass(frozen=True)
class Interval:
    low: int
    high: int

    def __post_init__(self) -> None:
        if self.low > self.high:
            raise ValueError("reversed interval")

    def __add__(self, other: Interval) -> Interval:
        return Interval(self.low + other.low, self.high + other.high)

    def __sub__(self, other: Interval) -> Interval:
        return Interval(self.low - other.high, self.high - other.low)

    def __neg__(self) -> Interval:
        return Interval(-self.high, -self.low)

    def scale(self, constant: int) -> Interval:
        endpoints = (self.low * constant, self.high * constant)
        return Interval(min(endpoints), max(endpoints))

    def add_constant(self, constant: int) -> Interval:
        return Interval(self.low + constant, self.high + constant)

    def arithmetic_shift(self, shift: int) -> Interval:
        if shift < 0:
            return self.scale(1 << -shift)
        return Interval(self.low >> shift, self.high >> shift)

    @property
    def max_abs(self) -> int:
        return max(abs(self.low), abs(self.high))

    @property
    def required_signed_bits(self) -> int:
        width = 1
        while (
            self.low < -(1 << (width - 1))
            or self.high > (1 << (width - 1)) - 1
        ):
            width += 1
        return width

    def fits(self, width: int) -> bool:
        return self.required_signed_bits <= width

    def as_dict(self) -> dict[str, int]:
        return {
            "low": self.low,
            "high": self.high,
            "max_abs": self.max_abs,
            "required_signed_bits": self.required_signed_bits,
        }


def signed_interval(width: int) -> Interval:
    return Interval(-(1 << (width - 1)), (1 << (width - 1)) - 1)


def rounded_shift(value: Interval, shift: int) -> Interval:
    if shift <= 0:
        return value.arithmetic_shift(shift)
    return value.add_constant(1 << (shift - 1)).arithmetic_shift(shift)


def add_check(
    checks: list[dict[str, object]], name: str, value: Interval, declared_bits: int
) -> None:
    checks.append(
        {
            "name": name,
            "declared_signed_bits": declared_bits,
            **value.as_dict(),
            "headroom_bits": declared_bits - value.required_signed_bits,
            "passes": value.fits(declared_bits),
        }
    )


def enclosing(values: list[Interval]) -> Interval:
    return Interval(
        min(value.low for value in values), max(value.high for value in values)
    )


def constant_interval(values: list[int]) -> Interval:
    return Interval(min(values), max(values))


def q30_node_intervals(model: FixedWideStateV1CircuitModel) -> list[Interval]:
    state = signed_interval(40)
    converted: list[Interval] = []
    for fractional_bits in model.VOLTAGE_FRACTIONAL_BITS:
        if int(fractional_bits) == 28:
            converted.append(state.scale(4))
        else:
            converted.append(rounded_shift(state, 2))
    return converted


def rhs_bounds(
    model: FixedWideStateV1CircuitModel, checks: list[dict[str, object]]
) -> list[Interval]:
    input_product = signed_interval(32).scale(model.input_conductance_q47)
    add_check(checks, "RHS input conductance product", input_product, 73)
    input_biased = input_product.add_constant(1 << 26)
    add_check(checks, "RHS input product plus rounding bias", input_biased, 73)
    input_current = input_biased.arithmetic_shift(27)
    add_check(checks, "RHS converted input current Q44", input_current, 55)

    rhs = [Interval(int(value), int(value)) for value in model.fixed_rhs_q44]
    rhs[0] = rhs[0] + input_current
    add_check(checks, "RHS reachable output lanes", enclosing(rhs), 55)
    return rhs


def tube_stamp_bounds() -> list[Interval]:
    current = signed_interval(32)
    direct = current.scale(1 << 13)
    cathode = (-(current + current)).scale(1 << 13)
    zero = Interval(0, 0)
    return [direct, direct, cathode, zero, direct, zero, direct, cathode, zero]


def solver_tube_pin_bounds(checks: list[dict[str, object]]) -> None:
    node = signed_interval(40)
    q32_to_q24 = rounded_shift(node, 8)
    q28_to_q20 = rounded_shift(node, 8)
    q32_to_q20 = rounded_shift(node, 12)
    grid_cathode = q32_to_q24 - q32_to_q24
    plate_cathode = q28_to_q20 - q32_to_q20
    add_check(
        checks,
        "solver node conversion before tube-pin subtraction",
        enclosing([q32_to_q24, q28_to_q20, q32_to_q20]),
        40,
    )
    add_check(
        checks, "solver Vgk wide difference before saturation", grid_cathode, 41
    )
    add_check(
        checks, "solver Vpk wide difference before saturation", plate_cathode, 41
    )
    add_check(
        checks,
        "solver saturated tube-pin interface storage",
        signed_interval(32),
        32,
    )


def network_bounds(
    model: FixedWideStateV1CircuitModel,
    name: str,
    checks: list[dict[str, object]],
) -> dict[str, object]:
    node = signed_interval(40)
    node_q30 = q30_node_intervals(model)
    capacitor_state = signed_interval(40)
    prior_current = signed_interval(48)

    matrix_currents: list[list[Interval]] = []
    matrix_products: list[Interval] = []
    matrix_biased: list[Interval] = []
    for row in range(model.node_count):
        row_currents: list[Interval] = []
        for column in range(model.node_count):
            product = node.scale(int(model.matrix_q47[row, column]))
            shift = int(model.VOLTAGE_FRACTIONAL_BITS[column]) + 3
            matrix_products.append(product)
            matrix_biased.append(product.add_constant(1 << (shift - 1)))
            row_currents.append(rounded_shift(product, shift))
        matrix_currents.append(row_currents)

    add_check(checks, f"{name} static matrix products", enclosing(matrix_products), 81)
    add_check(
        checks,
        f"{name} matrix products plus rounding bias",
        enclosing(matrix_biased),
        81,
    )

    branch_currents: list[Interval] = []
    delta_intervals: list[Interval] = []
    capacitor_products: list[Interval] = []
    capacitor_biased: list[Interval] = []
    for capacitor in model.capacitors:
        voltage_a = (
            Interval(0, 0)
            if capacitor.node_a is None
            else node_q30[capacitor.node_a]
        )
        voltage_b = (
            Interval(0, 0)
            if capacitor.node_b is None
            else node_q30[capacitor.node_b]
        )
        delta = voltage_a - voltage_b - capacitor_state
        product = delta.scale(int(capacitor.conductance_q47))
        biased = product.add_constant(1 << 32)
        branch = biased.arithmetic_shift(33)
        if model.integration_method == "trapezoidal":
            branch = branch - prior_current
        delta_intervals.append(delta)
        capacitor_products.append(product)
        capacitor_biased.append(biased)
        branch_currents.append(branch)

    all_deltas = enclosing(delta_intervals)
    all_products = enclosing(capacitor_products)
    all_biased = enclosing(capacitor_biased)
    all_branches = enclosing(branch_currents)
    add_check(checks, f"{name} capacitor Q30 differences", all_deltas, 44)
    add_check(checks, f"{name} capacitor conductance products", all_products, 92)
    add_check(checks, f"{name} capacitor products plus rounding bias", all_biased, 92)
    add_check(checks, f"{name} unsaturated branch currents Q44", all_branches, 63)

    tube = tube_stamp_bounds()
    add_check(
        checks,
        f"{name} two-current cathode sum before Q44 shift",
        -(signed_interval(32) + signed_interval(32)),
        34,
    )
    add_check(checks, f"{name} tube stamps Q44", enclosing(tube), 63)

    # The KCL input is a public signed-55 contract. Proving against its full
    # range also covers the much smaller reachable RHS-engine interval.
    accumulator = [-signed_interval(55) for _ in range(model.node_count)]
    intermediate: list[Interval] = accumulator.copy()
    for column in range(9):
        capacitor = model.capacitors[column]
        branch = branch_currents[column]
        for row in range(model.node_count):
            stamp = Interval(0, 0)
            if capacitor.node_a == row:
                stamp = stamp + branch
            if capacitor.node_b == row:
                stamp = stamp - branch
            accumulator[row] = accumulator[row] + matrix_currents[row][column] + stamp
            intermediate.append(accumulator[row])

    capacitor = model.capacitors[9]
    for row in range(model.node_count):
        stamp = Interval(0, 0)
        if capacitor.node_a == row:
            stamp = stamp + branch_currents[9]
        if capacitor.node_b == row:
            stamp = stamp - branch_currents[9]
        accumulator[row] = accumulator[row] + tube[row] + stamp
        intermediate.append(accumulator[row])

    all_accumulators = enclosing(intermediate)
    final_residual = enclosing(accumulator)
    add_check(checks, f"{name} every serialized KCL partial sum", all_accumulators, 63)
    add_check(checks, f"{name} final KCL residual and absolute value", final_residual, 63)

    return {
        "capacitor_delta_by_index": [value.as_dict() for value in delta_intervals],
        "capacitor_branch_current_by_index_q44": [
            value.as_dict() for value in branch_currents
        ],
        "kcl_final_by_row_q44": [value.as_dict() for value in accumulator],
        "worst_partial_sum_q44": all_accumulators.as_dict(),
    }


def chord_bounds(
    model: FixedWideStateV1CircuitModel, checks: list[dict[str, object]]
) -> dict[str, object]:
    residual = signed_interval(25)
    products: list[Interval] = []
    accumulators: list[Interval] = []
    final_by_row: list[Interval] = []
    scaled: list[Interval] = []
    updated: list[Interval] = []
    for row in range(model.node_count):
        accumulator = Interval(0, 0)
        for column in range(model.node_count):
            product = residual.scale(int(model.chord_inverse_q[row, column]))
            products.append(product)
            accumulator = accumulator + product
            accumulators.append(accumulator)
        final_by_row.append(accumulator)
        for residual_fraction in (30, 34, 40):
            node_fraction = int(model.VOLTAGE_FRACTIONAL_BITS[row])
            shift = model.inverse_fractional_bits + residual_fraction - node_fraction
            correction = rounded_shift(accumulator, shift)
            scaled.append(correction)
            updated.append(signed_interval(40) - correction)

    all_products = enclosing(products)
    all_accumulators = enclosing(accumulators)
    all_scaled = enclosing(scaled)
    all_updated = enclosing(updated)
    add_check(checks, "chord coefficient-residual products", all_products, 43)
    add_check(checks, "chord serialized partial sums", all_accumulators, 48)
    add_check(checks, "chord scaled correction", all_scaled, 49)
    add_check(checks, "chord voltage-minus-correction before saturation", all_updated, 50)
    return {
        "accumulator_by_row": [value.as_dict() for value in final_by_row],
        "worst_partial_sum": all_accumulators.as_dict(),
        "worst_scaled_correction": all_scaled.as_dict(),
        "worst_pre_saturation_update": all_updated.as_dict(),
    }


def main() -> int:
    tube = FixedFactorizedKoren12AX7()
    backward_euler = FixedWideStateV1CircuitModel(tube_lut=tube)
    trapezoidal = FixedWideStateTrapezoidalV1CircuitModel(tube_lut=tube)
    checks: list[dict[str, object]] = []

    add_check(
        checks,
        "frozen static matrix coefficients",
        constant_interval([int(value) for value in backward_euler.matrix_q47.flat]),
        41,
    )
    add_check(
        checks,
        "backward-Euler capacitor coefficients",
        constant_interval(
            [int(value.conductance_q47) for value in backward_euler.capacitors]
        ),
        47,
    )
    add_check(
        checks,
        "trapezoidal capacitor coefficients",
        constant_interval(
            [int(value.conductance_q47) for value in trapezoidal.capacitors]
        ),
        48,
    )
    add_check(
        checks,
        "fixed RHS ROM coefficients",
        constant_interval([int(value) for value in backward_euler.fixed_rhs_q44]),
        48,
    )
    add_check(
        checks,
        "chord inverse coefficients",
        constant_interval(
            [int(value) for value in backward_euler.chord_inverse_q.flat]
        ),
        18,
    )

    reachable_rhs = rhs_bounds(backward_euler, checks)
    solver_tube_pin_bounds(checks)
    modes = {
        "backward_euler": network_bounds(backward_euler, "backward-Euler", checks),
        "trapezoidal": network_bounds(trapezoidal, "trapezoidal", checks),
    }
    chord = chord_bounds(backward_euler, checks)
    failures = [str(check["name"]) for check in checks if not bool(check["passes"])]
    report = {
        "model": "12ax7_passive_riaa_v1",
        "method": (
            "conservative independent integer intervals over every declared "
            "state/input bit pattern and frozen generated coefficient"
        ),
        "scope": [
            "wide RHS engine",
            "backward-Euler and trapezoidal wide KCL engines",
            "tube-current KCL stamps",
            "wide chord corrector",
            "wide solver tube-pin conversions",
        ],
        "deliberate_saturators_excluded_from_no_wrap_claim": [
            "signed-25 residual operand conversion",
            "signed-40 corrected node commit",
            "signed-40 capacitor voltage-history commit",
            "signed-48 trapezoidal current-history commit",
            "signed-32 tube-pin voltage interface",
        ],
        "all_checks_pass": not failures,
        "failures": failures,
        "checks": checks,
        "reachable_rhs_by_row_q44": [value.as_dict() for value in reachable_rhs],
        "network_modes": modes,
        "chord": chord,
    }
    output = ROOT / "reference" / "results" / "wide_arithmetic_bounds.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = {
        "all_checks_pass": report["all_checks_pass"],
        "checks": len(checks),
        "failures": failures,
        "maximum_required_bits": max(
            int(check["required_signed_bits"]) for check in checks
        ),
        "output": str(output.relative_to(ROOT)),
    }
    print(json.dumps(summary, indent=2))
    if failures:
        raise SystemExit("arithmetic bound failure: " + ", ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
