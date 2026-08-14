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
unity-gain recovery. The standalone output-safety test covers reset,
positive/negative rounding, sample-qualified gain changes, exact-unity bypass,
graceful ramp-down, and a forced clamp with and without a valid input sample.

`make formal-mute` independently uses the Yosys 0.66 built-in SAT engine. After
one assumed reset clock it leaves sample data, validity, mute request, and force
mute arbitrary. Fifteen assertions cover reset state, synchronous force clamp,
valid timing, held state, the exact saturating gain transition, endpoint output,
gain monotonicity, and status decode. Temporal induction closes at depth 2. A
separate satisfiability run reaches `0xffff` gain after four accepted samples,
showing the reset assumptions admit the intended unmute path. Logs are retained
under `build/formal_output_mute_ramp/`.

The asynchronous FIFO test uses unrelated 10 ns write and 14 ns read clocks. It
fills exactly, rejects and records a ninth word, drains in order, records an
empty read, clears both owning-domain sticky flags, and preserves 128 further
words over repeated pointer wraps. The RTL includes Gray one-bit-transition and
blocked-pointer formal assertions under `FORMAL`; they are not claimed as proven
for all time. `make formal-async-fifo` uses `clk2fflogic` to retain independent
clock transitions and exhaustively checks 13 Gray-transition, blocked-pointer,
occupancy/watermark, valid, and sticky-fault properties through 32 global formal
steps after a disciplined shared-reset release. A separate satisfiable 24-step
trace reaches depth four and both overflow/underflow stickies. Unbounded
induction does not close with the current incomplete invariant set; the bounded
result also cannot represent analog metastability.

The held-bus snapshot test uses unrelated 10 ns source and 14 ns destination
clocks to require three exact 16-bit captures and recovery when the destination
is reset during an active request. `make formal-cdc-snapshot` separately leaves
both clock levels, request, and four-bit live data arbitrary after a disciplined
shared startup reset. Nine assertions cover destination capture provenance and
hold stability, exact source-domain data, one-cycle valid, completion bounded by
accepted requests, and idle only after all accepted requests complete for every
40-step interleaving. A separate satisfiable trace accepts and completes one
nonzero `0xa` transfer and returns to available. This is a bounded digital logic
result: it neither proves progress if a clock stops, models analog metastability,
nor covers an independently resetting destination in the formal environment.

The toggle-pulse CDC directed test transfers two source commands across
unrelated 10 ns/34 ns clocks. It also resets the destination while the retained
source toggle is one and requires exactly one replay after release; only
idempotent commands may use this primitive. `make formal-cdc-pulse` assumes a
new event is launched only after the previous event has been observed, then
leaves both clocks and source event timing arbitrary. Ten pipeline, decode,
pulse-width, at-most-one-outstanding, no-fabrication, and delivery-accounting
properties hold through 40 global steps. A satisfiable trace accepts and
delivers two events. Progress with a stopped clock, independently resetting
domains, events outside the separation contract, and analog metastability are
not proven.

The asynchronous audio-clock monitor's directed test uses 320-clock windows to
acquire three exact ten-edge measurements, reject an 11-edge window, reacquire,
clear retained evidence, reject a stopped clock as zero edges, and revoke live
state after BCLK reset. `make formal-audio-clock` uses a reduced four-clock,
one-edge, two-good-window instance with arbitrary BCLK/fabric clock levels and
clear timing after disciplined startup reset. Sixteen assertions cover exact
binary/Gray counter and synchronizer evolution, measurement cadence, every
window-state branch, measured delta, lock/count invariants, and sticky-clear
precedence through 32 global steps. A 48-step witness acquires lock and later
retains a bad-rate error while unlocked. This bounded digital proof does not
establish Gray-bus skew/placement, metastability MTBF, absolute clock accuracy,
or progress if either clock stops.

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

The calibration generator preserves 4,159 deterministic vectors in each
direction: signed endpoints, zero/negative coefficients, realistic study
coefficients, full coefficient range, and 4,096 seeded random tuples. Python and
one-clock RTL must agree exactly. The input test records 14 PCM endpoint events
and 51 invalid configurations. The output test deliberately produces 4,079
saturations and 52 invalid configurations; saturation is not weakened to make
random vectors pass. Both diagnostic blocks are cleared explicitly after the
count/sticky checks.

`make formal-audio-calibration` complements those vectors with arbitrary
full-width samples, coefficients, valid timing, and clears. Twelve assertions
cover the input conversion's signed-32 post-shift range, exact registered
valid/output/hold behavior in both directions, exact PCM24 clipping, saturating
endpoint/saturation counters, and invalid-configuration sticky precedence.
Yosys 0.66 SAT temporal induction closes at depth 2. A separate trace reaches
one endpoint event, one output saturation, and both invalid-configuration
stickies. This proves the digital arithmetic/control contract, not the physical
converter voltage calibration.

The frame-scheduler unit test reduces the period to eight clocks for directed
coverage while preserving the production phase relationship. A source holds a
nonzero frame until the one-clock ready pulse, leaves the next boundary empty,
and supplies a second signed-endpoint frame after that miss. An independent
one-clock preprocessing register and phase counter require outputs `[frame A,
zero, frame B]` only at consumer phase zero. Exactly one underflow is retained
and then cleared. The test does not claim asynchronous rate conversion.

The mode-0 SPI integration drives eight complete 80-bit frames at 5 MHz through
the real register bank and calibration guard, plus a ten-bit abort and withheld
response. `make formal-spi-control` independently leaves the asynchronous pins,
response channel, and diagnostic clear arbitrary. Eleven synchronization,
bit-count, request-field, response-state, saturating-count, frame-reset, and
sticky-precedence assertions hold through 32 fabric clocks. Because a request
requires 40 synchronized input bits, a separate 100-step satisfiable trace
reaches request decode plus short-frame and underflow evidence. The result is
explicitly bounded and does not prove analog metastability, a placed SCLK rate,
or complete-frame wire order; the directed integration supplies the latter.

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
scripts/run_mute_formal.py          safety-ramp temporal induction/reachability
scripts/run_async_fifo_formal.py    32-step arbitrary-clock FIFO safety bound
scripts/run_calibration_control_formal.py  atomic calibration induction/witness
scripts/run_frame_scheduler_formal.py  phase/zero-fill/counter induction
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
| value-only factorized tube vs fixed | 4,110 randomized/directed vectors plus 100,000-point accuracy probe | bit-exact at latency 8; 47.49 nA worst current error; isolated route 113.24 MHz vs 98.304 MHz (`DEFAULT` grade) |
| iterative Hermite RTL vs fixed kernel | 4,096 full-range directed/random vectors plus busy/reset transitions | bit-exact, latency 3; 265 LC / 2 DSP OOC; named-part route 132.54 MHz vs 98.304 MHz (`DEFAULT` grade) |
| RTL vs fixed LUT | 4,096 deterministic vectors | bit-exact, latency 8 |
| chord RTL vs fixed correction | 1,024 deterministic vectors | bit-exact, latency 10, 18 saturation cases |
| wide chord RTL vs fixed correction | 1,024 deterministic vectors | bit-exact, latency 10, 95 saturation vectors; Q30/Q34/Q40 |
| pipelined wide chord RTL/open route | 1,024 deterministic vectors plus named-part route | bit-exact, latency 12; 100.92 MHz vs 98.304 MHz request (`DEFAULT` grade), 9 DSP48E1 |
| wide RHS RTL vs fixed network | 1,024 deterministic vectors | bit-exact, latency 2 |
| wide KCL RTL vs fixed network | 1,024 deterministic vectors | bit-exact, early-current latency 11; delays through 19 clocks; 48 fallback / 18 overflow vectors |
| trapezoidal wide KCL RTL vs fixed | 1,024 deterministic vectors | bit-exact residual/current state, early-current latency 11; delays through 19 clocks; 1,013 deliberate current-saturation vectors |
| pipelined wide KCL RTL/open route | 1,024 vectors per integration mode plus named-part route | bit-exact, early-current latency 15; legal relaxed-constraint route 42.07 MHz; exact maximum diagnostic is the critical cone (`DEFAULT` grade) |
| diagnostic-pipelined wide KCL RTL/open route | 1,024 vectors per integration mode plus named-part route | bit-exact, diagnostic-enabled latency 19; 92.23 MHz vs 98.304 MHz request; 29,514 LUTX / 10,436 FFX / 1,814 CARRY4 / 72 DSP (`DEFAULT` grade) |
| trapezoidal wide solver RTL vs fixed | 512 sequential samples | bit-exact all 29 state words and diagnostics, latency 116, zero events |
| trapezoidal wide solver synthesis | Yosys 0.66 structural | 12,786 LC, 120 DSP48E1, 8 RAMB18E1 + 1 RAMB36E1; no Fmax claim |
| value-only factorized wide/terminal solver RTL | 512 sequential samples per mode | every state/diagnostic bit-exact at 116/127 clocks; zero events |
| value-only factorized complete solver synthesis | Yosys 0.66 plus open pack | 14,140 LC / 166 DSP / 13 RAMB18E1 + 5 RAMB36E1; 49,530 packed LUT elements; route pending |
| factorized cutoff-domain audit | paired 12 ms / 1.5 V runs per integrator | -5 V flags classified; -8 V outputs bit-exact; zero expanded-domain events |
| banked wide solver RTL vs fixed | 36,864 total 1.0/1.5 V updates | every state exact, every bank selected, latency 116; zero residual/range/arithmetic events |
| banked wide solver synthesis | Yosys 0.66 structural | BE 13,302 LC; trap 13,840 LC; both 120 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1 |
| banked solver vs full Newton | 100 ms, 20 mV/0.5/1.0 V per mode | raw burst error <=-75.28 dB; no alignment or diagnostics; 1 V final RMS 0.372/0.291 mV |
| Vgk-slew-qualified bank selector | 100 ms, 0.5/1.0/1.5 V per mode | <=1 V bit-exact to prior selector; zero 1.5 V residual failures; pre-resolution severe baseline -61.80/-62.12 dB |
| banked error decomposition | 100 ms, 1.0/1.5 V per mode | all intermediate layers converge; fixed circuit/state/chord burst error 6.40--19.07 mV vs <=0.168 mV integer tube evaluation |
| grid-current resolution study | 128/256/512/1,024 entries | implemented 1,024: 12.55 nA exact-mapping worst; 1.5 V burst -72.87/-81.77 dB and final 0.631/0.321 mV |
| banked correction-count study | 3--6 passes, 100 ms, 1.0/1.5 V | fourth improves burst 5.65--9.02 dB; six-pass residual <=0.207 uA; fourth projects to 145 clocks |
| backward-Euler terminal correction RTL | 512 sequential plus 18,432 overload updates | every state/diagnostic exact, constant 127 clocks, zero events; output-exact to four-pass |
| backward-Euler terminal correction synthesis | Yosys 0.66 structural | 13,296 LC, 120 DSP48E1, 8 RAMB18E1 + 1 RAMB36E1; no Fmax claim |
| captured banked terminal RTL overload | 384,000 updates; 20 mV/0.5/1.0/1.5 V bursts | full state exact, zero diagnostics; burst RMS error 0.288/1.237/4.895/6.817 mV; H2--H10 ratio error <=0.00122 percentage points |
| captured trapezoidal banked terminal overload | 384,000 updates; 20 mV/0.5/1.0/1.5 V bursts | full state/current history exact, zero diagnostics; burst RMS error 0.276/1.210/4.709/3.604 mV |
| banked terminal 48 kHz stream vs fixed | 64 outputs / 1,024 circuit samples | bit-exact, zero diagnostics, 127-clock solver |
| banked terminal stream synthesis | Yosys 0.66 structural | 18,466 LC, 168 DSP48E1, 8 RAMB18E1 + 1 RAMB36E1; no Fmax claim |
| trapezoidal banked terminal solver synthesis | Yosys 0.66 structural | 14,945 LC, 174 DSP48E1, 8 RAMB18E1 + 1 RAMB36E1; no Fmax claim |
| parallel-tube terminal solver RTL/synthesis | 512 sequential samples plus baseline regression | every state/diagnostic bit-exact, latency 95 vs 127 clocks; harness 15,887 LC / 7,360 FF / 209 DSP48E1 / 16 RAMB18E1 + 2 RAMB36E1; no Fmax claim |
| parallel/pipelined terminal solver RTL/synthesis | 512 sequential samples plus default-path regressions | every state/diagnostic bit-exact, latency 119 clocks; harness 16,348 LC / 12,378 FF / 209 DSP48E1 / 16 RAMB18E1 + 2 RAMB36E1; no full-hierarchy Fmax claim |
| parallel/diagnostic-pipelined terminal solver RTL/synthesis | 512 sequential samples plus both KCL integration modes | every state/diagnostic bit-exact, latency 126 clocks; harness 14,990 LC / 13,458 FF / 209 DSP48E1 / 16 RAMB18E1 + 2 RAMB36E1; isolated KCL 92.23 MHz, full route open |
| parallel/diagnostic-pipelined full placement | deterministic three-pin harness, seed 1 | 34.20 MHz vs 98.304 MHz; 59,027 LUTX / 13,458 FFX / 4,036 CARRY4 / 209 DSP; placement-only report, routing deliberately skipped (`DEFAULT` grade) |
| half-parallel terminal-current RTL/route | 1,027 directed/random vectors plus named-part harness | bit-exact; 34 DSP vs 54; 4,296 LUTX / 2,412 FFX / 334 CARRY4; 90.50 MHz at default placement weight and 99.59 MHz at measured weight 20 vs 98.304 MHz (`DEFAULT` grade) |
| shared-terminal complete solver RTL/placement | 512 stateful vectors, deterministic three-pin harness, seed 1 | every state/diagnostic bit-exact at 127 clocks; 15,072 LC / 14,590 FF / 189 DSP / 20 RAMB18 equivalents; placement 25.02 MHz, so candidate is not promoted |
| trapezoidal banked terminal stream | 64 outputs / 1,024 circuit samples plus synthesis | bit-exact, zero diagnostics, 127 clocks; 20,241 LC / 222 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1; no Fmax claim |
| captured trapezoidal banked terminal stream frequency | 4,800 outputs each at 100 Hz/1/10/20 kHz | Q24 exact; <=0.000134 dB / <=0.000444 degree vs float; -74.79 dB worst linear-detrended null; zero diagnostics |
| fixed V1 WAV/null regression | 1,024 frames; 11/73/997/7013 Hz plus synthetic pop | trapezoidal terminal path zero diagnostics/clips; injected 23-sample delay recovered; raw/latency-only/gain-aligned residual +2.405/-30.462/-100.810 dB |
| deterministic PCM audio suite | 14 vectors / 69,440 outputs / 1,111,040 internal updates | zero diagnostics/clips; 5/0.5 mV H2–H10 THD 0.019826%/0.011559%; profile sideband IMD 0.461295%; impulse onset 34 samples / peak 138.118 mV; paired 0.5 V recovery 147.750 ms |
| trapezoidal 48 kHz stream vs fixed | 64 outputs / 1,024 circuit samples | bit-exact, zero diagnostics, 116-clock solver |
| trapezoidal stream synthesis | Yosys 0.66 structural | 17,735 LC, 168 DSP48E1, 8 RAMB18E1 + 1 RAMB36E1; no Fmax claim |
| wide factorized solver RTL vs fixed | 512 sequential samples | bit-exact all 19 states and diagnostics, latency 116, zero events |
| wide factorized solver synthesis | Yosys 0.66 structural | 12,544 LC, 120 DSP48E1, 8 RAMB18E1 + 1 RAMB36E1; no Fmax claim |
| wide 48 kHz stream vs fixed composition | 64 outputs / 1,024 circuit samples | bit-exact, zero diagnostics, 116-clock solver |
| wide stream synthesis | Yosys 0.66 structural | 17,492 LC, 168 DSP48E1, 8 RAMB18E1 + 1 RAMB36E1; no Fmax claim |
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
| factorized mono XC7 synthesis | Yosys 0.66 structural | 9,148 LC, 108 DSP48E1, 8 RAMB18E1 + 1 RAMB36E1; no Fmax claim |
| 48 kHz RTL stream vs fixed composition | 64 outputs / 1,024 circuit samples | bit-exact, zero diagnostics |
| full stream XC7 synthesis | Yosys 0.66 structural | 13,170 LC, 137 DSP48E1, 47 RAMB18E1; no Fmax claim |
| factorized 48 kHz stream vs fixed | 64 outputs / 1,024 circuit samples | bit-exact, zero diagnostics |
| factorized stream XC7 synthesis | Yosys 0.66 structural | 14,290 LC, 156 DSP48E1, 8 RAMB18E1 + 1 RAMB36E1; no Fmax claim |
| output mute/ramp RTL | directed reset/ramp/fault sequence | exact expected samples and gain; warning-free Verilator |
| output mute/ramp formal | 15 arbitrary-input properties after reset plus unity reachability | Yosys 0.66 SAT temporal induction closes at depth 2; four accepted samples reach `0xffff` |
| output mute/ramp XC7 synthesis | Yosys 0.66 structural | 171 LC, 2 DSP48E1, no RAM; no Fmax claim |
| asynchronous FIFO RTL | depth 8×32; unrelated 100/71.4 MHz clocks | exact directed full/empty plus 128 wrapped words; local levels reach 8 and return 0; watermarks retain/clear in owning domains; sticky faults clear |
| asynchronous FIFO formal | depth 4×1; arbitrary post-reset clocks/controls | 13 properties hold through 32 global steps; 24-step witness reaches full and both fault stickies; unbounded induction not claimed |
| asynchronous FIFO XC7 synthesis | Yosys 0.66 structural | 127 LC / 331 FF / no DSP or RAM; small memory expanded to registers; no Fmax/CDC claim |
| toggle-pulse CDC RTL/formal/synthesis | two separated events over unrelated clocks plus explicit odd-toggle destination-reset replay; ten properties over every 40-step protocol-constrained arbitrary-clock interleaving | exact directed delivery/replay; bounded formal pass plus two-event witness; 1 LC / 5 FF; only for low-rate idempotent commands; no placed CDC or analog-metastability claim |
| audio clock monitor RTL | exact 10-edge windows, then 11-edge fast and zero-edge stopped windows | three-window lock; bad window drops lock/latches error; exact rate reacquires; clear/reset inactive checked; warning-free |
| audio clock monitor formal | reduced 4-clock windows, one expected edge, two lock windows; arbitrary post-reset clock levels/clear | 16 properties hold through 32 global steps; 48-step witness locks then drops with retained rate error; bounded digital claim only |
| audio clock monitor synthesis | Yosys 0.66 structural | 68 LC / 125 FF / no DSP or RAM; zero warnings/problems; no placed CDC/clock-accuracy claim |
| I²S protocol loopback | 16 signed stereo frames; 24-bit/32-slot | exact channels/endpoints; independent slot/delay monitor; directed framing/underflow flags |
| I²S receiver/transmitter synthesis | Yosys 0.66 structural | RX 35 LC/105 FF; TX 97 LC/137 negative-edge FF; no warnings/DSP/RAM/Fmax claim |
| bidirectional I²S/CDC bridge RTL | 20 stereo frames; unrelated 50/76.9 MHz stress clocks | exact BCLK→fabric→BCLK order after multi-frame plus one-in-four receive stalls; local RX I²S/fabric watermarks 3/3 and TX fabric/I²S 4/4; owning-domain diagnostics checked |
| bidirectional I²S/CDC bridge synthesis | Yosys 0.66 flattened structural | with four local-domain levels/watermarks: 571 LC / 1,547 FF / no DSP or RAM; two 8×64 memories register-expanded; no Fmax/CDC claim |
| held-bus CDC snapshot RTL/formal/synthesis | three 16-bit captures; unrelated clocks plus destination reset during request; nine properties over every 40-step arbitrary-clock interleaving after shared startup reset | every directed image exact; bounded formal pass plus nonzero complete-transfer witness; warning-free; 5 LC / 75 FF / no DSP/RAM; no placed CDC or analog-metastability claim |
| atomic multi-domain register snapshot RTL | same-clock unit plus controlled I²S hierarchy | image/sequence advance only on capture valid; busy command rejected; stopped BCLK times out with old image retained; later re-arm, timeout evidence capture, and clear exact; warning-free |
| PCM24/Q8.24 calibration RTL | 4,159 vectors each direction | bit-exact, one clock, endpoint/invalid/4,079 output-saturation events checked; warning-free |
| PCM24/Q8.24 calibration formal | arbitrary full-width samples/coefficients/valid/clear | 12 arithmetic and registered-state properties close Yosys SAT temporal induction at depth 2; endpoint/saturation/both-invalid witness found |
| PCM24/Q8.24 calibration synthesis | Yosys 0.66 structural | input 95 LC/66 FF/4 DSP; output 86 LC/58 FF/4 DSP; no RAM/Fmax claim |
| atomic calibration commit RTL | invalid/muted-valid/live-valid/clear sequence | active pair resets zero; muted pair commits together with one ack; rejected attempts preserve both values and set the correct sticky flag; warning-free |
| atomic calibration commit formal | 12 arbitrary-input transition properties plus path witness | Yosys 0.66 SAT temporal induction closes at depth 2; invalid reject, atomic commit, and unsafe reject all reachable |
| atomic calibration commit synthesis | Yosys 0.66 structural | 14 LC / 67 FF / no DSP or RAM; zero warnings/problems; no Fmax/CDC claim |
| fabric frame scheduler RTL | 3 launches at 8-clock test period | exact held A/zero-fill/B order after one-clock preprocess; phase zero; one underflow/clear; warning-free |
| fabric frame scheduler formal | 9 arbitrary-source transition properties plus launch witness | Yosys 0.66 SAT temporal induction closes at depth 2; absent boundary increments once and following present boundary is reachable |
| fabric frame scheduler synthesis | Yosys 0.66 structural, 2,048-clock default | 41 LC / 43 FF / no DSP or RAM; no Fmax/ASRC claim |
| calibrated fabric mono adapter RTL | 64 PCM frames / 1,024 nonlinear updates | every input calibration, raw model output, and duplicated PCM frame bit-exact; unrelated right input ignored; five-clock stall held; directed overrun retains old frame and clears; model/calibration diagnostics zero; warning-free |
| calibrated fabric mono adapter synthesis | Yosys 0.66 flattened structural | with output ramp: 20,489 LC / 15,592 FF / 232 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1; zero structural problems; no Fmax/CDC/stereo claim |
| pin-facing I²S mono top RTL | 64 serial inputs; actual 3.072/98.304 MHz clocks with unrelated phase | startup calibration atomic; model/PCM exact; 45 DAC frames exact; FIFO high-water 1; four clock windows measure 1,024 edges and lock; live update rejected; transport 192 BCLK / 62.500 µs / 3 samples; startup starvation retained; warning-free |
| pin-facing I²S mono top synthesis | Yosys 0.66 flattened structural | with output ramp, calibration guard, FIFO diagnostics, rate monitor: 21,014 LC / 16,907 FF / 232 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1; zero structural problems; no placed CDC/I/O/converter claim |
| SPI control transport RTL/formal/synthesis | eight complete 5 MHz frames plus abort/withheld response; 11 properties over 32 arbitrary-pin fabric steps and a 100-step request/error witness | exact directed wire order/read/write/errors; bounded formal pass; 112 LC / 172 FF / no DSP/RAM; no placed SCLK/metastability claim |
| SPI-controlled pin top RTL | 15 mode-0 frames plus one aborted frame at 5 MHz; 100 MHz fabric and unrelated BCLK | identity, calibration commit/readback, retained short-frame fault, retained then refreshed force-mute snapshot, snapshotted transport count, and one BCLK-domain diagnostic clear all exact; warning-free |
| SPI-controlled pin top synthesis | Yosys 0.66 flattened structural | 22-word multi-domain snapshot, timeout, fail-closed BCLK guard, and transport: 21,589 LC / 18,094 FF / 232 DSP48E1 / 8 RAMB18E1 + 1 RAMB36E1; zero structural problems; no placed SCLK/CDC/I/O/Fmax claim |
| controlled clock-fault mute RTL | 320-clock windows, exactly 10 BCLK edges, three-window lock | startup fail-closed; stopped BCLK drops lock and clamps output; reacquisition stays clamped behind sticky evidence; snapshot exact; fabric/I²S clear releases guard; warning-free |
| guarded wide stream RTL | startup plus one state-reset transaction | warning-free; mute precedes reset; phase clean; one ack; unity restored |
| guarded wide stream synthesis | Yosys 0.66 structural | 17,562 LC, 170 DSP48E1, 8 RAMB18E1 + 1 RAMB36E1; no Fmax claim |
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

The separate `smpte_profile_60hz_7khz` fixture uses 60 Hz and 7 kHz at a 4:1
input peak ratio. Its simultaneous least-squares analysis fits the carrier plus
first- and second-order upper/lower sidebands. Each sideband pair reports
`(lower peak + upper peak) / carrier peak`, which returns the modulation depth
for ideal symmetric AM; the scalar is the root-sum-square of the two pair
depths. The frozen result is 0.461295%. This is a traceable standards-profile
regression, not a claim that software filtering, calibration, bandwidth, and
uncertainty satisfy every requirement of SMPTE RP 120. The V1 RIAA response
also changes the 4:1 input ratio to an 84.78:1 output peak ratio; that physical
equalization is measured, not normalized away.

The impulse and recovery gates use separately initialized matched controls.
Subtracting the silence control proves the 5 mV one-sample impulse residual is
exactly zero before input sample 1,024, first exceeds four output PCM LSBs after
34 samples, and peaks at 138.118 mV after 52 samples. This thresholded onset is
not the previously measured 51-sample identity-resampler group delay. The
250 ms recovery pair replaces the nominal 5 mV tone with a 0.5 V tone for 5 ms
and subtracts an undisturbed trajectory. A 1 ms sliding-RMS envelope crosses
10% of the 400.872 mV nominal RMS for the final time 147.750 ms after the input
burst stop. This WAV metric deliberately retains interpolation/circuit/
decimation delay; the upstream 768 kHz solver-only result is 146.570 ms. The
final 10 ms deviation is 18.650 mV RMS. Multi-second 1.0/1.5 V floating-model
recovery remains characterization outside the accepted fixed-solver region.

The complete-stream frequency report performs no alignment. It fits the raw
48 kHz input/output with absolute sample indices. A separate identity-path
interpolator/decimator measurement establishes the 51-sample causal converter
delay; only the field named `circuit_attributed_after_converter_removal`
subtracts that converter phase. End-to-end fields retain the physical latency.

Implemented audio fixtures now cover silence, log sweep, low-level/nominal sine,
multitone, selected high-frequency intermodulation products, the 60 Hz/7 kHz
SMPTE-style profile above, synthetic pops, a separately gated impulse, 11 Hz
warp, grid-conduction overload, and paired long recovery. A calibrated full
SMPTE/CCIF analyzer implementation and licensed/locally supplied music remain
absent. Every found numerical bug gets the smallest durable regression vector.

## Physical verification plan

Calibrate generator/interface/analyzer independently, then measure cartridge
load, front-end/ADC, digital loopback, DAC/line, and complete path in stages.
Archive raw samples, instrument settings, calibration date, environment, board
revision, FPGA bitstream hash, model version, and control-register dump. A real
Kennedy circuit comparison requires the same stimulus capture split to hardware
and FPGA, followed by gain/latency alignment and variation reporting. Listening
is useful product evidence but never replaces electrical equivalence data.
