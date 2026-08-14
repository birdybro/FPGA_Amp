# FPGA Amp

FPGA Amp is a physically informed vacuum-tube audio simulator. The immediate
target is a moving-magnet cartridge feeding the two triodes of a 12AX7 through
the passive RIAA network published by Kevin Kennedy in 1998. It is modeled as a
coupled electrical circuit—not as an EQ block followed by a waveshaper.

```text
AT-VM95E R/L source -> 47.5 kΩ || 150 pF -> 12AX7 #1
 -> 47 nF / 210 kΩ / 33.2 kΩ / 10 nF / 3.3 nF passive RIAA
 -> 12AX7 #2 -> 470 nF -> 2.21 MΩ line load
```

The project keeps three categories separate:

- **Reference:** the frozen 1998 circuit, including its measured low-frequency
  RIAA departure.
- **Approximation:** tube-model, integration, LUT, fixed-point, solver, and RTL
  errors measured against the immediately upstream reference.
- **Enhancement:** future subsonic filtering, tube variation, noise, and other
  modern/creative controls, all explicitly opt-in.

## Current measured milestone

The mono reference and complete 768 kHz circuit solver are operating:

- ngspice DC: stage 1 is 180.0 V / 0.992 mA and stage 2 is 192.8 V /
  1.072 mA at a 300 V supply.
- SPICE circuit gain is 41.087 dB at 1 kHz. Relative RIAA error is
  -0.919 to +0.000 dB from 20 Hz to 20 kHz; this is a property of the frozen
  historical network, not digitally corrected.
- The 768 kHz backward-Euler nonlinear nodal model differs from the ngspice
  5 mV-peak, 1 kHz result by -53.10 dB normalized residual and 0.0018 dB RMS
  gain, with no failed solves.
- A four-frequency SPICE transient sweep exposes backward-Euler's audio-band
  phase cost: at 100 Hz it is +0.00131 dB / +0.0244°, while at 20 kHz it is
  -0.0646 dB / +4.72°. Raising backward-Euler to 3.072 MHz still leaves 1.24°
  at 20 kHz. An explicit 768 kHz trapezoidal candidate improves 10/20 kHz
  floating error to at most 0.00846 dB / 0.0582°.
- A 100 ms floating overload comparison finds the trapezoidal candidate finite
  and convergent through 1.5 V peak / 26.4 µA stage-two grid current. At 20 mV,
  its 10% / 1% / 1 mV recovery agrees with backward Euler within 2.6 µs. Both
  retain the modeled long recovery above 0.5 V; trapezoidal does not conceal or
  correct that reference behavior.
- The bit-accurate trapezoidal candidate uses the wide Q28/Q32 node contract,
  Q30 previous capacitor voltage, and explicit signed Q4.44 previous capacitor
  current. Across six 5 mV points from 20 Hz through 20 kHz it stays within
  0.000131 dB / 0.000784° of floating trapezoidal, with zero convergence,
  saturation, range, or correction-fallback events. Its RTL is bit-exact at the
  same 116-clock schedule, including the banked large-signal captures below.
  It remains an optional numerical candidate rather than a silent reference
  change.
- In the 5 ms burst gate, fixed trapezoidal stays diagnostic-clean through
  0.5 V peak and retains the same severe-overload boundary as backward Euler:
  1.0/1.5 V cause 1,107/1,690 residual failures and 1.5 V causes 4,048 tube-
  domain clips. Stored capacitor current reaches 203.34 uA with no arithmetic
  saturation. The doubled 470 nF companion coefficient requires signed 48-bit
  Q0.47, one bit wider than the current backward-Euler RTL KCL contract.
- The 128 × 256 Q0.31 tube LUT has 0.139 µA mean and 9.33 µA worst absolute
  error in a 100,000-point full-range probe.
- The complete bit-accurate three-pass chord candidate is -57.87 dB normalized
  residual from analytical/full-Newton float on the initial multitone; isolated
  state/chord error is -70.33 dB relative to the same circuit using the tube LUT.
- A settled 1 kHz sweep exposes a narrower low-level limitation: at 5 mV peak,
  fixed THD is 0.0733% versus 0.0191% analytical. Doubling either LUT axis does
  not fix the existing 2-D implementation.
- A new factorized Koren candidate replaces that current surface with three
  value/slope 1-D tables and cubic Hermite interpolation. Its bit-accurate Python
  model measures 50.6 nA worst plate-current error in 100,000 points and 0.0188%
  THD at 5 mV versus 0.0191% analytical. Its 1,024-point grid-current branch
  measures 12.55 nA worst / 2.82 nA active-region RMS error; total raw storage
  is 262,144 bits (14.22 raw RAMB18 equivalents). Standalone RTL is exact across
  4,110 vectors at the existing eight-clock latency; structural synthesis
  reports 1,496 logic cells, 35 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1. Solver and
  complete-stream modes are also
  bit-exact at the unchanged 126-clock solver schedule.
- The SystemVerilog tube lookup accepts physical Q-format voltages, is
  bit-exact for 4,096 randomized vectors, and has eight-clock latency.
- The nine-node chord corrector is bit-exact for 1,024 randomized/boundary
  vectors, including 18 saturation cases, with ten-clock latency; XC7 synthesis
  uses 9 DSP48E1 blocks and no block RAM.
- A device-neutral depth-8 dual-clock FIFO now crosses full audio words with
  binary local/Gray synchronized pointers, two-flop CDC synchronizers, registered
  reads, sticky overflow/underflow, and conservative local-domain occupancy plus
  high-water diagnostics. Unrelated 100/71.4 MHz test clocks preserve a 128-word
  wrap sequence after directed full/empty faults; directed fill reaches exactly
  depth eight and both estimates return to zero after drain. Generic XC7 synthesis
  uses 127 logic cells / 331 flip-flops / no DSP or RAM; Yosys intentionally
  expands this small 8×32 memory to registers. Embedded formal invariants exist,
  but no formal engine is installed in the current environment.
- Separate I²S receive/transmit blocks now implement signed 24-bit stereo in
  32-BCLK slots with the mandatory one-clock I²S delay. A warning-free 16-frame
  loopback covers positive/negative endpoints, independent 32-period slot/delay
  monitoring, injected LRCLK framing failure, and transmit underflow/clear.
  Warning-free XC7 synthesis measures 35 LC / 105 rising-edge flops for receive
  and 97 LC / 137 falling-edge flops for transmit, with no DSP or RAM.
- A bidirectional I²S asynchronous bridge now composes those protocol blocks
  with independent depth-8 stereo-frame FIFOs. A warning-free test sends 20
  exact frames from BCLK to an unrelated fabric clock and back while applying
  fabric receive backpressure; all six bridge diagnostics remain clean apart
  from deliberate DAC startup starvation, which clears in its owning domain.
  Directed multi-frame receive backpressure records 3/3-frame receive and
  4/4-frame transmit high-water marks without loss. Flattened XC7
  synthesis reports 571 LC / 1,547 FF / no DSP or RAM. The small
  8×64 memories are explicitly register-expanded.
- A Gray-counter audio-clock monitor now measures BCLK over 32,768 fabric
  clocks, accepts 1,024 ± 1 edges, and requires three consecutive windows for
  lock. Warning-free directed RTL acquires at the exact ratio, observes 11
  rather than 10 edges after a deliberate speed change, drops lock/latches the
  error, reacquires, clears, detects a stopped clock as zero edges, and revokes
  live state on BCLK reset. The pin top
  measures exactly 1,024 edges in four windows. Standalone synthesis is 68 LC /
  125 FF / no DSP or RAM. This detects gross rate error; FIFO drift remains the
  longer-term mismatch diagnostic and neither mechanism performs rate matching.
  The register-controlled wrapper now treats missing lock or retained rate
  error as an explicitly modern immediate-mute condition. A shortened-window
  integration test proves startup qualification, stopped-BCLK clamp, recovery
  that remains latched, coherent fault snapshot, and host clear before release;
  model scheduling continues silently so the receive FIFO is not filled.
- Standalone converter calibration now maps PCM24 to physical input Q8.24 volts
  and physical output volts back to saturating PCM24 with explicit positive
  Q8.24 coefficients, full-width products, symmetric rounding, endpoint/clip
  counters, and invalid-configuration muting. Python and warning-free RTL match
  4,159 vectors per direction. Structural synthesis measures 95 LC / 66 FF / 4
  DSP48E1 input and 86 LC / 58 FF / 4 DSP48E1 output. The serial bridge and
  converter-specific control remain outside the framed fabric adapter below.
- A deterministic fabric frame scheduler now accepts one held stereo frame per
  2,048-clock interval and launches it one clock before phase zero, so the
  registered input calibrator reaches the core on its required 48 kHz phase.
  Warning-free RTL verifies held-frame handshakes, a missing-frame zero fill,
  phase alignment, and saturating underflow diagnostics. Generic synthesis is
  41 LC / 43 FF / no DSP or RAM. This aligns frequency-locked domains; it is not
  asynchronous sample-rate conversion and cannot absorb oscillator drift.
- A fabric-domain mono adapter now composes that scheduler, both calibration
  boundaries, and the exact trapezoidal/banked/terminal phono stream. It models
  only left input and explicitly duplicates the mono result into both output
  slots; this is bring-up routing, not stereo. A 64-frame warning-free
  regression checks every calibrated input, raw Q8.24 model output, and held
  PCM frame exactly, including unrelated right-channel data and five clocks of
  output backpressure, then forces and clears one held-output overrun without
  overwriting the older frame. Model and calibration diagnostics remain zero.
  The core remains reset through initial scheduler phase
  acquisition so hidden interpolator zeros cannot advance physical capacitor
  state before the first accepted frame. A downstream modern safety ramp begins
  muted, reaches exact-unity bypass, and leaves reference mode bit-identical;
  the integration test also checks a synchronous force-mute gain clamp.
  Flattened structural synthesis is 20,489 LC / 15,592 FF / 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1. This leaves only 8 DSPs on the provisional
  XC7A100T and has no placed timing, serial-pin, or physical-converter claim.
- A pin-facing digital top now composes the asynchronous I²S bridge with that
  adapter. With exactly frequency-locked but phase-offset 3.072 MHz BCLK and
  98.304 MHz fabric clocks, a warning-free integration test delivers all 64
  unrelated stereo inputs to the left-only model exactly, checks all 64 raw
  model outputs, and receives 45 consecutive observable post-startup DAC frames
  as exact mono duplicates. Receive prefill precedes audio-reset release;
  expected serial startup starvation remains observable. The active ADC/DAC
  scaling pair now resets to zero and commits atomically only while the output
  ramp is muted. The same test accepts the startup pair, then rejects a live
  candidate without changing either active coefficient and clears the unsafe
  diagnostic. Timestamped serial/fabric events measure 192 BCLKs, 62.500 µs,
  or three 48 kHz frames from the first complete ADC PCM frame to the first
  complete valid model-output DAC frame. This is transport latency, not FIR or
  circuit group delay. All four local FIFO views remain at a one-frame
  high-water mark, and the clock monitor is locked after four exact 1,024-edge
  windows. Flattened synthesis is 21,014 LC / 16,907 FF / 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1. This is a
  digital protocol integration, not placed CDC/I/O timing or converter/analog
  validation. The digital ramp cannot revoke frames already queued in the CDC
  transmit FIFO and is not a substitute for physical analog muting. Host
  register transport and candidate CDC remain open.
- Exact RTL RHS and KCL engines stamp all ten capacitor histories and the
  physical conductance network. Each passes 1,024 vectors at 12 and 10 clocks.
- The integrated solver matches 512 sequential fixed-model samples bit-for-bit
  at every node and capacitor, completes three corrections plus its diagnostic
  residual in 126 of 128 available clocks, and reports no deadline misses.
- Hierarchical out-of-context XC7 synthesis of that complete solver reports
  8,024 estimated logic cells, 89 DSP48E1, and 47 RAMB18E1 blocks. This is an
  accuracy-first baseline; no Fmax is claimed before place-and-route.
- The selectable factorized solver also matches 512 persistent-state samples
  exactly at 126 clocks. Its hierarchy measures 9,148 logic cells, 108 DSP48E1s,
  and 8 RAMB18E1 + 1 RAMB36E1: 37 fewer RAMB18-equivalents at the cost of 19
  DSPs and 1,124 logic cells.
- The complete 48 kHz reference stream—16× interpolation, nonlinear circuit,
  saturating output-format conversion, and 16× decimation—matches 64 consecutive
  Python outputs exactly with zero diagnostic events. Structural synthesis is
  13,170 estimated XC7 logic cells, 137 DSP48E1s, and 47 RAMB18E1s.
- The factorized stream independently matches 64 outputs / 1,024 nonlinear
  updates with zero diagnostics. It synthesizes to 14,290 logic cells, 156
  DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1. Both modes remain explicit while broader accuracy
  and overload tests determine the preferred hardware configuration.
- At 5 mV the factorized fixed raw null is -42.90 dB, but its mean-removed null
  is -59.63 dB: a -2.840 mV DC difference dominates the raw result. Fundamental
  phase error is 0.00958°. These are reported separately; no DC/gain alignment
  is used to conceal implementation error.
- A 5 mV fixed-vs-analytical sweep at 20, 50, 100 Hz and 1, 10, 20 kHz bounds
  fundamental gain error to 0.00846 dB and phase error to 0.0729°, with no
  residual-limit failures, saturations, or tube-range clips. Raw high-frequency
  nulls remain DC-offset dominated and are not substituted for gain/phase error.
- A 5 ms, 1 kHz overload-burst study measures grid current, clipping asymmetry,
  and recovery against an undisturbed trajectory. The 20 mV fixed case is clean
  and recovers below 10% / 1% nominal RMS in 8.67 / 24.6 ms. At 1.0 V the
  residual limit fails; at 1.5 V stage-two grid current reaches 26.3 µA and the
  transformed tube domain clips.
- Increasing the fixed chord count from three to six reduces the 1.0 V maximum
  residual from 6.93 to 2.31 µA but still leaves 30 failures and projects a
  213-clock serialized schedule. At 1.5 V it remains inadequate. Overload needs
  a different solver/range strategy rather than an unbudgeted extra pass.
- A physically derived, fixed-schedule cutoff-Jacobian bank removes the 1.0 V
  residual failure for both backward-Euler and trapezoidal state. RTL matches
  every fixed state, retains the 116-clock schedule, and records zero
  diagnostics. A Vgk-slew-qualified shallow matrix extends that result through
  the tested 1.5 V peak burst without activating at 0.5 or 1.0 V. Structural
  synthesis is 13,302 logic cells / 120 DSPs / 8 RAMB18E1 + 1 RAMB36E1 for
  backward Euler and 13,840 / 120 / 8 RAMB18E1 + 1 RAMB36E1 for trapezoidal.
- A fixed-intermediate domain audit proves that all former 1.5 V range events
  were only `Vgk < -5 V`: measured `Vpk`, transformed coordinate, and `E1`
  remained inside their tables. The plate-law acceptance bound is now -8 V,
  covering the measured -7.03 V minimum, while the grid-current lookup still
  clamps below -5 V at its negative-grid leakage floor. Backward-Euler and
  trapezoidal 12 ms outputs are bit-exact before/after this diagnostic change.
  Integrated RTL is full-state exact at both 1.0 and 1.5 V; after the independent
  slew-selector change, all four captures have zero residual, range, arithmetic,
  or fallback events.
- Against full Newton with the same Q8.24 input, banked 1.0 V burst error is
  -76.43 dB backward Euler and -76.79 dB trapezoidal, improving the failing DC
  chord by 22.98 and 23.13 dB. No gain, DC, or delay alignment is applied.
- The optional backward-Euler terminal correction reuses the final measured
  residual for a fourth chord update and commits state bit-exact to a
  conventional four-pass fixed trajectory. Its complete 48→768→48 kHz stream
  matches 64 external outputs across 1,024 nonlinear updates exactly with zero
  diagnostics at a measured 127-clock solver latency. Full-hierarchy XC7
  synthesis reports 18,466 logic cells, 168 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1; the
  one-clock schedule margin is not a timing-closure claim.
- A captured 100 ms RTL campaign now covers 20 mV, 0.5 V, 1.0 V, and 1.5 V
  overload bursts—384,000 updates including the control trajectory. All fixed
  state is exact and all diagnostics remain zero. Over the final three burst
  cycles, H2--H10 content grows from 0.903% to 25.213%, stage-two grid current
  reaches 26.267 µA, and peak asymmetry changes from +2.659 to -0.541 dB.
  Against analytical Newton, terminal-RTL burst RMS error is 0.288, 1.237,
  4.895, and 6.817 mV; harmonic-window phase error stays within 0.00221° and
  H2--H10 ratio within 0.00122 percentage points. This transient-window
  spectral fit is not mislabeled as settled continuous-drive THD.
- Trapezoidal terminal correction now recomputes all ten Q4.44 companion-current
  histories from the corrected, saturated branch voltages on that same final
  edge. A second 384,000-update campaign is full-state exact and diagnostic-
  clean; burst RMS error versus floating trapezoidal is 0.276, 1.210, 4.709,
  and 3.604 mV. Its 64-output complete stream is exact at 127 clocks. Generated
  constant multipliers reduce the solver to 14,945 logic cells / 174 DSPs; the
  full stream measures 20,241 / 222 / 8 RAMB18E1 + 1 RAMB36E1. This fits the provisional
  A7-100T structurally with 18 DSPs free, but timing is not claimed.
- Schedule-neutral attempts to reduce its remaining 4.709/3.604 mV severe-
  burst error are preserved as negative results. Corrected-state bank
  reselection, rational terminal-residual relaxation, full dual-triode median
  Jacobians, and stage-one-split banks each fail cross-level, recovery, or
  residual-limit acceptance. Reference behavior and production coefficients
  remain unchanged; `make terminal-bank-study`, `make terminal-relaxation-study`,
  and `make dual-triode-bank-study` regenerate the evidence.
- A protocol-neutral fabric register bank now resets muted, atomically commits
  the two converter-calibration shadows, and freezes 16 diagnostic words behind
  a saturating snapshot sequence. Directed RTL covers accepted/invalid/unsafe
  commits, busy writes, clears, and malformed addresses; structural synthesis is
  323 LC / 715 FF / no DSP or block RAM. The wrapper below supplies pin
  integration; a host protocol is supplied by the SPI composition below.
- A register-controlled pin wrapper now owns calibration and mute, freezes 21
  fabric-coherent status words, synchronizes sticky I²S faults, and transfers
  diagnostic clear once across the unrelated BCLK domain. Integration is
  warning-free. It also fails closed through BCLK qualification and after a
  retained rate error without changing reference-circuit state. Structural
  synthesis is 21,375 LC / 17,787 FF / 232 DSP48E1 /
  8 RAMB18E1 + 1 RAMB36E1. Raw multibit I²S levels and
  named-part timing are not claimed.
- A mode-0 SPI bridge now oversamples CS/SCLK/MOSI in the fabric domain and
  executes fixed 80-bit request/response frames on that register bus. Eight
  warning-free 5 MHz transactions cover real calibration, readback, malformed
  address, short frame, withheld response, and diagnostic clear. Standalone
  synthesis is 112 LC / 172 FF / no DSP or RAM. The complete composition then
  passes 15 SPI frames through the pin-facing hierarchy, including untorn
  force-mute snapshots, snapshotted transport count, calibration ownership,
  a retained short-frame fault, and one I²S-domain clear event. Flattened
  synthesis is 21,507 LC / 17,959 FF /
  232 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1; placed SCLK/CDC/I/O limits remain open.
- A dependency-free Python host client defines the same ten-byte full-duplex
  wire frame, register/capability constants, status validation, explicit-mute
  snapshot/clear commands, and guarded calibration commit sequencing. Six unit
  tests cover exact bytes and failure behavior through a fake transport; a
  physical `spidev`/USB/embedded backend remains board-specific and unvalidated.
- A captured complete-stream sweep at 100 Hz, 1 kHz, 10 kHz, and 20 kHz proves
  all 19,200 Q8.24 outputs exact with zero diagnostics. Relative to the composed
  floating trapezoidal reference, gain/phase error stays within 0.000134 dB /
  0.000444°. The worst mean-removed null is -63.77 dB at 20 kHz because the
  fixed/float startup-state residual drifts 87.89 µV across the 50 ms window;
  retaining that metric while removing only its fitted linear drift gives a
  -74.79 dB shape null. No gain, phase, or fractional-delay alignment is used.
- The fixed stream now has a real PCM WAV boundary with mandatory, explicit
  input/output peak-voltage mappings and no hidden normalization. A 1,024-frame
  synthetic MM/pop/multitone regression runs the trapezoidal terminal model
  with zero diagnostics or WAV clips. Its independent null fixture recovers an
  injected 23-sample delay exactly and preserves +2.405 dB raw, -30.462 dB
  latency-aligned, and -100.810 dB opt-in gain-aligned residuals as separate
  fields. Optional fractional alignment is labeled with its interpolation
  method; it is never enabled by default.
- A 14-vector PCM24 library exercises silence, 5/0.5 mV 1 kHz, selected
  19/20 kHz products, a 60 Hz/7 kHz 4:1 SMPTE-style profile, a 100 Hz/1/10 kHz
  multitone, 11 Hz warp, a record pop, a separately controlled impulse, a
  20 Hz–20 kHz log sweep, and both short severe and paired 250 ms accepted-range
  overload records. All 69,440 external frames / 1,111,040 nonlinear updates
  pass with zero model diagnostics or WAV clips. H2–H10 THD is 0.019826% at
  5 mV peak and 0.011559% at 0.5 mV; profile sideband IMD is 0.461295%. The
  5 mV one-sample impulse is strictly causal, first exceeds four PCM LSBs after
  34 samples, and peaks at 138.118 mV. Paired 0.5 V recovery crosses 10% of
  nominal RMS at 147.750 ms after the input burst stop and ends at 18.650 mV
  RMS over the final 10 ms. The high-frequency fixture remains a selected-
  product report, and the SMPTE-style fit is not a calibrated RP 120
  conformance claim.
- Moving only the shallow trapezoidal threshold from -2.50 to -2.75 V prevents
  bank activation at 0.5 V, preserves zero 1.0 V failures, and reduces final
  10 ms mean error from 1.042 to 0.537 mV with the former 128-point grid-current
  branch. This historical selector A/B remains reproducible; the denser branch
  below supersedes its absolute final-window figure.
- A 20 mV/sample previous-Vgk slew qualifier separates the measured severe
  cutoff arc from every accepted <=1.0 V trajectory. Backward Euler adds a
  fourth matrix evaluated at (-2.25 V, 261 V); trapezoidal reuses its shallow
  matrix. The 100 ms 1.5 V residual-failure counts fall from 72/67 to zero and
  the 12 ms RTL proof is full-state exact across 36,864 total updates. With the
  old 128-point grid-current branch, severe burst error remained
  -61.80/-62.12 dB and final 10 ms error remained 18.27/17.36 mV. Those results
  are retained as the pre-resolution baseline, not current accuracy.
- A converged layer decomposition localized that severe recovery error to the
  128-entry linear grid-current table, not the factorized plate law. The
  implemented 1,024-entry branch reduces direct worst error from 716 to
  12.55 nA. At 1.5 V it improves raw burst error to -72.87/-81.77 dB and the
  final-window circuit error to 0.631/0.321 mV for backward Euler/trapezoidal,
  with all fixed diagnostics clean. Standalone and 36,864-state integrated RTL
  regressions are bit-exact and structural RAM use remains eight RAMB18E1s plus one RAMB36E1.
- A second decomposition passes continuously evaluated quantized coefficients
  through the exact Q24/Q20 input and Q31 current interfaces of the banked fixed
  circuit. Integer Hermite evaluation accounts for only 0.149–0.168 mV burst
  RMS, while fixed node/capacitor/chord arithmetic accounts for 6.40–19.07 mV.
  Every intermediate solve is diagnostic-clean. This directs the next accuracy
  work to circuit/state/chord arithmetic rather than another tube-table change.
- A banked three-to-six-pass sensitivity study confirms that solver truncation
  is material: a fourth pass improves 1.0/1.5 V burst error by 5.65–9.02 dB,
  and six passes reduce maximum residual below 0.207 µA and burst RMS to
  2.35–2.94 mV. Recovery-state error is not monotonic with pass count, however,
  and a conventional extra serialized pass projects to 145 clocks versus the
  128-clock deadline. An optional backward-Euler terminal path instead reuses
  the already-computed diagnostic residual: it is output-exact to four-pass,
  completes in 127 measured clocks, and explicitly reports the preterminal
  residual. The later accuracy-first trapezoidal implementation also recomputes
  and commits all ten corrected companion-current histories on that edge.
- Removing the shallowest cutoff matrix is not a valid optimization: the 100 ms
  selector study leaves 289 backward-Euler or 119 trapezoidal 1.0 V residual
  failures. All generated matrices remain required; activation thresholds are
  studied separately from coefficient-bank removal.
- A new one-second silence/click audit exposes a Q12.20 state deadband that the
  KCL diagnostics miss: after bipolar 100 mV one-sample clicks, fixed output is
  still -5.368 mV in the final 100 ms while analytical output is about 7.2 uV
  RMS. The current RTL remains bit-exact to that now-rejected state contract;
  wider internal output/history precision is the active redesign.
- A 40-bit Q28/Q32 all-node Python candidate with Q30 capacitor history,
  branch-current stamping, and Q30/Q34/Q40 staged correction precision reduces
  that late raw residual from 5.375 mV to 38.74 uV RMS with zero diagnostics.
  At 5 mV/1 kHz it improves raw fixed/analytical null from -42.90 to -63.83 dB,
  with -0.000058 dB gain and -0.000187 degree phase error. Its standalone
  wide-state chord corrector is now bit-exact RTL, but complete KCL/state
  integration, schedule, and hierarchical synthesis gates remain.
- Across 20 Hz, 50 Hz, 100 Hz, 1 kHz, 10 kHz, and 20 kHz at 5 mV, that
  candidate stays within 0.000196 dB gain and 0.000982 degree phase of the
  analytical model with zero diagnostics. Raw null spans -95.26 to -44.75 dB;
  high-frequency values remain reported separately from their DC-dominated
  mean-removed residuals.
- A bounded block-floating correction selector requests Q30/Q34/Q40 but reduces
  precision when needed to keep all 25-bit residual operands in range. It
  eliminates arithmetic saturation in the 1.5 V burst (729 recorded fallbacks),
  while ordinary signals never fall back. At 20 mV, 1% recovery improves from
  24.61 ms legacy to 14.92 ms, matching analytical; post-burst error falls from
  5.80 mV to 0.258 mV RMS. Severe overload remains rejected: 1.0/1.5 V still
  produce 1,122/1,695 convergence failures and 1.5 V retains 4,046 range clips.
- The wide Q28/Q32 chord block accepts only the bounded Q30/Q34/Q40 correction
  schedule, matches 1,024 randomized and boundary vectors exactly at 10 clocks,
  and synthesizes structurally to 1,701 XC7 logic cells, 9 DSP48E1s, and no
  block RAM. The constrained three-format shifter avoids the 5,531-cell cost of
  the rejected arbitrary-shift experiment.
- Wide network RTL now matches 1,024 exact RHS and 1,024 exact KCL vectors. The
  two-clock RHS omits capacitor history by design; the ten-clock KCL evaluates
  all ten Q30 branch differences, tests delayed tube-current handshakes, and
  globally selects correction precision. Structural XC7 results are 31 logic
  cells / 4 DSPs for RHS and 8,034 logic cells / 72 DSPs for KCL.
- The same KCL block now has an explicit trapezoidal mode. It remains ten clocks
  and matches 1,024 independent residual/current-history vectors exactly,
  including 1,013 deliberately extreme Q4.44 current-saturation cases. The
  original backward-Euler vector set remains exact and warning-free.
- The integrated wide factorized solver matches Python bit-for-bit for 512
  sequential samples, including every node, capacitor, residual, and diagnostic.
  The measured schedule is 116 clocks, leaving 12 of 128 clocks, with zero test
  diagnostics. Hierarchical XC7 synthesis is 12,544 logic cells, 120 DSP48E1s,
  and 8 RAMB18E1 + 1 RAMB36E1; Fmax remains unmeasured.
- The explicitly selectable trapezoidal solver also matches 512 persistent
  samples exactly, including ten Q4.44 current histories, at the unchanged
  116-clock latency. Its separate chord-inverse ROM is required by the doubled
  capacitor companions. Structural synthesis measures 12,786 logic cells,
  120 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1: +242 cells and no DSP/BRAM change versus
  backward Euler. This is structural evidence only; Fmax remains unmeasured.
- The corresponding complete 48 kHz stream matches 64 outputs spanning 1,024
  nonlinear updates exactly with zero diagnostics. Structural synthesis is
  17,492 logic cells, 168 DSP48E1s, and 8 RAMB18E1 + 1 RAMB36E1, so the mono reference fits
  the provisional A7-100T resource envelope but leaves only 72 of 240 DSPs.
- The selectable trapezoidal 48 kHz stream likewise matches all 64 outputs /
  1,024 nonlinear updates exactly with zero diagnostics and 5.02 nA maximum
  residual. Structural synthesis is 17,735 logic cells, 168 DSP48E1s, and
  8 RAMB18E1 + 1 RAMB36E1: +243 cells with unchanged DSP/BRAM versus backward Euler.
- A 23,040-sample captured RTL run at 5 mV / 1 kHz is Q32 bit-exact to fixed
  Python. Measured directly from RTL output, gain/phase error versus analytical
  float is -0.000054 dB / -0.000187 degrees, THD is 0.019371% versus 0.019059%,
  and raw/mean-removed residual is -63.83 / -88.45 dB.
- Captured solver output at 100 Hz, 1 kHz, 10 kHz, and 20 kHz remains Q32
  bit-exact to fixed Python. Against analytical float, maximum gain/phase error
  is 0.000194 dB / 0.000982 degrees with zero runtime diagnostics. This is an
  RTL-simulation result, not an FPGA or analog measurement.
- The same four-point captured sweep in trapezoidal mode is exact to fixed at
  every output and persistent state, and stays within 0.000128 dB / 0.000784°
  of floating trapezoidal with zero diagnostics. The report links, but does not
  combine, the independent ngspice layer: float trapezoidal differs by at most
  0.00846 dB / 0.0582° at the measured 10/20 kHz points.
- The complete 48 kHz trapezoidal boundary is captured for 4,800 outputs at
  each of 100 Hz, 1 kHz, 10 kHz, and 20 kHz. Every RTL output is fixed-model
  exact, all diagnostics remain zero, and the full chain stays within 0.000111
  dB / 0.001185° of its composed floating reference. The report measures the
  causal rate-converter path separately at exactly 51 external samples
  (1.0625 ms), then subtracts that phase only in the explicitly labeled
  circuit-attributed view.
- A captured 100 ms overload campaign matches all fixed nodes, capacitor states,
  outputs, and diagnostics for 384,000 total solver updates. The 20 mV burst
  reaches the 10% / 1% recovery thresholds in 8.47 / 14.92 ms. Bursts at 0.5 V
  and above remain outside even the 10% threshold after 85 ms in both analytical
  and RTL trajectories. Solver residual failures begin at 1.0 V; the 1.5 V case
  has 4,046 modeled-tube range clips and 729 safe scale fallbacks but no arithmetic
  saturation.
- A separate floating trapezoidal run extends physical-model observation to
  235 ms after the burst. It directly measures the 0.5 V case crossing 10% of
  nominal output at 146.552 ms. The 1.0/1.5 V cases remain above that threshold;
  50--240 ms envelope fits identify 110.1/98.2 ms dominant coupled modes and
  project 297/408 ms crossings. Those projections are not reported as measured
  recovery. Node/capacitor checkpoints show stage-two plate/output displacement
  dominates the observed window, rather than the isolated 1.039 s product of
  470 nF and 2.21 MΩ.
- Direct 850 ms trajectories then falsify those early single-exponential
  projections. The 1.0 V case reaches sustained 10% recovery at 270.112 ms but
  never reaches 1%; the 1.5 V case remains above 10% after 835 ms. More
  importantly, deviation nearly cancels at 362/316 ms and then rebounds by
  451×/413× to 31.6/183.8 mV RMS. Recovery is therefore gated on the last
  sliding-RMS threshold crossing, and no severe fixed/RTL accuracy is claimed.
- At the accepted 0.5 V boundary, a separate selectable-trapezoidal RTL run
  captures 192,000 control and 192,000 overload updates. Every node and both
  voltage/current histories for all ten capacitors are fixed-model exact, all
  diagnostics are zero, and sustained 10% recovery is 146.570 ms—18.23 µs from
  the independent floating result. The 1% threshold remains outside 235 ms.
- A continuous-time small-signal linearization of the frozen nodal circuit now
  solves `det(G+sC)=0` at the tube DC bias. All eight finite modes are stable.
  The two recovery-relevant time constants are 143.936 ms and 1.067763 s, with
  99.49% and >99.999999% of their normalized capacitor energy in the 470 nF
  output branch. Their opposing signs explain why an early exponential fit
  failed. Applying the slow mode only after the 835 ms measured endpoint
  estimates the last severe 1 mV crossing near 6.33 s; a seven-second direct
  run is required before turning that estimate into a measurement.
- The resulting seven-second trajectories now measure the complete tail. At
  1.0 V, sustained 10%/1%/1 mV recovery occurs at 0.270112/3.053927/4.536427 s;
  at 1.5 V it occurs at 2.429673/4.888292/6.370790 s. Full Newton covers the
  first 850 ms; a two-pass floating chord solver covers the near-bias tail only
  after a 100 ms overlap stays below 33.2 nV maximum error. A final-cycle probe
  stays below 17.9 nV and all solves converge. The modal estimates were within
  61.4 ms, but the measured times now supersede them.
- A downstream, explicitly non-reference output guard now starts muted, applies
  a configurable sample-qualified linear ramp, bypasses exactly at unity, and
  synchronously clamps held output on a fault. Its warning-free RTL regression
  passes signed rounding/reset/control cases; generic XC7 synthesis reports 171
  logic cells, 2 DSP48E1s, and no block RAM.
- The guarded wide-stream top now enforces model-change sequencing: linear
  ramp-down, frame-aligned core reset, 64-output muted warmup, acknowledgment,
  and ramp-up. A warning-free integration regression proves no reset or warmup
  sample escapes before mute. Structural synthesis reports 17,562 logic cells,
  170 DSP48E1s, and 8 RAMB18 + 1 RAMB36; this remains an unplaced estimate.
- A four-stage 16× half-band reference provides at least 91.6 dB per-stage image
  rejection and suppresses the measured cubic 45 kHz→3 kHz decimation alias to
  -137.8 dB with bit-accurate Q8.24/Q1.23 MACs. An 8,192-output RTL capture now
  reproduces -137.814 dB exactly with zero saturation. A separate complete-tube
  0.5 V / 15 kHz capture is also exact, but has a 1.402 mV finite-window 3 kHz
  projection before decimation. A phase-aware decomposition now isolates all 16
  internal frequencies that fold to ±3 kHz. The 45 kHz component produces zero
  Q8.24 output in the analysis window; removing the complete out-of-band family
  changes the 3 kHz output by only 10.77 nV (-176.96 dBc), below the measured
  fixed-rounding closure. The remaining 3 kHz output dominates by 102.37 dB, so
  the raw -74.59 dBc bin is no longer left ambiguous or mislabeled as aliasing.

There is no physical host-adapter backend, fabricated analog front end,
converter board, named-part timing result, or physical measurement yet. The
implemented digital mute primitive is not independent analog speaker protection.

## Verification chain

```text
published circuit/data
        -> ngspice
        -> Python floating-point circuit model
        -> bit-accurate Python LUT model
        -> synthesizable SystemVerilog
        -> synthesis
        -> future FPGA and analog measurement
```

The exact circuit and operating points are in
[`docs/phono_stage.md`](docs/phono_stage.md). Equations and measured error
layers are in [`docs/modeling.md`](docs/modeling.md), and the source decisions
are annotated in [`docs/references.md`](docs/references.md).

## Reproduce

Python 3.10+, NumPy, PyYAML, and Matplotlib are required. Verilator is needed
for RTL tests. If ngspice/Yosys are unavailable, the non-root bootstrap downloads
the distribution packages into ignored `.tools/` without changing the host:

```bash
make tools
make test
```

Individual workflows:

```bash
make spice                         # DC, AC, and 5 mV transient
python3 scripts/spice_level_sweep.py
python3 scripts/run_reference.py --plots
python3 scripts/compare_spice_python.py
make spice-python-frequency          # four SPICE transients + integrator study
make trapezoidal-overload            # floating integrator overload stability
python3 scripts/characterize_solver.py
python3 scripts/study_solver_architecture.py
python3 scripts/compare_fixed_float.py
make accuracy-sweeps                # settled level and low-level LUT studies
make factorized-study               # smooth 1-D/Hermite tube candidate
make factorized-frequency           # 20 Hz-20 kHz fixed/analytical sweep
make factorized-frequency-wide      # same sweep with wide-state candidate
make factorized-frequency-trapezoidal # explicit-voltage/current-history candidate
make factorized-domain              # before/after cutoff-domain equivalence audit
make state-drift                    # one-second silence/click state audit
make state-wide                     # wide-state candidate on the same audit
make state-wide-audio               # 5 mV/1 kHz legacy/wide A/B
make linear-modes                   # physical G+sC poles at tube DC bias
make wide-rtl-audio                 # capture and measure 23,040 RTL samples
make wide-rtl-frequency             # captured 100 Hz-20 kHz solver sweep
make trapezoidal-rtl-frequency      # captured selectable-integrator sweep
make trapezoidal-rtl-recovery       # accepted 0.5 V long-recovery capture
make trapezoidal-stream-rtl-frequency # captured complete 48 kHz sweep
make trapezoidal-terminal-stream-rtl-frequency # accuracy-first stream sweep
make wide-rtl-overload              # captured 100 ms overload/recovery sweep
make terminal-banked-rtl-metrics    # terminal H1-H10/clipping/recovery capture
make wide-stream-rtl-alias          # captured nonlinear decimation-alias test
make wav-null-regression            # fixed V1 PCM WAV + explicit null fixture
make audio-regression               # nine-vector distortion/IMD/overload suite
make overload-study                 # grid conduction, clipping, recovery
make overload-trapezoidal           # fixed/float trapezoidal burst comparison
make overload-long                  # 235 ms floating severe-recovery observation
make overload-severe-long           # direct 850 ms multimode recovery test
make overload-seven-second          # complete severe floating recovery timing
make overload-wide                  # same bursts with wide-state candidate
make overload-iterations            # three-to-six-pass solver trade
make overload-banked                # cutoff-Jacobian bank convergence study
make banked-slew-selector           # qualify the severe shallow-bank selector
make banked-error-decomposition     # localize tube/circuit/chord error
make banked-iterations              # banked three-to-six-pass waveform study
make grid-current-resolution        # sweep grid-conduction table accuracy
python3 scripts/study_lut_resolution.py
python3 scripts/analyze_frontend.py
python3 scripts/design_resampler.py
make arithmetic-bounds             # prove wide RHS/KCL/chord integer widths
make rtl                           # lint + 4,096 bit-exact vectors
make factorized-rtl                # smooth tube RTL + directed clip vectors
make chord-rtl                     # lint + 1,024 circuit-correction vectors
make wide-chord-rtl                # exact 40-bit Q28/Q32 correction vectors
make network-rtl                   # RHS/KCL bit-exact unit tests
make wide-network-rtl              # branch-current RHS/KCL exact tests
make trapezoidal-network-rtl       # explicit current-history KCL vectors
make solver-rtl                    # 512-sample persistent-state integration
make solver-factorized-rtl         # exact smooth-tube solver integration
make wide-solver-rtl               # exact 40-bit branch-current solver
make trapezoidal-solver-rtl        # exact selectable integration-mode solver
make banked-solver-rtl             # exact four-bank cutoff solver
make terminal-banked-solver-rtl    # exact 127-clock terminal correction
make trapezoidal-banked-solver-rtl # exact five-bank cutoff solver
make trapezoidal-terminal-banked-solver-rtl # exact terminal current commit
make banked-rtl-overload           # 1.0/1.5 V full-state bank-selection gate
make terminal-banked-rtl-overload  # terminal full-state overload gate
make banked-accuracy               # 100 ms banked/full-Newton waveform gate
make banked-selector               # prove required cutoff-bank partitions
make banked-threshold              # sweep shallow trapezoidal activation
make halfband-rtl                  # exact 2x units and complete 16x streams
make stream-rtl                    # complete 48 kHz reference stream
make stream-factorized-rtl         # complete smooth-tube reference stream
make stream-wide-rtl               # complete wide-state reference stream
make stream-terminal-banked-rtl    # complete banked terminal-correction stream
make stream-trapezoidal-rtl        # complete trapezoidal reference stream
make stream-trapezoidal-terminal-banked-rtl # 127-clock trap terminal stream
make guarded-stream-rtl            # mute/reset/warmup model-change sequence
make mute-rtl                      # reset/ramp/fault output safety primitive
make audio-clock-rtl               # BCLK/fabric ratio lock and error monitor
make async-fifo-rtl                # unrelated-clock CDC ordering/fault gate
make cdc-pulse-rtl                # one-shot host command CDC
make spi-control-rtl              # 80-bit mode-0 register transport
make i2s-rtl                       # 24-bit/32-slot stereo protocol loopback
make i2s-bridge-rtl                # exact bidirectional I2S/fabric CDC loopback
make calibration-rtl               # bit-exact PCM24/physical-volts boundary
make calibration-control-rtl       # atomic muted coefficient-pair commit
make control-registers-rtl         # snapshot/shadow/transaction register bank
make frame-scheduler-rtl           # deterministic 48 kHz fabric phase launch
make mono-adapter-rtl               # exact framed PCM-to-model-to-PCM datapath
make i2s-mono-top-rtl               # serial ADC through model to serial DAC
make i2s-control-top-rtl            # register-owned pin hierarchy and clear CDC
make i2s-spi-top-rtl                # complete SPI-controlled I2S audio hierarchy
make synth                         # generic XC7 structural estimate
make synth-factorized              # factorized tube structural estimate
make synth-chord                   # generic XC7 chord-corrector estimate
make synth-wide-chord              # wide-state corrector structural estimate
make synth-wide-network            # wide RHS/KCL structural estimates
make synth-solver                  # hierarchical complete-solver estimate
make synth-solver-factorized       # smooth-tube hierarchy/resource trade
make synth-wide-solver             # wide-state hierarchy estimate
make synth-trapezoidal-solver      # trapezoidal hierarchy estimate
make synth-banked-solver           # backward-Euler banked hierarchy estimate
make synth-terminal-banked-solver  # terminal-correction hierarchy estimate
make synth-trapezoidal-banked-solver # trapezoidal banked hierarchy estimate
make synth-trapezoidal-terminal-banked-solver # terminal-current hierarchy
make synth-stream-wide             # complete wide-state stream estimate
make synth-stream-trapezoidal-terminal-banked # accuracy-first mono stream
make synth-stream-terminal-banked  # complete terminal-correction stream estimate
make synth-stream-trapezoidal      # complete trapezoidal stream estimate
make synth-stream-guarded          # wide stream plus safety/control guard
make synth-halfband                # complete interpolator/decimator estimates
make synth-stream                  # complete reference-stream estimate
make synth-stream-factorized       # smooth-tube stream resource estimate
make synth-mute                    # output ramp structural estimate
make synth-audio-clock             # audio clock ratio monitor estimate
make synth-async-fifo              # depth-8 dual-clock FIFO estimate
make synth-cdc-pulse               # one-shot command crossing estimate
make synth-spi-control             # oversampled SPI transport estimate
make synth-i2s                     # receiver/transmitter structural estimates
make synth-i2s-bridge              # bidirectional protocol/CDC bridge estimate
make synth-calibration             # dynamic converter-scaling estimates
make synth-calibration-control     # atomic calibration guard estimate
make synth-control-registers       # fabric control/snapshot register estimate
make synth-frame-scheduler         # frame-phase scheduler estimate
make synth-mono-adapter            # calibrated accuracy-first fabric datapath
make synth-i2s-mono-top            # protocol/CDC plus calibrated mono datapath
make synth-i2s-control-top         # register-controlled complete pin hierarchy
make synth-i2s-spi-top             # SPI transport plus complete pin hierarchy
```

Run a user-supplied 48 kHz integer-PCM WAV through an explicitly selected V1
fixed model by supplying the physical peak-voltage mappings at both boundaries:

```bash
python3 scripts/process_wav.py input.wav output.wav \
  --report build/process.json \
  --mode banked-terminal-trapezoidal \
  --input-full-scale-v 0.02 --output-full-scale-v 2.0

python3 scripts/compare_wav.py reference.wav candidate.wav \
  --report build/null.json --residual-wav build/residual.wav \
  --spectrum-csv build/residual_spectrum.csv
```

The comparison defaults to integer latency alignment but does not fit gain, DC,
or fractional delay. `--gain-align` and `--fractional-delay` are opt-in and every
applied transformation is recorded alongside the unaligned metrics.

Generated CSV, plots, logs, ROM images, and reports are intentionally ignored;
every one has a source script. The compact LUT characterization report is kept
under `model/generated/` as part of the numerical contract.

## Repository map

- `reference/spice/`: frozen analog golden reference and Koren tube subcircuit
- `reference/tube_data/`, `reference/vectors/`: traceable comparison data
- `model/python/fpga_amp/`: mathematical, nonlinear circuit, and fixed models
- `model/configurations/`: circuit and simulation values
- `models/phono/`: versioned model asset metadata
- `rtl/tube/`, `rtl/circuit/`, `rtl/phono/`: synthesizable tube and V1 solver
- `sim/unit/`, `sim/integration/`: self-checking RTL testbenches
- `scripts/`: all reproduction, comparison, analysis, and synthesis entry points
- `docs/`: engineering decisions, budgets, known limitations, and hardware path

The prioritized engineering ledger is [`TASKS.md`](TASKS.md). The next critical
path is further reducing terminal-solver approximation error without breaking
the 128-clock deadline and proving the 98.304 MHz one-clock-margin design in
named-part place-and-route; the latter requires vendor tooling not present in
the current environment.

## License

GPL-3.0; see [`LICENSE`](LICENSE).
