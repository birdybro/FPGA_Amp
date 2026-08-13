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
- The 128 × 256 Q0.31 tube LUT has 0.139 µA mean and 9.33 µA worst absolute
  error in a 100,000-point full-range probe.
- The complete bit-accurate three-pass chord candidate is -57.87 dB normalized
  residual from analytical/full-Newton float on the initial multitone; isolated
  state/chord error is -70.33 dB relative to the same circuit using the tube LUT.
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
- A four-stage 16× half-band reference provides at least 91.6 dB per-stage image
  rejection and suppresses the measured cubic 45 kHz→3 kHz decimation alias to
  -137.8 dB with bit-accurate Q8.24/Q1.23 MACs; polyphase RTL is not implemented yet.

There is no 48/768 kHz resampler RTL, serial-audio wrapper, fabricated analog
front end, converter board, or physical audio measurement yet.

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
python3 scripts/characterize_solver.py
python3 scripts/study_solver_architecture.py
python3 scripts/compare_fixed_float.py
python3 scripts/study_lut_resolution.py
python3 scripts/analyze_frontend.py
python3 scripts/design_resampler.py
make rtl                           # lint + 4,096 bit-exact vectors
make chord-rtl                     # lint + 1,024 circuit-correction vectors
make network-rtl                   # RHS/KCL bit-exact unit tests
make solver-rtl                    # 512-sample persistent-state integration
make synth                         # generic XC7 structural estimate
make synth-chord                   # generic XC7 chord-corrector estimate
make synth-solver                  # hierarchical complete-solver estimate
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
path is wider frequency/overload equivalence, then bit-exact 16× interpolation
and decimation around the now-complete mono circuit solver.

## License

GPL-3.0; see [`LICENSE`](LICENSE).
