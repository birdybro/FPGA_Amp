# Control plane and diagnostics

Audio processing accepts a versioned parameter snapshot only on a 48 kHz sample
boundary. Host protocol parsing never writes datapath registers directly. A
shadow bank, commit sequence number, and acknowledge bit make multiregister
changes atomic; model changes invoke mute/state initialization before commit.

The datapath-side reset transaction is implemented by `model_change_guard`.
Software asserts a level request only after `output_ready`, holds it until the
one-cycle acknowledgment, then deasserts it to re-arm the next transaction.
Acknowledgment follows muted core reset plus 64 valid warmup outputs; it does not
claim that ramp-up has reached unity. `change_busy` remains asserted during
ramp-up and `output_ready` identifies the eventual full-gain state. Model-asset
shadow registers and a host protocol remain open.

`phono_control_registers` now supplies the first concrete fabric-domain host
boundary. Its protocol-neutral request/registered-response bus accepts one
32-bit word transaction per fabric clock. It resets with mute asserted, owns a
coherent two-register calibration shadow pair, converts a commit command into
one update pulse, waits for the existing guard response, and records attempted
and accepted transaction sequences separately. Shadow writes are rejected while
a commit is pending. An invalid or live/unmuted attempt advances only the
attempted sequence and latches explicit rejected status; it cannot change the
active pair.

The same block copies all configured diagnostic input words on one snapshot
command. A saturating sequence identifies each completed image, and subsequent
reads access only the retained image. The inputs to that port must already be
in the fabric domain; this block does not pretend that unsynchronized I²S-domain
levels form a coherent word. A single control write can also pulse the existing
fabric diagnostic clear and independently clear register-local sticky evidence.
Verilator proves snapshot retention across changing live inputs, reset-muted
state, accepted/invalid/unsafe calibration transactions, pending-pair write
rejection, clear pulses, and bad-address reporting. XC7 structural synthesis is
323 estimated logic cells / 715 flip-flops / no DSP or block RAM; the one Yosys
warning is the expected 16x32 snapshot array expansion to registers. No Fmax is
claimed.

## Implemented word register map

Addresses are word addresses, not byte addresses. There are no partial writes.
SPI, UART, or an embedded processor may translate to this bus without changing
the audio solver.

| Address | Name | Access | Meaning |
|---:|---|---|---|
| `0x00` | identity | R | `0x46504741` (`FPGA`) |
| `0x01` | ABI version | R | major/minor `0x0001_0000` |
| `0x02` | capabilities | R | snapshot, calibration, mute, diagnostic clear |
| `0x03` | live status | R | mute, muted, ramping, commit busy, snapshot valid |
| `0x04` | control | R/W | bit 0 mute level; bits 1/2/3 snapshot, diagnostic clear, local-sticky clear commands |
| `0x05` | snapshot sequence | R | saturating completed-image sequence |
| `0x06` | calibration attempted | R | saturating commit-attempt sequence |
| `0x07` | calibration accepted | R | sequence of the last accepted attempt |
| `0x08` | ADC calibration shadow | R/W | signed Q8.24 input peak volts |
| `0x09` | DAC calibration shadow | R/W | signed Q8.24 reciprocal output peak volts |
| `0x0a` | calibration command | W | bit 0 commits the complete shadow pair |
| `0x0b` | ADC calibration active | R | guard-owned active coefficient |
| `0x0c` | DAC calibration active | R | guard-owned active coefficient |
| `0x0d` | sticky status | R | bus, rejected, invalid, and unsafe evidence |
| `0x20...` | diagnostic snapshot | R | retained configured diagnostic words |

`phono_i2s_control_top` connects 20 words to that aperture:

| Address | Snapshot contents |
|---:|---|
| `0x20` | clock lock/error, scheduled-frame, mute/ramp, calibration/configuration errors, synchronized I²S sticky faults, fabric FIFO faults, force mute |
| `0x21` | measurement-valid, lock/error, good-window count, measured BCLK edges |
| `0x22` | fabric RX/TX FIFO level and high-water views plus scheduler phase |
| `0x23` | output gain, solver latency, minimum correction format, mute/ramp |
| `0x24...0x31` | scheduler underflow, input endpoint, output PCM saturation/overrun, resampler saturation/overrun, input phase, output conversion, and six solver counters |
| `0x32...0x33` | 63-bit preterminal solver residual, low word first |

The four I²S-domain sticky bits are safe to synchronize because they remain
asserted until an explicit clear. Their multibit FIFO level/high-water views are
not copied across the domain; the snapshot deliberately includes only the two
fabric-owned FIFO views. A toggle-based command crossing converts one fabric
diagnostic-clear pulse into one I²S-clock pulse. Its unit test transfers two
events exactly once across unrelated clocks; structural synthesis is 1 LC / 5
FF. This crossing is for low-rate idempotent host commands, not event traffic.

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

This guard and its register bank are protocol-neutral and contain no hidden CDC
or coefficient slew. Bus requests must already be synchronous to the fabric
clock. Muted digital state makes the coefficient transition click-free at the
model boundary, but does not empty PCM already queued for the DAC. The
register-controlled pin wrapper supplies digital integration; queued-frame and
physical analog mute sequencing remain required.

The asynchronous audio FIFOs now expose local occupancy estimates and retained
high-water marks in all four owning-domain views (receive I²S/fabric and
transmit fabric/I²S). These values are derived from the local binary pointer and
the already synchronized remote Gray pointer. A write-side level may lag a read
high; a read-side level may lag a write low. They are intentionally raw-domain
diagnostics, not a coherent snapshot. Only fabric-owned views may connect
directly to the implemented snapshot bank; I²S-owned values still require safe
synchronization or a domain-local snapshot. Existing domain-local diagnostic
clear inputs also reset the corresponding watermark to the current projected
occupancy.

Clock status now includes a fabric-domain measurement-valid pulse, last BCLK
edge count, consecutive-good-window count, live rate-lock flag, and sticky rate
error. The default monitor requires three 1,024 ± 1 edge windows. It is already
in the fabric domain and can enter the implemented coherent diagnostic snapshot
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
`spi_control_transport` now implements the first such bridge without generating
an SPI-derived fabric clock. Two-flop input synchronizers and fabric-domain edge
detection oversample mode-0 CS/SCLK/MOSI; MISO changes on observed falling edges.
Each CS-low transaction is exactly 80 bits, MSB first:

```text
request  = write[1] + word_address[7] + write_data[32]
response = status[8] + read_data[32]
```

Response-status bit 0 is the register-bus error. CS deassertion before all 80
bits latches a frame error; a missing bus reply before response shifting latches
underflow; completed-frame count saturates. The test uses 5 MHz SPI against a
100 MHz fabric model and drives eight complete reads/writes through the real
register bank and calibration guard, including bad-address status, a ten-bit
abort, a deliberately withheld reply, and diagnostic clear. The transport is
warning-free and synthesizes to 112 LC / 172 FF / no DSP or RAM. This is not a
placed SCLK-limit claim; the board constraint must preserve comfortable
oversampling margin. Full pin-wrapper composition remains the next integration
step. No protocol-specific state belongs in the audio solver.
