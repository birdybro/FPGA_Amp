# Moving-magnet analog front end

The real cartridge never connects directly to FPGA pins. The Rev-A EVT board
implements a flat, low-current-noise, differential converter driver that
presents the same load modeled in the reference wrapper. It is routed and
electrically checked in KiCad but remains unbuilt.

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
| A | flat 26.064 dB (Rev-A OPA1656/PCM4202 population) | -28.42 dBFS | -14.44 dBFS | 0.709 µV RMS |
| B | 20 dB at 1 kHz plus analog 3180/318 µs shelf; 75 µs pole digital | -34.49 dBFS | -2.10 dBFS | 0.716 µV RMS |
| C | conventional 40 dB/1 kHz full analog RIAA | -14.49 dBFS | +18.77 dBFS | 0.701 µV RMS |

Architecture A is selected for requirements development. In this calculation B
does not materially improve noise and sacrifices broadband/transient headroom.
C gives the ADC the least noise burden but clips the specified stress cases and
prevents the FPGA from reproducing arbitrary historical interstage/RIAA loading.
An eventual partial-condition design may still win after real ADC/front-end
measurements, but it requires a new measured report; this table is not a dogma.

The updated calculation uses the fitted PCM4202's 2.12 V RMS differential full
scale and 116 dB typical unweighted dynamic range, rather than the earlier
generic 2 V/119 dB study point. OPA1656 is the fitted-board noise baseline. Its
4.3 nV/√Hz 1 kHz and 6 fA/√Hz typical figures are treated as white across the
band, so the result explicitly excludes 1/f behavior and is not a measurement.

## Rev-A EVT realization

The routed board is in
`hardware/kicad/phono_adc_eval_rev_a/`. Each channel uses a 100 ohm input
limiter, 47.5 kilohm 0.1% termination, relay-switched 47/100 pF C0G loading, one
half of an OPA1656 non-inverting stage, and an OPA1632 fully differential ADC
driver. The default 19.1 kilohm / 1.00 kilohm gain network is 26.064 dB; relay
states select 20.008 or 32.002 dB. The PCM4202 is strapped for 48 kHz master
I2S with its internal high-pass filter disabled. Local low-noise post-regulators
derive +/-12 V, +5 V, and +3.3 V from separately supplied rails.

KiCad 10.0.5 reports zero schematic ERC violations, zero PCB DRC violations,
and zero unrouted connections on the 130 x 90 mm four-layer route. These are
connectivity/layout checks—not noise, RF, ESD, stability, or audio measurements.

## Input/load requirements

- 47.5 kΩ reference termination with at least 0.1% initial tolerance. Offer a
  separately labeled 47.0 kΩ compatibility mode if desired.
- The sum of tonearm cable, connector, ESD device, amplifier input, PCB, and
  selectable capacitor is 100–200 pF for the nominal AT-VM95E. Provide measured
  settings, not capacitor-label arithmetic. Reasonable switched increments are
  0/47/100 pF C0G after parasitic characterization.
- Input capacitance must stay low and predictable when unpowered. Protection
  cannot rely on ordinary high-capacitance TVS parts across the cartridge.
- Nominal gain 26.064 dB, with 20.008/32.002 dB optional and hardware-muted
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
