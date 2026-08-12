# V1 phono reference

## Frozen historical circuit

V1 is the mono “Single Tube Phono Stage” drawn by Kevin Kennedy on 1998-02-17.
Both halves of one 12AX7 form two unbypassed common-cathode stages around a
passive RIAA network. The source schematic is linked in `references.md`; the
machine-readable values are `model/configurations/v1.yaml`.

```text
source--47.5k to ground--221R--g V1a
                 300V--121k--p V1a--47n--210k--+--g V1b
                                 k--1.21k--0    |
                                               +--3.3n--0
                                               +--33.2k--10n--0
                                               +--2.21M--0
                 300V--100k--p V1b--470n--out--2.21M--0
                                 k--1.21k--0
```

`3.3 nF` is a shunt capacitor at the second grid. A low-resolution reading of
the schematic originally suggested 300 pF/series interpretations; topology
inspection and the RIAA sweep disproved both. That correction is recorded in
the changelog so it cannot become an invisible reference edit.

| Part/function | Frozen value |
|---|---:|
| B+ | 300 V |
| input termination | 47.5 kΩ |
| grid stopper | 221 Ω |
| stage 1 plate/cathode | 121 kΩ / 1.21 kΩ, unbypassed |
| plate coupling | 47 nF |
| RIAA series arm | 210 kΩ |
| RIAA low-frequency branch | 33.2 kΩ + 10 nF to ground |
| RIAA high-frequency capacitor | 3.3 nF to ground |
| stage 2 grid leak | 2.21 MΩ |
| stage 2 plate/cathode | 100 kΩ / 1.21 kΩ, unbypassed |
| output coupling/load | 470 nF / 2.21 MΩ |

No cathode bypass capacitor exists in this topology. The large 2.21 MΩ
reference load is part of the published circuit; a future practical line driver
must buffer it without silently changing reference loading.

## Cartridge wrapper

The test source is the Audio-Technica AT-VM95E nominal equivalent: ideal source,
485 Ω winding resistance, 550 mH winding inductance, 47.5 kΩ termination, and
150 pF total shunt capacitance. The last value represents cable, connector,
front-end, and selectable capacitance together. It is not an FPGA-only setting:
the physical input must present it to the cartridge.

The ideal LC resonance is 17.52 kHz. With winding resistance and the 47.5 kΩ
load, the computed terminal response peaks by only +0.064 dB near 7.59 kHz and
is -3.48 dB at 20 kHz for the analytical wrapper. ngspice reports -5.00 dB at
20 kHz because the circuit input and tube capacitances add to the explicit
150 pF. These two numbers intentionally answer different loading questions.

## Measured ngspice baseline

| Node/quantity | Result |
|---|---:|
| stage 1 cathode | 1.2001 V |
| stage 1 plate | 179.994 V |
| stage 1 plate current | 0.9918 mA |
| stage 2 grid | 2.213 mV |
| stage 2 cathode | 1.2970 V |
| stage 2 plate | 192.808 V |
| stage 2 plate current | 1.0719 mA |
| circuit gain at 1 kHz | 41.087 dB |
| cartridge-source to output at 1 kHz | 41.019 dB |
| phase at 1 kHz | -0.849° |

Relative to the canonical 3180/318/75 µs replay curve and normalized at 1 kHz,
the physical circuit spans -0.919 to +0.000 dB error over 20 Hz–20 kHz, with
0.364 dB RMS error. The largest departure is the low end. Reference mode keeps
it. An ideal-RIAA mode may be useful for diagnostics but is not the circuit.

The 1 kHz sweep is essentially linear at cartridge levels: 5 mV peak produces
0.562 V peak output and 0.0189% H2–H10 THD in this Koren SPICE model. At 0.5 V
peak input it produces 2.21% THD. The first tested level beyond 1 dB compression
is 1.1 V peak—far outside an MM cartridge signal. These are model results, not
measurements of a physical Kennedy preamp, and positive-grid behavior remains a
weakly supported part of the tube model.

## Stability policy

Changing a frozen component, B+, tube parameter set, source, or reference load
requires a model version increment plus a changelog entry. Tolerance, aged-tube,
noise, subsonic, and modern output-loading variants must not overwrite nominal
results.
