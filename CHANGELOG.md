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
