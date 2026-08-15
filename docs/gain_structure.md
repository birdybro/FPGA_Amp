# Gain and headroom

All cartridge values below are RMS at 1 kHz unless marked as peaks. The analysis
reference ADC is the routed Rev-A PCM4202 path at 2.12 V RMS differential full
scale and 26.0639 dB flat gain. This is a calculated board contract, not a
measured converter or assembled-board result.

## Physical input and ADC

| Cartridge case | Level | After 26.0639 dB | ADC level |
|---|---:|---:|---:|
| very quiet | 0.5 mV RMS | 10.05 mV RMS | -46.48 dBFS |
| nominal AT-VM95E | 4 mV RMS | 80.4 mV RMS | -28.42 dBFS |
| high output/hot groove | 10 mV RMS | 201 mV RMS | -20.46 dBFS |
| severe program transient | 20 mV RMS | 402 mV RMS | -14.44 dBFS |
| click/pop design case | 100 mV RMS-equivalent | 2.010 V RMS | -0.46 dBFS |

The click value is a headroom test, not a stationary sine requirement. An input
hard clamp must protect the ADC beyond it, while a pre-clamp clip flag preserves
diagnostic evidence. A selectable 20/26/32 dB gain scheme is plausible, but 26 dB
is the reference study point because it accommodates the 100 mV case without
throwing away ADC performance at nominal level.

## Reference circuit at 1 kHz

The ngspice source-to-output gain is 41.019 dB (×112.46). The cartridge input
loading is -0.068 dB at 1 kHz, and the first stage's input-to-plate gain is
29.689 dB. For small signals:

| Cartridge source | V1 output | V1 output level |
|---|---:|---:|
| 0.5 mV RMS | 56.2 mV RMS | -25.0 dBV |
| 4 mV RMS | 449.8 mV RMS | -6.94 dBV / -4.72 dBu |
| 10 mV RMS | 1.125 V RMS | +1.02 dBV / +3.24 dBu |
| 20 mV RMS | 2.249 V RMS | +7.04 dBV / +9.26 dBu |

The practical DAC/line path therefore needs at least 2.25 V RMS clean output for
a 20 mV 1 kHz input if it reproduces the reference output voltage literally.
A calibrated digital attenuation of about 3 dB may be required for 2 V RMS DACs;
that is an output scaling choice after the reference model, not a change to tube
gain. Volume must occur outside the frozen circuit unless a versioned physical
volume-control topology is being modeled.

The routed PCM5242 output EVT calculates 4.00038 V RMS balanced full scale into
20 kilohm and 2.00019 V RMS RCA full scale into 10 kilohm. The balanced path
therefore has 5.00 dB of voltage margin over the literal 2.249 V reference case.
The RCA path is 1.02 dB short of that literal level and requires an explicit
calibrated scaling policy; it may not silently reduce reference-model gain.

The Koren SPICE level sweep reaches its first tested 1 dB compression point only
at 1.1 V peak cartridge source, so ordinary 1 kHz MM overload is dominated by
the physical front end/ADC unless gain is planned carefully. Low-frequency warp,
record pops, and the RIAA bass boost are more relevant headroom cases and remain
required multitone/transient regressions. The deterministic PCM suite now gives
finite-window evidence for that warning: a 5 mV-peak 11 Hz warp plus 1 mV-peak
1 kHz tone reaches 5.359 V peak, and the 5 mV log sweep reaches 4.136 V peak.
Those explicit capture mappings had to increase from 2 V to 8 V; the initially
clipped run was rejected rather than normalized. A deliberately nonphysical
1.5 V-peak, 5 ms input burst reaches 109.14 V at the virtual output and remains
at 1.720 V RMS over the final 1,024 samples of the 85.3 ms record. These are
virtual-node verification values, not DAC requirements or ordinary cartridge
claims, but they show why Q8.24's +/-128 V boundary and every downstream scaling/
clip counter must remain explicit.

## Digital representation

ADC samples are converted immediately to calibrated cartridge-terminal volts.
The implemented coefficient is ADC peak volts divided by measured analog gain,
quantized to signed Q8.24. At the prior 2.0 V RMS / 26 dB study point this was
0.1417571566 V peak or `2378290` Q8.24; the quantized value was 0.1417571306 V.
The actual Rev-A PCM4202 coefficient must be derived from measured per-channel
gain and full scale rather than copying that example. Likewise, PCM5242 output
calibration is per output mode/load and remains outside the reference circuit.
Output scaling and saturation occur only after the reference model.

The floating model uses volts and amperes. The tube primitive uses Q8.24 `Vgk`,
Q12.20 `Vpk`, and Q0.31 currents. Full circuit state formats are not yet frozen;
candidate plate and coupling nodes must cover at least -50 to +350 V during
overload without wraparound. Every physical-to-DAC scaling factor will be
versioned separately from the model asset.

Future line, phase-inverter, power-tube, transformer, speaker, and physical
power-amplifier rows cannot be honestly populated before a V2 circuit is selected.
