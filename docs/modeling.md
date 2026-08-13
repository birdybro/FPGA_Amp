# Modeling and error layers

## Tube equation

The first 12AX7 model is Norman Koren's improved triode equation. In compact
form, with voltages referenced to cathode,

```text
E1 = (Vpk / Kp) * ln(1 + exp(Kp * (1/mu + Vgk/sqrt(Kvb + Vpk²))))
Ip = 2 * E1^Ex / Kg1      for positive E1 and Vpk
```

with `mu=100`, `Ex=1.4`, `Kg1=1060`, `Kp=600`, and `Kvb=300`. The implementation
uses numerically stable logarithm/exponential forms and clips nonphysical
negative plate voltage to zero current. Grid current is a temperature-scaled
diode followed by Koren's 2 kΩ implicit grid resistance, solved locally by
Newton iteration. Koren calls this grid-current estimate rough; overload claims
therefore carry a larger physical-model uncertainty than ordinary negative-grid
operation.

The checked approximate GE curve digitization gives 0.0131 mA RMS and 0.0346 mA
worst error for the Koren equation, smaller than the declared ±0.05 mA manual
graph-reading uncertainty. This validates the transcription and nominal region,
not production-tube variance.

## Discrete circuit

The Python model solves KCL on grid, plate, cathode, RIAA, and output nodes.
Resistors are conductance stamps. Capacitors use backward-Euler companions:

```text
Gc = C / dt
Ieq[n] = Gc * vcap[n-1]
```

Tube currents depend on `Vgrid−Vcathode` and `Vplate−Vcathode`; their local
derivatives enter the Newton Jacobian. Previous-sample voltages are the initial
guess. All capacitor history is committed after a solve. Backward Euler was
chosen first for deterministic robustness; its numerical damping is measured,
not asserted harmless.

At 768 kHz, the current 5 mV-peak 1 kHz comparison against ngspice has 0.880 mV
residual RMS on 397.6 mV reference RMS (-53.10 dB normalized), 1.524 mV worst
sample error, and 0.00179 dB RMS gain error over the last 10 ms. Major remaining
contributors are integration-method and SPICE-output resampling differences.

A matched transient sweep now quantifies that integration term directly. With
the physical cartridge/load retained and the Python model driven from SPICE's
`INPUT` node, 768 kHz backward Euler measures the following fundamental errors:

| Frequency | Gain error | Phase error | Raw normalized residual |
|---:|---:|---:|---:|
| 100 Hz | +0.001307 dB | +0.02443° | -66.42 dB |
| 1 kHz | +0.001894 dB | +0.11221° | -53.10 dB |
| 10 kHz | -0.048491 dB | +2.29757° | -27.83 dB |
| 20 kHz | -0.064578 dB | +4.71974° | -21.50 dB |

All Newton solves converge in at most two iterations. The high-frequency phase
error decreases monotonically with backward-Euler rate, but even 3.072 MHz
leaves 0.608° at 10 kHz and 1.235° at 20 kHz. Rate alone is therefore an
expensive and incomplete fix.

The floating model now has an explicitly selected `trapezoidal` companion
candidate. It stores previous branch current as well as voltage and uses

```text
Gc = 2*C/dt
Ieq[n] = Gc*vcap[n-1] + icap[n-1]
icap[n] = Gc*(vcap[n] - vcap[n-1]) - icap[n-1]
```

At 768 kHz it measures +0.005806 dB / +0.03900° at 10 kHz and -0.008455 dB /
+0.05817° at 20 kHz, with no failed solve. It is a candidate rather than a
reference-circuit change. Backward Euler remains the implemented RTL behavior.

The first trapezoidal large-signal gate applies 5 ms, 1 kHz bursts inside a
100 ms trajectory. Both floating methods remain finite and Newton-convergent at
20 mV, 0.5 V, 1.0 V, and 1.5 V. For 20 mV, backward-Euler versus trapezoidal
10% / 1% / 1 mV recovery is 8.4648 / 14.9180 / 18.2799 ms versus 8.4648 /
14.9154 / 18.2773 ms. At 1.5 V their stage-two grid-current peaks are 26.288 /
26.403 uA. Both remain above the 10%-nominal recovery threshold after 85 ms at
0.5 V and above, demonstrating that the long memory is shared circuit/model
behavior rather than a backward-Euler artifact. The two methods differ by
4.31 mV RMS over the final 10 ms only in the 1.5 V case; lower tested levels
are within 0.631 mV.

The first downstream fixed candidate retains Q30 previous branch voltage and
adds a signed Q4.44 previous-current state for every capacitor. Conductance is
`2*C/dt`; KCL and state commit use the identical rounded Q4.44 branch product.
Current history initializes to zero at the quantized DC operating point, and
the implementation rejects trapezoidal selection through the legacy implicit-
history path.

Across the six-frequency 5 mV sweep, fixed trapezoidal differs from floating
trapezoidal by at most 0.000131 dB and 0.000784 degrees. It records no residual-
limit, saturation, tube-range, or correction-fallback events. Raw residual at
20 kHz is -43.99 dB because of a -0.257 mV DC difference; the explicitly
reported mean-removed residual is -68.15 dB. Nominal capacitor-current peaks
remain below 2.25 uA in this sweep. This clears nominal fixed state/rounding,
not overload range or RTL scheduling.

The matched fixed overload run remains diagnostic-clean at 20 mV and 0.5 V.
At 1.0/1.5 V, it records 1,107/1,690 residual-limit failures; 1.5 V also has
4,048 factorized-tube range clips and 728 safe correction-scale fallbacks. The
largest capacitor-current history magnitude is 203.34 uA, with no arithmetic
saturation. The doubled output-coupling companion is 0.72192 S or
101601207593478 in Q0.47, which requires a signed 48-bit coefficient rather
than the current backward-Euler RTL block's measured 47 bits.

Three nonlinear solution forms have now been measured. Full Newton with a live
Jacobian is the float reference and needs at most two correction passes for the
20 mV 1 kHz test. Raw fixed-point iteration around the linear network is rejected:
12 relaxed passes still miss the residual target throughout the multitone study,
and larger relaxation diverges. A chord method using the quiescent tube Jacobian
as a constant inverse converges every multitone sample in three passes, with
-137.28 dB normalized output residual and 1.85 µV worst output difference from
full Newton. Chord is the fixed/RTL candidate, not yet the accepted fixed result.

## Ideal RIAA reference

The independent reference is

```text
H(s) = (1 + s*318 us) / ((1 + s*3180 us) * (1 + s*75 us))
```

normalized at 1 kHz. Against the two-decimal values published in RIAA Bulletin
E1, the maximum point difference is 0.0705 dB at 14 kHz. The test bound is
0.075 dB because the table is rounded/internally approximate; it does not relax
the equation.

## LUT and numerical contract

The FPGA primitive samples `Ip=f(Vgk,Vpk)` on a uniform 128 × 256 grid over
-5…+1 V and 0…400 V. It uses one-dimensional interpolation for `Ig`, bilinear
interpolation for `Ip`, Q16 coordinates, and Q0.31 currents. A one-port ROM
schedule reads four corners and reuses one multiply datapath. See
`fixed_point.md` for exact formats and rounding.

Full-range 100,000-point analytical comparison gives 0.139 µA mean, 0.237 µA
RMS, and 9.33 µA worst absolute error. Restricting comparison to negative grid
and plate voltage at least 20 V reduces the observed worst error to 1.43 µA in
the 50,000-point resolution study. Relative error is deliberately not the main
metric near cutoff, where division by a nearly zero physical current is
misleading.

That full-range current metric does not bound low-level harmonic error. A
20–30 ms 1 kHz sweep shows 0.0733% H2–H10 THD for the complete fixed model at
5 mV peak versus 0.0191% for the analytical model. At 0.5 V the results converge
to 2.2395% and 2.2417%, with -55.98 dB waveform residual. Thus the present LUT/
state approximation is most visible at ordinary cartridge levels, even though
gain remains close (+0.0324 dB at 5 mV).

A controlled resolution study does not justify simply increasing BRAM. At
5 mV, moving from 128×256 to 256×256 changes complete fixed THD from 0.0733%
to 0.0723% while doubling raw plate-table storage. A 512×256 table gives
0.0683%; 256×512 gives 0.0731%. Fixed versus same-LUT floating residual is
-34.58 dB for 128×256 and improves only to about -36.5 dB with more grid points.
A transformed, smooth polynomial, Hermite, or hybrid approximation should be
studied before changing the frozen RTL table.

That study selected a candidate based on the algebra already present in the
Koren law rather than fitting an unrelated waveshaper:

```text
r(Vpk) = 1 / sqrt(Kvb + Vpk^2)
z       = 1/mu + Vgk*r(Vpk)
f(z)    = ln(1 + exp(Kp*z)) / Kp
E1      = Vpk*f(z)
Ip(E1)  = 2*E1^Ex/Kg1
```

The three scalar functions use 512, 1024, and 2048 uniformly spaced value and
derivative-times-step entries. A Q0.16 cubic Hermite coordinate is evaluated in
Horner form. Including the unchanged 128-entry grid-current branch, the fixed
candidate contains 233,472 raw bits, 22.2% of the present 2-D-plus-grid raw
table bits. This is a storage comparison rather than a placed-BRAM claim.

On 100,000 random quantized inputs it has 10.5 nA mean, 16.0 nA RMS, and
51.8 nA worst plate-current error. Circuit-level 5 mV/1 kHz THD is 0.0188%
versus 0.0191% analytical; 0.5 V results are 2.2419% and 2.2417%. The 5 mV
unaligned waveform residual is still only -42.90 dB, despite +0.00026 dB
fundamental gain error, demonstrating a separate state/phase error that requires
diagnosis. The standalone factorized RTL is exact at eight clocks, its solver
integration is exact at 126 clocks, and its complete stream matches the fixed
composition exactly. Wider frequency/overload evidence remains open before
choosing it as the default implementation.

Residual decomposition at 5 mV shows the raw null is dominated by a -2.840 mV
mean difference. Removing that mean for diagnosis—not for acceptance—gives a
-59.63 dB AC residual; the fundamental phase error is 0.00958°. The fixed
initial state is obtained by quantizing a floating DC solution, and the very
slow output coupling network preserves small operating-point discrepancies.
The raw result remains the primary unaligned metric while fixed-domain DC
initialization and coefficient error are investigated.

A one-second state regression has isolated a more severe discontinuity case.
With silence except for +100 mV and -100 mV one-sample clicks at 0.1 and 0.3 s,
the Q12.20 fixed output holds +35.655 mV between events and -5.368 mV from 0.5 s
through the end. Analytical output is 7.2 uV RMS in the final 100 ms. The final
output and 470 nF coupling-capacitor state errors are 5.373 and 5.299 mV even
though the fixed maximum KCL residual is only 0.334 uA and every diagnostic
counter is zero. This proves that the residual criterion does not detect
long-time state deadbands. The exact raw waveform and all node/capacitor
checkpoints are retained in `state_drift_summary.json`.

A 40-bit all-node candidate addresses both causes rather than only widening the
output. High-voltage nodes use Q28, low-voltage/output nodes Q32, capacitor
history Q30, and capacitor current is evaluated as a cancellation-safe branch
product. Its three corrections stage residual precision Q30 -> Q34 -> Q40.
On the identical click audit, final instantaneous output error is 41.3 uV and
late raw residual is 38.74 uV RMS, a 42.9 dB reduction from the legacy late
residual. The between-click residual improves by 40.1 dB. The final plate/
capacitor differences remain about 5.3--5.4 mV because the fixed factorized tube
has a different quantized operating point; the coupling output no longer traps
that entire difference.

At nominal 5 mV/1 kHz, the wide-state raw null is -63.83 dB and mean-removed
null -88.43 dB, versus -42.90/-59.63 dB for the legacy state. Gain and phase
errors are -0.000058 dB and -0.000187 degrees. The remaining -0.257 mV mean
difference is still reported raw. Frequency, overload, complete-RTL schedule,
and hierarchical resource proof remain gates before this candidate can replace
the explicit legacy implementation. The correction sub-block alone is now
verified in RTL.

The matched six-frequency sweep reduces the legacy worst gain/phase bounds
from 0.00846 dB / 0.0729 degrees to 0.000196 dB / 0.000982 degrees. There are
zero residual-limit, saturation, or range events. The wide candidate raw nulls
are -95.26, -87.71, -79.73, -63.83, -49.47, and -44.75 dB from 20 Hz through
20 kHz. At the last two points, the mean-removed nulls are -74.50/-68.37 dB;
raw values remain primary and the separate mean report is diagnostic only.

The wide-state overload rerun uses a bounded adaptive residual scale. Each pass
requests Q30/Q34/Q40, then selects the finest no-greater format from that same
three-value set for which all nine 25-bit operands fit. At 20 mV and 0.5 V no
fallback occurs. At 1.5 V, 729 fallback events prevent any arithmetic
saturation; the minimum is Q34. This improves numerical robustness but not the
quiescent-Jacobian convergence envelope.

The standalone wide correction block matches 1,024 exact vectors at ten clocks,
including 95 output-saturation vectors. Its constant-format Q30/Q34/Q40 scaling
synthesizes to 1,701 generic XC7 logic cells and nine DSP48E1s. A fully variable
shift version required 5,531 cells and was rejected. The branch-current KCL and
complete scheduler are integrated and verified below.

The branch-current network is now independently implemented. Its two-clock RHS
and ten-clock KCL blocks each match 1,024 exact vectors. The KCL regression
covers all three correction formats, 48 deliberate format fallbacks, 18
minimum-format overflows, and delayed tube-current arrival. Static-matrix and
capacitor coefficient widths were proven from generated bounds before synthesis;
the resulting KCL uses 7,804 generic XC7 logic cells and 72 DSP48E1s. The
integrated persistent-state solver then matches 512 sequential samples exactly
at 116 clocks, including all node, capacitor, output, residual, and diagnostic
values. The test has zero saturation, range, convergence, missed-request, or
deadline events and maximum residual 4.705 nA. Generic XC7 synthesis reports
11,981 logic cells, 122 DSPs, and 8 RAMB18s. Timing closure remains separate.

Composition with the existing 16x interpolator and decimator also remains
bit-exact: 64 external samples exercise 1,024 nonlinear updates with zero
diagnostics and a 4.598 nA maximum residual. Structural synthesis measures
16,993 logic cells, 170 DSP48E1s, and 8 RAMB18E1s. These counts fit mono on the
provisional A7-100T but rule out simple stereo duplication on its 240 DSPs.

A longer 23,040-sample solver capture now closes the nominal measurement loop.
For a Q8.24-quantized 5 mV / 1 kHz input, captured RTL Q8.32 output is bit-exact
to fixed Python. Against analytical float over the final 10 ms, its gain error
is -0.0000542 dB, phase error -0.0001866 degrees, THD 0.0193708% versus
0.0190586%, and raw/mean-removed residual -63.834/-88.448 dB. The residual mean
is retained at -0.2573 mV rather than removed from reference behavior. Maximum
fixed KCL residual is 4.961 nA and all diagnostics are zero.

Four captured-RTL frequency points extend that result over representative
audio-band locations. At 100 Hz, 1 kHz, 10 kHz, and 20 kHz, every Q8.32 output
sample is exact to fixed Python. Relative to analytical float, maximum absolute
gain and phase error are 0.0001943 dB and 0.0009814 degrees. The worst raw null
is -44.755 dB at 20 kHz, while its mean-removed null is -68.367 dB; both are
reported because the raw high-frequency residual is dominated by a small DC
difference. No saturation, tube-range clip, residual-limit failure, or
correction-scale fallback occurs. These are captured simulator values, not
placed-FPGA or physical-audio measurements.

The captured-RTL overload trajectory runs a 5 ms, 1 kHz burst inside a 100 ms
record, extending observation after the burst from 35 ms to 85 ms. The 5 mV
control plus 20 mV, 0.5 V, 1.0 V, and 1.5 V cases account for 384,000 exact
full-state RTL comparisons. At 20 mV the captured trajectory reaches 10%, 1%,
and 1 mV RMS recovery in 8.466, 14.918, and 18.297 ms. At 0.5 V and above,
neither the analytical nor RTL trajectory returns below the 10% nominal-output
threshold inside 85 ms, so this is a real modeled long-state response rather
than solely fixed-point error. At the end of the run, RTL/analytical residual
is 0.194 mV RMS for 0.5 V and 0.0548 mV RMS for 1.0 V, but 17.36 mV RMS for the
range-clipped 1.5 V case.

The captured diagnostics reproduce the previous fixed characterization exactly:
zero residual-limit events through 0.5 V, 1,122 at 1.0 V, and 1,695 at 1.5 V.
The last case also records 4,046 factorized-tube range clips and 729 correction-
scale fallbacks. Adaptive scaling prevents arithmetic saturation. Stage-two
grid current peaks at 0.0806 uA at 1.0 V and 26.30 uA at 1.5 V. These severe
cases remain rejected as an accuracy claim even though RTL is exact to its
fixed numerical contract.

At 20 mV, fixed 10%/1%/1 mV recovery becomes 8.466/14.918/18.297 ms versus
analytical 8.465/14.918/18.280 ms. Legacy fixed needed 8.668/24.612/34.643 ms.
Post-burst wide fixed/analytical RMS is 0.258 mV at both 20 mV and 0.5 V,
versus 5.80/7.69 mV legacy. However, 1.0 V still produces 1,122 residual-limit
failures (6.70 uA maximum), and 1.5 V produces 1,695 failures (17.19 uA),
4,046 tube-range clips, and a 36.82 mV post-burst RMS error. A live/adaptive
Jacobian or another nonlinear strategy is still required above 0.5 V.

The same comparison now spans 20 Hz, 50 Hz, 100 Hz, 1 kHz, 10 kHz, and 20 kHz
at 5 mV peak, using at least ten stimulus cycles and analyzing at least the last
five. Maximum fundamental gain and phase errors are 0.00846 dB and 0.0729°.
No fixed residual-limit, arithmetic-saturation, or tube-range event occurs in
683,520 processed samples. At 10 and 20 kHz the raw residual is only about
-23.5 dB because a few-millivolt mean difference is large relative to the RIAA-
attenuated AC output; direct gain errors remain 0.00056 and -0.00033 dB. This is
why the report retains raw null, mean-removed null, gain, phase, and DC separately.

## Overload and recovery

A reproducible 1 kHz test runs a nominal 5 mV signal, substitutes a 5 ms burst,
then compares recovery with an undisturbed nominal trajectory. Recovery is the
last crossing of a 1 ms sliding-RMS threshold, not the first momentary crossing.
At 20 mV, analytical/fixed 10%-of-nominal recovery is 8.46/8.67 ms; 1% recovery
is 14.9/24.6 ms, and the fixed path reaches 1 mV RMS at 34.6 ms. No residual,
range, or arithmetic diagnostic fires.

The 0.5 V burst does not reach even 10% recovery within the 35 ms post-window,
although its fixed residual remains below 0.631 µA. At 1.0 V, stage-two grid
current reaches 0.063 µA analytical / 0.081 µA fixed and 1,134 fixed samples
exceed the 2 µA residual criterion. At 1.5 V, stage-two grid current is 26.29 /
26.31 µA, 1,698 samples exceed the residual limit, and 4,046 nonlinear
evaluations clip an internal transformed/table range. The analytical Newton
model converges throughout. Those clip/failure counts prohibit claiming the
present three-pass fixed result as overload-equivalent above the tested 0.5 V
case. Koren's grid-current branch is itself only a rough physical estimate.

Adding corrections alone is rejected as the overload solution. On a shorter
controlled burst, increasing from three to six corrections reduces the 1.0 V
maximum residual from 6.93 to 2.31 µA and failures from 942 to 30. At 1.5 V it
only reduces 17.34 to 5.83 µA and leaves 960 failures. A serialized extra
residual-plus-chord pass uses the measured 19 + 10 clocks, so six corrections
project 213 clocks versus the 128-clock deadline. This projection is not an RTL
timing measurement, but it is sufficient to reject a simple serial-pass increase.

## Explicit error budget status

| Layer | Present evidence | Status |
|---|---|---|
| physical 12AX7 variation | GE graph plus Koren parameters | not bounded statistically |
| analytical tube equation | 0.0131 mA RMS vs approximate GE points | provisional |
| grid conduction | Koren rough diode/RGI model | high uncertainty |
| SPICE circuit | reproducible DC/AC/transient | golden numerical reference, not hardware truth |
| 768 kHz backward-Euler integration | four SPICE transients, 100 Hz--20 kHz | <=0.0646 dB gain; phase grows to 4.72 degrees |
| 768 kHz trapezoidal float candidate | 10/20 kHz SPICE transients | <=0.00846 dB gain / <=0.0582 degree phase; downstream proof open |
| trapezoidal float overload stability | 20 mV--1.5 V, 100 ms records | finite/convergent; clean recovery matches BE; shared long memory above 0.5 V |
| fixed trapezoidal state | six 5 mV points, 20 Hz--20 kHz | <=0.000131 dB / <=0.000784 degree vs float trapezoidal; zero diagnostics; RTL open |
| fixed trapezoidal overload | 20 mV--1.5 V bursts | clean through 0.5 V; 203.34 uA history-current peak; severe solver/range limit unchanged |
| trapezoidal KCL RTL | 1,024 randomized/directed vectors | exact residual and Q4.44 next current; 10 clocks; integrated |
| trapezoidal solver RTL | 512 persistent samples | exact 9 node + 20 capacitor states; 116 clocks; 12,451 LC / 122 DSP / 8 RAMB18 structural |
| trapezoidal 48 kHz RTL stream | 64 outputs / 1,024 updates | exact fixed composition; zero diagnostics; 17,556 LC / 170 DSP / 8 RAMB18 structural |
| chord vs full Newton | -137.28 dB normalized residual, 3-pass multitone | float architecture candidate |
| fixed tube LUT | 0.139 µA mean / 9.33 µA worst full range | measured |
| fixed factorized tube | 10.5 nA mean / 51.8 nA worst; 233,472 raw table bits | measured; standalone RTL passing |
| factorized RTL vs fixed | 4,107 vectors exact at 8 clocks; 1,597 LC / 37 DSP / 8 RAMB18 | standalone and solver passing |
| factorized solver vs fixed | 512 stateful samples exact at 126 clocks; 9,194 LC / 110 DSP / 8 RAMB18 | passing |
| factorized stream vs fixed | 64 outputs / 1,024 updates exact; 14,366 LC / 158 DSP / 8 RAMB18 | passing; broader stimuli open |
| factorized frequency response | six 5 mV points, 20 Hz–20 kHz | ≤0.00846 dB gain / ≤0.0729° phase; zero diagnostics |
| factorized overload/recovery | 5 ms bursts, 20 mV–1.5 V | clean at 20/500 mV; residual failure at 1 V; range clip at 1.5 V |
| overload iteration count | 3–6 corrections at 1.0/1.5 V | improved but still failing; projected 213 clocks at six |
| long fixed state / click recovery | 1 s silence with +/-100 mV single-sample clicks | Q12.20 deadband leaves -5.368 mV late output; must be redesigned |
| wide-state Python candidate | same 1 s click audit; 5 mV/1 kHz | 38.74 uV late residual; -63.83 dB nominal raw null; complete-RTL proof open |
| wide chord RTL vs fixed | 1,024 randomized/directed vectors | bit-exact, latency 10; 1,701 LC / 9 DSP / 0 RAMB18 structural |
| wide RHS/KCL RTL vs fixed | 1,024 vectors each | bit-exact, latency 2/10; KCL fallback/overflow/delayed-current coverage |
| wide factorized solver RTL vs fixed | 512 persistent samples | bit-exact all state/diagnostics, latency 116; 11,981 LC / 122 DSP / 8 RAMB18 |
| wide factorized stream vs fixed | 64 outputs / 1,024 updates | bit-exact, zero diagnostics; 16,993 LC / 170 DSP / 8 RAMB18 |
| captured wide solver RTL vs analytical | 23,040 samples, 5 mV/1 kHz | Q32 exact to fixed; -0.000054 dB / -0.000187 degree gain/phase error; 0.019371% THD |
| captured wide solver RTL frequency sweep | 5 mV, 100 Hz/1/10/20 kHz | Q32 exact to fixed; <=0.0001943 dB gain / <=0.0009814 degree phase; zero diagnostics |
| captured trapezoidal solver RTL frequency | 5 mV, 100 Hz/1/10/20 kHz | all fixed states exact; <=0.000128 dB / <=0.000784 degree vs float; zero diagnostics |
| captured wide solver RTL overload | 384,000 updates, 5 ms bursts, 85 ms observation | full state exact to fixed; clean through 0.5 V; failures at 1 V; range clips at 1.5 V |
| captured nonlinear decimation alias | 131,072 internal / 8,192 external samples | exact to fixed; 45 kHz to 3 kHz alias -137.814 dBc; zero saturation |
| wide-state frequency response | 5 mV, 20 Hz--20 kHz | <=0.000196 dB gain / <=0.000982 degree phase; zero diagnostics |
| wide-state overload/recovery | 20 mV--1.5 V bursts | clean through 0.5 V; convergence fails at 1 V; adaptive scale prevents arithmetic saturation |
| RTL LUT | 4,096 vectors bit-exact to fixed Python | passing |
| fixed chord/state vs float LUT circuit | -70.33 dB initial multitone; -34.58 dB at 5 mV/1 kHz | signal-dependent; low-level improvement required |
| low-level complete fixed model | 2-D: 0.0733%; factorized: 0.0188%; analytical: 0.0191% THD | device error improved; RTL/state-phase work open |
| interpolation/decimation | exact fixed/RTL streams; captured alias -137.814 dB | implemented; full-tube 3 kHz bin has pre-decimation content |
| ADC/front end/DAC | analytical requirements only | unvalidated |
| physical FPGA/audio chain | absent | unvalidated |

These errors are never collapsed into one “accuracy” number because they refer
to different upstream truths.
