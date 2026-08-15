# Shielded MM phono / PCM4202 ADC Rev-A EVT board

This directory contains a routed four-layer KiCad 10 evaluation board for the
flat-gain Architecture A input path. It is a concrete bench prototype, not a
production fabrication release and not evidence of measured performance.

```text
isolated panel RCA harness -> 100 ohm RF limiter -> 47.5 kilohm load
  -> selectable 0/47/100/147 pF C0G load -> OPA1656 flat gain
  -> OPA1632 fully differential driver/filter -> PCM4202 stereo ADC
  -> 24-bit I2S to the FPGA board
```

The board is 130 x 90 mm with F.Cu / continuous L2 GND / L3 POWER_SIG /
B.Cu. Cartridge entry, relay loading, flat gain, differential drivers, ADC,
local post-regulation, and digital headers are physically partitioned. The RCA
and turntable-ground connectors are EVT harness/terminal choices; production
parts remain enclosure decisions.

## Fixed electrical contract

- ADC: PCM4202DBR, 48 kHz single-rate master, 24-bit I2S.
- SCKI: 24.576 MHz from the digital board (`512 fS`).
- ADC outputs: 6.144 MHz BCK (`128 fS`), 48 kHz LRCK, serial data, and L/R
  clip indicators. The current 64-fS FPGA interface must be extended and
  verified before this board is treated as digitally compatible.
- PCM4202 straps: `S/M=0`, `FMT1:FMT0=01`, `FS2:FS0=001`, `HPFD=1`.
  `HPFD=1` disables the converter high-pass filter so reference mode retains
  the external circuit's low-frequency behavior.
- Analog rails: TPS7A39 local +12.0/-11.9 V from external +/-15.5 V;
  TPS7A2050 +5 V from +5.7 V; TPS7A2033 +3.3 V from +3.7 V. Relay +5 V is
  supplied separately.
- Input termination: 47.5 kilohm, 0.1%, per channel. Installed capacitance is
  switchable in 47 pF and 100 pF increments. Cable, connector, ESD, relay,
  amplifier, and PCB parasitics are additional and must be measured.
- ADC reset and all relay controls fail low. The signal path must be hardware
  muted before changing gain or capacitance.

The gain relay truth table is:

| `GAIN_BANK_CTL` | `GAIN_RANGE_CTL` | Selected gain | Meaning |
|---:|---:|---:|---|
| 0 | X | 26.064 dB | unpowered/reset default |
| 1 | 0 | 20.008 dB | high-headroom range |
| 1 | 1 | 32.002 dB | low-level range; 100 mV stress clips |

The capacitance relays act independently:

| `CAP_47PF_CTL` | `CAP_100PF_CTL` | Installed C0G increment |
|---:|---:|---:|
| 0 | 0 | 0 pF |
| 1 | 0 | 47 pF |
| 0 | 1 | 100 pF |
| 1 | 1 | 147 pF |

`design.py` is the auditable source for exact gain, headroom, clock, strap, and
rail calculations. Its committed result is `design_calculations.json`.

## Reproduction and verification

From the repository root:

```sh
make kicad-phono-adc-check
make kicad-phono-adc-render
```

To regenerate and autoroute from source, set `FREEROUTING_JAR` to Freerouting
2.2.4 or a verified compatible release and run:

```sh
make kicad-phono-adc-route FREEROUTING_JAR=/path/to/freerouting.jar
make kicad-phono-adc-check
```

The committed routed board passes KiCad ERC and DRC with zero violations and
zero unconnected items. `verify.py` additionally locks the critical IC and
relay pad maps, component population, ADC straps/clocks, layer structure,
outline, minimum routing geometry, and generated calculation consistency.

## Release gates

Do not order this as a production board until all of the following are closed:

- enclosure-qualified isolated RCA jacks and turntable ground-post mechanics;
- measured total input capacitance in every relay state;
- input-referred noise, hum, gain, overload recovery, channel separation, RF
  injection, and ESD tests on populated hardware;
- stackup/return-current and safety review with the intended enclosure/power
  board;
- 128-fS PCM4202 receive timing verified in RTL and at the pins; and
- muted relay switching and all power-up/down fault cases verified.

## Primary component sources

- [TI PCM4202 data sheet](https://www.ti.com/lit/ds/symlink/pcm4202.pdf)
- [TI OPA1656 data sheet](https://www.ti.com/lit/ds/symlink/opa1656.pdf)
- [TI OPA1632 data sheet](https://www.ti.com/lit/ds/symlink/opa1632.pdf)
- [TI TPS7A39 data sheet](https://www.ti.com/lit/ds/symlink/tps7a39.pdf)
- [TI TPS7A20 data sheet](https://www.ti.com/lit/ds/symlink/tps7a20.pdf)
