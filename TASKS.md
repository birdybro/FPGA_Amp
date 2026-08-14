# Engineering task ledger

Last updated: 2026-08-14

## Current milestone

Close the measured factorized fixed/analytical DC-state and severe-overload
solver gaps, reproduce waveform metrics from captured integrated RTL, and
harden the 48/768 kHz stream boundary. The circuit remains frozen at version
0.1.0; safety processing remains explicitly outside it.

## Active, highest value first

- [ ] Isolate and reduce the remaining fixed circuit/state/chord error. With
  the implemented 1,024-point grid branch, raw final-window error is now
  0.372/0.291 mV at 1.0 V and 0.631/0.321 mV at 1.5 V for backward Euler/
  trapezoidal. A continuous-coefficient fixed-interface A/B bounds integer tube
  evaluation to <=0.168 mV burst RMS and identifies circuit/state/chord as the
  6.40--19.07 mV dominant burst layer. The implemented terminal correction
  cuts 1.0/1.5 V burst RMS to 4.895/6.817 mV for backward Euler and
  4.709/3.604 mV for trapezoidal at 127 clocks. Held-bank reselection,
  rational terminal relaxation, full dual-triode operating points, and
  stage-one-split banks all fail cross-level/recovery acceptance. Further
  contraction now requires a different solver formulation or additional
  schedule margin; do not tune the frozen circuit or accept a one-level fit.
- [ ] Prove 98.304 MHz named-part timing for the 127-clock trapezoidal terminal
  stream. Generic synthesis fits XC7A100T structurally at 20,241 LC / 222 of
  240 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1, but the parallel terminal-current path and one-clock
  sample margin require the open Yosys/nextpnr-Himbaechel place/route flow
  before hardware selection. Project X-Ray contains the exact
  `xc7a100tcsg324-1` part, but the current experimental backend uses a single
  `DEFAULT` timing grade, so routing evidence and qualified -1 speed-grade
  signoff must remain distinct. The first full-solver harness packs at 50,789
  `SLICE_LUTX` / 174 DSP and reaches only 13.90 MHz after placement. A
  value-only tube substitution places at 13.67 MHz, falsifying the hypothesis
  that Hermite is the dominant whole-solver limiter. A standalone bit-exact
  iterative Hermite replacement now
  closes post-route at 132.54 MHz with two DSPs and three-clock latency, but
  inserting that latency into all three dependent tube functions would exceed
  the current 127-clock solver budget. The separately named value-only linear
  candidate instead retains eight clocks: 100,000-point error is 47.49 nA
  worst, tube and complete terminal solver RTL are bit-exact, and the isolated
  tube routes at 113.24 MHz. Its full harness packs at 49,530 `SLICE_LUTX`, 166
  DSP, 13 RAMB18E1, and 5 RAMB36E1. The isolated 54-DSP terminal-current block
  improves from 51.95 to 88.83 MHz when its exact overflow count is balanced,
  but still misses 98.304 MHz. Isolated chord routes at 46.40 MHz and isolated
  KCL routes at 16.64 MHz, with KCL's accumulator-to-global-fallback cone
  matching the whole-solver failure. A bit-exact residual staging register and
  balanced KCL reductions retain the 127-clock integrated contract and improve
  KCL placement to 33.92 MHz. Parallel evaluation of the two physical tube
  sections is bit-exact at 84/95 clocks and fits structurally at 209/240 DSPs.
  The recovered margin now funds two KCL column-fill clocks, two KCL finish
  clocks, and two chord-apply clocks per pass: the complete solver is exact at
  119 clocks and the chord route closes at 100.92 MHz. A legal 42.07 MHz KCL
  route instead identified the exact maximum diagnostic as the limiter.
  Accumulator and final-only maximum pipelines plus exact sign-extension fit
  tests now produce a bit-exact 126-clock complete schedule and raise the
  isolated KCL to 92.23 MHz post-route. Close the remaining 6.6% KCL gap and
  resolve the full-hierarchy congestion: the 14,990-LC design packs to 59,027
  slice LUT elements / 209 DSPs but places at only 34.20 MHz. Region analysis
  shows KCL and terminal-current spanning nearly all DSP rows while the two
  tube engines and chord occupy separated hard-block regions. The same netlist
  uses only 209/740 DSPs on XC7A200T, but seed/default placement reaches 23.83
  MHz, a second seed reaches 30.55 MHz, and timing-weight-20 reaches only 35.22
  MHz. Capacity alone is therefore rejected as the fix. A selectable two-batch
  terminal-current schedule now proves 1,027 standalone and 512 integrated
  vectors exact at 127 clocks, cuts DSP use from 209 to 189, and routes its
  isolated block at 90.50 MHz with the default weight and 99.59 MHz with timing
  weight 20, closing that block's constraint. The complete hierarchy
  nevertheless places at only 25.02 MHz with 59,514 LUTX / 14,590 FFX, worse
  than baseline. Timing weight 20 raises the complete candidate only to 32.56
  MHz and disperses its 34 terminal DSPs across a 91-by-167 coordinate region;
  it remains slower than the selected baseline's 34.20 MHz. Resource sharing
  in one block and placer-weight tuning are therefore both insufficient. An
  overlapping hierarchy floorplan improves the candidate to 36.83 MHz by
  reserving left/center DSP columns for KCL/RHS and center/right columns for
  nonlinear blocks, but still misses by 2.67x. Develop a broader cross-block
  time-multiplexed schedule; only one clock remains in this candidate, so do
  not add a per-pass stage or alter the frozen numerical contract.
## Completed this milestone

- [x] Implement and measure two-batch terminal-current resource sharing. Use
  fixed lane-pair muxes to avoid synthesis-created variable-index trees, pass
  1,027 exact block vectors and 512 complete stateful vectors, and retain the
  exact 127-clock deadline. Measure 34 rather than 54 isolated DSPs, 90.50 MHz
  with the default placement weight, and 99.59 MHz with timing weight 20. Then
  measure the complete 189-DSP hierarchy at only 25.02 MHz placement. Keep the
  implementation selectable and reject it as the default full-solver timing
  fix rather than reporting an isolated-only resource/timing win.

- [x] Preserve open-XC7 tuning experiments with validated, filesystem-safe run
  tags. Reproduce the isolated timing-weight-20 closure in its own artifact
  directory, then place the complete shared-terminal solver at the same weight.
  Measure only 32.56 MHz versus the 98.304 MHz target and retain the default
  25.02 MHz evidence separately.

- [x] Add and measure a nextpnr pre-place hierarchy floorplan. Reject a strict
  76-of-80-DSP left partition after it fails to complete a first heap iteration;
  retain overlapping two-column regions with 80 sites of slack per group.
  Measure 36.83 MHz, 13.1% above the unconstrained weight-20 candidate but still
  2.67x short, and skip routing.

- [x] Extend the pinned nextpnr-Himbaechel bootstrap and device-qualified runner
  to XC7A200T, add a Nexys Video timing-only harness, and place the unchanged
  complete solver. Measure 28% DSP and 21% packed-LUT occupancy, then test two
  seeds and a doubled heap timing weight. The best 35.22 MHz estimate remains
  2.79x short, so skip routing and reject larger-device capacity alone rather
  than claiming the 209/740-DSP fit solves timing.

- [x] Add a placement-only open-XC7 stage that emits separate placed netlist,
  log, report, and summary artifacts without claiming routing. Add a flattened
  placed-JSON hierarchy analyzer. Reproduce the complete 126-clock candidate at
  34.20 MHz placement with 59,027 LUTX / 13,458 FFX / 4,036 CARRY4 / 209 DSP /
  20 RAMB18 equivalents, then stop before routing because the miss is 2.87x.
  Quantify the KCL/terminal/tube/chord hard-block dispersion instead of
  extrapolating the isolated 92.23 MHz KCL result.

- [x] Use legal route evidence to pipeline the KCL accumulator and only the
  consumed final maximum-residual diagnostic. Preserve 1,024 vectors in each
  integration mode and 512 complete stateful vectors, including all 48 format
  fallbacks and 18 correction saturations. Replace generic signed-25 bounds
  compares with the exact sign-extension predicate; improve isolated KCL
  post-route timing from 42.07 through 64.90/72.31 to 92.23 MHz. Measure the
  complete exact schedule at 126 clocks and 14,990 LC / 13,458 FF / 209 DSP /
  20 RAMB18 equivalents without claiming full-hierarchy closure.

- [x] Add selectable bit-exact timing boundaries to the KCL column/finish and
  chord apply paths. Preserve 1,024 vectors in each KCL integration mode, 1,024
  chord vectors, the unchanged default latencies, and 512 complete stateful
  terminal vectors. Measure the combined schedule at 119 clocks, the chord at
  100.92 MHz post-route, and the KCL at only 38.95 MHz after placement. Record
  the remaining KCL miss instead of claiming whole-solver closure.

- [x] Add a selectable parallel dual-triode schedule without changing either
  physical operating point or arithmetic. Preserve 512-vector backward-Euler
  and complete trapezoidal/banked/terminal state and diagnostics exactly;
  reduce measured latency from 116/127 to 84/95 clocks. Add a named open-flow
  harness and measure 15,887 LC / 7,360 FF / 209 DSP / 20 RAMB18-equivalents,
  leaving 31 DSPs and 33 clocks per internal sample for timing work.
- [x] Isolate the actual network timing hierarchy. Measure chord correction at
  46.40 MHz and the original KCL engine at 16.64 MHz post-route. Capture
  capacitor 9 early, stage the final residual in the existing second-tube wait
  window, and balance cross-row fit/max/saturation reductions. Preserve 1,024
  backward-Euler, 1,024 trapezoidal, and 512 terminal-solver exact vectors;
  retain 127 integrated clocks while improving KCL placement to 33.92 MHz.
- [x] Factor the ten terminal trapezoidal current recomputations into a
  bit-exact timing unit, preserve both 512-vector solver regressions at 116/127
  clocks, and add named-part terminal/KCL/chord harnesses. Measure 54 DSPs and
  51.95 MHz for the original serial overflow count, replace it with an exact
  balanced popcount, and improve isolated post-route timing to 88.83 MHz.

- [x] Implement and independently label the value-only factorized timing
  candidate. Reproduce its 1,024/8,192/4,096 tables; measure 47.49 nA worst
  static current error; pass 4,110 tube, 512 wide-solver, and 512 complete
  terminal-solver vectors at unchanged latency; compare five circuit levels
  against Hermite and analytical full Newton; route the isolated tube at
  113.24 MHz. Do not promote it until the complete route is measured.
- [x] Break the three-dependent-multiply cubic-Hermite path into a reusable,
  bit-exact iterative kernel. Verify 4,096 full-range vectors, reset, and a
  start-while-busy transition; preserve all 4,110 factorized-tube vectors;
  measure 265 LC / 2 DSP structurally and 132.54 MHz after named-part routing.
  Keep its experimental `DEFAULT` timing grade and unintegrated cycle cost
  explicit.
- [x] Bound the oversampled SPI transport under arbitrary asynchronous raw-pin,
  response, and clear activity. Prove 11 synchronizer, bit-count, request,
  response-state, saturating-frame-count, frame-reset, and sticky-precedence
  properties through 32 fabric clocks; separately reach request decode,
  short-frame, and response-underflow paths in 100 steps. Keep the eight-frame
  directed integration as byte-order/full-frame evidence and do not claim
  unbounded induction or a placed SCLK limit.
- [x] Exhaustively prove converter-boundary arithmetic/control safety. Cover
  the valid positive input-coefficient range before the explicit signed-32
  cast, exact registered valid/output/hold behavior, output PCM endpoint
  saturation, and both saturating counters/sticky-clear transitions in 12
  assertions under arbitrary full-width samples and coefficients. Close Yosys
  SAT temporal induction at depth 2 and reach endpoint, saturation, and both
  invalid-configuration paths without replacing the Python bit-exact vectors.
- [x] Bound the asynchronous BCLK-rate monitor that drives the modern
  fail-closed mute guard. In a reduced four-clock/two-window instance, prove 16
  exact BCLK binary/Gray, synchronizer, window, delta, lock/drop, saturation,
  and sticky-clear properties for every 32-step arbitrary-clock interleaving.
  Reach lock followed by a retained bad-rate state in 48 steps. Keep physical
  clock accuracy, synchronizer placement/metastability, stopped-clock liveness,
  and the production 1,024-edge ratio as separately verified claims.
- [x] Bound the low-rate diagnostic-clear toggle CDC under arbitrary clock
  levels and a protocol assumption that the preceding event is observed before
  another launches. Prove ten exact pipeline, pulse-width, outstanding-event,
  no-fabrication, and accounting properties through 40 global steps; reach two
  delivered events. Add directed evidence that destination reset with an odd
  retained source toggle replays the idempotent command, and document that this
  primitive is not a reset-independent or arbitrary-rate event channel.
- [x] Bound the coherent held-bus CDC snapshot under arbitrary source and
  destination clock levels after disciplined shared startup reset. Prove nine
  capture provenance, hold stability, exact-data, valid-pulse, accounting, and
  idle properties through 40 global steps, then find a nonzero complete-transfer
  witness. Keep the result explicitly bounded and retain the directed
  destination-reset-during-request RTL test because mid-transaction reset is
  outside the formal environment.
- [x] Formally prove deterministic frame scheduling under arbitrary source
  validity/data and diagnostic clear. Use nine assertions for phase wrap,
  ready/valid/present launch strobes, accepted data, zero fill, and the exact
  saturating 32-bit underflow transition. Close Yosys 0.66 SAT temporal
  induction at depth 2 and reach an absent boundary followed by a present one.
- [x] Formally prove the atomic converter-calibration guard. Under arbitrary
  candidates, valid, mute, and clear inputs after reset, require exact
  acknowledge, simultaneous pair commit, rejection immutability, sticky
  accumulation, and clear precedence in 12 assertions. Close Yosys 0.66 SAT
  temporal induction at depth 2 and find one invalid-reject/commit/unsafe-reject
  witness. This covers the guard, not the upstream host transport.
- [x] Add a sound bounded multi-clock formal environment around the asynchronous
  FIFO. After a shared reset asserted on local edges and released while clocks
  are low, leave both clock levels and all controls arbitrary. Prove 13 Gray,
  blocked-pointer, occupancy/watermark, valid, and sticky-fault properties for
  every 32-step interleaving; separately reach depth four and both illegal-side
  stickies in 24 steps. Keep unbounded induction explicitly open because the
  current invariant set does not close it.
- [x] Formally verify the single-clock modern output mute/ramp control contract.
  With arbitrary post-reset data and controls, prove 15 reset, force-clamp,
  valid, hold, exact gain-transition, endpoint, monotonicity, and status
  assertions by Yosys 0.66 SAT temporal induction at depth 2. Separately find a
  non-vacuous witness reaching unity gain after four accepted samples. Package
  both checks as `make formal-mute`; the result does not claim CDC or analog
  speaker-safety coverage.
- [x] Integrate coherent I²S-domain FIFO diagnostics into the atomic register
  snapshot. Delay image/sequence commit until the held-bus CDC returns, expose
  busy/available status, pack RX/TX level and high-water nibbles at `0x35`, and
  make a 131,072-clock timeout retain the old image/sequence with sticky
  evidence. Prove normal capture, busy rejection, stopped-BCLK timeout,
  recovery/re-arm, timeout snapshot, and explicit clear; update the host client
  to poll completion and reject stale sequence results. Bump the compatible ABI
  minor to 1.1. Current structural synthesis is 354 LC / 735 FF for the register
  bank, 21,466 LC / 17,922 FF for the controlled hierarchy, and 21,589 LC /
  18,094 FF with SPI; the complete variants retain 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1 and zero structural-check problems.
- [x] Implement the held-bus CDC primitive needed for coherent I²S-domain
  occupancy snapshots. Use a four-phase request/acknowledge protocol, hold all
  16 bits through two synchronizer stages plus a settling clock, re-arm safely,
  and survive destination reset during an active request. Prove three exact
  captures warning-free and synthesize to 5 LC / 75 FF / no DSP or RAM. The
  register transaction integration is recorded above.
- [x] Define the host-side SPI/register ABI in dependency-free Python. Encode
  exact ten-byte full-duplex frames, validate identity/version/capabilities and
  response status, require explicit mute ownership for snapshot/clear commands,
  and guard calibration commit/poll/sequence checks. Cover exact wire bytes,
  malformed/error responses, accepted/rejected calibration, and invalid host
  preconditions with six deterministic tests. A physical adapter backend remains
  a board task rather than part of the protocol contract.
- [x] Convert the measured BCLK-rate status into a fail-closed modern output
  policy at the register-controlled wrapper. Hold the immediate mute through
  three-window startup qualification, reassert it on stopped BCLK, retain it
  through clock reacquisition, snapshot the evidence, and release only after an
  explicit host clear reaches both fabric and I²S domains. Keep model scheduling
  active so startup qualification cannot overflow the receive FIFO. Updated
  later structural synthesis is 21,466 LC / 17,922 FF for the controlled
  hierarchy and 21,589 LC / 18,094 FF with SPI, both retaining 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1 and zero structural-check problems.
- [x] Compose the SPI transport, fabric register bank, guarded calibration, and
  pin-facing I²S/model hierarchy. Prove 15 complete 5 MHz frames through the
  actual stack, including startup commit/readback, retained and refreshed
  force-mute snapshots, a snapshotted short-frame fault and transport count,
  and exactly one diagnostic clear in the unrelated BCLK domain. Synthesize the
  flattened hierarchy to
  21,506 LC / 17,959 FF / 232 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1 with zero
  structural-check problems; placed timing and a physical host backend remain
  open.
- [x] Implement an oversampled SPI mode-0 transport for the fabric register bus
  without a derived clock. Prove eight 80-bit transactions through the real
  register/calibration guard at 5 MHz, including identity read, calibration
  writes/commit/readback, bus-error status, short frame, withheld response,
  diagnostic clear, and saturating completion count. Synthesize warning-free to
  112 LC / 172 FF / no DSP or RAM. The complete composition is recorded above.
- [x] Integrate the fabric register bank around the pin-facing mono hierarchy.
  Freeze 20 fabric-coherent diagnostic words, synchronize four sticky I²S
  faults, transfer diagnostic clear by one toggle event, and own calibration/
  mute through the bus. Prove retained snapshots, startup calibration, and one
  I²S clear pulse across unrelated clocks; synthesize the crossing to 1 LC /
  5 FF and the complete wrapper to 21,363 LC / 17,755 FF / 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1. No Fmax is claimed.
- [x] Implement a protocol-neutral fabric control register bank with reset-muted
  state, a coherent calibration shadow/commit transaction, distinct attempted
  and accepted sequences, retained rejection/bus errors, pulsed diagnostics
  clear, and atomic diagnostic snapshots. Prove accepted, invalid, unsafe,
  busy-write, bad-address, and snapshot-retention behavior warning-free;
  synthesize to 323 LC / 715 FF / no DSP or RAM. Pin and SPI integration are
  recorded above.
- [x] Test three schedule-neutral refinements to the remaining trapezoidal
  terminal error. Preserve exact negative results showing that within-sample
  bank reselection worsens 1.5 V/recovery, 5/4 residual relaxation improves
  burst error but displaces recovery state, and full dual-triode/stage-one-
  split Jacobian banks either fail cross-level validation or create 58
  residual-limit misses. Retain the production coefficients and schedule.

- [x] Implement and integrate a Gray-counter BCLK/fabric rate monitor. Require
  three consecutive 1,024 ± 1 edge windows for lock, drop lock and latch a bad
  window, reacquire after correction, clear retained evidence, detect a stopped
  BCLK as zero edges, and revoke live state on BCLK reset. The actual-rate pin
  test measures 1,024 edges across four
  windows without changing audio/latency. Synthesize standalone to 68 LC / 125
  FF and the updated pin top to 21,014 LC / 16,907 FF / 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1.
- [x] Add conservative local-domain occupancy and retained high-water
  diagnostics to both sides of each asynchronous FIFO. Reach exact depth eight,
  drain to zero, clear watermarks, and preserve the 128-word wrap test. At the
  bridge, backpressure records RX 3/3 and TX 4/4 frames without loss; at the
  locked pin-level rate all four views peak at one frame without changing audio
  or latency. Updated synthesis is FIFO 127 LC / 331 FF, bridge 571 LC / 1,547
  FF, and the later clock-monitored pin top 21,014 LC / 16,907 FF; no DSP/RAM
  change from diagnostics.
- [x] Correct the pin-level integration clocks from the accidentally ratio-only
  100/3.125 MHz test to the stated 98.304/3.072 MHz rates. Timestamp internal
  handshakes and serial boundaries; gate the deterministic intervals and record
  192 BCLK / 62.500 us / 3.000 sample periods from the first complete ADC frame
  to the first complete valid model-output DAC frame. Keep this transport result
  separate from resampler/circuit and physical-converter group delay.
- [x] Compose the I²S/CDC bridge with the calibrated accuracy-first mono
  adapter. Under exactly frequency-locked 3.072/98.304 MHz clocks with unrelated
  phase, deliver all 64 serial stereo inputs to calibrated model state exactly,
  match all raw model outputs, and recover 45 consecutive observable DAC frames
  as exact mono duplicates. Retain expected startup starvation and zero all
  other diagnostics; atomically commit the startup converter-scaling pair while
  muted and reject a later live pair without changing active values; synthesize
  the later clock-monitored top to 21,014 LC / 16,907 FF /
  232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1 with no placed CDC/I/O/converter claim.
- [x] Add a protocol-neutral atomic calibration commit guard. Reset both active
  Q8.24 coefficients inactive, accept a positive pair only while fully muted,
  acknowledge the pair together, and preserve active values on invalid or live
  attempts with separate sticky diagnostics. Pass warning-free directed and
  pin-top regressions; synthesize the standalone guard to 14 LC / 67 FF / no
  DSP or RAM.
- [x] Compose the framed mono fabric datapath from scheduler through input
  calibration, exact trapezoidal/banked/terminal stream, output calibration,
  held ready/valid output, and explicit mono duplication. Match 64 calibrated
  inputs, raw model outputs, and PCM frames bit-for-bit under five clocks of
  output backpressure; force and clear one output overrun without overwriting
  the held frame while model/calibration diagnostics remain zero. Prevent the discovered hidden
  startup-state advance by holding the core reset through phase acquisition;
  integrate the downstream safety ramp and synthesize the combined hierarchy to
  20,489 LC / 15,592 FF / 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1 with no structural problems and no timing claim.
- [x] Correct synthesis resource accounting to retain both RAMB18E1 and
  RAMB36E1 primitives plus their 18-Kib equivalent total. Existing factorized
  hierarchies use 8 RAMB18E1 + 1 RAMB36E1, not the formerly reported eight
  RAMB18E1-only count; numerical implementation is unchanged.
- [x] Align asynchronous-bridge frames to the solver's deterministic fabric
  schedule. Accept one held stereo frame per 2,048-clock period, prelaunch for
  one-clock calibration, inject zero on starvation, and retain a saturating
  underflow count. Verify phase zero and directed A/zero/B order warning-free;
  synthesize to 41 LC / 43 FF / no DSP or RAM.
- [x] Define and implement the converter calibration boundary without selecting
  hidden gain: PCM24 to input-referred Q8.24 volts and physical Q8.24 line volts
  to saturating PCM24. Match 4,159 Python/RTL vectors per direction with
  explicit endpoint, saturation, and invalid-coefficient diagnostics; synthesize
  to 95/86 LC, 66/58 FF, and 4 DSP48E1 per direction with no warnings.
- [x] Integrate the I²S protocol and CDC primitives into a bidirectional stereo
  frame bridge. Preserve 20 exact BCLK-to-fabric-to-BCLK frames under unrelated
  clocks and deliberate ready backpressure, verify owning-domain diagnostics,
  and synthesize the later instrumented hierarchy to 571 LC / 1,547 FF with zero
  structural problems and explicit register-expanded FIFO storage.
- [x] Implement conventional 24-bit stereo I²S in 32-BCLK slots. Loop 16 signed
  frames exactly through warning-free receive/transmit RTL; independently check
  32-period slots and delay bits; inject framing and underflow faults; synthesize
  RX/TX to 35/97 LC and 105/137 FF with no warnings or structural problems.
- [x] Implement a device-neutral dual-clock FIFO with Gray pointer crossings,
  two-flop synchronizers, registered read data, sticky overflow/underflow, and
  embedded formal invariants. Preserve directed and 128 wrapped words under
  unrelated clocks; with later occupancy watermarks, synthesize depth 8×32 to
  127 LC / 331 FF with zero
  structural problems and a documented register-expansion warning.
- [x] Add nine original, physically scaled PCM24 regressions covering silence,
  nominal/low-level THD, high-frequency intermodulation products, multitone,
  warp, pop, log sweep, and 1.5 V overload. Process 32,448 outputs / 519,168
  nonlinear updates with zero model diagnostics or WAV clips; measure
  0.019826%/0.011559% H2--H10 THD at 5/0.5 mV peak.
- [x] Extend the deterministic audio suite to 14 vectors / 69,440 external
  frames / 1,111,040 nonlinear updates. Add a 60 Hz/7 kHz, 4:1
  SMPTE-RP-120-style sideband profile (explicitly not an analyzer-conformance
  claim), a differential 5 mV one-sample impulse, and paired 250 ms nominal/
  0.5 V overload trajectories. With zero fixed diagnostics or WAV clips,
  measure 0.461295% profile IMD, a strictly causal 34-sample impulse onset and
  138.118 mV peak, and 147.750 ms 10%-nominal recovery relative to the input
  burst stop.
- [x] Add dependency-free 16/24/32-bit PCM WAV I/O, explicit peak-voltage
  scaling through the exact fixed V1 stream, and transparent latency/gain/
  fractional-delay null tooling. Run a 1,024-frame terminal-trapezoidal audio
  regression with zero diagnostics/clips, exact recovery of an injected
  23-sample delay, and separate +2.405/-30.462/-100.810 dB raw/latency/gain
  residuals.
- [x] Capture the complete trapezoidal terminal stream at 100 Hz, 1 kHz,
  10 kHz, and 20 kHz for 4,800 outputs each. Prove fixed/RTL identity and zero
  diagnostics; bound gain/phase error to 0.000134 dB / 0.000444 degree; and
  separate the 87.89 uV worst fitted startup drift from the -74.79 dB
  detrended waveform null.
- [x] Implement trapezoidal terminal correction with exact corrected Q4.44
  capacitor-current commit on the final chord edge. Match all state across
  384,000 overload updates with zero diagnostics; reduce 1.0/1.5 V burst RMS
  error to 4.709/3.604 mV; carry it through 64 complete-stream outputs; and
  synthesize the 127-clock solver/stream to 14,945/20,241 LC, 174/222 DSP48E1,
  and 8 RAMB18E1 + 1 RAMB36E1.
- [x] Separate all 16 internal frequencies that fold to ±3 kHz in the captured
  complete-stream stress test. Prove the isolated 45 kHz third-harmonic output
  is exactly zero in Q8.24, capture the combined out-of-band projection exactly,
  and measure only a -176.96 dBc complete-vs-family-removed effect below fixed
  rounding closure; the nonfolded 3 kHz bin dominates by 102.37 dB.
- [x] Capture the banked terminal RTL through 384,000 control/overload updates
  at 20 mV, 0.5 V, 1.0 V, and 1.5 V. Preserve H1--H10, clipping asymmetry,
  grid current, recovery, and null metrics; prove full-state fixed equivalence
  and zero diagnostics while matching analytical burst THD within 0.00122
  percentage points and phase within 0.00221 degrees.
- [x] Carry the banked terminal solver through the complete mono resampling
  stream. Match 64 external outputs / 1,024 nonlinear updates exactly at the
  measured 127-clock solver latency with zero diagnostics, and synthesize the
  full hierarchy to 18,466 LC / 168 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1.
- [x] Implement the backward-Euler terminal correction in fixed Python and
  synthesizable RTL. Prove output/state identity to conventional four-pass,
  match 18,432 overload updates exactly at 127 clocks with zero diagnostics,
  and synthesize to 13,296 LC / 120 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1.
- [x] Sweep three through six corrections on the current banked solver for both
  integrators at 1.0/1.5 V over 100 ms. Measure fourth-pass burst improvement
  of 5.65--9.02 dB, six-pass residual <=0.207 uA, non-monotonic recovery-state
  error, and the rejected 145-clock minimum extra-pass projection.
- [x] Split integer tube evaluation from fixed circuit/state/chord error using
  the same Q24/Q20 input and Q31 current interfaces. Prove all intermediate
  banked runs diagnostic-clean; measure <=0.168 mV tube-evaluator burst error
  versus 6.40--19.07 mV circuit/state/chord error.
- [x] Decompose banked severe-overload error, sweep the grid-current table, and
  implement the selected 1,024-entry branch in fixed Python and RTL. Reduce
  direct worst error from 716 to 12.55 nA and 1.5 V final error from
  18.27/17.36 mV to 0.631/0.321 mV, preserve zero diagnostics, prove standalone
  and 36,864-state integrated RTL exactness, and retain eight mapped RAMB18E1s plus one RAMB36E1.
- [x] Add a Vgk-slew-qualified shallow bank for the severe cutoff arc. Preserve
  bit-exact <=1.0 V behavior, remove all 1.5 V residual-limit misses in both
  integration modes, prove 36,864 RTL states exact with every bank exercised,
  and retain the 116-clock schedule with no added DSP or block RAM.
- [x] Separate the factorized plate-law domain from its grid-current lookup.
  Prove every former 1.5 V range event was only `Vgk < -5 V`, expand plate-law
  acceptance to -8 V while retaining the -5 V grid leakage-floor clamp, and
  prove before/after audio bit-exactness. Exact integrated RTL now has zero
  arithmetic/range/fallback events at 1.5 V; the later slew-qualified bank
  closes the then-remaining 57/53 residual misses.
- [x] Tighten the shallow trapezoidal bank threshold from -2.50 to -2.75 V.
  Avoid every 0.5 V activation, retain zero 1.0 V failures and exact RTL, and
  reduce the final-window mean error from 1.042 to 0.537 mV.
- [x] Compare 100 ms banked waveforms against full Newton without alignment.
  At 1.0 V, improve raw burst error from -53.45/-53.65 dB to -76.43/-76.79 dB
  for backward Euler/trapezoidal; retain the trapezoidal 0.537 mV final-window
  mean error as an open selector/state discrepancy.
- [x] Implement integration-mode-specific cutoff-Jacobian banks in RTL; prove
  all 9,216 overload states per mode bit-exact, exercise every bank at the
  unchanged 116-clock latency, and synthesize without added DSP or block RAM.
- [x] Derive fixed cutoff-region Jacobian banks from the analytical stage-two
  trajectory. In the 100 ms Python gate, remove all 1.0 V residual failures in
  both integration modes without extra corrections, arithmetic/range events,
  or fallbacks; retain the separate 1.5 V residual limitation explicitly.
- [x] Prove wide RHS, backward-Euler/trapezoidal KCL, tube-stamp, and chord
  arithmetic bounds with conservative full-interface integer intervals. All 47
  checks pass; directed regressions cover the corrected 44-bit capacitor delta,
  34-bit `INT32_MIN` cathode-current sum, and saturating tube-pin conversion.
- [x] Establish repository engineering instructions and reproducible tool bootstrap.
- [x] Capture wide-solver RTL at 100 Hz, 1 kHz, 10 kHz, and 20 kHz; prove Q32
  fixed equivalence and <=0.0001943 dB / <=0.0009814 degree analytical error.
- [x] Capture 100 ms overload/recovery trajectories through 1.5 V; compare all
  state exactly and extend post-burst observation to 85 ms.
- [x] Capture the 16× decimator's cubic nonlinear alias trajectory; match 8,192
  outputs exactly and measure -137.814 dBc with zero saturation.
- [x] Integrate frame-aligned reset/warmup and the mute ramp around the wide
  stream; prove no state-reset sample escapes and synthesize the guarded top.
- [x] Compare 768 kHz backward Euler with SPICE at 100 Hz, 1 kHz, 10 kHz, and
  20 kHz; expose 4.72 degree high-frequency phase error and measure a floating
  trapezoidal candidate at <=0.0582 degrees for 10/20 kHz.
- [x] Compare 100 ms backward-Euler/trapezoidal overload trajectories through
  1.5 V; prove finite convergence and matched clean-region recovery.
- [x] Implement explicit fixed trapezoidal capacitor branches with Q30 voltage
  and signed Q4.44 previous-current history; pass the six-frequency nominal
  sweep with zero diagnostics.
- [x] Run fixed trapezoidal overload through 1.5 V; pass the <=0.5 V clean
  region, bound stored capacitor current, and expose the required 48-bit
  companion-conductance width.
- [x] Widen the KCL capacitor coefficient to signed 48-bit, add explicit
  previous/current-next ports, and pass 1,024 exact trapezoidal vectors without
  regressing the backward-Euler KCL.
- [x] Add persistent Q4.44 current state and a separate trapezoidal chord-
  inverse ROM to the selectable solver; match all 29 state words and diagnostics
  across 512 samples at 116 clocks and synthesize the hierarchy.
- [x] Carry trapezoidal state through the complete interpolator/solver/
  decimator stream; match 64 outputs / 1,024 internal updates with zero
  diagnostics and synthesize the selectable hierarchy.
- [x] Capture trapezoidal solver RTL at 100 Hz, 1 kHz, 10 kHz, and 20 kHz;
  prove complete fixed-state equivalence, nominal diagnostics, and bounded
  gain/phase error while linking the separate ngspice integration layer.
- [x] Capture the complete 48 kHz trapezoidal stream for 4,800 outputs at each
  of 100 Hz, 1 kHz, 10 kHz, and 20 kHz; prove exact fixed equivalence, zero
  diagnostics, and <=0.000111 dB / <=0.001185 degree error against the composed
  floating model. Measure the rate converters independently at exactly 51
  external samples / 1.0625 ms so their phase is not attributed to the circuit.
- [x] Extend floating trapezoidal overload observation to 235 ms after the
  burst. Measure 0.5 V 10%-nominal recovery at 146.552 ms, fit the coupled
  stage-two recovery modes at 98.2--118.1 ms, retain 1.0/1.5 V crossings as
  labeled projections, and record complete node/capacitor checkpoints.
- [x] Directly simulate nominal, 1.0 V, and 1.5 V floating trajectories through
  850 ms. Falsify the earlier single-exponential projection, measure 1.0 V
  sustained 10% recovery at 270.112 ms, and expose 413--451× late rebounds
  after opposing circuit modes temporarily cancel near 316--362 ms.
- [x] Capture selectable trapezoidal RTL through the accepted 0.5 V overload
  and 235 ms recovery window. Match 384,000 complete fixed-state updates with
  zero diagnostics and measure sustained 10% recovery at 146.570 ms, 18.23 µs
  from the independent floating trajectory.
- [x] Linearize the actual nine-node/tube circuit at DC and solve `det(G+sC)=0`
  without a generalized-eigenvalue dependency. Verify eight stable finite modes;
  identify 143.936 ms and 1.067763 s output-coupling modes that explain the
  overload cancellation/rebound and bound the next direct record at seven seconds.
- [x] Run seven-second nominal/1.0 V/1.5 V recovery trajectories. Measure all
  sustained 10%/1%/1 mV crossings through 6.371 s; validate the late two-pass
  chord handoff against Newton below 33.2 nV over 100 ms and 17.9 nV at the
  final-cycle probe, with zero solve failures.
- [x] Select, document, and version the Kennedy 1998 two-stage passive-RIAA circuit.
- [x] Implement AT-VM95E R/L/47.5 kΩ/150 pF cartridge loading.
- [x] Build ngspice DC, 10 Hz–100 kHz AC, transient, and 1 kHz H1–H10 level sweeps.
- [x] Verify nominal DC and quantify historical RIAA error without correcting it.
- [x] Implement canonical mathematical RIAA and regress against Bulletin E1.
- [x] Implement the Koren 12AX7 analytical/grid-current model and compare checked
  manufacturer-curve digitization.
- [x] Implement the 768 kHz nonlinear nodal/capacitor-state Python model and
  compare it with ngspice.
- [x] Characterize one through four Newton passes at 20 mV peak.
- [x] Reject raw linear-network fixed-point iteration and select three-pass
  quiescent-Jacobian chord iteration as the measured fixed/RTL candidate.
- [x] Implement reproducible 12AX7 tube LUTs, study four resolutions, and record
  mean/worst interpolation error.
- [x] Define tube-interface Q formats and a bit-accurate Python LUT model.
- [x] Define all V1 state/matrix/residual/inverse formats and implement an
  integer-only three-pass chord model with explicit rounding and saturation.
- [x] Decompose initial multitone error into tube-LUT and fixed-state/chord layers.
- [x] Design the four-stage 16× float/Q1.23-coefficient half-band reference,
  measure response/latency, and verify rejection of a nonlinear 45 kHz alias.
- [x] Implement the fixed Q8.24/Q1.23 per-stage MAC/rounding/saturation model and
  preserve the nonlinear alias test as a regression.
- [x] Reduce chord correction to DSP-native 18×25 operands; measure its error
  independently against the original Q17.15 × Q4.44 correction.
- [x] Implement, lint, synthesize, and verify the nine-node chord-correction RTL
  against 1,024 exact vectors including saturation boundaries.
- [x] Add CI jobs for Python/RTL/generated-asset regressions and ngspice/model
  cross-comparisons.
- [x] Implement synthesizable eight-clock 12AX7 RTL with range diagnostics.
- [x] Pass warning-free Verilator lint and 4,096 bit-exact randomized vectors.
- [x] Run generic XC7 synthesis and record actual structural resource use.
- [x] Implement exact capacitor-history RHS and heterogeneous-format KCL RTL;
  pass 1,024 vectors per block including residual saturation boundaries.
- [x] Integrate both 12AX7 halves, all ten capacitor branches, three corrections,
  final residual, state commit, and runtime diagnostics in a mono scheduler.
- [x] Match all nodes, capacitor states, output, residual, and counters for 512
  sequential fixed-model/RTL samples at a measured 126-clock latency.
- [x] Synthesize the complete hierarchy: 8,024 estimated XC7 logic cells,
  89 DSP48E1s, and 47 RAMB18E1s, with no structural check problems.
- [x] Implement serial-MAC half-band interpolator/decimator primitives and the
  complete 48↔768 kHz four-stage chains with saturation/overrun diagnostics.
- [x] Match 2,048 interpolation and 128 decimation stream outputs exactly;
  record the visible 18-internal-sample scheduler delay and structural resources.
- [x] Integrate the complete 48 kHz reference stream around the nonlinear solver,
  including saturating Q12.20-to-Q8.24 output conversion and diagnostics.
- [x] Match 64 consecutive end-to-end outputs / 1,024 nonlinear updates exactly;
  synthesize the full stream at 13,170 estimated LC, 137 DSP, and 47 RAMB18.
- [x] Sweep analytical and fixed behavior from 0.5 mV to 5 V at 1 kHz using the
  settled SPICE analysis window; quantify THD, compression, residual, and clips.
- [x] Measure low-level distortion at four larger LUT resolutions and reject a
  raw BRAM increase as an ineffective fix.
- [x] Implement and measure a fixed factorized Koren candidate using three
  value/slope 1-D LUTs with cubic Hermite interpolation: 51.8 nA worst current
  error and 0.0188% versus 0.0191% analytical THD at 5 mV.
- [x] Implement the standalone factorized tube RTL and pass 4,110 bit-exact
  randomized/boundary vectors at eight clocks, including five clip cases;
  after the grid-resolution implementation, synthesize at 1,496 LC,
  35 DSP48E1, and 8 RAMB18E1 + 1 RAMB36E1.
- [x] Integrate the factorized primitive as a selectable solver mode; match all
  state and diagnostics for 512 samples at 126 clocks and synthesize the full
  hierarchy at 9,148 LC, 108 DSP48E1, and 8 RAMB18E1 + 1 RAMB36E1.
- [x] Propagate factorized mode through the complete stream; match 64 outputs /
  1,024 circuit updates exactly with zero diagnostics and synthesize at 14,290
  LC, 156 DSP48E1, and 8 RAMB18E1 + 1 RAMB36E1.
- [x] Sweep 5 mV factorized fixed vs analytical at 20/50/100 Hz and
  1/10/20 kHz: ≤0.00846 dB gain error, ≤0.0729° phase error, and no diagnostic
  failures across 683,520 nonlinear samples.
- [x] Characterize 5 ms overload bursts at 20 mV, 0.5 V, 1.0 V, and 1.5 V,
  including peak grid current, clipping asymmetry, residual/range diagnostics,
  and recovery relative to an undisturbed nominal trajectory.
- [x] Sweep three through six chord corrections at 1.0/1.5 V; quantify residual,
  output error, range events, and the 126-to-213-clock serialized projection.
- [x] Run a 768,000-sample silence/bipolar-click state audit with node and all
  capacitor checkpoints; expose the Q12.20 deadband and preserve it as a
  reproducible regression rather than hiding it with output DC removal.
- [x] Implement a 40-bit Q28/Q32 node, Q30 history, branch-current Python
  candidate with staged Q30/Q34/Q40 correction precision. Reduce the click
  audit's late residual from 5.375 mV to 38.74 uV and the nominal 1 kHz raw null
  from -42.90 to -63.83 dB with zero diagnostics.
- [x] Sweep the wide-state candidate at 20/50/100 Hz and 1/10/20 kHz: bound
  gain/phase error to 0.000196 dB / 0.000982 degrees with zero diagnostics.
- [x] Re-run 20 mV--1.5 V overload with adaptive Q30/Q34/Q40 residual scaling:
  eliminate arithmetic saturation and improve clean-region recovery/error, but
  retain explicit 1.0/1.5 V convergence and 1.5 V range failures.
- [x] Implement the 40-bit Q28/Q32 chord corrector with bounded Q30/Q34/Q40
  scaling; match 1,024 vectors at ten clocks and synthesize to 1,701 XC7 logic
  cells / 9 DSP48E1 / no RAMB18. Reject the 5,531-cell arbitrary-shift version.
- [x] Implement two-clock wide RHS and ten-clock branch-current KCL blocks;
  match 1,024 vectors each with adaptive fallback, true overflow, and delayed
  tube-current coverage. Synthesize at 31 LC / 4 DSP and 8,034 LC / 72 DSP.
- [x] Integrate the wide factorized solver; match all 19 persistent states and
  diagnostics across 512 sequential samples at 116 clocks. Synthesize the
  hierarchy at 12,544 LC / 120 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1.
- [x] Integrate the wide solver into 16x interpolation/decimation; match 64
  outputs / 1,024 solves exactly with zero diagnostics and synthesize at 17,492
  LC / 168 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1.
- [x] Capture 23,040 wide-solver RTL samples at 5 mV/1 kHz; prove Q32 exactness
  and measure -0.000054 dB gain, -0.000187 degree phase, 0.019371% THD, and
  -63.834 dB raw residual directly from RTL output.
- [x] Implement and test a downstream Q0.16 output mute/ramp with reset-muted
  startup, symmetric rounding, exact-unity bypass, and synchronous fault clamp;
  synthesize at 171 XC7 logic cells, 2 DSP48E1s, and no block RAM.
- [x] Quantify flat/partial/full-analog RIAA front-end architectures.
- [x] Produce initial gain/headroom, MM loading, noise, converter, clock, control,
  safety, stereo schedule, and hardware-verification engineering documents.

## Known discrepancies and failing regressions

- No failing regression.
- Python backward-Euler MNA versus ngspice ranges from -66.42 dB raw residual at
  100 Hz to -21.50 dB at 20 kHz. The 20 kHz gain error is only -0.0646 dB, but
  phase error is +4.72 degrees. Floating trapezoidal reduces that phase error to
  +0.0582 degrees. The fixed trapezoidal model is now nominally bounded against
  that floating candidate and implemented through the complete RTL stream. The
  legacy unbanked solver still fails severe-overload convergence; the selected
  banked terminal path is diagnostic-clean through the tested 1.5 V burst but
  retains 3.604 mV trapezoidal burst RMS approximation error. The SPICE link is
  still based on separate, non-sample-identical transient stimuli.
- The frozen historical circuit is -0.919 dB from ideal RIAA at its worst audio-
  band point. This is reference behavior, not an implementation defect.
- The explicit 2-D-LUT RTL mode produces 0.0733% THD versus 0.0191% analytical
  at 5 mV/1 kHz. The separately selectable, fully integrated factorized RTL mode
  reduces this to 0.0188%; both modes remain named and independently verified.
- At 1.0 V peak the factorized fixed candidate records 5,209 residual-limit
  failures and 7.03 µA maximum residual; overload solver behavior remains open.
- In a 5 ms burst, factorized residual-limit failures begin at the tested 1.0 V
  level (1,134 samples); 1.5 V causes 4,046 transformed-domain clip events.
  Bursts ≥0.5 V do not recover below 10% nominal RMS within the 35 ms window.
- The Q12.20 output/capacitor state can freeze after a discontinuity. In the
  one-second bipolar-click audit the final fixed output is -5.368 mV versus
  4.5 uV instantaneous analytical output; no runtime diagnostic fires.
- The wide candidate fixes that state deadband but not severe nonlinear
  convergence: 1.0/1.5 V bursts still exceed the residual limit 1,122/1,695
  times, and the latter clips the transformed tube domain 4,046 times.
- Yosys reports 204 Xilinx BRAM primitive port-resize warnings on the hierarchical
  solver while `check` reports no structural problem. Track tool-version behavior;
  do not describe synthesis as warning-free.

## Research and hardware questions

- Obtain better positive-grid 12AX7 data and quantify grid-current/overload error.
- Evaluate piecewise/hybrid tube approximation if full circuit synthesis proves
  the 47-RAMB18 primitive to be the dominant capacity constraint.
- Measure Architecture A with a real JFET front end and at least two ADCs before
  freezing converter/gain/anti-alias parts.
- Determine a credible stereo architecture; the selected solver uses 127/128
  clocks and cannot be time-multiplexed across two channels at the present
  throughput. The calibrated, muted pin-facing mono hierarchy uses 232/240 A7-100T
  DSPs, preventing duplication.
- Select a first full integrated-amplifier topology only after V1 phono equivalence.

## Verification debt

- The full-phono circuit RTL is bit-exact to fixed Python and now has nominal
  four-point solver and complete-stream captures. SPICE comparison remains at
  four frequencies and large-signal cross-layer coverage is still incomplete.
- PCM WAV processing, explicit null comparison, and deterministic distortion,
  IMD-product, SMPTE-profile, impulse, and paired long-recovery gates now exist.
  The SMPTE-profile sideband fit is traceable but is not a calibrated RP 120
  instrument implementation; licensed/user-supplied music remains absent. The
  I²S protocol and CDC FIFO primitives now form a bidirectional frame bridge, and standalone
  physical-unit calibration now composes with the accuracy-first mono core at
  the fabric frame boundary and a pin-facing top adds the asynchronous bridge.
  The modeled-output ramp and atomic converter-coefficient commit are now
  integrated, and the SPI-controlled pin wrapper supplies transport, shadow
  commit, and coherent fabric snapshots. A tested host codec/client now defines
  framing and guarded operations; a physical adapter backend,
  queued-frame/physical analog muting, and CDC/I/O timing constraints remain
  absent. The single-clock mute/ramp properties now have a Yosys SAT proof;
  asynchronous-FIFO properties now have a 32-step arbitrary-clock SAT bound,
  while a complete invariant set for unbounded induction remains open.
  The cubic and full-tube alias-family tests are captured from RTL; the latter
  is bounded below fixed rounding closure rather than inferred from the
  confounded raw bin.
- No qualified named-speed-grade Fmax, FPGA capture, analog converter, or physical tube
  measurement exists.
- GE curve digitization has ±0.05 mA visual uncertainty; production tube spread
  and tolerance statistics are not characterized.
- Front-end noise excludes flicker, hum, EMI, protection parasitics, distortion,
  reference noise, and PCB effects until physical measurement.

## Later milestones

- [ ] Stereo scheduling and converter interface on Arty A7-100T reference platform.
- [x] Standalone 24-bit/32-slot I²S receive/transmit protocol primitives.
- [x] Bidirectional stereo-frame I²S/fabric asynchronous bridge.
- [x] Bit-exact PCM24/input-volts/output-volts calibration primitives.
- [x] Frequency-locked bridge-to-core fabric frame scheduler.
- [x] Calibrated framed mono adapter around the accuracy-first V1 stream.
- [x] Pin-facing digital I²S/CDC plus calibrated mono-model integration.
- [x] Atomic muted converter-calibration commit boundary and diagnostics.
- [x] PCM WAV processing and latency/gain/fractional-delay null comparison.
- [x] Deterministic WAV distortion/IMD-product/overload regression library.
- [x] Traceable SMPTE-profile sideband, paired long-recovery, and impulse WAV
  gates.
- [ ] Licensed/user-supplied music WAV gate with provenance and redistribution
  rights.
- [ ] Fabricated MM front end, ADC/FPGA/DAC loopback, and calibrated line output.
- [ ] Validated phase inverter, power tubes, transformer, dynamic supply, feedback,
  and speaker interaction for one selected integrated-amplifier circuit.
- [ ] Transparent protected physical power stage; FPGA/DAC never drive speakers directly.
