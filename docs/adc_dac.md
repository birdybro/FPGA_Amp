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

The first timing-closed board candidate uses the Nexys Video's fixed 100 MHz
source and the 384 kHz internal-rate profile instead of the nominal 98.304 MHz
tree above. The implemented XC7-only clock leaf is:

```text
100 MHz board oscillator
  -> MMCM: 12.288 MHz ADAU1761 MCLK
       -> MMCM: 49.152 MHz fabric
            -> ce_sim /128 = 384 kHz
            -> framed scheduler /1024 = 48 kHz
            -> planned BCLK /16 = 3.072 MHz
                 -> shared LRCLK /64 = 48 kHz
```

The exact MMCM ratios are generated and checked by `make audio-clock-plan`;
the clock-only harness is openly synthesized, routed, and converted to a
CRC-readable bitstream. The BCLK/LRCLK divider, shared physical LRCLK wrapper,
reset release, and ADAU1761 I2C configuration are not part of that harness yet.
This is an implementation architecture for the explicit 8x candidate, not a
silent change to 16x reference-mode numerical behavior.

The implemented protocol baseline is 24-bit signed I²S in 32-BCLK stereo slots,
so 48 kHz produces the planned 3.072 MHz BCLK. Receiver and transmitter are
separate BCLK-domain primitives with conventional one-bit-delay timing and no
converter-specific register assumptions. A dual-clock FIFO exists for the case
where BCLK/fabric phase is not proven synchronous. A bidirectional bridge now
integrates the protocol blocks with independent depth-8 stereo-frame FIFOs and
held ready/valid fabric interfaces. It deliberately performs no volts/code
calibration, channel scheduling, rate matching between independent nominal
sample clocks, or converter register setup.

Separate fabric-domain calibration primitives now implement the exact PCM24 to
physical-Q8.24 boundary. ADC direction uses input-referred peak volts at PCM
full scale; DAC direction uses reciprocal output peak volts and saturates before
serialization. Nonpositive coefficients mute and flag the sample. The
coefficients remain host/measured inputs, so this arithmetic does not select or
validate any listed ADC/DAC and cannot correct historical-circuit response.

The pin-facing top stores the two active coefficients behind an atomic commit
guard. Both reset to zero and accept a positive candidate pair only while the
digital output ramp reports fully muted. Invalid or live attempts preserve the
old pair and set separate sticky diagnostics. This establishes a safe
fabric-domain update boundary; converter register programming and host-to-
fabric CDC remain future board-control responsibilities.

The fabric frame scheduler consumes one held stereo frame at a deterministic
2,048-clock cadence and prelaunches for the one-clock input calibrator. A missing
frame becomes an explicit zero plus underflow count rather than an off-phase
core request. This handles unknown phase only when BCLK and fabric are frequency
locked. A converter with an independent master oscillator still requires an
explicit rate-control/ASRC decision; finite FIFO depth is not rate matching.

The pin-facing digital mono top now composes the bridge, scheduler, calibration,
and selected nonlinear stream. Its regression uses the exact planned ratio,
3.072 MHz BCLK to 98.304 MHz fabric, with independent phase. Bridge fabric reset
is released first; after a received frame crosses and is held, fabric-synchronous
audio reset is released. This proves one reset/rate contract in simulation, not
that either the FPGA or an unselected converter is the hardware clock master.
Each receive/transmit FIFO now reports local-domain occupancy and a retained
high-water mark. At the exact locked test rate all four views peak at one frame.
Write-side values conservatively lag completed reads high and read-side values
lag writes low; polling drift is useful evidence but is neither rate matching
nor a coherent CDC snapshot.

The pin top also instantiates a BCLK/fabric ratio monitor. Its default 333.33 µs
window expects 1,024 ± 1 BCLK rising edges and requires three consecutive good
windows, so nominal lock takes about 1 ms. One bad window drops lock immediately
and latches an error. The exact-rate integration measures 1,024 edges in each of
four windows. The ±1 count tolerance is a coarse ±0.098% configuration check;
smaller sustained differences appear as FIFO occupancy drift. Board startup may
observe this status but must not simply hold the depth-8 receive FIFO undrained
for the entire acquisition interval.

Jitter sensitivity must be checked at the highest analog input frequency. For a
20 kHz full-scale sine, 1 ps RMS aperture jitter alone corresponds to roughly
138 dB SNR; converter internal clocking, oscillator phase noise, and power noise
must be evaluated together rather than quoting one time-domain number.

## Latency accounting

The tube LUT is eight 98.304 MHz clocks (0.0814 µs) per evaluation. Digital
frame flow now exists through I²S, interpolation, solver, decimation, the
modern digital output ramp, and output serialization. The pin-level RTL now
timestamps actual valid/ready and serial-frame events at 3.072 MHz and both
supported fabric rates. From completion of the first ADC PCM frame to completion
of the first corresponding valid model-output DAC frame, both paths measure
exactly 192 BCLKs: 62.500 µs or 3.000 48 kHz sample periods. At
768 kHz / 98.304 MHz, accepted calibrated input to first model output-valid is
277 fabric clocks (2.8178 µs). This is four clocks beyond the older report
because each circular-history 2x decimator performs its center tap in a
dedicated cycle. At 384 kHz / 49.152 MHz the corresponding interval is 265
clocks (5.3914 µs). Mute/output calibration adds two clocks and the held
transmit frame is accepted one clock later in both cases. The detailed reports
are `model/generated/phono_i2s_mono_top_latency.json` and
`model/generated/phono_i2s_mono_top_384khz_latency.json`.

This is transaction/valid transport latency, not signal group delay. The first
fixture code becomes nonzero at output index 19 because of initialized circuit
state, filtering, and PCM quantization; that index is retained as a regression
but is not used as an impulse-delay estimate. The separately measured identity
resampler has 51 samples of causal converter delay, while a real circuit also
has frequency-dependent phase. Converter digital filters, aperture, analog
filters, and board propagation remain unknown. Final end-to-end latency will
use an analog loopback impulse/correlation measurement, not a sum of optimistic
data-sheet typical values.
