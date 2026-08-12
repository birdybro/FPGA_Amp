# ADC, DAC, and audio clocks

No converter is selected for a production PCB. The following current, official
candidate specifications narrow prototype work; they are not claims about a
complete implementation.

## ADC candidates

| Candidate | Relevant published capability | Engineering position |
|---|---|---|
| AKM AK5572EN | 2-channel differential, up to 768 kHz, 121 dB dynamic range, 112 dB S/(N+D), 124 dB mono mode, TDM | Leading high-performance prototype candidate; confirm exact full scale, group delay, supply/reference, and current availability in data sheet |
| TI PCM4202 | 2-channel, 24-bit, 216 kHz, 118 dB A-weighted dynamic range, -105 dB THD+N, I²S | Mature audio-analysis baseline; lower integration rate but credible measured-performance target |
| TI TAA5242 | 2-channel, 192 kHz, 119 dB dynamic range, 2 V RMS differential full scale, I²S/TDM | Convenient match to the quantitative 2 V/119 dB front-end study; -98 dB THD+N may limit high-level transparency |

The initial board should expose converter clipping before any digital scaling.
At 48 kHz operation, a 24.576 MHz master allows standard clock ratios, but the
analog anti-alias path must suppress energy above Nyquist. Running the ADC at
96/192 kHz and explicitly decimating before the 48 kHz model is an alternative
if measured RF/alias performance justifies the added block and latency.

## DAC candidates

| Candidate | Relevant published capability | Engineering position |
|---|---|---|
| TI PCM5242 | 32-bit/384 kHz voltage output, 114 dB SNR, 4.2 V RMS differential, integrated PLL/filters and soft mute | Practical first line-output path with enough voltage headroom; verify residual DSP bypass and latency |
| TI PCM1792A | 24-bit/192 kHz current output, 127 dB stereo dynamic range, -108 dB THD+N | Higher performance ceiling, but external I/V and mute circuitry add analog noise and complexity |
| AKM AK4493S | 32-bit/768 kHz, 123 dB S/N and -115 dB THD+N at 2 V RMS published | Strong performance candidate; supply, filter, clock, availability, and output-stage implementation still require detailed review |

Reference line output needs about 2.25 V RMS at a 20 mV RMS 1 kHz cartridge
input. A 2 V RMS DAC therefore needs calibrated attenuation or a post-DAC gain
stage; the 4.2 V RMS differential PCM5242 class offers more direct headroom.
Reconstruction filtering and line-driver load are measured as part of the full
path, never subtracted from a data-sheet number.

## Nominal clock tree

```text
24.576 MHz low-jitter oscillator
  +-> ADC/DAC master clock
  +-> FPGA MMCM -> 98.304 MHz fabric
          +-> ce_sim /128 = 768 kHz
          +-> ce_audio /2048 = 48 kHz
          +-> serial clock scheduling, BCLK = 3.072 MHz for 64-bit stereo frame
```

ADC and DAC share the audio master to avoid asynchronous sample-rate conversion.
The fabric processes a single clock with enables. If a converter or USB source
must become clock master, its serial port crosses through an explicit dual-clock
FIFO and a rate-control policy; two “nominally 48 kHz” oscillators are not
silently connected.

Jitter sensitivity must be checked at the highest analog input frequency. For a
20 kHz full-scale sine, 1 ps RMS aperture jitter alone corresponds to roughly
138 dB SNR; converter internal clocking, oscillator phase noise, and power noise
must be evaluated together rather than quoting one time-domain number.

## Latency accounting

The tube LUT is eight 98.304 MHz clocks (0.0814 µs) per evaluation, but complete
latency is unknown until interpolation, solver, decimation, converter filters,
and mute ramps exist. Each block will publish integer/fractional sample delay.
The end-to-end report will use an analog loopback impulse/correlation measurement,
not the sum of optimistic data-sheet typical values.
