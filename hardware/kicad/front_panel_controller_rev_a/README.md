# Front-panel controller PCB — revision A EVT

This directory contains the generated, routed KiCad controller board for the
5-inch touchscreen, user controls, and motor-volume daughterboard. Open
`front_panel_controller.kicad_pro` in KiCad 10. KiCad does not live-reload
files changed externally, so close and reopen the schematic/PCB editor after a
generator or routing run.

## Checked artifact

The checked-in board is 150 x 90 mm with six copper layers:

```text
L1  F.Cu    components and signals
L2  GND1    continuous ground reference
L3  PWR     power and routing
L4  SIG2    signals
L5  GND2    continuous ground reference
L6  B.Cu    signals and ground pour
```

KiCad 10.0.5 reports zero schematic ERC violations, zero PCB DRC
violations, and zero unconnected items after zone fill. The open route has
1,895 track segments and 314 vias at minimum 0.20 mm track / 0.30 mm drill.
The source-aware verifier checks the package pin map, connector electrical map,
layer stack, board size, source damping, regulator choice, and routed
geometries.

This is an EVT routing baseline, **not a fabrication release**. In particular,
the checked board deliberately carries `NOT FAB RELEASED` silkscreen and the
following gates remain open:

- replace and sign off the provisional 40-pin/6-pin FFC land patterns against
  the exact Molex 54104-4031 and 52271-0679 drawings;
- define the fabricator's six-layer stackup, then review impedance, return
  paths, SDRAM flight time/skew, and LTDC edge integrity;
- perform a specialist layout review of the TPS62132 buck and TPS61165 boost,
  including switch-node copper, hot loops, thermal paths, and emissions;
- freeze enclosure, display, harness, encoder, and mounting geometry; and
- close sourcing, assembly, bring-up, ESD, thermal, EMC, and lifetime tests.

No fabrication-output target is provided while those stop conditions are
open.

## Implemented electrical architecture

- STM32H753ZIT6 in LQFP-144 with all supply pins, 11 local 100 nF bypass
  sites, connected VCAP pins with two 2.2 uF low-ESR capacitors, filtered
  VDDA/VREF+, HSE/LSE footprints, reset, BOOT0, and 10-pin SWD.
- An independently checked 106-I/O allocation covering RGB565 LTDC, touch,
  x16 FMC SDRAM, Quad-SPI, FPGA control SPI, three quadrature encoders,
  mute/standby, ambient sensing, and the motor-volume interface.
- IS42S16160J 32 MiB x16 SDR SDRAM and W25Q256JV 32 MiB Quad-SPI flash.
- Twenty 33 ohm LTDC source-damping resistors plus clock damping for SDRAM and
  Quad-SPI. Values are provisional until stackup-specific measurement/SI.
- Exact NHD-5.0-800480AF-ASXP-CTP electrical pin assignment. Unused RGB LSBs
  are grounded for RGB565; DE, HSYNC, VSYNC, standby, and the capacitive-touch
  reset/interrupt signals are retained.
- TPS61165 backlight boost from 12 V with a 3.32 ohm feedback resistor for
  approximately 60.2 mA nominal LED current and 32 kHz PWM target. The display
  data sheet's typical LED string voltage is about 21.1 V.
- TPS62132 fixed 3.3 V / 3 A buck. TPS62133 is intentionally rejected here
  because it is the fixed 5 V member, not the 3.3 V part.
- Separate harnesses for panel-mounted encoders/buttons, digital-board control,
  and the motor-volume board. The motor position tracks remain control inputs
  only and never carry audio.
- `FORCE_MUTE_N` defaults asserted through hardware. A healthy MCU must
  intentionally establish control; the GUI is not allowed to become the sole
  safety path.

The high-quality source/model/parameter knobs are panel-mounted optical
encoder candidates rather than PCB-mounted consumer encoders. This keeps shaft
loads in the metal panel and lets enclosure mechanics determine the exact
Grayhill 62H or Bourns EM14 variant. The motorized volume mechanism remains on
the separate, already-routed motor board so its PWM currents do not share the
display/MCU board.

Direct Ethernet is not available in this LQFP-144 Rev-A allocation: the RMII
pin set conflicts with the chosen LTDC/FMC functions. Adding Ethernet requires
an external SPI bridge/module or a package/architecture revision. The eARC
receiver is also intentionally absent; it belongs on the separately licensed
digital/eARC mainboard next to the HDMI connector and ASRC.

## Reproduction

```text
make kicad-controller-generate
make kicad-controller-route FREEROUTING_JAR=/path/to/freerouting.jar
make kicad-controller-check
make kicad-controller-render
```

`generate.py` recreates the native schematic, source placement, custom symbol
library, project, and BOM from one part/net model. It erases routing by design.
`route_open.py` exchanges DSN/SES with Freerouting and refills zones on import.
It also applies one reviewed 1.6 mm U2 ground dogleg when v2.2.4 stops one
connection short; the mandatory DRC remains the acceptance gate. The checked
route used Freerouting v2.2.4. `verify_pin_assignment.py` rejects
duplicate package pins or package-position drift before board generation.

## Primary references

- [Newhaven NHD-5.0-800480AF-ASXP-CTP data sheet](https://newhavendisplay.com/content/specs/NHD-5.0-800480AF-ASXP-CTP.pdf)
- [ST STM32H753ZI data sheet](https://www.st.com/resource/en/datasheet/stm32h753zi.pdf)
- [ST AN4938 hardware-development guidance](https://www.st.com/resource/en/application_note/an4938-getting-started-with-stm32h74xig-and-stm32h75xig-mcu-hardware-development-stmicroelectronics.pdf)
- [ST official open pin data](https://github.com/STMicroelectronics/STM32_open_pin_data), pinned extract provenance commit `7d1f1514ed5583ec5007ad91236b4e1d377295b1`
- [ISSI IS42S16160J data sheet](https://www.issi.com/WW/pdf/42-45S83200J-16160J.pdf)
- [TI TPS61165 data sheet](https://www.ti.com/lit/ds/symlink/tps61165.pdf)
- [TI TPS62132/TPS6213x data sheet](https://www.ti.com/lit/gpn/TPS62133)
- [Freerouting open autorouter](https://github.com/freerouting/freerouting)
