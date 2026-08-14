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

The asynchronous FIFO test uses unrelated 10 ns write and 14 ns read clocks. It
fills exactly, rejects and records a ninth word, drains in order, records an
empty read, clears both owning-domain sticky flags, and preserves 128 further
words over repeated pointer wraps. The RTL includes Gray one-bit-transition and
blocked-pointer formal assertions under `FORMAL`; they are not claimed as proven
because SymbiYosys/SMT solvers are unavailable in the current environment.

The I²S test passes 16 stereo frames through independent transmitter and
receiver blocks, including signed 24-bit maximum/minimum and pseudorandom-like
channel patterns. A separate monitor—not the receiver—requires 31 stable sampled
edges between LRCLK changes and a zero serial delay bit on each transition.
Starving the next frame sets transmitter underflow; a one-edge LRCLK corruption
sets receiver framing error; both sticky flags clear in the BCLK domain.

The bidirectional bridge test uses a 20 ns BCLK and an unrelated, phase-offset
13 ns fabric clock. An I²S transmitter supplies 20 nonzero signed stereo frames;
the fabric scoreboards each receive handshake, loops each frame back, and
deliberately removes receive ready one cycle in four. Held valid/data stability
is checked during every stall. A second I²S receiver requires the exact same 20
frames in order. Bridge framing and both FIFO overflow/underflow pairs remain
clear; deliberate zero output during pipeline startup sets the serial underflow
flag, which is then cleared in the BCLK domain.

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
scripts/characterize_wide_solver_rtl_overload.py --banked --terminal-correction  terminal H1-H10/clipping/recovery
scripts/characterize_wide_stream_rtl_alias.py     captured cubic alias/full stream
scripts/process_wav.py                         explicit-voltage fixed V1 WAV path
scripts/compare_wav.py                         latency/gain/residual WAV comparison
scripts/run_wav_null_regression.py             synthetic end-to-end audio gate
scripts/generate_audio_regression_vectors.py   original physical-level fixtures
scripts/run_audio_regression.py                fixed distortion/IMD/overload gate
scripts/characterize_overload_recovery.py     grid conduction and recovery
scripts/characterize_overload_recovery.py --trapezoidal  fixed integrator overload
scripts/characterize_long_overload_recovery.py  235 ms physical-model tail
scripts/measure_severe_overload_recovery.py     direct 850 ms multimode tail
scripts/measure_seven_second_recovery.py        complete severe recovery timing
scripts/study_overload_iterations.py          pass-count/deadline trade
scripts/study_banked_chord_iterations.py      banked pass-count waveform trade
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
| banked error decomposition | 100 ms, 1.0/1.5 V per mode | all intermediate layers converge; fixed circuit/state/chord burst error 6.40--19.07 mV vs <=0.168 mV integer tube evaluation |
| grid-current resolution study | 128/256/512/1,024 entries | implemented 1,024: 12.55 nA exact-mapping worst; 1.5 V burst -72.87/-81.77 dB and final 0.631/0.321 mV |
| banked correction-count study | 3--6 passes, 100 ms, 1.0/1.5 V | fourth improves burst 5.65--9.02 dB; six-pass residual <=0.207 uA; fourth projects to 145 clocks |
| backward-Euler terminal correction RTL | 512 sequential plus 18,432 overload updates | every state/diagnostic exact, constant 127 clocks, zero events; output-exact to four-pass |
| backward-Euler terminal correction synthesis | Yosys 0.66 structural | 13,296 LC, 120 DSP48E1, 8 RAMB18E1; no Fmax claim |
| captured banked terminal RTL overload | 384,000 updates; 20 mV/0.5/1.0/1.5 V bursts | full state exact, zero diagnostics; burst RMS error 0.288/1.237/4.895/6.817 mV; H2--H10 ratio error <=0.00122 percentage points |
| captured trapezoidal banked terminal overload | 384,000 updates; 20 mV/0.5/1.0/1.5 V bursts | full state/current history exact, zero diagnostics; burst RMS error 0.276/1.210/4.709/3.604 mV |
| banked terminal 48 kHz stream vs fixed | 64 outputs / 1,024 circuit samples | bit-exact, zero diagnostics, 127-clock solver |
| banked terminal stream synthesis | Yosys 0.66 structural | 18,466 LC, 168 DSP48E1, 8 RAMB18E1; no Fmax claim |
| trapezoidal banked terminal solver synthesis | Yosys 0.66 structural | 14,945 LC, 174 DSP48E1, 8 RAMB18E1; no Fmax claim |
| trapezoidal banked terminal stream | 64 outputs / 1,024 circuit samples plus synthesis | bit-exact, zero diagnostics, 127 clocks; 20,241 LC / 222 DSP48E1 / 8 RAMB18E1; no Fmax claim |
| captured trapezoidal banked terminal stream frequency | 4,800 outputs each at 100 Hz/1/10/20 kHz | Q24 exact; <=0.000134 dB / <=0.000444 degree vs float; -74.79 dB worst linear-detrended null; zero diagnostics |
| fixed V1 WAV/null regression | 1,024 frames; 11/73/997/7013 Hz plus synthetic pop | trapezoidal terminal path zero diagnostics/clips; injected 23-sample delay recovered; raw/latency-only/gain-aligned residual +2.405/-30.462/-100.810 dB |
| deterministic PCM audio suite | 9 vectors / 32,448 outputs / 519,168 internal updates | zero diagnostics/clips; 5/0.5 mV H2–H10 THD 0.019826%/0.011559%; explicit 1/18/21 kHz two-tone products |
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
| captured RTL nonlinear alias | 131,072 internal / 8,192 outputs | cubic -137.814 dBc; full-tube 45 kHz fold Q24-zero; complete family effect -176.96 dBc below rounding closure; zero saturation |
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
| asynchronous FIFO RTL | depth 8×32; unrelated 100/71.4 MHz clocks | exact directed full/empty plus 128 wrapped words; sticky faults clear in owning domains |
| asynchronous FIFO XC7 synthesis | Yosys 0.66 structural | 114 LC / 323 FF / no DSP or RAM; small memory expanded to registers; no Fmax/CDC claim |
| I²S protocol loopback | 16 signed stereo frames; 24-bit/32-slot | exact channels/endpoints; independent slot/delay monitor; directed framing/underflow flags |
| I²S receiver/transmitter synthesis | Yosys 0.66 structural | RX 35 LC/105 FF; TX 97 LC/137 negative-edge FF; no warnings/DSP/RAM/Fmax claim |
| bidirectional I²S/CDC bridge RTL | 20 stereo frames; unrelated 50/76.9 MHz stress clocks | exact BCLK→fabric→BCLK order under one-in-four receive stalls; owning-domain diagnostics checked |
| bidirectional I²S/CDC bridge synthesis | Yosys 0.66 flattened structural | 549 LC / 1,531 FF / no DSP or RAM; two 8×64 memories register-expanded; no Fmax/CDC claim |
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

`scripts/compare_wav.py` implements that policy for integer PCM. It searches a
bounded signed latency using DC-removed normalized correlation; positive lag
means the candidate is delayed. Short searches use direct dot products and long
recordings use FFT dot products with exact-overlap mean/energy normalization.
The reported search bound retains at least half of a short fixture, preventing
spuriously perfect edge correlations over only a few samples. It always records
zero-lag metrics. Silence/constant streams return deterministic zero latency and
explicitly report that latency is not identifiable. Integer
alignment is on by default, while gain and fractional-delay alignment are opt-in.
The gain fit is a scalar candidate multiplier and never fits a DC offset. The
fractional option uses a parabolic correlation-peak estimate and labeled linear
interpolation. Reports preserve metrics before and after gain, the applied
transformations, a residual WAV clip count, and optional Hann-windowed spectrum.

`scripts/process_wav.py` is the offline physical-scaling boundary for the actual
fixed V1 stream. It requires 48 kHz integer PCM, an explicitly named integration/
solver mode, and peak volts corresponding to WAV full scale on input and output.
It does not normalize. Stereo files are scheduled as independent model instances
and each channel receives its own diagnostic report. This is an offline software
path, not evidence of stereo RTL scheduling or an I²S implementation.

The generated audio suite is original repository content, not licensed music.
Each manifest entry states input/output peak volts at PCM full scale. Harmonic
and arbitrary-tone amplitudes are simultaneous least-squares fits, so a
non-coherent analysis interval does not leak a fundamental into the reported
harmonics. The 19/20 kHz fixture reports selected 1/18/21 kHz spectral products
relative to the combined fundamentals; it is deliberately named `ccif_like`
and is not presented as a standards-compliant CCIF/ITU scalar. Silence produces
174.6 uV RMS of deterministic initialized fixed-model offset over the first
1,024 outputs; that is numerical/startup behavior, not stochastic circuit noise.

The complete-stream frequency report performs no alignment. It fits the raw
48 kHz input/output with absolute sample indices. A separate identity-path
interpolator/decimator measurement establishes the 51-sample causal converter
delay; only the field named `circuit_attributed_after_converter_removal`
subtracts that converter phase. End-to-end fields retain the physical latency.

Implemented audio fixtures now cover silence, log sweep, low-level/nominal sine,
multitone, selected high-frequency intermodulation products, synthetic pops,
11 Hz warp, and grid-conduction overload. Still missing are a separately gated
impulse response, standardized SMPTE/CCIF measurement procedures, long WAV-level
recovery, and licensed/locally supplied music. Every found numerical bug gets
the smallest durable regression vector.

## Physical verification plan

Calibrate generator/interface/analyzer independently, then measure cartridge
load, front-end/ADC, digital loopback, DAC/line, and complete path in stages.
Archive raw samples, instrument settings, calibration date, environment, board
revision, FPGA bitstream hash, model version, and control-register dump. A real
Kennedy circuit comparison requires the same stimulus capture split to hardware
and FPGA, followed by gain/latency alignment and variation reporting. Listening
is useful product evidence but never replaces electrical equivalence data.
