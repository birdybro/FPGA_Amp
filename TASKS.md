# Engineering task ledger

Last updated: 2026-08-13

## Current milestone

Close the measured factorized fixed/analytical DC-state and severe-overload
solver gaps, reproduce waveform metrics from captured integrated RTL, and
harden the 48/768 kHz stream boundary. The circuit remains frozen at version
0.1.0; safety processing remains explicitly outside it.

## Active, highest value first

- [ ] Evaluate overload-specific solver strategies (adaptive Jacobian, parallel
  tube evaluation, or higher-rate schedule); implement and verify the measured
  cutoff-Jacobian bank in RTL. Extra chord passes remain rejected.
- [ ] Extend integrated-solver RTL capture beyond nominal frequency response to
  level-dependent harmonics, clipping asymmetry, and recovery metrics.
- [ ] Separate folded nonlinear harmonics from preexisting in-band solver energy
  in the complete stream; the present full-tube 3 kHz bin is intentionally not
  reported as pure 45 kHz-to-3 kHz aliasing.

## Completed this milestone

- [x] Derive fixed cutoff-region Jacobian banks from the analytical stage-two
  trajectory. In the 100 ms Python gate, remove all 1.0 V residual failures in
  both integration modes without extra corrections, arithmetic/range events,
  or fallbacks; retain the 1.5 V tube-domain limitation explicitly.
- [x] Prove wide RHS, backward-Euler/trapezoidal KCL, tube-stamp, and chord
  arithmetic bounds with conservative full-interface integer intervals. All 37
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
- [x] Implement the standalone factorized tube RTL and pass 4,107 bit-exact
  randomized/boundary vectors at eight clocks, including five clip cases;
  synthesize at 1,597 LC, 37 DSP48E1, and 8 RAMB18E1.
- [x] Integrate the factorized primitive as a selectable solver mode; match all
  state and diagnostics for 512 samples at 126 clocks and synthesize the full
  hierarchy at 9,194 LC, 110 DSP48E1, and 8 RAMB18E1.
- [x] Propagate factorized mode through the complete stream; match 64 outputs /
  1,024 circuit updates exactly with zero diagnostics and synthesize at 14,366
  LC, 158 DSP48E1, and 8 RAMB18E1.
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
  hierarchy at 12,439 LC / 122 DSP48E1 / 8 RAMB18E1.
- [x] Integrate the wide solver into 16x interpolation/decimation; match 64
  outputs / 1,024 solves exactly with zero diagnostics and synthesize at 17,552
  LC / 170 DSP48E1 / 8 RAMB18E1.
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
  that floating candidate and implemented through the complete RTL stream.
  Severe-overload convergence remains unresolved and the SPICE link is still
  based on separate, non-sample-identical transient stimuli.
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
- Determine a credible stereo architecture; one solver uses 126/128 clocks and
  cannot be time-multiplexed across two channels at the present throughput. The
  best-accuracy mono stream now uses 170/240 A7-100T DSPs, preventing duplication.
- Select a first full integrated-amplifier topology only after V1 phono equivalence.

## Verification debt

- The full-phono circuit RTL is bit-exact to fixed Python and now has nominal
  four-point solver and complete-stream captures. SPICE comparison remains at
  four frequencies and large-signal cross-layer coverage is still incomplete.
- WAV/null, CDC, and formal infrastructure remain absent. The cubic alias test
  is captured from RTL, while a full-tube alias decomposition still needs a
  method that separates preexisting in-band energy from folded harmonics.
- No vendor place-and-route/Fmax, FPGA capture, analog converter, or physical tube
  measurement exists.
- GE curve digitization has ±0.05 mA visual uncertainty; production tube spread
  and tolerance statistics are not characterized.
- Front-end noise excludes flicker, hum, EMI, protection parasitics, distortion,
  reference noise, and PCB effects until physical measurement.

## Later milestones

- [ ] Stereo scheduling and converter interface on Arty A7-100T reference platform.
- [ ] WAV/null comparison and distortion/overload regression library.
- [ ] Fabricated MM front end, ADC/FPGA/DAC loopback, and calibrated line output.
- [ ] Validated phase inverter, power tubes, transformer, dynamic supply, feedback,
  and speaker interaction for one selected integrated-amplifier circuit.
- [ ] Transparent protected physical power stage; FPGA/DAC never drive speakers directly.
