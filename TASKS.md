# Engineering task ledger

Last updated: 2026-08-13

## Current milestone

Surround the bit-exact, synthesizable 126-clock mono V1 circuit solver with the
48/768 kHz sample-rate chain, then prove frequency, level, and overload behavior
against the floating and SPICE references. The circuit is frozen at version 0.1.0.

## Active, highest value first

- [ ] Extend fixed-vs-float comparison across frequency, level, silence, impulse,
  grid conduction, overload/recovery, and long-duration capacitor-state drift.
- [ ] Prove fixed residual/overflow bounds and determine whether tube LUT
  resolution must increase before circuit RTL is frozen.
- [ ] Automate RTL frequency and level comparisons through the integrated solver,
  including DC, gain, harmonics, clipping asymmetry, and recovery.
- [ ] Wrap the exact half-band chains around the solver, resolve Q20/Q24 output
  scaling, and reproduce the nonlinear alias measurement through RTL captures.
- [ ] Add reset/state-initialization and post-model mute ramp regressions.

## Completed this milestone

- [x] Establish repository engineering instructions and reproducible tool bootstrap.
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
- [x] Quantify flat/partial/full-analog RIAA front-end architectures.
- [x] Produce initial gain/headroom, MM loading, noise, converter, clock, control,
  safety, stereo schedule, and hardware-verification engineering documents.

## Known discrepancies and failing regressions

- No failing regression.
- Python MNA versus ngspice is -53.10 dB normalized residual for the one tested
  5 mV-peak/1 kHz case. More frequency/level coverage is required before this is
  an acceptance bound.
- The frozen historical circuit is -0.919 dB from ideal RIAA at its worst audio-
  band point. This is reference behavior, not an implementation defect.
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
  cannot be time-multiplexed across two channels at the present throughput.
- Select a first full integrated-amplifier topology only after V1 phono equivalence.

## Verification debt

- The full-phono circuit RTL is bit-exact to fixed Python, but fixed versus float/
  SPICE still has only the initial multitone and one SPICE transient comparison.
- The resampler RTL is not yet wrapped around the solver, and its measured alias
  rejection still derives from the bit-accurate Python chain. WAV/null, CDC, and
  formal infrastructure remain absent.
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
