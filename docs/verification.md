# Verification

## Reproducible gates

`make test` runs the mathematical unit suite and the bit-exact RTL test. The
reference tests cover the canonical RIAA table, AT-VM95E resonance, 12AX7 bias,
LUT absolute error, V1 DC nodes, 1 kHz gain, and solver convergence. Verilator
checks 4,096 deterministic randomized tuples including range boundaries and
requires exact `Ip`, `Ig`, clipping, valid timing, and eight-clock latency.
The chord-corrector test requires exact nine-node outputs and saturation status
for 1,024 vectors, including forced positive/negative limits, at ten clocks.
The network tests require 1,024 exact RHS and 1,024 exact KCL vectors. The
integration test then carries one persistent circuit state through 512 samples
and compares every node, capacitor, residual, output, and diagnostic count.
The complete stream test independently composes the fixed interpolator, 1,024
fixed nonlinear updates, output format conversion, and decimator, then requires
64 consecutive 48 kHz RTL outputs to be exactly equal without latency/gain
alignment.

The analog/reference commands are intentionally separate so a missing external
tool is not reported as a pass:

```text
make spice                          ngspice DC/AC/transient
scripts/spice_level_sweep.py        H1-H10/THD/gain compression
scripts/compare_spice_python.py     transient residual
scripts/characterize_solver.py      fixed-iteration residual/convergence
scripts/study_lut_resolution.py     BRAM/error trade study
scripts/study_factorized_tube.py    factorized current/circuit accuracy
scripts/run_synthesis.py            XC7 structural resource report
```

## Current acceptance record

| Comparison | Evidence | Result |
|---|---|---|
| ideal RIAA vs E1 table | published frequencies | 0.0705 dB max table/equation difference |
| Koren vs approximate GE curves | checked digitization | 0.0131 mA RMS, 0.0346 mA worst |
| physical V1 vs ideal RIAA | ngspice AC, 20 Hz–20 kHz | -0.919…+0.000 dB, 0.364 dB RMS |
| Python MNA vs ngspice | 5 mV peak, 1 kHz, last 10 ms | -53.10 dB normalized residual, 0.00179 dB gain error |
| 2-pass vs converged solver | 20 mV peak, 1 kHz | all samples ≤100 pA residual; -136.84 dB output residual |
| LUT vs analytical tube | 100,000 random full-range points | 0.139 µA mean, 9.33 µA worst |
| factorized fixed vs analytical tube | 100,000 quantized full-range points | 10.5 nA mean, 51.8 nA worst; 12.67 raw RAMB18 equivalents |
| factorized fixed circuit vs analytical | 5 mV / 0.5 V, 1 kHz, 20–30 ms | 0.0188% / 2.2419% THD vs 0.0191% / 2.2417% |
| factorized RTL vs fixed tube | 4,107 randomized/directed vectors | bit-exact, 5 clip cases, latency 8 |
| RTL vs fixed LUT | 4,096 deterministic vectors | bit-exact, latency 8 |
| chord RTL vs fixed correction | 1,024 deterministic vectors | bit-exact, latency 10, 18 saturation cases |
| RHS RTL vs fixed network | 1,024 deterministic vectors | bit-exact, latency 12 |
| KCL RTL vs fixed residual | 1,024 deterministic vectors | bit-exact, latency 10, 18 saturation vectors |
| full mono RTL vs fixed circuit | 512 sequential samples | bit-exact all state/diagnostics, latency 126 |
| full mono XC7 synthesis | Yosys 0.66 structural | 8,024 LC, 89 DSP48E1, 47 RAMB18E1; no Fmax claim |
| 48 kHz RTL stream vs fixed composition | 64 outputs / 1,024 circuit samples | bit-exact, zero diagnostics |
| full stream XC7 synthesis | Yosys 0.66 structural | 13,170 LC, 137 DSP48E1, 47 RAMB18E1; no Fmax claim |
| fixed vs analytical level sweep | 0.5 mV–5 V, 1 kHz, 20–30 ms | first ≥1 dB compression 1.1 V; residual-limit failure 1.0 V; LUT clip 1.1 V |
| fixed vs analytical at 5 mV | H2–H10 least-squares fit | 0.0733% vs 0.0191% THD; +0.0324 dB gain error |
| fixed vs analytical at 0.5 V | H2–H10 / waveform | 2.2395% vs 2.2417% THD; -55.98 dB residual |
| synthesized RTL vs hardware | none | not validated |

## A/B and null methodology

Waveform comparison first selects a steady interval or estimates latency by
cross-correlation, then performs integer alignment, optional fractional-delay
alignment, and least-squares gain reporting. The default residual does **not**
gain-normalize away a real amplitude error: raw residual RMS, normalized residual,
gain error, and worst sample error are separate fields. Fractional alignment must
be labeled because it can conceal phase/integration error.

Future audio regressions include silence, impulse, log sweep, low-level sine,
20/50/100 Hz and 1/10/20 kHz levels, multitone, SMPTE/CCIF IMD, synthetic pops,
5–20 Hz warp, grid-conduction overload, recovery, and licensed/locally supplied
music. Every found numerical bug gets the smallest durable regression vector.

## Physical verification plan

Calibrate generator/interface/analyzer independently, then measure cartridge
load, front-end/ADC, digital loopback, DAC/line, and complete path in stages.
Archive raw samples, instrument settings, calibration date, environment, board
revision, FPGA bitstream hash, model version, and control-register dump. A real
Kennedy circuit comparison requires the same stimulus capture split to hardware
and FPGA, followed by gain/latency alignment and variation reporting. Listening
is useful product evidence but never replaces electrical equivalence data.
