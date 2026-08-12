# Gain and headroom

All cartridge values below are RMS at 1 kHz unless marked as peaks. The analysis
reference ADC is 2.0 V RMS differential full scale and a flat 26 dB front-end.
This is a calibration target, not a claim that a chosen converter has already
been laid out or measured.

## Physical input and ADC

| Cartridge case | Level | After 26 dB | ADC level |
|---|---:|---:|---:|
| very quiet | 0.5 mV RMS | 9.98 mV RMS | -46.0 dBFS |
| nominal AT-VM95E | 4 mV RMS | 79.8 mV RMS | -28.0 dBFS |
| high output/hot groove | 10 mV RMS | 199.5 mV RMS | -20.0 dBFS |
| severe program transient | 20 mV RMS | 399 mV RMS | -14.0 dBFS |
| click/pop design case | 100 mV RMS-equivalent | 1.995 V RMS | -0.02 dBFS |

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

The Koren SPICE level sweep reaches its first tested 1 dB compression point only
at 1.1 V peak cartridge source, so ordinary 1 kHz MM overload is dominated by
the physical front end/ADC unless gain is planned carefully. Low-frequency warp,
record pops, and the RIAA bass boost are more relevant headroom cases and remain
required multitone/transient regressions.

## Digital representation

ADC samples are converted immediately to calibrated cartridge volts. The
floating model uses volts and amperes. The tube primitive uses Q8.24 `Vgk`,
Q12.20 `Vpk`, and Q0.31 currents. Full circuit state formats are not yet frozen;
candidate plate and coupling nodes must cover at least -50 to +350 V during
overload without wraparound. Every physical-to-DAC scaling factor will be
versioned separately from the model asset.

Future line, phase-inverter, power-tube, transformer, speaker, and physical
power-amplifier rows cannot be honestly populated before a V2 circuit is selected.
