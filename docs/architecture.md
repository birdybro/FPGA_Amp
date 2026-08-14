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

`phono_stream_mono_wide_guarded.sv` composes the accepted wide reference core
with a downstream, explicitly non-reference safety/control boundary. A model
change is accepted only in the ready state. The guard ramps the 48 kHz output to
zero, waits for an input enable, holds the core reset for 2,047 fabric clocks,
and releases it in time for the following 48 kHz enable at phase zero. It then
discards 64 output samples while muted, acknowledges the initialized state, and
ramps up. The reference core remains a separate module and its behavior is not
changed by this policy.

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

`rtl/io/async_fifo.sv` implements the fallback CDC primitive rather than
assuming BCLK is synchronous to fabric. Each domain owns a binary pointer and
exports only its Gray encoding through two explicitly marked synchronizer
registers. Full/empty decisions use the locally registered pointer plus the
synchronized remote pointer; memory data crosses only after the corresponding
pointer has propagated. Reads are registered. Overflow and underflow are sticky
in their owning domains. Reset assertion may be asynchronous, but a board-level
reset conditioner must deassert each reset synchronously to its clock. The FIFO
is infrastructure outside the historical circuit behavior.

The adjacent I²S primitives use the conventional Philips timing relationship:
LRCLK low is left, the LRCLK transition occurs one BCLK before the MSB, receive
samples on rising edges, and transmit changes LRCLK/data on falling edges. The
frozen initial format is 24 signed sample bits in each 32-BCLK channel slot;
inputs are sign-extended into `{left[31:0], right[31:0]}` frames and transmitter
padding is zero. Receiver framing error and transmitter starvation are sticky.
The transmit negative-edge registers require an explicit opposite-edge BCLK
constraint in the placed design.

`rtl/io/i2s_async_bridge.sv` composes the protocol blocks and two depth-8,
64-bit asynchronous FIFOs into a bidirectional stereo frame interface. Receive
data is held under fabric ready/valid backpressure. Fabric transmit valid is
accepted only when the transmit FIFO reports ready; violating that contract is
retained as FIFO overflow. The BCLK prefetch never requests an empty FIFO, and
the transmitter substitutes a zero frame plus a sticky starvation flag when no
frame reaches a left-slot boundary. All framing, overflow, underflow, and serial
starvation flags remain observable in their owning domains. The bridge does not
establish whether FPGA or converter is final clock master. It remains a reusable
block and is also composed with the adapter by the pin-facing mono top.

The standalone calibration layer now provides the missing arithmetic on each
side of that bridge: PCM24 to input-referred physical Q8.24 volts, and physical
Q8.24 line voltage to saturating PCM24. Coefficients are explicit fabric-domain
control values and invalid values mute with diagnostics. The current mono
adapter uses these primitives with a fixed framed-channel policy; atomic
coefficient commit and external bridge/control integration remain unresolved.

`rtl/io/audio_frame_scheduler.sv` closes the phase-alignment gap without hiding
rate mismatch. At the 98.304 MHz target it raises ready for one fabric clock per
2,048-clock audio interval. A held bridge frame is launched one clock before
phase zero; the registered PCM24-to-Q8.24 calibrator then presents valid to the
core exactly at phase zero. If no frame is available, the scheduler launches a
zero frame to preserve solver cadence and increments a saturating underflow
counter. If BCLK and fabric derive from independent nominal-48-kHz oscillators,
FIFO occupancy will still drift toward overflow or underflow. This scheduler is
therefore valid for frequency-locked clocks with arbitrary phase, not an ASRC.

`rtl/top/phono_fabric_mono_adapter.sv` is the first complete fabric-domain PCM
composition. It selects PCM24 from the left 32-bit slot, applies the explicit
input calibration, runs the accuracy-first trapezoidal/banked/terminal V1
stream, applies output calibration, and duplicates the resulting mono PCM24
sample into sign-extended left and right slots. The unrelated right input is
discarded deliberately; duplication is a bring-up policy and must not be
described as stereo circuit modeling. A held output register preserves an
unaccepted frame and counts any later model result that cannot be stored.

The scheduler needs almost one sample period to acquire initial phase. Because
the interpolator emits scheduled zero-valued internal samples without waiting
for its first external input, simply releasing every reset together advanced
the virtual capacitor state before the first accepted frame. The adapter holds
the model core in reset through that acquisition interval. The first scheduler
launch registers input calibration while the core is still reset; the following
phase-zero edge releases the core and consumes exactly that sample. This is
numerical startup alignment, not output pop protection. A separate mute/ramp
and atomic control update are still required around the physical output path.

`rtl/top/phono_i2s_mono_top.sv` connects the bridge and adapter without adding
sample-rate conversion or converter policy. It exposes separate BCLK-domain,
fabric-domain, and audio-state resets. The bridge fabric reset is released
first so a complete received frame can cross and be held; `audio_rst_n`, which
must be synchronized to the fabric clock, is then released to begin scheduler
phase acquisition. This avoids both an initial scheduled zero and the hidden
pre-input state advance described above. The demonstrated clocks are exactly
frequency locked at 3.072 and 98.304 MHz but have unrelated phase. Independent
nominal-rate oscillators remain invalid because FIFO occupancy would drift.

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
47 RAMB18 for the surface mode and 9,148 LC / 108 DSP / 8 RAMB18 + 1 RAMB36 for factorized
mode. These are generic structural counts, not timing closure.

At complete-stream scope the corresponding counts are 13,170 LC / 137 DSP /
47 RAMB18 for the surface mode and 14,290 LC / 156 DSP / 8 RAMB18 + 1 RAMB36 for the
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
outputs and 1,024 internal solves. Its 168-DSP structural result leaves no room
for full channel duplication on the 240-DSP A7-100T. The 12-clock-per-solve
margin is insufficient to serialize a second complete solver, so stereo now
requires a finer-grained shared schedule or a larger reference part.

The guarded hierarchy adds the model-change state machine and output multiplier.
Generic XC7 synthesis reports 17,562 logic cells, 170 DSP48E1s, and 8 RAMB18 + 1 RAMB36.
The separately synthesized unguarded hierarchy reports 17,492 LC / 168 DSP /
8 RAMB18 + 1 RAMB36;
out-of-context logic-cell estimates are optimization-dependent and are not
additive. No placed timing result is implied by their small difference.

## Runtime observability contract

The solver provides counters for rejected sample requests, processing deadline
misses, node/residual saturation, LUT range clipping, and residual-limit
failures, plus the last residual and measured sample latency. The wider stream
will additionally provide saturating counters for input/ADC clipping,
LUT range clipping, arithmetic saturation by node type, solver residual failure,
maximum/average iteration count, missed 768 kHz deadlines, serial FIFO overrun
or underrun, and DAC clipping. Counters are sticky until software clears them.
