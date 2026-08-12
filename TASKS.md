# Engineering task ledger

Last updated: 2026-08-12

## Current milestone

Turn the verified 12AX7 device primitive and floating V1 nodal circuit into a
bit-accurate, synthesizable mono 768 kHz circuit stream without losing the
measured SPICE behavior. The reference circuit is frozen at model version 0.1.0.

## Active, highest value first

- [ ] Extend fixed-vs-float comparison across frequency, level, silence, impulse,
  grid conduction, overload/recovery, and long-duration capacitor-state drift.
- [ ] Prove fixed residual/overflow bounds and determine whether tube LUT
  resolution must increase before circuit RTL is frozen.
- [ ] Implement a bit-accurate fixed nonlinear common-cathode stage and compare
  DC, gain, harmonics, clipping, and recovery with float/SPICE.
- [ ] Implement synthesizable common-cathode/network state updates with solver
  residual, saturation, LUT-range, and deadline diagnostics.
- [ ] Extend the fixed/RTL path to both triodes and the physical passive-RIAA
  network; automate 20 Hz–20 kHz and level comparisons.
- [ ] Design and verify four 2× half-band interpolators plus nonlinear-output
  decimation; measure ripple, rejection, latency, alias products, and resources.
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
- [x] Implement synthesizable eight-clock 12AX7 RTL with range diagnostics.
- [x] Pass warning-free Verilator lint and 4,096 bit-exact randomized vectors.
- [x] Run generic XC7 synthesis and record actual structural resource use.
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
- Yosys reports 188 Xilinx-techmap port-resize warnings while `check` reports no
  structural problem. Track tool-version behavior; do not describe synthesis as
  warning-free.

## Research and hardware questions

- Obtain better positive-grid 12AX7 data and quantify grid-current/overload error.
- Evaluate piecewise/hybrid tube approximation if full circuit synthesis proves
  the 47-RAMB18 primitive to be the dominant capacity constraint.
- Measure Architecture A with a real JFET front end and at least two ADCs before
  freezing converter/gain/anti-alias parts.
- Confirm whether shared stereo solver/network arithmetic closes the 128-cycle
  internal deadline after named-part place-and-route.
- Select a first full integrated-amplifier topology only after V1 phono equivalence.

## Verification debt

- The fixed full-phono candidate has only an initial multitone comparison; no
  common-cathode/full-phono circuit RTL exists yet.
- No oversampling, decimator, alias measurement, WAV/null tool, CDC, or formal
  infrastructure exists yet.
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
