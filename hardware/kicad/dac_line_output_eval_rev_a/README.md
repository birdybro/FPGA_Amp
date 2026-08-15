# PCM5242 DAC / protected line-output Rev-A EVT board

This directory contains a routed four-layer KiCad 10 evaluation board for the
stereo FPGA-to-line-output path. It is a concrete bench prototype, not a
production fabrication release and not evidence of measured audio performance.
Open `dac_line_output_eval.kicad_pro` in KiCad 10. KiCad does not live-reload
files changed by the generator, so close/reopen the board after regeneration.

```text
FPGA 24-bit I2S + 24.576 MHz SCK
  -> PCM5242 in external-clock slave / I2C mode
  +-> 499 ohm/leg + 1 nF differential reconstruction -> fail-open relays -> balanced harness
  +-> 499 ohm + 2.2 nF shunt reconstruction -> fail-open relay -> isolated-RCA harness
```

The board is 112 x 72 mm with F.Cu / continuous L2 GND / L3 POWER_SIG /
B.Cu. Digital/control entry, DAC and charge pump, reconstruction networks,
relays, and panel harnesses are physically partitioned. The harness connectors
are EVT choices; production XLR/RCA mechanics belong to the enclosure design.

## Fixed electrical contract

- DAC: PCM5242RHBR, 48 kHz slave, 24-bit I2S in 32-BCK channel slots.
- Clocks: 24.576 MHz external SCK (`512 fS`), 3.072 MHz BCK (`64 fS`), and
  48 kHz LRCK. External SCK is used instead of making the DAC PLL the reference.
- Control: I2C mode with `MODE1=0`, `MODE2=1`, `ADR1=0`, and `ADR2=0`.
  Reference firmware must hold XSMT low while configuring and reading back a
  unity path; optional miniDSP/creative processing is disabled in reference
  mode.
- Supplies: separate external 3.7 V analog and digital feeds post-regulated by
  two TPS7A2033 devices, plus a separate 5 V relay feed. The power board owns
  sequencing and the single reviewed chassis/signal-ground bond.
- Balanced output: the official EVM-style 499 ohm per-leg and 1 nF
  differential network. Into 20 kilohm differential, calculated full scale is
  4.00038 V RMS at DC and 3.97214 V RMS at 20 kHz.
- RCA output: the data-sheet-style 499 ohm / 2.2 nF single-ended network. Into
  10 kilohm, calculated full scale is 2.00019 V RMS at DC and 1.98314 V RMS at
  20 kHz.
- Output switching: three Omron G6K-2F-Y 5 V relays use only normally-open
  contacts, so loss of power opens every signal output.

Two SN74LVC1G08 gates provide independent fail-low interlocks:

```text
LINE_RELAY_EN_SAFE = LINE_RELAY_EN_CTL AND HARD_MUTE_N
DAC_XSMT_SAFE      = DAC_SOFT_UNMUTE_CTL AND HARD_MUTE_N
```

Each input is pulled low. The external supervisor can therefore force both
PCM5242 soft mute and physical relay mute even if the controller is stuck high,
reset, absent, or unpowered. The intended unmute order is configure/read back
the DAC while XSMT is low, energize output relays, then raise XSMT. Mute reverses
that order after allowing the DAC ramp to finish.

`design.py` is the auditable source for exact clock, loading, output-level, and
reconstruction-response calculations. Its committed result is
`design_calculations.json`.

## Reproduction and verification

From the repository root:

```sh
make kicad-dac-line-check
make kicad-dac-line-render
```

To regenerate and route from source, set `FREEROUTING_JAR` to Freerouting 2.2.4
or a verified compatible release:

```sh
make kicad-dac-line-route FREEROUTING_JAR=/path/to/freerouting.jar
make kicad-dac-line-check
```

The route script rotates the PCM5242 so its clock pins face the digital side and
its four analog outputs face the reconstruction networks. Freerouting completes
the dense routing; a deterministic reviewed back-edge trace finishes J2.4 I2C
SDA without passing through the header's other even-numbered pads.

The committed board passes KiCad ERC and DRC with zero violations and zero
unconnected items. `verify.py` also locks the PCM5242 and interlock pad maps,
mode straps, normally-open relay contacts, filter values, DNP chassis options,
calculation consistency, board stack/outline, and minimum routing geometry.

## Release gates

Do not order this as a production board until all of the following are closed:

- PCM5242 register write/readback and every mute transition are verified with
  the external supervisor able to dominate a stuck controller;
- loaded THD+N, dynamic range, frequency response, channel balance, crosstalk,
  output impedance, DC, and clipping are measured on populated hardware;
- power-up, shutdown, brownout, missing-clock, hot-plug, and harness-unplug
  behavior are measured without an audible or damaging transient;
- enclosure-qualified XLR/RCA connectors, pin-1/chassis treatment, isolated
  RCA mounting, and keyed harnesses are selected;
- the provisional PESD5V0X1BCL output clamps pass leakage/capacitance/audio and
  IEC ESD/EFT/RF-immunity qualification; and
- a fabricator stackup, DFM, return-current, thermal, assembly, and sourcing
  review is complete.

## Primary component sources

- [TI PCM5242 data sheet](https://www.ti.com/lit/ds/symlink/pcm5242.pdf)
- [TI PCM5242EVM user guide](https://www.ti.com/lit/ug/slau592a/slau592a.pdf)
- [TI TPS7A20 data sheet](https://www.ti.com/lit/ds/symlink/tps7a20.pdf)
- [TI SN74LVC1G08 data sheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf)
- [Omron G6K relay family](https://components.omron.com/sg-en/products/relays/G6K)
