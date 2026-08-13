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

`phono_stream_mono.sv` now implements this digital reference boundary from
48 kHz Q8.24 physical input volts through 16× interpolation, the complete V1
solver, saturating Q12.20-to-Q8.24 line-voltage conversion, and anti-alias
decimation. Volume, muting, converter serialization, and enhancements remain
outside the circuit reference.

## Solver shape

The floating reference has nine dynamic nodes and ten capacitor branches
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
floating reference. The implemented fixed/RTL path uses exactly three Q17.1
chord corrections and a fourth residual-only pass, with residual, saturation,
LUT-range, request, and deadline counters.

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
RAMB18s before circuit arithmetic. A mono solve requires eight tube requests:
two for each of three corrections plus two for the final diagnostic residual.
Stereo on one serialized engine cannot meet the present schedule.
The current direction is mono completion followed by either duplicated L/R table
engines, a higher-throughput ROM pipeline, or a measured smaller-table trade.
Deadline counters remain mandatory; no full stereo budget is claimed yet.

The complete mono scheduler now has a measured 126-clock latency:

```text
RHS/history stamping                12 clocks
4 overlapped KCL + two-tube passes  84 clocks
3 chord corrections                 30 clocks
total                              126 clocks
```

The surface-LUT and factorized/Hermite tube primitives deliberately share the
same eight-clock request/valid contract, so selecting either implementation
does not alter this schedule. The measured hierarchy trade is 8,024 LC / 89 DSP /
47 RAMB18 for the surface mode and 9,194 LC / 110 DSP / 8 RAMB18 for factorized
mode. These are generic structural counts, not timing closure.

At complete-stream scope the corresponding counts are 13,170 LC / 137 DSP /
47 RAMB18 for the surface mode and 14,366 LC / 158 DSP / 8 RAMB18 for the
factorized mode. Both produce exact mode-specific fixed-model outputs.

The KCL engine evaluates nine matrix rows in parallel while the single tube ROM
engine serializes the two device evaluations. Completed RHS and chord results
launch the following residual pass on the same edge, eliminating control
bubbles. This leaves two clocks before the 128-clock/768 kHz deadline. It is a
simulation-proven schedule, not an Fmax claim; named-part place-and-route at
98.304 MHz remains required. Stereo therefore needs duplication or a materially
higher-throughput shared architecture.

The replacement wide-state arithmetic keeps the same ten-clock correction and
ten-clock ordinary KCL interfaces. Direct capacitor branches reduce RHS setup
from 12 clocks to 2. The integrated factorized controller measures 116 clocks,
including persistent Q30 history commit, Q28/Q32 tube-coordinate conversion,
and diagnostic handshakes. It matches 512 sequential fixed-model samples and
therefore has a simulation-proven 12-clock margin. Named-part timing closure is
still required before that margin is a hardware claim.

The complete wide stream is also simulation-proven exact for 64 external
outputs and 1,024 internal solves. Its 170-DSP structural result leaves no room
for full channel duplication on the 240-DSP A7-100T. The 12-clock-per-solve
margin is insufficient to serialize a second complete solver, so stereo now
requires a finer-grained shared schedule or a larger reference part.

## Runtime observability contract

The solver provides counters for rejected sample requests, processing deadline
misses, node/residual saturation, LUT range clipping, and residual-limit
failures, plus the last residual and measured sample latency. The wider stream
will additionally provide saturating counters for input/ADC clipping,
LUT range clipping, arithmetic saturation by node type, solver residual failure,
maximum/average iteration count, missed 768 kHz deadlines, serial FIFO overrun
or underrun, and DAC clipping. Counters are sticky until software clears them.
