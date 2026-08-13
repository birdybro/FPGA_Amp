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
alignment. The wide-stream bench also accepts up to 8,192 external samples and
can capture arbitrary exact trajectories for longer measurements. The
guarded-stream integration test covers muted startup, ramp-down before core
reset, 48 kHz phase-aligned reset release, muted warmup, one acknowledgment, and
unity-gain recovery. The standalone output-safety test covers reset, positive/negative rounding,
sample-qualified gain changes, exact-unity bypass, graceful ramp-down, and a
forced clamp with and without a valid input sample.

The analog/reference commands are intentionally separate so a missing external
tool is not reported as a pass:

```text
make spice                          ngspice DC/AC/transient
scripts/spice_level_sweep.py        H1-H10/THD/gain compression
scripts/compare_spice_python.py     transient residual
scripts/compare_spice_python_frequency.py  four-point integrator/SPICE sweep
scripts/characterize_solver.py      fixed-iteration residual/convergence
scripts/study_lut_resolution.py     BRAM/error trade study
scripts/study_factorized_tube.py    factorized current/circuit accuracy
scripts/analyze_factorized_domain.py  paired cutoff-domain equivalence audit
scripts/characterize_factorized_frequency.py  six-point audio-band equivalence
scripts/characterize_state_drift.py           one-second silence/click state audit
scripts/characterize_wide_state_audio.py      nominal-level state-format A/B
scripts/analyze_linearized_modes.py           physical G+sC pole extraction
scripts/characterize_wide_solver_rtl.py       captured 1 kHz RTL metrics/null
scripts/sweep_wide_solver_rtl.py              captured four-point RTL sweep
scripts/sweep_wide_solver_rtl.py --trapezoidal  captured integrator sweep
scripts/characterize_trapezoidal_solver_rtl_recovery.py  accepted long recovery
scripts/sweep_wide_stream_rtl.py --trapezoidal  captured complete 48 kHz sweep
scripts/characterize_wide_solver_rtl_overload.py  captured 100 ms burst/recovery
scripts/characterize_wide_stream_rtl_alias.py     captured cubic alias/full stream
scripts/characterize_overload_recovery.py     grid conduction and recovery
scripts/characterize_overload_recovery.py --trapezoidal  fixed integrator overload
scripts/characterize_long_overload_recovery.py  235 ms physical-model tail
scripts/measure_severe_overload_recovery.py     direct 850 ms multimode tail
scripts/measure_seven_second_recovery.py        complete severe recovery timing
scripts/study_overload_iterations.py          pass-count/deadline trade
scripts/study_trapezoidal_overload.py         floating integrator stability
scripts/characterize_factorized_frequency.py --trapezoidal  fixed integrator sweep
scripts/run_synthesis.py            XC7 structural resource report
```

## Current acceptance record

| Comparison | Evidence | Result |
|---|---|---|
| ideal RIAA vs E1 table | published frequencies | 0.0705 dB max table/equation difference |
| Koren vs approximate GE curves | checked digitization | 0.0131 mA RMS, 0.0346 mA worst |
| physical V1 vs ideal RIAA | ngspice AC, 20 Hz–20 kHz | -0.919…+0.000 dB, 0.364 dB RMS |
| Python MNA vs ngspice | 5 mV peak, 1 kHz, last 10 ms | -53.10 dB normalized residual, 0.00179 dB gain error |
| backward Euler vs ngspice frequency | 5 mV, 100 Hz/1/10/20 kHz | <=0.0646 dB gain; phase rises from 0.0244 to 4.7197 degrees |
| trapezoidal float candidate vs ngspice | 5 mV, 10/20 kHz | <=0.00846 dB gain, <=0.0582 degree phase; zero failed solves |
| trapezoidal overload stability | 20 mV/0.5/1.0/1.5 V, 85 ms post-burst | finite/convergent; 20 mV recovery within 2.6 us of BE |
| long trapezoidal overload recovery | 0.5/1.0/1.5 V, 235 ms post-burst | 0.5 V 10% recovery 146.552 ms; 98.2--118.1 ms fitted modes; severe crossings remain labeled projections |
| severe trapezoidal overload recovery | 1.0/1.5 V, 835 ms post-burst | 1.0 V sustained 10% 270.112 ms; 1.5 V not 10%; 413--451x cancellation rebound falsifies early fit |
| linearized physical-circuit modes | 9-node G+sC at tube DC bias | rank 8; all stable; recovery modes 143.936 ms / 1.067763 s; slow mode >99.999999% output-cap energy |
| complete severe floating recovery | 1.0/1.5 V, 6.985 s post-burst | all 10%/1%/1 mV crossings measured; latest 6.370790 s; chord/Newton overlap <=33.2 nV |
| fixed trapezoidal vs trapezoidal float | 5 mV, 20/50/100/1k/10k/20k Hz | <=0.000131 dB gain, <=0.000784 degree phase; zero diagnostics |
| fixed trapezoidal overload | 20 mV/0.5/1.0/1.5 V, 5 ms burst | clean through 0.5 V; 1,107/1,690 failures at 1/1.5 V; 203.34 uA max capacitor current |
| 2-pass vs converged solver | 20 mV peak, 1 kHz | all samples ≤100 pA residual; -136.84 dB output residual |
| LUT vs analytical tube | 100,000 random full-range points | 0.139 µA mean, 9.33 µA worst |
| factorized fixed vs analytical tube | 100,000 quantized full-range points plus dense grid probe | plate 8.31 nA mean / 50.56 nA worst; grid 12.55 nA worst / 2.82 nA active RMS; 14.22 raw RAMB18 equivalents |
| factorized fixed circuit vs analytical | 5 mV / 0.5 V, 1 kHz, 20–30 ms | 0.0188% / 2.2419% THD vs 0.0191% / 2.2417% |
| factorized fixed low-level null | 5 mV, 1 kHz, 20–30 ms | -42.90 dB raw; -59.63 dB mean-removed diagnostic; -2.840 mV mean; 0.00958° phase error |
| factorized fixed frequency sweep | 5 mV, 20/50/100/1k/10k/20k Hz | ≤0.00846 dB gain, ≤0.0729° phase; zero fixed diagnostics |
| factorized overload burst | 5 ms at 20 mV / 0.5 / 1.0 / 1.5 V | residual clean through 0.5 V; failures at 1.0 V; legacy -5 V flags later proven output-neutral |
| overload solver iterations | 3–6 chord corrections, 1.0/1.5 V | six still fails; 213-clock serialized projection |
| long state/click recovery | 1 s, +/-100 mV one-sample clicks | fixed late output -5.368 mV vs 7.2 uV analytical RMS; diagnostics silent |
| wide-state click recovery | same 1 s stimulus | 38.74 uV late raw residual, 5.01 nA max KCL residual, zero diagnostics |
| wide-state nominal audio | 5 mV/1 kHz, 20--30 ms | -63.83 dB raw null, -0.000058 dB gain, -0.000187 degree phase error |
| wide-state frequency sweep | 5 mV, 20/50/100/1k/10k/20k Hz | <=0.000196 dB gain, <=0.000982 degree phase, zero diagnostics |
| wide-state overload burst | 20 mV / 0.5 / 1.0 / 1.5 V | recovery improved; 1,122/1,695 failures at 1/1.5 V; 729 safe scale fallbacks at 1.5 V |
| factorized RTL vs fixed tube | 4,110 randomized/directed vectors | bit-exact including all expected clip flags, latency 8 |
| RTL vs fixed LUT | 4,096 deterministic vectors | bit-exact, latency 8 |
| chord RTL vs fixed correction | 1,024 deterministic vectors | bit-exact, latency 10, 18 saturation cases |
| wide chord RTL vs fixed correction | 1,024 deterministic vectors | bit-exact, latency 10, 95 saturation vectors; Q30/Q34/Q40 |
| wide RHS RTL vs fixed network | 1,024 deterministic vectors | bit-exact, latency 2 |
| wide KCL RTL vs fixed network | 1,024 deterministic vectors | bit-exact, latency 10; 48 fallback / 18 overflow vectors; delayed tube current |
| trapezoidal wide KCL RTL vs fixed | 1,024 deterministic vectors | bit-exact residual/current state, latency 10; 1,013 deliberate current-saturation vectors |
| trapezoidal wide solver RTL vs fixed | 512 sequential samples | bit-exact all 29 state words and diagnostics, latency 116, zero events |
| trapezoidal wide solver synthesis | Yosys 0.66 structural | 12,786 LC, 120 DSP48E1, 8 RAMB18E1; no Fmax claim |
| factorized cutoff-domain audit | paired 12 ms / 1.5 V runs per integrator | -5 V flags classified; -8 V outputs bit-exact; zero expanded-domain events |
| banked wide solver RTL vs fixed | 36,864 total 1.0/1.5 V updates | every state exact, every bank selected, latency 116; zero residual/range/arithmetic events |
| banked wide solver synthesis | Yosys 0.66 structural | BE 13,302 LC; trap 13,840 LC; both 120 DSP48E1 / 8 RAMB18E1 |
| banked solver vs full Newton | 100 ms, 20 mV/0.5/1.0 V per mode | raw burst error <=-75.28 dB; no alignment or diagnostics; 1 V final RMS 0.372/0.291 mV |
| Vgk-slew-qualified bank selector | 100 ms, 0.5/1.0/1.5 V per mode | <=1 V bit-exact to prior selector; zero 1.5 V residual failures; pre-resolution severe baseline -61.80/-62.12 dB |
| banked error decomposition | 100 ms, 1.0/1.5 V per mode | all floating layers converge; after grid refinement fixed evaluation/state/chord dominates burst RMS |
| grid-current resolution study | 128/256/512/1,024 entries | implemented 1,024: 12.55 nA exact-mapping worst; 1.5 V burst -72.87/-81.77 dB and final 0.631/0.321 mV |
| trapezoidal 48 kHz stream vs fixed | 64 outputs / 1,024 circuit samples | bit-exact, zero diagnostics, 116-clock solver |
| trapezoidal stream synthesis | Yosys 0.66 structural | 17,735 LC, 168 DSP48E1, 8 RAMB18E1; no Fmax claim |
| wide factorized solver RTL vs fixed | 512 sequential samples | bit-exact all 19 states and diagnostics, latency 116, zero events |
| wide factorized solver synthesis | Yosys 0.66 structural | 12,544 LC, 120 DSP48E1, 8 RAMB18E1; no Fmax claim |
| wide 48 kHz stream vs fixed composition | 64 outputs / 1,024 circuit samples | bit-exact, zero diagnostics, 116-clock solver |
| wide stream synthesis | Yosys 0.66 structural | 17,492 LC, 168 DSP48E1, 8 RAMB18E1; no Fmax claim |
| captured wide RTL nominal audio | 23,040 samples, 5 mV/1 kHz | Q32 exact; -63.834 dB raw null; 0.019371% THD; zero diagnostics |
| captured wide RTL frequency sweep | 5 mV, 100 Hz/1/10/20 kHz | Q32 exact; <=0.0001943 dB gain, <=0.0009814 degree phase; zero diagnostics |
| captured trapezoidal RTL frequency sweep | 5 mV, 100 Hz/1/10/20 kHz | all states exact; <=0.000128 dB / <=0.000784 degree vs float; zero diagnostics |
| captured trapezoidal RTL recovery | 384,000 updates, 0.5 V burst / 235 ms post | all states exact; zero diagnostics; 10% recovery 146.570 ms, +18.23 us vs float |
| captured trapezoidal complete stream | 4,800 outputs each at 5 mV, 100 Hz/1/10/20 kHz | Q24 exact; <=0.000111 dB / <=0.001185 degree vs composed float; zero diagnostics; converter delay 51 samples |
| captured wide RTL overload/recovery | 384,000 updates; 20 mV/0.5/1.0/1.5 V bursts | full state exact; zero saturation; failures at 1 V; range clips at 1.5 V |
| captured RTL nonlinear alias | 131,072 cubic internal / 8,192 outputs | bit-exact; -137.814 dBc 45 kHz to 3 kHz alias; zero saturation |
| RHS RTL vs fixed network | 1,024 deterministic vectors | bit-exact, latency 12 |
| KCL RTL vs fixed residual | 1,024 deterministic vectors | bit-exact, latency 10, 18 saturation vectors |
| full mono RTL vs fixed circuit | 512 sequential samples | bit-exact all state/diagnostics, latency 126 |
| full mono XC7 synthesis | Yosys 0.66 structural | 8,024 LC, 89 DSP48E1, 47 RAMB18E1; no Fmax claim |
| factorized mono RTL vs fixed circuit | 512 sequential samples | bit-exact all state/diagnostics, latency 126 |
| factorized mono XC7 synthesis | Yosys 0.66 structural | 9,148 LC, 108 DSP48E1, 8 RAMB18E1; no Fmax claim |
| 48 kHz RTL stream vs fixed composition | 64 outputs / 1,024 circuit samples | bit-exact, zero diagnostics |
| full stream XC7 synthesis | Yosys 0.66 structural | 13,170 LC, 137 DSP48E1, 47 RAMB18E1; no Fmax claim |
| factorized 48 kHz stream vs fixed | 64 outputs / 1,024 circuit samples | bit-exact, zero diagnostics |
| factorized stream XC7 synthesis | Yosys 0.66 structural | 14,290 LC, 156 DSP48E1, 8 RAMB18E1; no Fmax claim |
| output mute/ramp RTL | directed reset/ramp/fault sequence | exact expected samples and gain; warning-free Verilator |
| output mute/ramp XC7 synthesis | Yosys 0.66 structural | 171 LC, 2 DSP48E1, no RAM; no Fmax claim |
| guarded wide stream RTL | startup plus one state-reset transaction | warning-free; mute precedes reset; phase clean; one ack; unity restored |
| guarded wide stream synthesis | Yosys 0.66 structural | 17,562 LC, 170 DSP48E1, 8 RAMB18E1; no Fmax claim |
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

The complete-stream frequency report performs no alignment. It fits the raw
48 kHz input/output with absolute sample indices. A separate identity-path
interpolator/decimator measurement establishes the 51-sample causal converter
delay; only the field named `circuit_attributed_after_converter_removal`
subtracts that converter phase. End-to-end fields retain the physical latency.

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
