# Changelog

All notable engineering changes are recorded here. The project is pre-release; dates use ISO 8601.

## Unreleased

### Added

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
  packed ROM generation, and an exact 4,107-vector RTL regression with directed
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
- Added a standalone downstream output mute/ramp with reset-muted startup,
  sample-qualified linear transitions, symmetric signed rounding, exact-unity
  bypass, synchronous fault clamp, and a self-checking RTL regression.
- Added warning-free Verilator lint and a 4,096-vector bit-exact testbench with checked eight-clock latency.
- Added non-root ngspice/Yosys bootstrap and a generic XC7 out-of-context synthesis report.
- Added quantitative cartridge/front-end noise, ADC headroom, and analog-versus-digital RIAA partition analysis.
- Added architecture, model, phono, fixed-point, gain, noise, analog front-end, converter/clock, hardware, controls, safety, verification, and annotated-reference documentation.

### Reference decisions

- V1 is one mono channel using both halves of one 12AX7, 300 V B+, unbypassed 1.21 kΩ cathode resistors, and the original two-pole passive equalizer values.
- High-resolution inspection corrected the equalizer capacitor transcription to 3300 pF shunt (the source scan's decimal text is easy to misread at page scale). The failed 300 pF/series interpretations were rejected by topology inspection and RIAA regression.
- The nominal external cartridge is the Audio-Technica AT-VM95E equivalent: 485 Ω, 550 mH, 47 kΩ load, and configurable total shunt capacitance (150 pF nominal).
- The Koren 12AX7 parameter set is the first analytical and SPICE tube model. Model error against manufacturer curves is tracked separately from numerical implementation error.

### Measured

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
- The fixed factorized candidate uses 233,472 raw table bits including grid
  current (12.67 raw RAMB18 equivalents). Its 100,000-point error is 10.5 nA
  mean, 16.0 nA RMS, and 51.8 nA worst at quantized inputs.
- At 5 mV/1 kHz, factorized fixed THD is 0.0188% versus 0.0191% analytical with
  +0.00026 dB fundamental gain error. At 0.5 V it is 2.2419% versus 2.2417%.
  The unaligned 5 mV waveform residual remains -42.90 dB and is tracked
  separately; the 1.0 V fixed solve still exceeds its residual limit.
- The standalone factorized RTL is bit-exact to fixed Python for all 4,107 test
  vectors. XC7 structural synthesis reports 1,597 estimated logic cells,
  37 DSP48E1s, and 8 RAMB18E1s; no Fmax is claimed.
- The complete factorized solver is bit-exact for 512 sequential samples and
  retains the 126-clock schedule with no diagnostic events. Its hierarchy uses
  9,194 estimated logic cells, 110 DSP48E1s, and 8 RAMB18E1s versus the 2-D
  solver's 8,024 / 89 / 47; this is a measured resource trade, not a free win.
- The complete factorized stream matches 64 outputs spanning 1,024 nonlinear
  updates with zero diagnostics. It synthesizes to 14,366 estimated logic cells,
  158 DSP48E1s, and 8 RAMB18E1s versus the surface stream's 13,170 / 137 / 47.
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
  11 clocks. Width-bound synthesis reports 31 LC / 4 DSP for RHS and 7,804 LC /
  72 DSP for KCL; the pre-bound KCL's 99-DSP result was rejected.
- The integrated wide solver matches every node, capacitor history, output,
  residual, and diagnostic across 512 sequential samples. Measured latency is
  116 clocks with zero test events. XC7 structural synthesis reports 11,981
  logic cells, 122 DSP48E1s, and 8 RAMB18E1s.
- The complete wide stream matches 64 outputs spanning 1,024 nonlinear updates
  exactly with zero diagnostics. Structural synthesis reports 16,993 logic
  cells, 170 DSP48E1s, and 8 RAMB18E1s; mono fits the A7-100T, naive stereo does
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
  contains 1.402 mV at 3 kHz before decimation; that output bin is explicitly
  rejected as a pure alias measurement.
- The guarded stream passes a warning-free reset transaction regression: core
  reset follows zero gain, warmup output remains muted, the 48 kHz phase counter
  stays aligned, one acknowledgment fires, and unity gain returns. Structural
  synthesis reports 17,142 logic cells, 172 DSP48E1s, and 8 RAMB18E1s.
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
  Structural synthesis is 12,451 logic cells, 122 DSP48E1s, and 8 RAMB18E1s,
  adding 470 cells but no DSP/BRAM versus backward Euler; no Fmax is claimed.
- The complete trapezoidal stream is bit-exact with zero diagnostics and a
  5.02 nA maximum residual. Structural synthesis is 17,556 logic cells,
  170 DSP48E1s, and 8 RAMB18E1s, adding 563 cells but no DSP/BRAM.
- Captured trapezoidal RTL at 100 Hz/1/10/20 kHz is state-exact to fixed and
  remains within 0.000128 dB / 0.000784 degrees of floating trapezoidal with
  zero diagnostics. The separate float/SPICE layer remains within 0.00846 dB /
  0.0582 degrees at the measured 10/20 kHz points.
- The output mute/ramp passes its warning-free directed Verilator regression;
  generic XC7 synthesis reports 171 estimated logic cells, 2 DSP48E1s, no block
  RAM, and no structural check errors. No placed timing is claimed.

### Changed

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
