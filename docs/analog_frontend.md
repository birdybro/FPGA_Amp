# Moving-magnet analog front end

The real cartridge never connects directly to FPGA pins. The initial electrical
requirement is a flat, low-current-noise, differential converter driver that
presents the same load modeled in the reference wrapper.

```text
RCA -> controlled 47.5 kΩ and selectable C -> low-capacitance RF/ESD network
    -> JFET-input gain (20/26/32 dB study points) -> differential driver
    -> passive anti-alias filter -> audio ADC
```

## Quantitative RIAA partition study

The script compares three exact study cases with a 2 V RMS, 119 dB ADC. Noise is
referred through the remaining normalized digital playback response. The test
uses equal-amplitude tones at each frequency for worst-case analog headroom; an
actual record spectrum is not flat.

| Architecture | Analog action | Nominal 4 mV at 1 kHz | 20 mV at analog-response peak | Combined RIAA-weighted input noise |
|---|---|---:|---:|---:|
| A | flat 26 dB | -28.0 dBFS | -14.0 dBFS | 0.656 µV RMS |
| B | 20 dB at 1 kHz plus analog 3180/318 µs shelf; 75 µs pole digital | -34.0 dBFS | -1.60 dBFS | 0.659 µV RMS |
| C | conventional 40 dB/1 kHz full analog RIAA | -14.0 dBFS | +19.27 dBFS | 0.652 µV RMS |

Architecture A is selected for requirements development. In this calculation B
does not materially improve noise and sacrifices broadband/transient headroom.
C gives the ADC the least noise burden but clips the specified stress cases and
prevents the FPGA from reproducing arbitrary historical interstage/RIAA loading.
An eventual partial-condition design may still win after real ADC/front-end
measurements, but it requires a new measured report; this table is not a dogma.

## Input/load requirements

- 47.5 kΩ reference termination with at least 0.1% initial tolerance. Offer a
  separately labeled 47.0 kΩ compatibility mode if desired.
- The sum of tonearm cable, connector, ESD device, amplifier input, PCB, and
  selectable capacitor is 100–200 pF for the nominal AT-VM95E. Provide measured
  settings, not capacitor-label arithmetic. Reasonable switched increments are
  0/47/100 pF C0G after parasitic characterization.
- Input capacitance must stay low and predictable when unpowered. Protection
  cannot rely on ordinary high-capacitance TVS parts across the cartridge.
- Nominal gain 26 dB, with 20/32 dB optional and break-before-make or muted
  switching. Input-to-ADC polarity and exact gain calibration are stored per
  channel.
- Pass 5 Hz–40 kHz without a hidden subsonic response in reference mode. A
  modern warp filter belongs after capture with an explicit enable.

## Protection and RF concept

Use a small symmetric series resistance, RF common-mode control at the chassis
entry, low-capacitance clamps to quiet analog rails after current limiting, and
a differential/common-mode RC network whose capacitance is included in the load
budget. Component values await RF injection and ESD testing. Protection should
survive cable handling and preamp-off insertion without normal audio conduction.
An analog clamp must prevent ADC overvoltage even if the FPGA is unconfigured.

## Grounding and layout

- Bond protective earth/chassis according to the power architecture. RCA shield
  and turntable ground terminal meet chassis at the entry region; signal-return
  bonding is a controlled single network, not accidental mounting-hardware paths.
- Keep the unbalanced high-impedance trace short and shielded. Convert to a
  balanced internal signal before the ADC driver and route it differentially.
- Separate converter/reference return currents from the cartridge entry. Do not
  split a ground plane under a high-speed differential pair; control current
  paths with placement and partitioning.
- Provide a physical turntable ground post. Measure 50/60 Hz and harmonic hum
  with representative turntables, cable shields, USB connected/disconnected,
  and the eventual power amplifier attached.

## Acceptance before PCB freeze

Measure input impedance/capacitance, gain tolerance, 20 Hz–20 kHz flatness,
input-referred noise density and integrated noise, 10 Hz/1 kHz/20 kHz overload,
100 mV transient recovery, common-mode/RF immunity, ESD behavior, DC offset,
channel crosstalk, and power-state pops. Record raw analyzer data and calibration;
the analytical budget alone is not validation.
