# Control plane and diagnostics

Audio processing accepts a versioned parameter snapshot only on a 48 kHz sample
boundary. Host protocol parsing never writes datapath registers directly. A
shadow bank, commit sequence number, and acknowledge bit make multiregister
changes atomic; model changes invoke mute/state initialization before commit.

The datapath-side reset transaction is now implemented by `model_change_guard`.
Software asserts a level request only after `output_ready`, holds it until the
one-cycle acknowledgment, then deasserts it to re-arm the next transaction.
Acknowledgment follows muted core reset plus 64 valid warmup outputs; it does not
claim that ramp-up has reached unity. `change_busy` remains asserted during
ramp-up and `output_ready` identifies the eventual full-gain state. The shadow
register bank and host protocol that supply the parameter snapshot remain open.

## Initial register groups

| Group | Examples | Update rule |
|---|---|---|
| identity | core version, model ID/version, build hash | read-only |
| transport | mute request/status, sample-rate status, FIFO status | synchronized handshake |
| calibration | ADC volts/FS, DAC volts/FS, channel gain/offset | muted or atomic boundary |
| reference model | nominal asset selection only in V1 | state-reset transaction |
| variation | tube parameter set, component seed/tolerances | labeled variation mode; state-reset transaction |
| modern | subsonic enable, user volume | outside reference block; click-free ramp |
| diagnostics | counters, maxima, sticky fault bits | coherent snapshot/read-clear |

Write access to reference values is not a backdoor “tone control.” Arbitrary
experiments are creative mode and the active mode is included in captures.

The implemented calibration primitives consume positive signed-Q8.24
coefficients. ADC calibration is input-referred peak volts at PCM full scale;
DAC calibration is reciprocal peak volts. `calibration_commit_guard` now owns
the active pair in the pin-facing top. Its two active values reset to zero and
change together only when `update_valid` presents two positive candidates while
the downstream digital ramp reports muted. An accepted update produces a
one-clock acknowledgment. Invalid and live/unmuted attempts leave both active
values unchanged and set separate sticky diagnostics. The host must commit a
valid startup pair before releasing audio state; otherwise the arithmetic
blocks deliberately emit valid zero samples and flag invalid configuration.

This guard is protocol-neutral and contains no hidden CDC or coefficient slew.
Candidates and `update_valid` must already be synchronous to the fabric clock.
The future shadow-register/host transaction layer must hold a coherent pair,
observe the acknowledgment, and prevent a stale request from being interpreted
as a new transaction. Muted digital state makes the coefficient transition
click-free at the model boundary, but does not empty PCM already queued for the
DAC.

The asynchronous audio FIFOs now expose local occupancy estimates and retained
high-water marks in all four owning-domain views (receive I²S/fabric and
transmit fabric/I²S). These values are derived from the local binary pointer and
the already synchronized remote Gray pointer. A write-side level may lag a read
high; a read-side level may lag a write low. They are intentionally raw-domain
diagnostics, not a coherent snapshot. The future status register layer must
synchronize or snapshot each owning-domain value before host access. Existing
domain-local diagnostic clear inputs also reset the corresponding watermark to
the current projected occupancy.

Clock status now includes a fabric-domain measurement-valid pulse, last BCLK
edge count, consecutive-good-window count, live rate-lock flag, and sticky rate
error. The default monitor requires three 1,024 ± 1 edge windows. It is already
in the fabric domain and can enter a future coherent diagnostic snapshot
directly. Lock is live status; the sticky bit retains a bad window until the
fabric diagnostic clear.

## Required counters

ADC/DAC clip, internal-node saturation, LUT out-of-range, solver residual failure,
iteration sum/max, deadline miss, FIFO under/overflow, invalid control commit,
and mute/fault events are saturating 32-bit counters. An overflowed diagnostic
counter remains all ones. Per-node maxima use physical Q formats and clear only
by explicit command. These semantics allow formal proofs of no wrap and atomic
snapshot behavior later.

SPI is the simplest board-control candidate; UART is useful for bring-up and an
embedded CPU/USB bridge may be layered above the same register transaction bus.
No protocol-specific state belongs in the audio solver.
