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

An 8×/384 kHz implementation is now a measured architecture candidate, not a
reference-mode change. It would provide 256 fabric clocks per nonlinear update
and remove the fourth 2× converter stage, creating enough schedule margin for
substantial multiplier reuse. Floating comparison bounds its 20 kHz SPICE
error at -0.06653 dB / +0.01167° and finds no meaningful selected-product
increase in 5 mV, 20 mV, or steady 0.5 V complete-circuit tests. A hot static-
tube stress is 11.33 dB worse than 16×, although still -118.65 dBc. The current
384 kHz fixed coefficient/state set and nonlinear core match 1,024 all-bank
chord, 1,024 KCL, and 512 persistent solver RTL vectors exactly. The core
consumes 127 of 256 clocks,
leaving 129 clocks for a more timing-friendly schedule. Its inverse matrix needs
signed 19-bit Q17.1 coefficients, one bit wider than the 768 kHz implementation.
Reference mode remains 16×. The separately named three-stage 8× converter and
384 kHz nonlinear core now compose into a complete bit-exact candidate stream:
64 external outputs cover 512 persistent solver updates with zero converter,
solver, or deadline diagnostics. Its default stage-3 enable occurs every 256
fabric clocks and interpolation scheduling delay is eight 384 kHz samples.
After sharing each decimator stage's center-tap multiplier and replacing its
shifting history with reset-masked circular distributed memory, Yosys synthesis
measures 16,315 LC / 10,520 FF / 207 DSP / 10 RAMB18 equivalents versus 16,704
/ 11,282 / 206 / 10 at 768 kHz. This is structural evidence, not Fmax closure.
The subsequent complete fixed-stream transient gate processes
772,608 nonlinear updates with zero diagnostics. Its accepted-range overload
recovery is close: 8× is 0.1875 ms later, -84.71 dB aligned overall, and
-81.02 dB in-band. The pop comparison uses the independently known -1.25-sample
converter delay and 64-tap windowed-sinc interpolation; it measures -35.92 dB
overall, 2.623 mV peak, and -53.33 dB in-band. Converter-only in-band error is
-67.49 dB, while the floating/fixed complete paths are -55.71/-53.33 dB, so the
remaining delta is primarily rate-dependent circuit behavior. Direct RTL
matches all 24,576 fixed outputs across 294,912 updates. The candidate remains
bit-exact at both rates. The subsequent absolute pop-response test drives
ngspice from each rate's actual interpolated INPUT-node waveform, subtracts a
matched 5 mV/1 kHz control trajectory, and applies the corresponding decimator.
Without latency, gain, or DC fitting, Python-to-SPICE external residual is
-61.47 dB / 0.539 mV maximum at 384 kHz and -61.00 dB / 0.546 mV at 768 kHz.
Both floating solves converge. This transient slightly favors 8×, but the
difference is too small and too stimulus-specific to establish a general
accuracy advantage. Named-part evidence is now negative: A100T packs but does
not legalize under the heap placer, while legal A200T static placement reaches
34.40 MHz against 98.304 MHz. An explicit 49.152 MHz schedule instead uses
1,024 clocks per 48 kHz input and 128 per 384 kHz update. The same 127-clock
solver and all 64 complete outputs remain exact with zero diagnostics, proving
one clock of real schedule margin. The shifting-history baseline reaches 38.34
MHz with static placement against 49.152 MHz. Circular decimator history cuts
4,173 packed flip-flops and lets heap placement legalize, but the resulting
22.79 MHz estimate still fails the clock. Static placement reaches 38.38 MHz,
effectively unchanged from the old 38.34 MHz result. The candidate remains
unpromoted pending registered cross-block scheduling and timing closure.

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

`rtl/io/audio_clock_rate_monitor.sv` independently checks the assumed rate
relationship. A continuously incrementing BCLK-domain counter crosses as Gray
code; the fabric domain measures 1,024 ± 1 rising edges per 32,768 fabric
clocks and requires three good windows for lock. Any bad window immediately
drops lock and latches a diagnostic. This is a roughly ±0.098% gross-rate check,
not phase alignment or ASRC; FIFO occupancy remains the slower drift indicator.

`rtl/io/async_fifo.sv` implements the fallback CDC primitive rather than
assuming BCLK is synchronous to fabric. Each domain owns a binary pointer and
exports only its Gray encoding through two explicitly marked synchronizer
registers. Full/empty decisions use the locally registered pointer plus the
synchronized remote pointer; memory data crosses only after the corresponding
pointer has propagated. Reads are registered. Overflow and underflow are sticky
in their owning domains. Reset assertion may be asynchronous, but a board-level
reset conditioner must deassert each reset synchronously to its clock. The FIFO
is infrastructure outside the historical circuit behavior. Its reset, Gray,
blocked-pointer, local-level/watermark, valid, and sticky-fault safety contract
now has a 13-property, 32-global-step Yosys SAT bound over arbitrary clock and
control interleavings. A full/overflow/underflow witness prevents vacuity;
unbounded induction and analog metastability behavior remain outside that
bounded result.

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

The standalone calibration layer provides the arithmetic on each side of that
bridge: PCM24 to input-referred physical Q8.24 volts, and physical Q8.24 line
voltage to saturating PCM24. Coefficients are explicit fabric-domain control
values and invalid values mute with diagnostics. The current mono adapter uses
these primitives with a fixed framed-channel policy.

At pin-top scope, `calibration_commit_guard` separates candidate and active
coefficient pairs. The active pair resets to zero, commits atomically only
while the output ramp is fully muted, and remains unchanged after invalid or
live update attempts. Separate sticky flags distinguish bad values from unsafe
timing. This closes the datapath-side atomicity rule, but not the host register
protocol or CDC that must deliver a coherent candidate snapshot. Twelve
arbitrary-input transition properties now close by Yosys SAT temporal induction
at depth 2, with a separate reject/commit/reject reachability witness.

`rtl/io/audio_frame_scheduler.sv` closes the phase-alignment gap without hiding
rate mismatch. At the 98.304 MHz target it raises ready for one fabric clock per
2,048-clock audio interval. A held bridge frame is launched one clock before
phase zero; the registered PCM24-to-Q8.24 calibrator then presents valid to the
core exactly at phase zero. If no frame is available, the scheduler launches a
zero frame to preserve solver cadence and increments a saturating underflow
counter. If BCLK and fabric derive from independent nominal-48-kHz oscillators,
FIFO occupancy will still drift toward overflow or underflow. This scheduler is
therefore valid for frequency-locked clocks with arbitrary phase, not an ASRC.
Nine arbitrary-source properties prove the exact phase, launch, zero-fill,
accepted-data, and saturating-counter transition contract by Yosys temporal
induction at depth 2; a separate trace reaches an absent then present boundary.

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
phase-zero edge releases the core and consumes exactly that sample. A separate
modern output ramp now follows the historical model and precedes DAC
calibration. Its exact-unity state bypasses multiplication, preserving reference
samples bit-for-bit. Physical analog muting is still required around the
hardware output path.

`rtl/top/phono_i2s_mono_top.sv` connects the bridge and adapter without adding
sample-rate conversion or converter policy. It exposes separate BCLK-domain,
fabric-domain, and audio-state resets. The bridge fabric reset is released
first so a complete received frame can cross and be held; `audio_rst_n`, which
must be synchronized to the fabric clock, is then released to begin scheduler
phase acquisition. This avoids both an initial scheduled zero and the hidden
pre-input state advance described above. The demonstrated clocks are exactly
frequency locked at 3.072 and 98.304 MHz but have unrelated phase. Independent
nominal-rate oscillators remain invalid because FIFO occupancy would drift.
The bridge now exposes occupancy and high-water diagnostics in each FIFO's two
local domains. They use synchronized Gray-pointer conversion and retain the
expected conservative staleness; the locked-rate integration peaks at one frame
in every view. A future control/status CDC must snapshot them before host use.
The fabric reset also resets active calibration to zero. A valid measured pair
is committed while `audio_rst_n` keeps the output ramp muted, and audio state is
released only after the one-clock commit acknowledgment. Later coefficient
updates require an explicit ramp-down to the same muted state.

At this fixed phase, timestamped RTL events measure 192 BCLKs (62.500 µs,
three 48 kHz frames) from completion of the first ADC PCM frame to completion
of the first valid model-output DAC frame. That is valid-token transport only;
it does not replace the independently measured resampler/circuit group delay or
include physical converter latency.

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

A separate bit-exact iterative Hermite kernel now proves that one product per
clock can route at 132.54 MHz in the open XC7 flow, but it takes three clocks
for one interpolation. It is not part of the eight-clock tube contract above.
The reciprocal, softplus, and power evaluations depend serially on one another,
and two of their results feed additional products; a direct substitution would
consume the solver's margin. Complete tube-cycle rescheduling is therefore a
prerequisite to integration, even though the local timing experiment passes.

The selectable value-only factorized candidate avoids that schedule growth.
Larger reciprocal/softplus/power ROMs reduce each interpolation to one product,
and the matching tube, 116-clock wide solver, and 127-clock terminal solver all
retain their existing interfaces and pass bit-exact tests. The default remains
Hermite while whole-solver routing and upstream-reference error are evaluated;
this is an approximation-architecture selection, not a circuit-mode control.

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
