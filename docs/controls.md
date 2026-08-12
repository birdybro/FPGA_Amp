# Control plane and diagnostics

Audio processing accepts a versioned parameter snapshot only on a 48 kHz sample
boundary. Host protocol parsing never writes datapath registers directly. A
shadow bank, commit sequence number, and acknowledge bit make multiregister
changes atomic; model changes invoke mute/state initialization before commit.

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
