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
  saturation, range, or correction-fallback events. RTL and large-signal fixed
  proof remain open; backward Euler is still the implemented RTL contract.
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
  model measures 51.8 nA worst current error in 100,000 points and 0.0188% THD
  at 5 mV versus 0.0191% analytical, using 233,472 raw table bits (12.67 raw
  RAMB18 equivalents). Its standalone RTL is exact across 4,107 vectors at the
  existing eight-clock latency; structural synthesis reports 1,597 logic cells,
  37 DSP48E1s, and 8 RAMB18E1s. Solver and complete-stream modes are also
  bit-exact at the unchanged 126-clock solver schedule.
- The SystemVerilog tube lookup accepts physical Q-format voltages, is
  bit-exact for 4,096 randomized vectors, and has eight-clock latency.
- The nine-node chord corrector is bit-exact for 1,024 randomized/boundary
  vectors, including 18 saturation cases, with ten-clock latency; XC7 synthesis
  uses 9 DSP48E1 blocks and no block RAM.
- Exact RTL RHS and KCL engines stamp all ten capacitor histories and the
  physical conductance network. Each passes 1,024 vectors at 12 and 10 clocks.
- The integrated solver matches 512 sequential fixed-model samples bit-for-bit
  at every node and capacitor, completes three corrections plus its diagnostic
  residual in 126 of 128 available clocks, and reports no deadline misses.
- Hierarchical out-of-context XC7 synthesis of that complete solver reports
  8,024 estimated logic cells, 89 DSP48E1, and 47 RAMB18E1 blocks. This is an
  accuracy-first baseline; no Fmax is claimed before place-and-route.
- The selectable factorized solver also matches 512 persistent-state samples
  exactly at 126 clocks. Its hierarchy measures 9,194 logic cells, 110 DSP48E1s,
  and 8 RAMB18E1s: 39 fewer BRAMs at the cost of 21 DSPs and 1,170 logic cells.
- The complete 48 kHz reference stream—16× interpolation, nonlinear circuit,
  saturating output-format conversion, and 16× decimation—matches 64 consecutive
  Python outputs exactly with zero diagnostic events. Structural synthesis is
  13,170 estimated XC7 logic cells, 137 DSP48E1s, and 47 RAMB18E1s.
- The factorized stream independently matches 64 outputs / 1,024 nonlinear
  updates with zero diagnostics. It synthesizes to 14,366 logic cells, 158
  DSP48E1s, and 8 RAMB18E1s. Both modes remain explicit while broader accuracy
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
  cells / 4 DSPs for RHS and 7,804 logic cells / 72 DSPs for KCL.
- The same KCL block now has an explicit trapezoidal mode. It remains ten clocks
  and matches 1,024 independent residual/current-history vectors exactly,
  including 1,015 deliberately extreme Q4.44 current-saturation cases. The
  original backward-Euler vector set remains exact and warning-free.
- The integrated wide factorized solver matches Python bit-for-bit for 512
  sequential samples, including every node, capacitor, residual, and diagnostic.
  The measured schedule is 116 clocks, leaving 12 of 128 clocks, with zero test
  diagnostics. Hierarchical XC7 synthesis is 11,981 logic cells, 122 DSP48E1s,
  and 8 RAMB18E1s; Fmax remains unmeasured.
- The explicitly selectable trapezoidal solver also matches 512 persistent
  samples exactly, including ten Q4.44 current histories, at the unchanged
  116-clock latency. Its separate chord-inverse ROM is required by the doubled
  capacitor companions. Structural synthesis measures 12,451 logic cells,
  122 DSP48E1s, and 8 RAMB18E1s: +470 cells and no DSP/BRAM change versus
  backward Euler. This is structural evidence only; Fmax remains unmeasured.
- The corresponding complete 48 kHz stream matches 64 outputs spanning 1,024
  nonlinear updates exactly with zero diagnostics. Structural synthesis is
  16,993 logic cells, 170 DSP48E1s, and 8 RAMB18E1s, so the mono reference fits
  the provisional A7-100T resource envelope but leaves only 70 of 240 DSPs.
- A 23,040-sample captured RTL run at 5 mV / 1 kHz is Q32 bit-exact to fixed
  Python. Measured directly from RTL output, gain/phase error versus analytical
  float is -0.000054 dB / -0.000187 degrees, THD is 0.019371% versus 0.019059%,
  and raw/mean-removed residual is -63.83 / -88.45 dB.
- Captured solver output at 100 Hz, 1 kHz, 10 kHz, and 20 kHz remains Q32
  bit-exact to fixed Python. Against analytical float, maximum gain/phase error
  is 0.000194 dB / 0.000982 degrees with zero runtime diagnostics. This is an
  RTL-simulation result, not an FPGA or analog measurement.
- A captured 100 ms overload campaign matches all fixed nodes, capacitor states,
  outputs, and diagnostics for 384,000 total solver updates. The 20 mV burst
  reaches the 10% / 1% recovery thresholds in 8.47 / 14.92 ms. Bursts at 0.5 V
  and above remain outside even the 10% threshold after 85 ms in both analytical
  and RTL trajectories. Solver residual failures begin at 1.0 V; the 1.5 V case
  has 4,046 modeled-tube range clips and 729 safe scale fallbacks but no arithmetic
  saturation.
- A downstream, explicitly non-reference output guard now starts muted, applies
  a configurable sample-qualified linear ramp, bypasses exactly at unity, and
  synchronously clamps held output on a fault. Its warning-free RTL regression
  passes signed rounding/reset/control cases; generic XC7 synthesis reports 171
  logic cells, 2 DSP48E1s, and no block RAM.
- The guarded wide-stream top now enforces model-change sequencing: linear
  ramp-down, frame-aligned core reset, 64-output muted warmup, acknowledgment,
  and ramp-up. A warning-free integration regression proves no reset or warmup
  sample escapes before mute. Structural synthesis reports 17,142 logic cells,
  172 DSP48E1s, and 8 RAMB18s; this remains an unplaced estimate.
- A four-stage 16× half-band reference provides at least 91.6 dB per-stage image
  rejection and suppresses the measured cubic 45 kHz→3 kHz decimation alias to
  -137.8 dB with bit-accurate Q8.24/Q1.23 MACs. An 8,192-output RTL capture now
  reproduces -137.814 dB exactly with zero saturation. A separate complete-tube
  0.5 V / 15 kHz capture is also exact, but already contains a 1.402 mV 3 kHz
  component before decimation; its output 3 kHz bin is therefore not mislabeled
  as isolated 45→3 kHz alias energy.

There is no serial-audio interface, control/sequencing wrapper, fabricated
analog front end, converter board, named-part timing result, or physical
measurement yet. The implemented mute primitive is not independent analog
speaker protection.

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
make state-drift                    # one-second silence/click state audit
make state-wide                     # wide-state candidate on the same audit
make state-wide-audio               # 5 mV/1 kHz legacy/wide A/B
make wide-rtl-audio                 # capture and measure 23,040 RTL samples
make wide-rtl-frequency             # captured 100 Hz-20 kHz solver sweep
make wide-rtl-overload              # captured 100 ms overload/recovery sweep
make wide-stream-rtl-alias          # captured nonlinear decimation-alias test
make overload-study                 # grid conduction, clipping, recovery
make overload-trapezoidal           # fixed/float trapezoidal burst comparison
make overload-wide                  # same bursts with wide-state candidate
make overload-iterations            # three-to-six-pass solver trade
python3 scripts/study_lut_resolution.py
python3 scripts/analyze_frontend.py
python3 scripts/design_resampler.py
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
make halfband-rtl                  # exact 2x units and complete 16x streams
make stream-rtl                    # complete 48 kHz reference stream
make stream-factorized-rtl         # complete smooth-tube reference stream
make stream-wide-rtl               # complete wide-state reference stream
make guarded-stream-rtl            # mute/reset/warmup model-change sequence
make mute-rtl                      # reset/ramp/fault output safety primitive
make synth                         # generic XC7 structural estimate
make synth-factorized              # factorized tube structural estimate
make synth-chord                   # generic XC7 chord-corrector estimate
make synth-wide-chord              # wide-state corrector structural estimate
make synth-wide-network            # wide RHS/KCL structural estimates
make synth-solver                  # hierarchical complete-solver estimate
make synth-solver-factorized       # smooth-tube hierarchy/resource trade
make synth-wide-solver             # wide-state hierarchy estimate
make synth-trapezoidal-solver      # trapezoidal hierarchy estimate
make synth-stream-wide             # complete wide-state stream estimate
make synth-stream-guarded          # wide stream plus safety/control guard
make synth-halfband                # complete interpolator/decimator estimates
make synth-stream                  # complete reference-stream estimate
make synth-stream-factorized       # smooth-tube stream resource estimate
make synth-mute                    # output ramp structural estimate
```

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
path is resolving overload convergence without breaking the 128-clock deadline,
then extending fixed/float and captured-RTL equivalence across long state,
frequency, level, and recovery tests.

## License

GPL-3.0; see [`LICENSE`](LICENSE).
