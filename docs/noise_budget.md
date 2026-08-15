# Noise budget

`scripts/analyze_frontend.py` numerically integrates the 20 Hz–20 kHz noise
density of the AT-VM95E R/L source into 47.5 kΩ || 150 pF at 20 °C. The Rev-A
ADC study point is the PCM4202's 116 dB typical unweighted dynamic range at
2.12 V RMS differential full scale. Values
exclude 1/f noise, hum, RF rectification, converter distortion, reference noise,
and PCB leakage; they are a lower-level design calculation, not a measurement.

## Input-referred contributors

| Contributor | Unweighted RMS | RIAA-weighted RMS |
|---|---:|---:|
| 485 Ω cartridge winding | 0.371 µV | 0.258 µV |
| 47.5 kΩ termination through MM source impedance | 2.825 µV | 0.515 µV |
| OPA1656 voltage noise, 4.3 nV/√Hz | 0.608 µV | included below |
| OPA1656 current noise, 6 fA/√Hz | 0.029 µV | included below |

The termination's unweighted contribution is high because the cartridge source
impedance rises with frequency. Playback RIAA attenuates that region, which is
why an unweighted “47 kΩ noise” shortcut is misleading here. The complete
OPA1656 analog estimate is 2.914 µV unweighted and about 0.701 µV after the
normalized playback weighting.

At the fitted flat 26.064 dB gain, ADC noise referred through the remaining
digital RIAA is 0.110 µV RMS. Analog plus ADC is 0.709 µV RMS, giving 75.0 dB
SNR for the 4 mV nominal reference before adding flicker, hum, tolerance, or
record noise.
The equivalent V1 line-output noise using 1 kHz gain is roughly 74 µV RMS, but
the actual output integration must use the physical circuit's frequency response.

| Input candidate | Voltage/current assumptions | Total unweighted input noise |
|---|---|---:|
| ADA4625-1 | 3.3 nV/√Hz, 4.5 fA/√Hz | 2.887 µV RMS |
| OPA1656 | 4.3 nV/√Hz, 6 fA/√Hz | 2.914 µV RMS |
| OPA210 | 2.2 nV/√Hz, 400 fA/√Hz | 3.459 µV RMS |

The bipolar OPA210 loses despite lower voltage noise because MM impedance makes
current noise significant. The comparison uses broadband typical numbers and
does not settle DC bias-current, overload, EMI, common-mode, package, or 1/f
tradeoffs. OPA1656 is now the Rev-A EVT BOM baseline because a dual JFET-input
part reduces channel count and preserves very low current noise. That is a
prototype choice, not measured proof that it is quieter than ADA4625-1 in this
circuit. The white-noise approximation is conservative relative to the
OPA1656's 2.9 nV/√Hz typical 10 kHz headline but still omits 1/f noise.

## Digital and downstream allocations

- ADC: the Rev-A PCM4202 calculation uses 116 dB typical unweighted dynamic
  range at its 2.12 V RMS differential full scale. Do not substitute its 118 dB
  A-weighted figure into an unweighted integration. The 26.064 dB gain leaves
  the calculated converter contribution below the analog estimate.
- Arithmetic: fixed circuit-state quantization should contribute at least 20 dB
  less RIAA-weighted noise than 0.70 µV input referred. Saturation counts are a
  separate overload metric, never averaged into quantization noise.
- DAC/line driver: the system target remains at least 115 dB A-weighted dynamic
  range at 2 V RMS and output noise below 4 µV RMS, with unweighted 20 Hz–20 kHz
  verification. The Rev-A PCM5242 EVT part publishes 114 dB A-weighted typical,
  so it does not close that production allocation on specification alone; the
  board is an architecture/mute prototype pending measurement and a production
  converter decision.
- Physical power stage: choose an input/output gain so its speaker-referred idle
  noise does not dominate the DAC; set a numeric target only with the eventual
  power and sensitivity requirements.

Deterministic model verification keeps all virtual resistor/tube/hum sources
disabled. Future noise modes need independent seeds and enable bits for thermal,
shot/1/f, supply ripple, heater hum, and creative microphonic modulation.
