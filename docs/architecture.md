# Architecture

## Accuracy boundary

Reference mode begins at the cartridge generator and ends at the line load.
Its circuit values come from the frozen model asset. Converter calibration maps
real volts to the model's physical units; it must not compensate reference
response. Approximation diagnostics sit beside the datapath. Modern features
are separate blocks with explicit bypass and mode state.

```text
physical RCA input
  -> selectable 47.5 kΩ / total capacitance and RF protection
  -> low-current-noise flat gain, nominally 26 dB
  -> differential anti-alias/ADC (2 V RMS differential design reference)
  -> calibrated volts/sample
  -> 48 kHz to 768 kHz interpolation
  -> nonlinear V1 circuit solver (reference)
  -> 768 kHz to 48 kHz anti-alias/decimation
  -> mute/volume outside reference model
  -> DAC/reconstruction/line driver
```

The first real-time target is 48 kHz external audio, 16× internal simulation,
and 98.304 MHz fabric. The fabric rate is a refinement of the original “about
96 MHz” target: it is exactly 128 clocks per 768 kHz simulation enable and 2048
clocks per 48 kHz sample when derived from a 24.576 MHz audio master. Datapath
logic uses enables, not derived fabric clocks.

## Solver shape

The floating reference has nine dynamic nodes and 13 physical capacitors
(including six tube parasitics). Each sample stamps capacitor companions,
evaluates both triodes, solves the coupled system, and commits state only after
the nonlinear solve. Previous-sample node voltages seed Newton iteration.

One and two-pass full-Newton experiments at 20 mV peak show the same -136.84 dB
output difference from the converged run, but only two passes satisfy the 100 pA
residual criterion on every sample. A simpler raw tube-current fixed-point update
fails the residual criterion even after 12 relaxed passes and can diverge.

The hardware candidate is instead chord iteration: freeze the nonlinear
Jacobian at the quiescent point, precompute its inverse, and apply a constant
matrix-vector correction to the exact nonlinear residual. For a deterministic
50 Hz + 1 kHz + 10 kHz multitone, three unrelaxed passes converge every sample
and are -137.28 dB normalized residual from full Newton. Full Newton remains the
floating reference; three-pass chord becomes eligible for fixed-point work, with
residual/deadline counters. Fixed coefficient quantization is not yet included.

## Clock and interface plan

- 24.576 MHz low-jitter oscillator: common audio master for 48/96/192 kHz family.
- 98.304 MHz MMCM output: sole fabric processing clock.
- 768 kHz and 48 kHz: synchronous one-cycle clock enables divided by 128 and
  2048 respectively.
- 3.072 MHz BCLK and 48 kHz LRCLK: external serial-audio clocks. Prefer a
  fabric-clocked edge-enable shifter when timing permits; otherwise use a small
  explicit asynchronous FIFO. Never treat an unverified phase relationship as
  synchronous.
- Host UART/SPI/USB: separate control domain, synchronized register handshakes,
  with audio parameters applied atomically at a sample boundary.

## Stereo scheduling

Duplicating the accuracy-first tube primitive would consume 32 DSPs and 94
RAMB18s before circuit arithmetic. A mono three-pass chord solve needs six tube
requests, consuming 48 of 128 clocks with the serialized eight-clock primitive
and leaving 80 for residual/matrix/state work. Stereo on one such engine would
consume 96 clocks for tube requests alone and is not a credible closed schedule.
The current direction is mono completion followed by either duplicated L/R table
engines, a higher-throughput ROM pipeline, or a measured smaller-table trade.
Deadline counters remain mandatory; no full stereo budget is claimed yet.

## Runtime observability contract

The integrated stream will provide saturating counters for input/ADC clipping,
LUT range clipping, arithmetic saturation by node type, solver residual failure,
maximum/average iteration count, missed 768 kHz deadlines, serial FIFO overrun
or underrun, and DAC clipping. Counters are sticky until software clears them.
