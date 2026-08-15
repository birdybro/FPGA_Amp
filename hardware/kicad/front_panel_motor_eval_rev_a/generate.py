#!/usr/bin/env python3
"""Generate the KiCad motor-volume evaluation board from one net model.

KiCad's Python board API is used for placement and net assignment.  A native
KiCad schematic with embedded custom symbols is emitted from the same PARTS
table, preventing schematic/PCB connectivity drift.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parent
NAME = "front_panel_motor_eval"
MM = pcbnew.FromMM


@dataclass(frozen=True)
class Part:
    ref: str
    value: str
    footprint: str
    nets: dict[str, str]
    xy: tuple[float, float]
    rotation: float = 0.0
    description: str = ""


PARTS = [
    Part("U1", "DRV8874PWPR", "Package_SO:HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm_Mask2.46x2.31mm", {
        "1": "PWM_DRV", "2": "DIR_DRV", "3": "SLEEP_DRV", "4": "MOTOR_FAULT_N",
        "5": "VREF", "6": "IPROPI_SENSE", "7": "IMODE_CFG", "8": "MOTOR_OUT1",
        "9": "GND", "10": "MOTOR_OUT2", "11": "VM_DRV", "12": "VCP",
        "13": "CPH", "14": "CPL", "15": "GND", "16": "GND", "17": "GND",
    }, (40.0, 18.0), description="Current-sensed PH/EN H-bridge; PWP PowerPAD must be soldered"),
    Part("J1", "MOTOR_5V_INPUT", "Connector_JST:JST_VH_B2P-VH-B_1x02_P3.96mm_Vertical", {"1": "MOTOR_5V_IN", "2": "GND"}, (10.5, 8.0), description="Keyed 4.75-5.25 V motor supply from PB"),
    Part("J2", "FP_MCU_CONTROL", "Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Vertical", {
        "1": "+3V3", "2": "GND", "3": "MOTOR_PWM", "4": "MOTOR_DIR",
        "5": "MOTOR_SLEEP", "6": "MOTOR_FAULT_N", "7": "MOTOR_CURRENT_ADC",
        "8": "POT_A_ADC", "9": "POT_B_ADC", "10": "BOARD_ID_ADC", "11": "GND", "12": "GND",
    }, (10.0, 28.0), description="MCU control/telemetry; prototype header, production connector TBD"),
    Part("J3", "PRM16_MOTOR", "Connector_JST:JST_VH_B2P-VH-B_1x02_P3.96mm_Vertical", {"1": "MOTOR_OUT1", "2": "MOTOR_OUT2"}, (70.0, 8.0), description="Twisted motor pair to supported volume mechanism"),
    Part("J4", "PRM16_POSITION", "Connector_JST:JST_XH_B6B-XH-A_1x06_P2.50mm_Vertical", {
        "1": "POT_A_HIGH", "2": "POT_A_WIPER", "3": "GND",
        "4": "POT_B_HIGH", "5": "POT_B_WIPER", "6": "GND",
    }, (63.0, 29.0), description="Two ratiometric position tracks; never carries audio"),
    Part("F1", "500mA_PTC", "Fuse:Fuse_1206_3216Metric", {"1": "MOTOR_5V_IN", "2": "VM_DRV"}, (20.5, 8.0), description="Resettable input fuse; select hold/trip after measured stall test"),
    Part("D1", "SMBJ6.0A", "Diode_SMD:D_SMB", {"1": "GND", "2": "VM_DRV"}, (27.5, 7.0), description="Motor-rail transient clamp"),
    Part("C1", "100nF_50V_X7R", "Capacitor_SMD:C_0805_2012Metric", {"1": "VM_DRV", "2": "GND"}, (34.0, 8.0)),
    Part("C2", "10uF_16V_X7R", "Capacitor_SMD:C_1210_3225Metric", {"1": "VM_DRV", "2": "GND"}, (29.0, 11.5)),
    Part("C3", "220uF_10V_LOW_ESR", "Capacitor_SMD:C_Elec_6.3x5.8", {"1": "VM_DRV", "2": "GND"}, (22.0, 13.5)),
    Part("C4", "100nF_16V_X7R", "Capacitor_SMD:C_0805_2012Metric", {"1": "VCP", "2": "VM_DRV"}, (45.0, 11.0)),
    Part("C5", "22nF_16V_X7R", "Capacitor_SMD:C_0805_2012Metric", {"1": "CPH", "2": "CPL"}, (45.0, 14.0)),
    Part("R1", "33R", "Resistor_SMD:R_0805_2012Metric", {"1": "MOTOR_PWM", "2": "PWM_DRV"}, (24.0, 18.0)),
    Part("R2", "100k", "Resistor_SMD:R_0805_2012Metric", {"1": "PWM_DRV", "2": "GND"}, (29.0, 20.5), 90.0),
    Part("R3", "33R", "Resistor_SMD:R_0805_2012Metric", {"1": "MOTOR_DIR", "2": "DIR_DRV"}, (24.0, 23.0)),
    Part("R4", "100k", "Resistor_SMD:R_0805_2012Metric", {"1": "DIR_DRV", "2": "GND"}, (28.0, 25.5), 90.0),
    Part("R5", "33R", "Resistor_SMD:R_0805_2012Metric", {"1": "MOTOR_SLEEP", "2": "SLEEP_DRV"}, (24.0, 28.0)),
    Part("R6", "100k", "Resistor_SMD:R_0805_2012Metric", {"1": "SLEEP_DRV", "2": "GND"}, (28.0, 30.5), 90.0),
    Part("R7", "10k", "Resistor_SMD:R_0805_2012Metric", {"1": "+3V3", "2": "MOTOR_FAULT_N"}, (19.0, 35.0)),
    Part("R8", "14.7k_1%", "Resistor_SMD:R_0805_2012Metric", {"1": "+3V3", "2": "VREF"}, (40.0, 27.0)),
    Part("R9", "10k_1%", "Resistor_SMD:R_0805_2012Metric", {"1": "VREF", "2": "GND"}, (45.0, 27.0)),
    Part("C6", "10nF_X7R", "Capacitor_SMD:C_0805_2012Metric", {"1": "VREF", "2": "GND"}, (42.5, 30.5)),
    Part("R10", "10k_1%", "Resistor_SMD:R_0805_2012Metric", {"1": "IPROPI_SENSE", "2": "GND"}, (49.0, 19.0), 90.0),
    Part("C7", "10nF_X7R", "Capacitor_SMD:C_0805_2012Metric", {"1": "IPROPI_SENSE", "2": "GND"}, (53.0, 19.0), 90.0),
    Part("R11", "1k", "Resistor_SMD:R_0805_2012Metric", {"1": "IPROPI_SENSE", "2": "MOTOR_CURRENT_ADC"}, (51.0, 23.0)),
    Part("R12", "62k_1%", "Resistor_SMD:R_0805_2012Metric", {"1": "IMODE_CFG", "2": "GND"}, (38.0, 34.0)),
    Part("R13", "100R", "Resistor_SMD:R_0805_2012Metric", {"1": "+3V3", "2": "POT_A_HIGH"}, (58.0, 27.0)),
    Part("R14", "100R", "Resistor_SMD:R_0805_2012Metric", {"1": "+3V3", "2": "POT_B_HIGH"}, (58.0, 32.0)),
    Part("R15", "1k", "Resistor_SMD:R_0805_2012Metric", {"1": "POT_A_WIPER", "2": "POT_A_ADC"}, (62.0, 23.0)),
    Part("C8", "10nF_C0G", "Capacitor_SMD:C_0805_2012Metric", {"1": "POT_A_ADC", "2": "GND"}, (66.0, 21.0), 90.0),
    Part("R16", "1k", "Resistor_SMD:R_0805_2012Metric", {"1": "POT_B_WIPER", "2": "POT_B_ADC"}, (62.0, 37.0)),
    Part("C9", "10nF_C0G", "Capacitor_SMD:C_0805_2012Metric", {"1": "POT_B_ADC", "2": "GND"}, (67.0, 40.0), 90.0),
    Part("R17", "22k_1%", "Resistor_SMD:R_0805_2012Metric", {"1": "+3V3", "2": "BOARD_ID_ADC"}, (20.0, 40.0)),
    Part("R18", "10k_1%", "Resistor_SMD:R_0805_2012Metric", {"1": "BOARD_ID_ADC", "2": "GND"}, (27.0, 40.0)),
    Part("R19", "DNP_SNUBBER", "Resistor_SMD:R_0805_2012Metric", {"1": "MOTOR_OUT1", "2": "MOTOR_SNUB"}, (60.0, 8.0), description="DNP; tune only from conducted/radiated measurements"),
    Part("C10", "DNP_SNUBBER", "Capacitor_SMD:C_0805_2012Metric", {"1": "MOTOR_SNUB", "2": "MOTOR_OUT2"}, (65.0, 8.0), description="DNP; tune only from conducted/radiated measurements"),
]

TEST_NETS = ["VM_DRV", "GND", "MOTOR_OUT1", "MOTOR_OUT2", "VREF", "IPROPI_SENSE", "POT_A_ADC", "POT_B_ADC"]
for index, net in enumerate(TEST_NETS, 1):
    PARTS.append(Part(f"TP{index}", net, "TestPoint:TestPoint_Plated_Hole_D2.0mm", {"1": net}, (25.0 + (index - 1) * 6.0, 46.0), description="Bring-up test point"))


def sym_name(part: Part) -> str:
    return "SYM_" + part.ref.replace("#", "P")


def symbol_pin_layout(part: Part) -> list[tuple[str, str, int, int, str]]:
    pins = sorted(part.nets, key=lambda value: int(value))
    split = (len(pins) + 1) // 2
    result = []
    for index, number in enumerate(pins):
        left = index < split
        row = index if left else index - split
        y = 300 - row * 100
        result.append((number, part.nets[number], -600 if left else 600, y, "R" if left else "L"))
    return result


UUID_NAMESPACE = uuid.UUID("dd8689ea-1d89-4ce0-b901-8b1a5a7a70ae")


def uid(token: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, token))


def q(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def effects(size: float = 1.27, hide: bool = False, justify: str = "") -> str:
    hidden = " (hide yes)" if hide else ""
    aligned = f" (justify {justify})" if justify else ""
    return f"(effects (font (size {size} {size})){aligned}{hidden})"


def native_symbol_definition(part: Part, standalone: bool = False) -> str:
    name = sym_name(part)
    pins = symbol_pin_layout(part)
    rows = max(1, (len(pins) + 1) // 2)
    bottom = -max(10.16, rows * 2.54)
    prefix = "TP" if part.ref.startswith("TP") else part.ref.rstrip("0123456789")
    def prop(name: str, value: str, at: str, size: float = 1.27, hide: bool = False) -> str:
        if standalone:
            hidden = " (hide yes)" if hide else ""
            return (
                f"  (property {q(name)} {q(value)} (at {at} 0)"
                f" (show_name no) (do_not_autoplace no){hidden} {effects(size)})"
            )
        return f"  (property {q(name)} {q(value)} (at {at} 0) {effects(size, hide=hide)})"

    lines = [
        f"(symbol {q('FPGA_Amp:' + name)}",
        "  (pin_names (offset 1.016))",
        "  (exclude_from_sim no) (in_bom yes) (on_board yes)",
    ]
    if standalone:
        lines.extend(["  (in_pos_files yes)", "  (duplicate_pin_numbers_are_jumpers no)"])
    lines.extend([
        prop("Reference", prefix, "0 12.7"),
        prop("Value", part.value, f"0 {bottom - 2.54:.2f}", 1.0),
        prop("Footprint", part.footprint, "0 0", hide=True),
        prop("Datasheet", "~", "0 0", hide=True),
        prop("Description", part.description, "0 0", hide=True),
        f"  (symbol {q(name + '_1_1')}",
        f"    (rectangle (start -10.16 10.16) (end 10.16 {bottom:.2f}) (stroke (width 0.254) (type default)) (fill (type background)))",
    ])
    for number, net, x_mil, y_mil, orient in pins:
        x = x_mil * 0.0254
        y = y_mil * 0.0254
        angle = 0 if orient == "R" else 180
        lines.append(
            f"    (pin passive line (at {x:.3f} {y:.3f} {angle}) (length 5.08) "
            f"(name {q(net)} {effects(1.0)}) (number {q(number)} {effects(1.0)}))"
        )
    lines.extend(["  )", "  (embedded_fonts no)", ")"])
    return "\n".join(lines)


def native_symbol_instance(part: Part, index: int, root_uuid: str) -> tuple[str, list[str], list[str]]:
    columns = 6
    x = 38.10 + (index % columns) * 88.90
    y = 35.56 + (index // columns) * 48.26
    symbol_uuid = uid(f"symbol-instance:{part.ref}")
    lines = [
        "(symbol",
        f"  (lib_id {q('FPGA_Amp:' + sym_name(part))})",
        f"  (at {x:.2f} {y:.2f} 0) (unit 1)",
        "  (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)",
        f"  (uuid {q(symbol_uuid)})",
        f"  (property \"Reference\" {q(part.ref)} (at {x:.2f} {y - 12.7:.2f} 0) {effects()})",
        f"  (property \"Value\" {q(part.value)} (at {x:.2f} {y + 15.24:.2f} 0) {effects(1.0)})",
        f"  (property \"Footprint\" {q(part.footprint)} (at {x:.2f} {y:.2f} 0) {effects(hide=True)})",
        f"  (property \"Datasheet\" \"~\" (at {x:.2f} {y:.2f} 0) {effects(hide=True)})",
        f"  (property \"Description\" {q(part.description)} (at {x:.2f} {y:.2f} 0) {effects(hide=True)})",
    ]
    labels = []
    wires = []
    for number, net, x_mil, y_mil, _orient in symbol_pin_layout(part):
        lines.append(f"  (pin {q(number)} (uuid {q(uid(f'pin:{part.ref}:{number}'))}))")
        pin_x = x + x_mil * 0.0254
        ly = y - y_mil * 0.0254
        direction = -1.0 if x_mil < 0 else 1.0
        lx = pin_x + direction * 2.54
        wires.append(
            f"(wire (pts (xy {pin_x:.3f} {ly:.3f}) (xy {lx:.3f} {ly:.3f})) "
            f"(stroke (width 0) (type default)) (uuid {q(uid(f'wire:{part.ref}:{number}'))}))"
        )
        labels.append(
            f"(label {q(net)} (at {lx:.3f} {ly:.3f} 0) "
            f"{effects(0.8, justify='left bottom')} (uuid {q(uid(f'label:{part.ref}:{number}'))}))"
        )
    lines.extend([
        "  (instances",
        "    (project \"\"",
        f"      (path {q('/' + root_uuid + '/' + symbol_uuid)} (reference {q(part.ref)}) (unit 1))",
        "    )",
        "  )",
        ")",
    ])
    return "\n".join(lines), labels, wires


def write_native_schematic() -> Path:
    path = ROOT / f"{NAME}.kicad_sch"
    root_uuid = uid("schematic-root")
    lines = [
        "(kicad_sch",
        "  (version 20250114)",
        "  (generator \"fpga_amp_generate\")",
        "  (generator_version \"1.0\")",
        f"  (uuid {q(root_uuid)})",
        "  (paper \"A2\")",
        "  (title_block (title \"FPGA Amp motor-volume evaluation board\") (date \"2026-08-15\") (rev \"A / EVT\") (company \"FPGA_Amp\")",
        "    (comment 1 \"Position transducer only - no audio path\")",
        "    (comment 2 \"Nominal hardware current regulation 297 mA; verify on mechanism\")",
        "    (comment 3 \"NOT PRODUCTION RELEASED\")",
        "    (comment 4 \"Generated from generate.py\"))",
        "  (lib_symbols",
    ]
    lines.extend("    " + line.replace("\n", "\n    ") for line in (native_symbol_definition(part) for part in PARTS))
    lines.append("  )")
    library = [
        "(kicad_symbol_lib",
        "  (version 20241209)",
        "  (generator \"kicad_symbol_editor\")",
        "  (generator_version \"9.0\")",
    ]
    for part in PARTS:
        definition = native_symbol_definition(part).replace(q("FPGA_Amp:" + sym_name(part)), q(sym_name(part)), 1)
        library.append("  " + definition.replace("\n", "\n  "))
    library.extend([")", ""])
    (ROOT / f"{NAME}.kicad_sym").write_text("\n".join(library), encoding="utf-8")
    (ROOT / "sym-lib-table").write_text(
        '(sym_lib_table\n  (version 7)\n  (lib (name "FPGA_Amp")(type "KiCad")'
        f'(uri "${{KIPRJMOD}}/{NAME}.kicad_sym")(options "")(descr "FPGA Amp generated motor board symbols"))\n)\n',
        encoding="utf-8",
    )

    instances = []
    labels = []
    wires = []
    for index, part in enumerate(PARTS):
        instance, part_labels, part_wires = native_symbol_instance(part, index, root_uuid)
        instances.append(instance)
        labels.extend(part_labels)
        wires.extend(part_wires)
    lines.extend("  " + wire.replace("\n", "\n  ") for wire in wires)
    lines.extend("  " + label.replace("\n", "\n  ") for label in labels)
    lines.extend("  " + instance.replace("\n", "\n  ") for instance in instances)
    lines.extend([
        "  (sheet_instances (path \"/\" (page \"1\")))",
        "  (embedded_fonts no)",
        ")",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def library_path(footprint: str) -> tuple[str, str]:
    library, name = footprint.split(":", 1)
    return f"/usr/share/kicad/footprints/{library}.pretty", name


def add_outline(board: pcbnew.BOARD) -> None:
    corners = [(2.0, 2.0), (82.0, 2.0), (82.0, 50.0), (2.0, 50.0), (2.0, 2.0)]
    for start, end in zip(corners, corners[1:]):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetWidth(MM(0.1))
        edge.SetStart(pcbnew.VECTOR2I(MM(start[0]), MM(start[1])))
        edge.SetEnd(pcbnew.VECTOR2I(MM(end[0]), MM(end[1])))
        board.Add(edge)


def add_text(board: pcbnew.BOARD, text: str, xy: tuple[float, float], layer: int, size: float = 1.0) -> None:
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetPosition(pcbnew.VECTOR2I(MM(xy[0]), MM(xy[1])))
    item.SetLayer(layer)
    item.SetTextHeight(MM(size))
    item.SetTextWidth(MM(size))
    item.SetTextThickness(MM(0.15))
    board.Add(item)


def add_zone(board: pcbnew.BOARD, net: pcbnew.NETINFO_ITEM, layer: int) -> None:
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    zone.SetNet(net)
    zone.SetLocalClearance(MM(0.25))
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in [(2.5, 2.5), (81.5, 2.5), (81.5, 49.5), (2.5, 49.5)]:
        outline.Append(MM(x), MM(y))
    board.Add(zone)


def write_board() -> Path:
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    board.SetLayerName(pcbnew.In1_Cu, "GND")
    board.SetLayerName(pcbnew.In2_Cu, "POWER")
    default = board.GetAllNetClasses()["Default"]
    default.SetClearance(MM(0.20))
    default.SetTrackWidth(MM(0.25))
    default.SetViaDiameter(MM(0.70))
    default.SetViaDrill(MM(0.35))
    board.GetDesignSettings().m_TrackMinWidth = MM(0.15)
    board.GetDesignSettings().m_MinClearance = MM(0.15)
    board.GetDesignSettings().m_MinThroughDrill = MM(0.20)

    net_names = sorted({net for part in PARTS for net in part.nets.values()})
    nets: dict[str, pcbnew.NETINFO_ITEM] = {}
    for name in net_names:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        nets[name] = net

    for part in PARTS:
        directory, footprint_name = library_path(part.footprint)
        footprint = pcbnew.FootprintLoad(directory, footprint_name)
        if footprint is None:
            raise RuntimeError(f"cannot load {part.footprint}")
        footprint.SetReference(part.ref)
        footprint.SetValue(part.value)
        if part.value.startswith("DNP_"):
            footprint.SetDNP(True)
        footprint.Reference().SetLayer(pcbnew.F_Fab)
        footprint.Value().SetLayer(pcbnew.F_Fab)
        footprint.SetPosition(pcbnew.VECTOR2I(MM(part.xy[0]), MM(part.xy[1])))
        footprint.SetOrientationDegrees(part.rotation)
        for pad_number, net_name in part.nets.items():
            matching = [pad for pad in footprint.Pads() if pad.GetNumber() == pad_number]
            if not matching:
                raise RuntimeError(f"{part.ref}: footprint lacks pad {pad_number}")
            for pad in matching:
                pad.SetNet(nets[net_name])
        board.Add(footprint)

    for ref, xy in [("H1", (5.5, 18.0)), ("H2", (78.5, 18.0)), ("H3", (5.5, 46.5)), ("H4", (78.5, 46.5))]:
        footprint = pcbnew.FootprintLoad("/usr/share/kicad/footprints/MountingHole.pretty", "MountingHole_3.2mm_M3")
        footprint.SetReference(ref)
        footprint.SetValue("M3_CHASSIS")
        footprint.Reference().SetLayer(pcbnew.F_Fab)
        footprint.Value().SetLayer(pcbnew.F_Fab)
        footprint.SetPosition(pcbnew.VECTOR2I(MM(xy[0]), MM(xy[1])))
        board.Add(footprint)

    add_outline(board)
    add_text(board, "FPGA AMP - MOTOR VOLUME EVT REV A", (43.0, 4.0), pcbnew.F_SilkS, 1.0)
    add_text(board, "J1 5V IN", (10.5, 14.0), pcbnew.F_SilkS, 0.8)
    add_text(board, "J2 MCU", (10.0, 43.0), pcbnew.F_SilkS, 0.8)
    add_text(board, "J3 MOTOR PAIR", (62.0, 15.0), pcbnew.F_SilkS, 0.8)
    add_text(board, "J4 POSITION", (74.5, 35.0), pcbnew.F_SilkS, 0.8)
    add_text(board, "NO AUDIO", (72.0, 42.0), pcbnew.F_SilkS, 0.8)
    for label, x in zip(["VM", "GND", "OUT1", "OUT2", "VREF", "IPR", "POTA", "POTB"], range(25, 73, 6)):
        add_text(board, label, (float(x), 49.0), pcbnew.F_SilkS, 0.8)
    add_zone(board, nets["GND"], pcbnew.In1_Cu)
    add_zone(board, nets["GND"], pcbnew.B_Cu)

    path = ROOT / f"{NAME}.kicad_pcb"
    pcbnew.SaveBoard(str(path), board)
    return path


def write_project_and_bom() -> None:
    project = {
        "board": {}, "boards": [], "cvpcb": {}, "erc": {}, "libraries": {},
        "meta": {"filename": f"{NAME}.kicad_pro", "version": 1},
        "net_settings": {"classes": [{"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.7, "via_drill": 0.35}], "meta": {"version": 3}},
        "pcbnew": {}, "schematic": {}, "sheets": [], "text_variables": {},
    }
    (ROOT / f"{NAME}.kicad_pro").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")
    rows = ["Reference,Value,Footprint,Description"]
    for part in PARTS:
        rows.append(",".join([part.ref, part.value, part.footprint, part.description.replace(",", ";")]))
    (ROOT / "bom.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> None:
    if shutil.which("kicad-cli") is None:
        raise SystemExit("kicad-cli is required")
    for stale in [ROOT / f"{NAME}-cache.lib", ROOT / f"{NAME}.sch"]:
        if stale.exists():
            stale.unlink()
    current = write_native_schematic()
    write_board()
    write_project_and_bom()
    print(f"generated {current.relative_to(ROOT.parent.parent.parent.parent)}")
    print(f"generated {(ROOT / f'{NAME}.kicad_pcb').relative_to(ROOT.parent.parent.parent.parent)}")
    print(f"parts={len(PARTS)} nets={len({n for p in PARTS for n in p.nets.values()})}")


if __name__ == "__main__":
    main()
