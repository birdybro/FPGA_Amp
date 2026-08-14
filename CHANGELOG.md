# Changelog

All notable engineering changes are recorded here. The project is pre-release; dates use ISO 8601.

## Unreleased

### Added

- Adopted a fully open Linux FPGA implementation path. A pinned non-root
  bootstrap now builds nextpnr-Himbaechel for XC7A100T against Project X-Ray,
  and `run_openxc7.py` probes versions then composes Yosys synthesis with
  deterministic named-part packing, placement, routing, FASM, log, and JSON
  report generation. Added a three-pin Arty-A7-100 timing harness around the
  complete 127-clock trapezoidal/banked/terminal solver so its internal
  arithmetic can be routed without turning wide diagnostic buses into package
  pins. The backend is explicitly experimental and reports a `DEFAULT` timing
  grade; no qualified XC7A100T-1 or bitstream claim is inferred.
- The first accuracy-first solver harness packs on `xc7a100tcsg324-1` at
  50,789 `SLICE_LUTX`, 6,372 flip-flops, 3,770 CARRY4, 174 DSP48E1, eight
  RAMB18E1, and one RAMB36E1. Seed-1 placement reaches only 13.90 MHz against
  98.304 MHz. A controlled value-only tube substitution later reaches only
  13.67 MHz at placement, so the earlier Hermite-path diagnosis is explicitly
  rejected rather than preserved as a convenient explanation. Both are
  retained as failing timing baselines, not qualified speed-grade signoff.
- Added a bit-exact iterative Q0.16 cubic-Hermite kernel that preserves the
  established signed-32 wrap and add-half rounding contract while scheduling
  one full-width 32x17 multiply per clock. It passes 4,096 deterministic
  full-range vectors, in-flight reset, ignored-start, and all 4,110 existing
  factorized-tube vectors at a three-clock kernel latency. Yosys measures 265
  logic cells and two DSP48E1s out of context. Its three-pin harness routes on
  `xc7a100tcsg324-1` at 132.54 MHz against 98.304 MHz using nextpnr's
  experimental `DEFAULT` grade (886 packed LUT elements, 231 FFX, 49 CARRY4,
  two DSPs). The kernel is not yet substituted into the tube/solver: its added
  dependency latency must first be reconciled with the 127-clock deadline.
- Added a separately selectable value-only factorized 12AX7 candidate rather
  than changing reference mode. Measured 1,024/8,192/4,096-point reciprocal,
  softplus, and power tables retain the Koren law and eight-clock interface
  while trading 458,752 raw table bits for linear interpolation. A 100,000-
  point fixed probe measures 4.95 nA mean, 7.87 nA RMS, and 47.49 nA worst
  plate-current error. The RTL passes 4,110 tube vectors and both 512-vector
  wide/terminal solver regressions exactly at 116/127 clocks. The isolated
  tube routes at 113.24 MHz (`DEFAULT` grade) with 27 DSP48E1s; complete solver
  synthesis falls from 174 to 166 DSPs, but full placement reaches only 13.67
  MHz versus the Hermite solver's 13.90 MHz. It is therefore not promoted to
  the reference/default path; full routing remains in progress for detailed
  path evidence.
- Factored the ten parallel trapezoidal terminal-current recomputations into a
  separately routable, bit-exact module and added terminal-current, KCL, and
  chord timing harnesses to the open flow. Both 512-vector solver regressions
  retain 116/127-clock latency. The isolated terminal block uses 54 DSP48E1s;
  replacing its serial diagnostic overflow sum with an explicitly widened
  balanced popcount improves post-route timing from 51.95 to 88.83 MHz while
  preserving exact results. This still fails the 98.304 MHz target and is not
  represented as solver closure.

- Added a bounded arbitrary-pin formal contract for the oversampled mode-0 SPI
  control transport. Eleven assertions cover the two-stage pin synchronizers,
  0--80 bit-count bound/transition, one-cycle request decode and exact fields,
  mutually exclusive response states, saturating completed-frame count, frame
  reset, and exact diagnostic clear/error precedence through 32 fabric clocks.
  A separate 100-step trace reaches a decoded request plus short-frame and
  response-underflow evidence. The existing eight complete transactions remain
  the byte-order/full-frame check; unbounded induction, placed SCLK limits, and
  analog asynchronous-input behavior are not claimed.
- Added exhaustive formal contracts for both converter-calibration arithmetic
  boundaries. Twelve assertions prove the PCM24-to-Q8.24 valid-coefficient
  shifted product always fits signed 32 bits, exact registered valid/output/
  hold behavior, Q8.24-to-PCM24 clipping at both signed endpoints, and exact
  clear/increment/saturation/sticky diagnostic transitions for arbitrary
  samples and signed coefficients. Yosys 0.66 SAT temporal induction closes at
  depth 2; a separate trace reaches an input endpoint, output saturation, and
  both invalid-configuration stickies. The existing 4,159-vector-per-direction
  Python/RTL test remains the bit-accurate implementation comparison.
- Added a bounded arbitrary-clock formal contract for the BCLK-rate monitor
  used by the modern fail-closed mute guard. Sixteen assertions cover exact
  BCLK binary/Gray evolution, both synchronizer stages, measurement cadence,
  inactive/activation/window transitions, measured delta, lock qualification
  and drop, counter saturation, and sticky-error clear precedence through 32
  global steps in a reduced-parameter instance. A separate 48-step trace first
  acquires lock and then retains an out-of-tolerance error while unlocked. This
  proves digital state-machine safety, not Gray-bus placement, metastability,
  absolute clock accuracy, or progress when either clock stops.
- Added a bounded arbitrary-clock formal contract for the low-rate toggle-pulse
  CDC used by diagnostic clear. Ten embedded/harness assertions cover exact
  toggle and three-stage destination transitions, pulse decode/width, at-most-
  one outstanding event, no fabricated delivery, and exact delivery accounting
  through 40 global steps when a source event waits for the preceding event to
  be observed. A separate trace delivers two events. The directed RTL test now
  makes the reset contract explicit: destination reset while the source toggle
  is odd replays the idempotent command once after release. This is not an
  arbitrary-rate event channel or an analog-metastability proof.
- Added a bounded arbitrary-clock formal contract for the coherent held-bus CDC
  snapshot. Nine embedded/harness assertions cover capture-event provenance,
  destination hold stability, exact returned data, one-cycle valid behavior,
  request/completion accounting, and idle only after completion through 40
  global steps. A separate satisfiable trace transfers nonzero `0xa` data and
  returns to idle. This digital safety result assumes one disciplined shared
  startup reset; destination reset during an active request remains covered by
  the directed RTL regression, and analog metastability is not modeled.
- Added a formal frame-scheduler contract. Nine arbitrary-source assertions
  cover reset phase, deterministic wrap, ready/valid/present launch strobes,
  accepted data, zero fill, and exact clear/increment/saturation behavior of the
  32-bit underflow count. Yosys 0.66 SAT temporal induction closes at depth 2;
  a separate trace reaches an absent boundary followed by a present launch.
- Added a formal contract for atomic converter-calibration commits. Twelve
  arbitrary-input assertions cover reset, exact acknowledgment, simultaneous
  positive-pair commit only while muted, rejected-state immutability, invalid/
  unsafe sticky accumulation, and clear precedence. Yosys 0.66 SAT temporal
  induction closes at depth 2; a separate trace reaches invalid rejection,
  accepted commit, and unsafe rejection. The claim remains local to the guard,
  not the host transport or physical converters.
- Added a bounded multi-clock formal environment for the asynchronous FIFO.
  Thirteen embedded/harness properties cover Gray transitions, blocked
  pointers, occupancy/watermark bounds, read-valid timing, and diagnostic
  sticky/clear behavior for every arbitrary clock/control interleaving through
  32 global steps after disciplined reset. A separate 24-step satisfiable trace
  reaches depth four plus overflow and underflow evidence. The result is
  deliberately labeled bounded; the current invariant set does not close
  unbounded induction and SAT does not model analog metastability.
- Added a reproducible formal contract for the modern output mute/ramp. Fifteen
  assertions cover reset, force clamp, valid timing, held state, exact
  saturating gain transitions, endpoint output, monotonicity, and status under
  arbitrary post-reset inputs. Yosys 0.66 SAT closes temporal induction at
  depth 2; a separate satisfiable trace reaches unity in four accepted samples
  to rule out a vacuous reset environment. `make formal-mute` runs both checks
  and retains logs without extending the result to CDC or physical protection.
- Integrated coherent I²S FIFO levels/high-water marks into the atomic control
  snapshot. Snapshot commands now commit the retained image and saturating
  sequence only after the held-bus CDC returns; live status reports busy and
  capture availability. A default 131,072-clock timeout preserves the previous
  image/sequence and latches explicit evidence. Unit/integration tests cover
  busy rejection, stopped-BCLK timeout, later re-arm, captured timeout evidence,
  and clear. The Python client polls completion and rejects stale results. The
  22-word map adds packed I²S diagnostics at `0x35`, and the compatible ABI
  minor is now 1.1. XC7 structural synthesis is 354 LC / 735 FF for the register
  bank, 21,466 LC / 17,922 FF for the controlled hierarchy, and 21,589 LC /
  18,094 FF with SPI; the complete variants retain 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1 and zero structural-check problems.
- Added a reusable 16-bit held-bus CDC snapshot primitive. Its four-phase
  request/acknowledge handshake holds destination data stable through two
  source-clock synchronizer stages and one final settling clock. Three exact,
  warning-free captures cover unrelated clocks and destination reset during an
  active request. XC7 structural synthesis is 5 LC / 75 FF / no DSP or RAM with
  zero warnings/problems; register-bank integration is intentionally separate.
- Added `fpga_amp.host_control`, a dependency-free host definition of the
  ten-byte full-duplex SPI/register ABI. It validates identity, ABI,
  capabilities, lengths, reserved status, and bus errors; makes mute ownership
  explicit for snapshot/clear commands; and guards atomic calibration
  commit/poll/sequence handling. Six fake-link unit tests cover exact wire
  bytes and accepted/error paths without claiming a physical adapter backend.
- Added fail-closed BCLK-rate muting to the register-controlled pin wrapper,
  explicitly outside the historical model. Output is immediately clamped until
  three good clock windows qualify. A stopped/bad BCLK reasserts the clamp, and
  retained error evidence prevents automatic unmute after clock recovery until
  a host clear. A shortened-window end-to-end regression proves qualification,
  stopped-clock detection, reacquisition, coherent fault snapshot, and exact
  fabric/I²S clear delivery without stopping model scheduling or filling the
  receive FIFO. Updated flattened XC7 synthesis is 21,375 LC / 17,787 FF for
  the controlled hierarchy and 21,507 LC / 17,959 FF with SPI; both retain
  232 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1 and have zero structural-check
  problems.
- Added the complete SPI-controlled pin hierarchy. `phono_i2s_spi_top` connects
  the oversampled mode-0 transport to the atomic register/calibration bank and
  I²S/model path. A warning-free 15-frame test covers startup calibration,
  register readback, two retained diagnostic images across a live force-mute
  change, a retained aborted-frame fault, snapshotted transport count, and one
  fabric-to-BCLK diagnostic clear.
  The snapshot aperture grows to 21 words and now records transport faults and
  completed frames. Flattened XC7 structural synthesis is 21,506 LC /
  17,959 FF / 232 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1 with zero structural-check
  problems; named-part SCLK, CDC, I/O, and fabric timing remain unproven.
- Added a mode-0 SPI transport that oversamples asynchronous pins in the fabric
  domain and never creates a derived clock. Fixed 80-bit transactions carry a
  40-bit write/address/data request followed by status plus 32-bit read data.
  Warning-free integration drives eight 5 MHz transactions through the real
  register bank and calibration guard, retaining short-frame and withheld-
  response diagnostics and returning bad-address status. Standalone XC7
  synthesis is 112 LC / 172 FF / no DSP or RAM; no placed SCLK limit is claimed.
- Added a register-controlled pin-facing wrapper. Its 20-word snapshot includes
  every fabric counter, clock status, fabric FIFO levels, solver residual, and
  safely synchronized sticky I²S faults while deliberately excluding unsafe
  multibit I²S levels. A 1-LC / 5-FF toggle crossing delivers each diagnostic-
  clear command once to BCLK. Warning-free integration proves bus-owned startup
  calibration, untorn snapshots, force-mute capture, and clear CDC. Complete XC7
  structural synthesis is 21,363 LC / 17,755 FF / 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1; named-part timing and the subsequently added host
  transport composition were still open at this layer.
- Added a protocol-neutral fabric control register bank. It resets muted,
  snapshots 16 moving diagnostic words atomically, saturates snapshot/commit
  sequences, holds a coherent two-word converter-calibration shadow pair, and
  distinguishes accepted, invalid, unsafe, busy, and malformed transactions.
  Warning-free Verilator covers retained snapshots, two diagnostic clear pulses,
  and the real calibration guard. XC7 structural synthesis reports 323 LC /
  715 FF / no DSP or block RAM with one expected snapshot-array expansion
  warning and no timing claim.
- Added reproducible schedule-neutral terminal-solver rejection studies.
  Corrected-state bank reselection improves the 1.0 V burst by only 0.101 mV
  while worsening the 1.5 V and recovery results. Unconditional 5/4 terminal-
  residual scaling reduces burst RMS to 3.570/3.454 mV but worsens late state;
  cutoff-only scaling does not preserve the benefit. Full dual-triode median
  Jacobians do not generalize, while stage-one-split banks create 58 residual-
  limit misses and about 6.12 mV burst error at 1.5 V. All tests retain raw,
  unaligned metrics and leave the physical reference, production bank, unity
  correction, and 127-clock implementation unchanged.
- Extended the original deterministic PCM24 suite from nine to fourteen
  vectors. The exact fixed stream now processes 69,440 external frames /
  1,111,040 nonlinear updates with zero diagnostics or WAV clips. A 60 Hz/
  7 kHz, 4:1 SMPTE-RP-120-style profile reports 0.461295% first/second
  sideband-pair IMD while explicitly declining calibrated conformance; a paired
  5 mV one-sample impulse is exactly zero before the event, crosses four output
  LSBs after 34 samples, and peaks at 138.118 mV; paired nominal/0.5 V, 250 ms
  records measure final 1 ms RMS-threshold recovery at 147.750 ms relative to
  the input burst stop and 18.650 mV RMS deviation over the final 10 ms.
  Known-signal unit tests prove ideal AM-depth recovery and final-crossing
  semantics, including a synthetic late rebound.
- Added a Gray-counter BCLK/fabric rate monitor to the pin top. The default
  fabric window requires 1,024 ± 1 BCLK edges and three consecutive good
  windows for lock; one bad window immediately drops lock and latches an error.
  Warning-free directed RTL locks on exact 10-edge short windows, observes 11
  after a deliberate speed-up, recovers after three restored windows, clears
  the sticky diagnostic, detects stopped BCLK as a zero-edge bad window, and
  revokes live state on BCLK reset. The actual-rate
  pin test measures exactly 1,024 edges in all four observed windows without
  changing latency or PCM. Warning-free standalone synthesis is 68 LC / 125 FF
  / no DSP or RAM; the updated pin top is 21,014 LC / 16,907 FF / 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1.
- Added conservative local-domain FIFO occupancy and high-water diagnostics.
  Gray-to-binary conversion uses only the already synchronized remote pointer;
  write-side estimates may lag reads high and read-side estimates may lag writes
  low, so no coherent cross-domain snapshot is claimed. The depth-8 unit reaches
  exactly eight, drains to zero, clears both watermarks, and preserves 128-word
  wrap ordering. Both bridge and actual-rate pin regressions remain warning-free;
  deliberate bridge backpressure reaches RX 3/3 and TX 4/4 frames without loss,
  while all four locked-rate pin views peak at one frame. Updated synthesis is
  127 LC / 331 FF for one 8×32 FIFO, 571 LC / 1,547 FF for the bridge, and,
  with the later rate monitor, 21,014 LC / 16,907 FF / 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1 for the pin top.
- Added a protocol-neutral atomic converter-calibration commit guard. The two
  active Q8.24 coefficients reset to zero and change together only for a
  positive candidate pair while the digital output is fully muted. Directed
  warning-free RTL proves invalid rejection, muted commit/acknowledgment, live
  rejection without active-value change, and diagnostic clear. The pin-level
  regression now commits its startup pair before audio-state release and
  rejects a later live update. Standalone XC7 synthesis is 14 LC / 67 FF / no
  DSP or RAM with zero warnings and structural problems; the later
  clock-monitored pin top is 21,014 LC / 16,907 FF / 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1.
- Added the pin-facing digital mono top that composes the asynchronous I²S
  bridge with the calibrated accuracy-first adapter. An exactly rate-locked but
  phase-offset 3.072/98.304 MHz test pre-fills receive CDC, releases audio state,
  matches all 64 calibrated serial inputs and raw model outputs, and recovers 45
  consecutive observable DAC frames as exact mono duplicates. Expected startup
  serial starvation is retained and every other diagnostic stays zero.
  With the later integrated safety, calibration, and clock diagnostics,
  flattened XC7 synthesis is 21,014 LC / 16,907 FF / 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1; converter selection, placed timing, physical analog
  mute, and validation remain open.
- Added the calibrated fabric mono adapter around the exact
  trapezoidal/banked/terminal V1 stream. It selects left PCM24, schedules and
  calibrates physical input volts, runs the nonlinear circuit, calibrates the
  line-voltage result, holds ready/valid output, and explicitly duplicates mono
  into both slots without claiming stereo. A warning-free 64-frame regression
  checks every calibrated input, raw model output, and PCM frame exactly under
  output backpressure, then records/clears a directed overrun while retaining
  the older frame; all model/calibration diagnostics stay zero. Holding the core reset through
  initial phase acquisition fixes the observed hidden capacitor-state advance
  from pre-input interpolator zeros. The later integrated modern output ramp
  starts muted and reaches exact unity before reference comparison. Flattened
  XC7 synthesis is 20,489 LC / 15,592 FF / 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1; no Fmax is claimed.
- Added a deterministic fabric audio-frame scheduler for the strict 2,048-clock
  48 kHz core phase. It raises ready once per period, prelaunches by the
  registered calibration latency, injects a zero frame on starvation, and
  retains a saturating underflow count. Warning-free directed RTL proves held
  ready/valid transfer and phase-zero A/zero/B order; XC7 synthesis is 41 logic
  cells / 43 flip-flops / no DSP or RAM. It is explicitly not an ASRC.
- Added bit-accurate converter calibration models and synthesizable RTL.
  PCM24 maps to input-referred Q8.24 physical volts using explicit measured
  peak-voltage scaling; Q8.24 line voltage maps through an explicit reciprocal
  coefficient to saturating PCM24. Full products, symmetric nearest rounding,
  saturating counters, invalid-coefficient muting, and one-clock latency match
  across 4,159 vectors per direction. Warning-free XC7 synthesis reports input
  95 LC / 66 FF / 4 DSP48E1 and output 86 LC / 58 FF / 4 DSP48E1, with no RAM
  and no timing claim.
- Added a bidirectional stereo I²S/fabric bridge around the protocol primitives
  and two depth-8 × 64-bit asynchronous FIFOs. Warning-free simulation preserves
  20 exact frames across unrelated clocks and deliberate receive backpressure,
  checks six bridge diagnostics, and clears expected startup starvation in its
  owning domain. With later occupancy instrumentation, flattened XC7 synthesis
  is 571 logic cells / 1,547 flip-flops /
  no DSP or RAM with explicit small-memory register expansion. Post-map
  flattening also prevents the resource reporter from omitting instantiated
  primitive registers; a rejected intermediate 67-FF count is not retained.
- Added conventional 24-bit stereo I²S receive/transmit primitives in 32-BCLK
  slots. Warning-free loopback verifies 16 signed frames, independent slot/delay
  timing, LRCLK framing faults, and starvation; warning-free XC7 synthesis is
  35 LC / 105 FF receive and 97 LC / 137 falling-edge FF transmit with no DSP or
  RAM. The resource parser now counts negative-edge Xilinx flip-flop variants.
- Added a device-neutral asynchronous FIFO with binary/Gray pointers, two-flop
  pointer synchronization, registered reads, sticky per-domain overflow/
  underflow, and embedded formal invariants. Unrelated-clock simulation covers
  exact fill/drain faults and 128 wrapped words; generic XC7 synthesis reports
  127 logic cells / 331 flip-flops with later occupancy watermarks and the small memory explicitly expanded to
  registers and zero structural problems.
- Added simultaneous least-squares tone, H2--H10 THD, and explicitly selected
  intermodulation-product measurement plus nine original PCM24 fixtures. The
  accuracy-first fixed stream processes 32,448 outputs / 519,168 internal
  updates with zero diagnostics or clips; measured WAV-boundary THD is
  0.019826% at 5 mV peak and 0.011559% at 0.5 mV peak. High-frequency product
  bins are retained without mislabeling them as a standards-compliant scalar.
- Added dependency-free 16/24/32-bit integer PCM WAV I/O, an offline 48 kHz
  fixed-V1 processor with mandatory peak-voltage mappings and per-channel
  diagnostics, and explicit latency/gain/fractional-delay null comparison with
  residual WAV and spectrum outputs. A 1,024-frame synthetic terminal-
  trapezoidal regression is diagnostic/clip clean, recovers an injected
  23-sample delay exactly, and retains raw, latency-only, and opt-in gain-aligned
  residuals separately.
- Added exact trapezoidal terminal correction. Ten corrected Q4.44 capacitor
  current histories commit on the existing final chord edge, remain full-state
  bit-exact across 384,000 overload updates, and retain the 127-clock schedule.
  Generated constant conductances reduce the measured solver from a rejected
  210-DSP first implementation to 174 DSP48E1s.
- Integrated that solver into the complete 48→768→48 kHz stream. All 64 Q8.24
  outputs / 1,024 internal updates are exact with zero diagnostics; structural
  synthesis measures 20,241 logic cells, 222 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1. Named-
  part timing remains unproven.
- Added a captured 100 Hz/1/10/20 kHz frequency gate for the complete
  trapezoidal terminal stream. All 19,200 outputs are exact; gain/phase error
  versus floating trapezoidal stays within 0.000134 dB / 0.000444 degree. The
  report preserves startup drift separately from its -74.79 dB worst linear-
  detrended waveform null.
- Added a phase-coherent complete-stream alias-family decomposition covering all
  16 internal frequencies that fold to ±3 kHz. The combined out-of-band
  projection is captured bit-exactly in RTL; the 45 kHz fold is exactly zero in
  the Q8.24 window and the family-removed difference is -176.96 dBc, below fixed
  rounding closure.
- Extended overload capture to the banked terminal RTL and added coherent
  H1--H10, clipping-asymmetry, grid-current, recovery, and direct analytical
  null metrics. The 384,000-update campaign is full-state bit-exact with zero
  diagnostics through 1.5 V peak.
- Integrated the backward-Euler banked terminal solver into the complete mono
  48→768→48 kHz stream. The fixed composition and RTL match all 64 external
  outputs across 1,024 nonlinear updates at the measured 127-clock solver
  latency, with zero diagnostics.
- Added a dedicated complete-stream wrapper, reproducible vectors/metadata,
  regression and synthesis targets. Out-of-context XC7 synthesis measures
  18,466 logic cells, 168 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1 with zero structural
  problems; timing remains unclaimed without named-part place-and-route.
- Added an optional backward-Euler terminal-correction contract that reuses the
  final diagnostic residual for one Q40 chord update. Fixed Python and RTL keep
  the preterminal residual semantics explicit, commit four-pass-exact persistent
  state, and preserve a distinct integration-mode selection.
- Added exact sequential and 1.0/1.5 V overload RTL regressions for the terminal
  path, plus a dedicated synthesis wrapper and reproducible Make targets.
- Added a full 100 ms banked correction-count study for both integrators at
  1.0/1.5 V, including unaligned burst/recovery metrics, diagnostics, bank use,
  and explicit measured-versus-projected latency labeling.
- Established the physical-reference → SPICE → Python float → Python fixed → RTL verification hierarchy.
- Selected and versioned the Kennedy 1998 single-12AX7 passive-RIAA phono stage as the V1 circuit artifact.
- Added reproducible project structure, engineering instructions, task ledger, and local-tool bootstrap path.
- Added the AT-VM95E R/L/load model, canonical RIAA reference, Koren 12AX7 plate/grid-current equations, checked GE curve points, and deterministic mathematical regressions.
- Added an automated ngspice golden reference with DC, 10 Hz–100 kHz AC, transient, and H1–H10 level-sweep extraction.
- Added a nine-node 768 kHz backward-Euler nonlinear nodal model of the complete V1 signal circuit and SPICE/null comparison tooling.
- Added reproducible 12AX7 LUT generation, resolution/error study, bit-accurate fixed interpolation, and a synthesizable serialized SystemVerilog tube primitive.
- Added an integer-only complete V1 chord candidate with per-node Q formats,
  Q0.47 conductances, Q4.44 diagnostic KCL residuals, explicit rounding/
  saturation, fixed capacitor state, and diagnostics.
- Added four-stage 16× half-band interpolation/decimation design, reproducible
  float/Q1.23 coefficients, response/latency extraction, and a nonlinear alias
  regression.
- Added bit-accurate Q8.24 half-band sample paths with Q1.23 coefficients,
  signed MAC rounding, per-stage saturation, and fixed-chain alias verification.
- Added GitHub Actions model/RTL/generated-asset and ngspice cross-model jobs.
- Added a synthesizable nine-row V1 chord corrector, reproducible coefficient/
  vector generation, exact boundary testbench, and generic XC7 synthesis flow.
- Added bit-exact capacitor-history RHS and heterogeneous-format KCL engines,
  each verified against 1,024 generated vectors with explicit saturation counts.
- Added the complete mono V1 solver scheduler: both serialized 12AX7 evaluations,
  three chord corrections, final residual, ten capacitor-state commits, and
  request/deadline/saturation/LUT/convergence diagnostics.
- Added a 512-sample persistent-state integration regression covering silence,
  tones, multitone, noise, and ±100 mV clicks.
- Added serial-MAC Q8.24/Q1.23 half-band interpolation and decimation primitives,
  four-stage 48↔768 kHz chains, coefficient ROM generation, and exact unit/stream
  regressions with phase, overrun, and saturation diagnostics.
- Added the complete mono 48 kHz reference stream, including 16× rate conversion,
  all circuit state, saturating line-output format conversion, and aggregated
  runtime diagnostics.
- Added a settled analytical/fixed 1 kHz sweep from 0.5 mV to 5 V and a targeted
  low-level LUT-resolution study with explicit raw memory tradeoffs.
- Added floating and bit-accurate factorized Koren models using reciprocal-root,
  softplus, and power value/slope 1-D tables with cubic Hermite interpolation,
  plus a reproducible 100,000-point and five-level circuit study.
- Added a synthesizable eight-clock factorized 12AX7 primitive, reproducible
  packed ROM generation, and an exact 4,110-vector RTL regression with directed
  endpoint and out-of-range cases.
- Added an explicit factorized-tube solver mode with independent initialization,
  persistent-state vectors, metadata, regression entry point, and synthesis path.
- Added factorized mode to the complete interpolator/circuit/decimator stream,
  including independent exact output vectors, metadata, and structural synthesis.
- Added a reproducible six-frequency, cycle-counted factorized fixed-versus-
  analytical circuit sweep with gain, phase, THD, raw/mean-removed residual,
  DC difference, range, saturation, and convergence reporting.
- Added controlled overload-burst and recovery analysis against an undisturbed
  nominal trajectory, including per-triode grid-current peaks, output clipping
  asymmetry, three recovery thresholds, and solver/range diagnostics.
- Added a three-through-six-correction overload solver study with analytical
  waveform error and explicit serialized latency projections.
- Added a one-second, 768,000-sample fixed/analytical state audit with bipolar
  synthetic clicks and complete node/capacitor checkpoints.
- Added a 40-bit heterogeneous-node/Q30-history Python candidate with direct
  capacitor branch-current stamping, staged Q30/Q34/Q40 correction residuals,
  a matched one-second audit, and nominal-level legacy A/B report.
- Added bounded adaptive correction-residual scaling and a wide-state overload
  comparison with fallback, range, recovery, and convergence counters.
- Added a synthesizable 40-bit Q28/Q32 chord corrector with explicit
  Q30/Q34/Q40 residual scaling, exact randomized/boundary vectors, and a generic
  XC7 structural synthesis path.
- Added independent wide-state RHS and KCL blocks with direct Q30 capacitor
  branch stamping, bounded correction-format selection, delayed-current
  handshaking, exact vectors, and structural synthesis targets.
- Added the complete persistent wide factorized solver, exact 512-sample
  integration vectors, fallback/minimum-format diagnostics, and hierarchical
  synthesis support.
- Added a complete wide 48 kHz reference stream with explicit Q8.32-to-Q8.24
  conversion, exact end-to-end vectors, diagnostics, and synthesis target.
- Added arbitrary-vector/capture support to the wide solver regression and an
  automated 23,040-sample RTL-versus-analytical nominal audio measurement.
- Added a captured wide-solver RTL frequency regression at 100 Hz, 1 kHz,
  10 kHz, and 20 kHz with fixed equivalence, analytical gain/phase bounds, and
  zero-diagnostic acceptance checks.
- Added shared arbitrary-trajectory wide-solver vector/capture infrastructure
  and a 100 ms captured overload/recovery regression through 1.5 V peak.
- Extended the wide complete-stream testbench and runner with bounded dynamic
  vector counts, alternate vector files, and direct 48 kHz output capture.
- Extended the complete decimator bench to 131,072 custom inputs / 8,192
  captured outputs and added a captured cubic nonlinear-alias regression.
- Added a model-change guard and complete guarded wide-stream top with muted
  startup, ramp-down, frame-aligned reset, muted warmup, acknowledgment, and
  ramp-up sequencing.
- Added a four-frequency ngspice/Python transient sweep, a two-rate refinement
  study, and an explicit floating trapezoidal capacitor-companion candidate.
- Added a 100 ms floating backward-Euler/trapezoidal overload stability study
  spanning 20 mV through 1.5 V peak.
- Added an explicit bit-accurate trapezoidal circuit candidate with Q30 previous
  capacitor voltage, signed Q4.44 previous current, identical rounded KCL/state
  branch arithmetic, nominal-range instrumentation, and a gated six-frequency
  comparison against floating trapezoidal.
- Extended the controlled overload harness to select fixed trapezoidal state,
  report all capacitor-current maxima, and enforce a diagnostic-clean <=0.5 V
  acceptance region while retaining severe overload as characterization.
- Added a parameterized 48-bit-capacitor KCL mode with Q4.44 previous/next
  current ports, exact trapezoidal branch stamping, state saturation reporting,
  and an independent 1,024-vector warning-free RTL regression.
- Added a selectable persistent trapezoidal solver with a separate generated
  chord-inverse ROM, ten Q4.44 current-state registers, exact 512-sample
  integration regression, and an explicit synthesis wrapper/target.
- Added selectable trapezoidal state to the complete 48 kHz stream, an exact
  64-output/1,024-update integration regression, and an explicit full-stream
  synthesis wrapper/target.
- Extended arbitrary-length solver capture and the four-point frequency sweep
  to trapezoidal state, including all current-history words, separate artifacts,
  gated gain/phase/diagnostics, and a non-combined link to ngspice evidence.
- Added reusable composed fixed/floating complete-stream references and a
  captured four-point 48 kHz trapezoidal sweep. The regression proves 19,200
  outputs exactly, gates float error and diagnostics, and reports the measured
  51-sample converter delay separately from circuit-attributed phase.
- Added a gated 250 ms floating trapezoidal overload study with direct sustained
  recovery timing, exponential-envelope fit quality, projected-versus-measured
  labels, and complete node/capacitor difference checkpoints.
- Added parallel 850 ms floating severe-overload trajectories and a regression
  that preserves their non-monotonic cancellation/rebound. This falsifies the
  earlier one-exponential projection instead of converting it into a claim.
- Added a 384,000-update selectable-trapezoidal RTL recovery capture at the
  accepted 0.5 V boundary, with full-state exactness, zero-diagnostic gates,
  and an explicitly non-sample-identical floating recovery comparison.
- Added a dependency-free continuous-time nodal pole extractor with tube
  small-signal linearization, mode shapes, capacitor-energy participation,
  stability gates, and measured-overload interpretation.
- Added parallel seven-second severe-recovery trajectories with a bounded
  Newton-to-chord handoff, overlap/final-probe error gates, and direct sustained
  timing for every 10%, 1%, and 1 mV threshold.
- Added a standalone downstream output mute/ramp with reset-muted startup,
  sample-qualified linear transitions, symmetric signed rounding, exact-unity
  bypass, synchronous fault clamp, and a self-checking RTL regression.
- Added warning-free Verilator lint and a 4,096-vector bit-exact testbench with checked eight-clock latency.
- Added non-root ngspice/Yosys bootstrap and a generic XC7 out-of-context synthesis report.
- Added quantitative cartridge/front-end noise, ADC headroom, and analog-versus-digital RIAA partition analysis.
- Added a reproducible fixed cutoff-Jacobian bank study using integration-mode-
  specific matrices derived from the analytical second-stage trajectory and a
  previous-sample Vgk selector held across the fixed three-correction schedule.
- Added generated four-bank backward-Euler and five-bank trapezoidal chord
  assets, a sample-held selector in the wide solver, explicit synthesis
  wrappers, and a 9,216-sample-per-mode full-state RTL overload regression.
- Added a parallel 100 ms banked/DC-chord/full-Newton waveform audit at 20 mV,
  0.5 V, and 1.0 V with Q8.24 stimulus, unaligned windowed residuals, and a
  -70 dB raw burst-error gate.
- Added a bank-prefix minimization study across 0.5/1.0 V and both integration
  modes; it preserves the negative result that every current cutoff matrix is
  required for the 1.0 V residual gate.
- Added a trapezoidal shallow-bank threshold sweep from -2.50 to -2.90 V and
  selected the most-negative diagnostic-clean threshold that excludes the
  accepted 0.5 V trajectory.
- Added a 100 ms previous-Vgk-slew selector study, a reproducible
  backward-Euler shallow Jacobian, matched fixed/RTL selector history, and
  1.0/1.5 V full-state overload gates for both integration modes.
- Added a converged four-layer banked error decomposition and a 128/256/512/
  1,024-entry grid-current resolution study with direct-current, burst,
  recovery, storage, and fixed-diagnostic measurements.
- Added architecture, model, phono, fixed-point, gain, noise, analog front-end, converter/clock, hardware, controls, safety, verification, and annotated-reference documentation.

### Fixed

- Corrected the pin-level integration bench's absolute clocks. Its former
  5 ns/160 ns half-periods exercised the correct 32:1 ratio but were actually
  100/3.125 MHz, not the documented 98.304/3.072 MHz. Femtosecond-resolution
  periods now exercise the stated rates without changing exact frame/model
  results. Timestamped handshake and serial markers are regression-gated and
  record 192 BCLKs / 62.500 µs / 3.000 samples from first complete ADC frame to
  first complete valid model-output DAC frame; this is transport latency, not
  signal group delay.
- Corrected synthesis resource reporting to count mapped RAMB36E1 primitives
  and publish RAMB18-equivalent totals. Every factorized-tube hierarchy maps
  eight RAMB18E1s plus one RAMB36E1 (10 RAMB18-equivalents); earlier eight-only
  summaries omitted the 36-Kib primitive. The same audit retains flattened
  primitive flip-flop totals and distinguishes local-array expansion warnings
  from asynchronous-FIFO memory inference. RTL numerical behavior is unchanged.
- Corrected the synthesis driver's `_factorized` alias detection so the real
  `triode_12ax7_factorized` top is synthesized directly while the legacy solver
  and stream wrapper aliases still receive their parameter override.
- Widened the wide-network capacitor difference from signed 43 to 44 bits and
  its full product from 91 to 92 bits. Capacitor 6 can legally join opposite
  signed-40 Q28 node extremes and subtract a full-range Q30 history; directed
  backward-Euler and trapezoidal vectors now prevent this silent-wrap defect
  from recurring.
- Widened signed Q31 tube currents before cathode-stamp negation so the legal
  `INT32_MIN` pair produces positive `2^32` instead of wrapping in a 33-bit
  expression; both triodes now have directed boundary vectors.
- Replaced 32-bit tube-pin subtraction in the wide solver with 40-bit node
  conversion, 41-bit subtraction, and explicit signed-32 saturation. Fixed
  Python now defines the same boundary behavior, and a regression forces both
  polarities instead of permitting extreme Vgk/Vpk values to wrap.

### Reference decisions

- V1 is one mono channel using both halves of one 12AX7, 300 V B+, unbypassed 1.21 kΩ cathode resistors, and the original two-pole passive equalizer values.
- High-resolution inspection corrected the equalizer capacitor transcription to 3300 pF shunt (the source scan's decimal text is easy to misread at page scale). The failed 300 pF/series interpretations were rejected by topology inspection and RIAA regression.
- The nominal external cartridge is the Audio-Technica AT-VM95E equivalent: 485 Ω, 550 mH, 47 kΩ load, and configurable total shunt capacitance (150 pF nominal).
- The Koren 12AX7 parameter set is the first analytical and SPICE tube model. Model error against manufacturer curves is tracked separately from numerical implementation error.

### Measured

- A fourth banked correction improves burst RMS by 5.65--9.02 dB, while six
  corrections reduce maximum residual to 0.111--0.207 uA and burst error to
  2.35--2.94 mV. Final recovery error is non-monotonic. A conventional added
  serial pass projects to 145 clocks, but residual reuse produces the identical
  fourth-correction output in 127 measured backward-Euler clocks. It reduces
  1.0/1.5 V burst RMS to 4.895/6.817 mV, matches 18,432 overload states exactly,
  and synthesizes to 13,296 LC / 120 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1.
- Split the post-grid-resolution fixed error at the exact Q24/Q20 and Q31 tube
  interfaces. Integer Hermite evaluation contributes at most 0.168 mV burst RMS
  across the 1.0/1.5 V banked campaigns, while node/capacitor/chord arithmetic
  contributes 6.40--19.07 mV. Every continuous-coefficient fixed-interface run
  is diagnostic-clean, redirecting optimization away from the tube datapath.
- Added a conservative full-interface integer interval proof for wide RHS,
  backward-Euler/trapezoidal KCL, tube stamps, chord correction, and solver
  tube-pin conversion, including every banked chord matrix. All 47 checks pass;
  the tightest cases require 44/44
  capacitor-delta bits, 34/34
  cathode-sum bits, 57/63 KCL-accumulator bits, and 89/92 capacitor-product
  bits. The proof is now a default regression gate.
- Added an exact fixed-intermediate domain audit that runs the -5 V and -8 V
  plate-law acceptance bounds on identical 1.5 V overload trajectories. It
  classifies every factor coordinate, counts the separate grid-current clamp,
  and requires bit-exact audio before accepting a diagnostic-domain change.
- The initial cutoff-Jacobian bank reduces 100 ms / 1 V residual failures from
  1,122/1,107 to zero for backward-Euler/trapezoidal state at 1.887/1.874 uA
  maximum residual, with zero saturation, tube-range clips, or correction
  fallbacks. Its initial 1.5 V result left 72/67 residual failures. The
  previously reported
  4,052/4,052 range events were subsequently proven to be only the conservative
  negative-grid acceptance boundary, separate from solver convergence.
- The factorized cutoff-domain audit observes `Vgk` down to -7.027 V while
  `Vpk`, transformed coordinate, and `E1` remain within their independent
  ranges. Expanding plate-law acceptance to -8 V removes all 3,294/3,292 false
  clip evaluations while leaving both integrator outputs bit-exact. The
  grid-current lookup remains clamped below -5 V at its leakage-floor entry.
- A 20 mV/sample previous-Vgk slew qualifier is inactive and output-bit-exact
  to the prior selector through 1.0 V, but selects the severe shallow cutoff arc
  at 1.5 V. The 100 ms residual-failure counts fall from 72/67 to zero at
  1.703/1.774 uA maximum residual with zero arithmetic/range/fallback events.
- Banked integrated RTL matches every fixed state across 36,864 total updates
  at 1.0/1.5 V. Every generated bank is selected in aggregate, both 1.5 V cases
  have zero residual/range/arithmetic/fallback events, and latency remains 116
  clocks.
- Banked RTL is bit-exact across all 9,216 captured overload states per mode,
  selects every generated bank, retains 116 clocks, and records no diagnostic
  event. XC7 structural synthesis measures 13,302/13,840 logic cells for
  backward Euler/trapezoidal with 120 DSP48E1s and 8 RAMB18E1 + 1 RAMB36E1 in either mode:
  +758/+1,054 logic cells and no DSP/RAM increase over the nominal solvers.
- At 1.0 V, the bank improves raw full-Newton burst error from -53.45 to
  -76.43 dB for backward Euler and from -53.65 to -76.79 dB for trapezoidal.
  The latter retains 0.537 mV final-window mean error after 85 ms recovery;
  mean-removed error is -89.75 dB, so the unhidden slow-state offset remains an
  optimization target rather than being removed by null alignment.
- Removing the least-negative cutoff matrix leaves 289 backward-Euler or 119
  trapezoidal 1.0 V residual failures. Coefficient-bank reduction is rejected;
  later selector work must retain all matrices or provide stronger evidence.
- Tightening the shallow trapezoidal threshold from -2.50 to -2.75 V eliminates
  all 231 bank activations in the 0.5 V campaign while retaining 154 necessary
  1.0 V activations and zero residual failures. It halves the measured 1.0 V
  final-window mean error from 1.042 to 0.537 mV; -2.80 V is rejected because
  it leaves two residual failures.
- At 1.5 V, the slew-qualified selector slightly improves the raw full-Newton
  burst error to -61.80/-62.12 dB but retains 18.26/17.36 mV final-window RMS
  error. This severe waveform discrepancy remains separate from the closed
  fixed-schedule residual gate.
- The 128-entry linear grid-current table, not the factorized plate law,
  dominated the former 1.5 V error. The implemented 1,024-entry branch reduces
  exact fixed-mapping worst error from 716 to 12.55 nA, raw burst error to
  -72.87/-81.77 dB, and final-window circuit error from 18.27/17.36 to
  0.631/0.321 mV for backward Euler/trapezoidal. All fixed diagnostics remain
  zero and integrated RTL is full-state exact.

- ngspice bias is 179.994 V/0.9918 mA for stage 1 and 192.808 V/1.0719 mA for stage 2; circuit gain is 41.087 dB at 1 kHz.
- The physical passive network's ideal-RIAA error is -0.919 to +0.000 dB over 20 Hz–20 kHz (0.364 dB RMS), retained as reference behavior.
- The 768 kHz float model is -53.10 dB normalized residual from the 5 mV-peak/1 kHz ngspice transient, with 0.00179 dB gain error and no nonconvergence.
- Two solver passes satisfy the 100 pA residual target for every sample in the 20 mV-peak/1 kHz characterization; a one-pass output is close but does not satisfy the residual criterion.
- Raw tube-current fixed-point iteration was rejected after missing the residual
  criterion even at 12 relaxed passes. Three-pass constant quiescent-Jacobian
  chord iteration converges every multitone sample and is -137.28 dB normalized
  output residual from full Newton; it is the fixed-point hardware candidate.
- The 128 × 256 LUT has 0.139 µA mean and 9.33 µA worst full-range absolute error in 100,000 random points.
- XC7 structural synthesis reports 16 DSP48E1, 47 RAMB18E1, and 414 estimated logic cells; no Fmax is claimed without named-part place-and-route.
- The flat 26 dB Architecture A study gives -28.0 dBFS for a 4 mV nominal cartridge and about 0.656 µV RMS combined RIAA-weighted input noise under stated assumptions.
- The complete fixed candidate is -57.87 dB normalized residual from analytical
  float on the initial settled multitone. Tube-LUT error is -56.14 dB, while the
  isolated fixed-state/chord layer is -70.33 dB; no saturation or LUT clips occur.
- Half-band image rejection is at least 91.6 dB per stage; the cubic 45 kHz
  harmonic aliases to 3 kHz at -144.34 dB with float and -137.91 dB with Q1.23
  coefficients/float MACs. The complete fixed MAC chain measures -137.81 dB
  with zero saturation in the test.
- The chord corrector passes 1,024 bit-exact vectors at ten-clock latency,
  including 18 saturation cases. XC7 synthesis reports 9 DSP48E1, no block RAM,
  and 1,109 estimated logic cells with no structural check errors.
- The complete mono RTL matches all fixed-model nodes, capacitor histories,
  output, residual, and diagnostics for 512 sequential samples. Scheduling takes
  126 clocks, leaving two clocks at the 98.304 MHz/768 kHz target.
- Complete hierarchical XC7 synthesis reports 8,024 estimated logic cells,
  89 DSP48E1s, and 47 RAMB18E1s. Structural checks pass; Fmax is not claimed.
- The complete half-band chains match 2,048 interpolation and 128 decimation
  outputs exactly with zero diagnostics. Interpolation uses 2,053 estimated XC7
  logic cells / 16 DSP48E1s and decimation 3,002 / 32 DSP48E1s.
- The end-to-end RTL matches 64 consecutive fixed-model outputs spanning 1,024
  nonlinear updates exactly, with zero saturation, overrun, phase, LUT, deadline,
  or convergence events. Synthesis reports 13,170 estimated XC7 logic cells,
  137 DSP48E1s, and 47 RAMB18E1s; Fmax remains unmeasured.
- Fixed and analytical models agree closely at 0.5 V (2.2395% versus 2.2417%
  THD, -55.98 dB waveform residual), but fixed low-level THD at 5 mV is 0.0733%
  versus 0.0191% analytical. Doubling either LUT axis does not resolve it.
- The fixed residual limit first fails at 1.0 V peak and LUT clipping begins at
  1.1 V; first tested ≥1 dB fixed gain compression is 1.1 V.
- The fixed factorized candidate uses 262,144 raw table bits including grid
  current (14.22 raw RAMB18 equivalents). Its 100,000-point plate error is
  8.31 nA mean, 14.11 nA RMS, and 50.56 nA worst at quantized inputs; the dense
  grid-current probe measures 12.55 nA worst and 2.82 nA active-region RMS.
- At 5 mV/1 kHz, factorized fixed THD is 0.0188% versus 0.0191% analytical with
  +0.00026 dB fundamental gain error. At 0.5 V it is 2.2419% versus 2.2417%.
  The unaligned 5 mV waveform residual remains -42.90 dB and is tracked
  separately; the 1.0 V fixed solve still exceeds its residual limit.
- The standalone factorized RTL is bit-exact to fixed Python for all 4,110 test
  vectors. XC7 structural synthesis reports 1,496 estimated logic cells,
  35 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1; no Fmax is claimed.
- The complete factorized solver is bit-exact for 512 sequential samples and
  retains the 126-clock schedule with no diagnostic events. Its hierarchy uses
  9,148 estimated logic cells, 108 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1 versus the 2-D
  solver's 8,024 / 89 / 47; this is a measured resource trade, not a free win.
- The complete factorized stream matches 64 outputs spanning 1,024 nonlinear
  updates with zero diagnostics. It synthesizes to 14,290 estimated logic cells,
  156 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1 versus the surface stream's 13,170 / 137 / 47.
- Decomposed the 5 mV factorized fixed null: -42.90 dB raw, -59.63 dB after
  reporting (not correcting) its -2.840 mV mean difference, with 0.00958°
  fundamental phase error. This prevents the DC/state discrepancy from being
  misidentified as low-level harmonic error.
- Across 20 Hz, 50 Hz, 100 Hz, 1 kHz, 10 kHz, and 20 kHz at 5 mV peak, the
  factorized fixed model stays within 0.00846 dB fundamental gain and 0.0729°
  phase of analytical float with zero residual-limit, saturation, or range events.
- A 20 mV, 5 ms burst has zero fixed diagnostics and reaches 10% / 1% nominal
  recovery thresholds in 8.67 / 24.6 ms. A 1.0 V burst has 1,134 residual-limit
  failures; a 1.5 V burst produces 26.3 µA stage-two grid current, 1,698 residual
  failures, and 4,046 transformed-domain clips. Recovery ≥0.5 V exceeds 35 ms.
- At 1.0 V, three-to-six chord corrections reduce maximum residual from 6.93 to
  2.31 µA and failures from 942 to 30, but project 126 to 213 clocks. At 1.5 V,
  six corrections still leave 5.83 µA and 960 failures.
- The state audit exposes a Q12.20 history deadband: fixed output holds
  +35.655 mV between clicks and -5.368 mV in the final 100 ms while analytical
  output is about 7.2 uV RMS. Final output/coupling-capacitor errors are 5.373 /
  5.299 mV despite zero diagnostics, so the current state contract is rejected
  for long recovery rather than presented as accepted RTL accuracy.
- On the identical audit, the wide-state candidate reduces late raw residual
  to 38.74 uV RMS and maximum KCL residual to 5.01 nA with zero diagnostics.
  At 5 mV/1 kHz its raw null is -63.83 dB, mean-removed null -88.43 dB, gain
  error -0.000058 dB, phase error -0.000187 degrees, and THD 0.01937% versus
  0.01906% analytical. No RTL or synthesis equivalence is claimed yet.
- Across six 5 mV frequencies from 20 Hz to 20 kHz, wide-state gain and phase
  error remain within 0.000196 dB and 0.000982 degrees with no diagnostic
  events. Raw null ranges from -95.26 dB at 20 Hz to -44.75 dB at 20 kHz.
- At 20 mV the wide candidate reaches 1% recovery in 14.918 ms versus 24.612 ms
  legacy and cuts post-burst residual from 5.80 to 0.258 mV RMS. Adaptive scale
  removes all 1.5 V operand saturations using 729 fallbacks, but 1.0/1.5 V still
  have 1,122/1,695 residual failures and 1.5 V keeps 4,046 tube-range clips.
- The wide chord RTL matches 1,024 fixed vectors, including 95 output-saturation
  vectors, at ten clocks. Constraining runtime scaling to Q30/Q34/Q40 reduces
  generic XC7 synthesis from a rejected 5,531-cell arbitrary-shift experiment
  to 1,701 logic cells, 9 DSP48E1s, and no block RAM.
- Wide RHS/KCL RTL each match 1,024 fixed vectors at 2/10 clocks. KCL testing
  includes 48 scale fallbacks, 18 true overflows, and tube-current delays through
  11 clocks. Width-bound synthesis reports 31 LC / 4 DSP for RHS and 8,034 LC /
  72 DSP for KCL; the pre-bound KCL's 99-DSP result was rejected.
- The integrated wide solver matches every node, capacitor history, output,
  residual, and diagnostic across 512 sequential samples. Measured latency is
  116 clocks with zero test events. XC7 structural synthesis reports 12,544
  logic cells, 120 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1.
- The complete wide stream matches 64 outputs spanning 1,024 nonlinear updates
  exactly with zero diagnostics. Structural synthesis reports 17,492 logic
  cells, 168 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1; mono fits the A7-100T, naive stereo does
  not fit its 240-DSP budget.
- Captured wide solver RTL is Q32-exact to fixed Python for 23,040 samples at
  5 mV/1 kHz. Versus analytical float it measures -0.000054 dB gain error,
  -0.000187 degree phase error, 0.019371% THD, and -63.834 dB raw residual.
- Across captured 5 mV RTL output at 100 Hz, 1 kHz, 10 kHz, and 20 kHz,
  maximum gain/phase error versus analytical float is 0.0001943 dB /
  0.0009814 degrees. Every output is Q32-exact to fixed Python and no runtime
  diagnostic fires.
- The captured 5 mV control and four overload records match fixed Python at all
  state and diagnostic outputs for 384,000 updates. The 20 mV case recovers
  below 10% / 1% nominal RMS in 8.466 / 14.918 ms; 0.5 V and above remain over
  10% after 85 ms in both analytical and captured trajectories. Residual-limit
  failures begin at 1.0 V; 1.5 V records 4,046 range clips and 729 adaptive-scale
  fallbacks with zero arithmetic saturation.
- The captured 16× decimator matches all 8,192 fixed outputs for the cubic
  15 kHz stimulus and measures the 45 kHz to 3 kHz alias at -137.814 dBc with
  zero saturation. A full-stream 0.5 V / 15 kHz stress run is also exact, but
  contains a 1.402 mV finite-window 3 kHz projection before decimation; the
  later phase-coherent family decomposition supersedes this initially
  unresolved raw-bin observation.
- The guarded stream passes a warning-free reset transaction regression: core
  reset follows zero gain, warmup output remains muted, the 48 kHz phase counter
  stays aligned, one acknowledgment fires, and unity gain returns. Structural
  synthesis reports 17,562 logic cells, 170 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1.
- At 768 kHz, backward-Euler gain/phase error versus ngspice reaches -0.0646 dB /
  +4.72 degrees at 20 kHz. Quadrupling rate leaves +1.235 degrees. The floating
  trapezoidal candidate measures -0.00846 dB / +0.0582 degrees at 20 kHz and
  +0.00581 dB / +0.0390 degrees at 10 kHz, with no failed solves.
- Trapezoidal Newton solves remain finite and convergent through 1.5 V / 26.4 uA
  grid current. At 20 mV, recovery thresholds match backward Euler within
  2.6 us; both methods preserve overload memory beyond 85 ms above 0.5 V.
- Fixed trapezoidal gain/phase error against its floating counterpart is at most
  0.000131 dB / 0.000784 degrees across six 5 mV points from 20 Hz to 20 kHz.
  No convergence, saturation, range, or correction-fallback diagnostics occur;
  maximum observed nominal capacitor history current is 2.25 uA.
- Fixed trapezoidal remains diagnostic-clean through 0.5 V peak; 1.0/1.5 V
  retain 1,107/1,690 convergence failures and 1.5 V retains 4,048 tube-domain
  clips. Capacitor history current peaks at 203.34 uA without saturation. The
  0.72192 S output-coupling companion requires signed 48-bit Q0.47 versus the
  existing backward-Euler KCL's 47-bit coefficient.
- Trapezoidal solver RTL matches fixed Python at all nine node, ten voltage-
  history, and ten current-history states for 512 samples at 116 clocks.
  Structural synthesis is 12,786 logic cells, 120 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1,
  adding 104 cells but no DSP/BRAM versus backward Euler; no Fmax is claimed.
- The complete trapezoidal stream is bit-exact with zero diagnostics and a
  5.02 nA maximum residual. Structural synthesis is 17,735 logic cells,
  168 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1, adding 243 cells but no DSP/BRAM.
- Captured trapezoidal RTL at 100 Hz/1/10/20 kHz is state-exact to fixed and
  remains within 0.000128 dB / 0.000784 degrees of floating trapezoidal with
  zero diagnostics. The separate float/SPICE layer remains within 0.00846 dB /
  0.0582 degrees at the measured 10/20 kHz points.
- The output mute/ramp passes its warning-free directed Verilator regression;
  generic XC7 synthesis reports 171 estimated logic cells, 2 DSP48E1s, no block
  RAM, and no structural check errors. No placed timing is claimed.

### Changed

- Inserted the existing non-reference output mute/ramp between the selected
  accuracy-first virtual circuit and DAC calibration. Reset starts at zero gain;
  exact unity bypass preserves reference samples bit-for-bit, and force mute
  synchronously clears the ramp state. Eight-sample integration regressions
  reach unity before the first nonzero fixture output and retain all 64 raw
  model/PCM comparisons. With the later calibration guard, the muted
  fabric/pin hierarchies measure 20,489/21,014 LC, 15,592/16,907 FF, and 232
  DSP48E1s. Queued CDC frames still require physical analog muting for immediate
  fault response.
- Increased the factorized grid-current table from 128 to 1,024 entries after a
  gated resolution sweep. This is an FPGA approximation change only: the Koren
  equation and frozen physical circuit are unchanged. Added dense exact-mapping
  regression limits and refreshed every affected hierarchy's resource report.
- Split factorized-tube cutoff handling into a -8 V plate-law acceptance bound
  and the unchanged -5 V grid-current lookup clamp. This changes only range
  diagnostics on the audited overload trajectory; fixed current, audio, and RTL
  schedule remain bit-exact.
- Reused a single interpolation multiply datapath in RTL, reducing generic XC7 synthesis from 24 to 16 DSP48E1 blocks while retaining bit-exact output and eight-clock latency.
- Reduced each chord-correction multiply from Q17.15 × Q4.44 to DSP-native
  Q17.1 × signed 25-bit Q30. It is -83.63 dB residual from the high-precision
  correction on the initial multitone with 0.492 mV worst output difference.
- Overlapped KCL matrix evaluation with tube lookup and launched completed RHS/
  chord results without scheduler bubbles, reducing mono latency from 130 to
  126 clocks and meeting the 128-clock simulation deadline.
- Time-multiplexed the three mutually exclusive Hermite interpolations through
  one arithmetic datapath, reducing factorized-tube synthesis from 65 to 37
  DSP48E1s while preserving exact output and eight-clock latency.
- Saturated capacitor-history commits to their declared state width in fixed
  Python and wide RTL; all existing characterized vectors remain in range.
