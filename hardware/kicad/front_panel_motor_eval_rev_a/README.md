# Motor-volume evaluation PCB — revision A

This is the first physical KiCad design derived from the product hardware
specification. It isolates the electrically noisy and mechanically uncertain
motor-volume subsystem so it can be measured before committing it to the large
LCD/MCU front-panel board.

Open `front_panel_motor_eval.kicad_pro` in KiCad 10. The checked board was
generated and verified with KiCad 10.0.5. KiCad does not live-reload files
changed by the generator, so close and reopen the schematic/PCB editor after an
external regeneration. Do not hand-edit generated connectivity without also
updating `generate.py`.

## Verified artifact

The checked-in board is an 80 x 48 mm, four-copper-layer EVT daughterboard with
44 schematic parts, four M3 mounting holes, 28 named nets, 235 routed segments,
and 28 vias. The last clean run reports:

```text
schematic ERC violations:  0
PCB DRC violations:        0
unconnected PCB items:     0
minimum routed width:      0.25 mm
minimum via drill:         0.35 mm
```

The bottom and inner-1 layers are GND pours. Inner-2 is reserved as `POWER` but
is not used as an indiscriminate plane in this small prototype. Connector and
test-point functions are labeled on silkscreen. R19/C10 carry KiCad DNP flags,
and placement export excludes them.

## Electrical intent

- 4.75–5.25 V motor input for the Bourns PRM16 4.5 V / 100 mA prototype motor.
- DRV8874 in PH/EN control mode with 33 ohm input damping and 100 kilohm
  fail-off pulldowns.
- 10 kilohm IPROPI resistor: nominal 0.45 V at 100 mA using the datasheet's
  nominal 450 microamp/amp scaling. This is stall telemetry, not precision
  metrology; the datasheet permits substantial absolute error below 0.4 A.
- 14.7/10 kilohm VREF divider and 10 kilohm IPROPI resistor: nominal hardware
  current regulation near 297 mA. This threshold and the 500 mA PTC are not
  released values until motor start/stall measurements are complete.
- IMODE uses 62 kilohms to select cycle-by-cycle regulation and latched-off
  overcurrent behavior. Firmware still detects ordinary stalls from IPROPI and
  stops without waiting for device OCP.
- Dual 10 kilohm-class potentiometer tracks are excited ratiometrically from
  MCU 3.3 V. Their filtered wipers carry position only and never audio.
- R19/C10 are deliberately DNP EMI-tuning sites. They may only be populated
  from measured motor emissions and driver-current evidence.

## Connectors

`J1` is keyed motor power. `J2` is the prototype MCU interface. `J3` is a
separate twisted motor pair. `J4` carries the two position tracks. Separating
J3 from J4 prevents PWM current from sharing position-sensor conductors.

This is an EVT instrument, not a production-released board. The PRM16 has a
published 15,000-cycle rotational life, while the product requirement remains
100,000 qualified full-range cycles.

The DRV8874 PowerPAD is assigned to GND using the standard non-via-in-pad KiCad
HTSSOP footprint. That is suitable for low-current motor evaluation only after
assembly inspection; a production layout must close copper area, thermal vias,
paste aperture, and fabricator capability from measured dissipation. The
0.25 mm routes are ample for the candidate's published 100 mA maximum motor
current but are not evidence for an unselected larger mechanism. Connector
families, PTC trip/hold rating, TVS selection, current threshold, and optional
snubber remain provisional until bench measurements.

Primary component references are the
[TI DRV8874 datasheet](https://www.ti.com/lit/ds/symlink/drv8874.pdf) and the
[Bourns PRM16 datasheet](https://www.bourns.com/docs/product-datasheets/PRM16.pdf).
The route was produced with
[Freerouting](https://github.com/freerouting/freerouting) v2.2.4 through
KiCad's DSN/SES interchange. Freerouting is intentionally not vendored.

## Commands

```text
make kicad-motor-generate
make kicad-motor-route FREEROUTING_JAR=/path/to/freerouting.jar
make kicad-motor-check
make kicad-motor-fab
```

`kicad-motor-route` starts from generated placement and can occasionally leave
an unrouted item because the open autorouter is heuristic. The mandatory check
target fails in that case; rerun the route rather than accepting an incomplete
board. Fabrication outputs are generated under
`build/kicad/front_panel_motor_eval/fab/` and are intentionally not committed.
Passing export is not an instruction to order boards: peer layout review,
mechanical fit, sourcing, assembly rules, and the provisional items above are
still open.
