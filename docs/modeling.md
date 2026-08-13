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

## Explicit error budget status

| Layer | Present evidence | Status |
|---|---|---|
| physical 12AX7 variation | GE graph plus Koren parameters | not bounded statistically |
| analytical tube equation | 0.0131 mA RMS vs approximate GE points | provisional |
| grid conduction | Koren rough diode/RGI model | high uncertainty |
| SPICE circuit | reproducible DC/AC/transient | golden numerical reference, not hardware truth |
| integration/solver | -53.10 dB residual vs SPICE at one level/frequency | measured, more sweeps needed |
| chord vs full Newton | -137.28 dB normalized residual, 3-pass multitone | float architecture candidate |
| fixed tube LUT | 0.139 µA mean / 9.33 µA worst full range | measured |
| fixed factorized tube | 10.5 nA mean / 51.8 nA worst; 233,472 raw table bits | measured; standalone RTL passing |
| factorized RTL vs fixed | 4,107 vectors exact at 8 clocks; 1,597 LC / 37 DSP / 8 RAMB18 | standalone and solver passing |
| factorized solver vs fixed | 512 stateful samples exact at 126 clocks; 9,194 LC / 110 DSP / 8 RAMB18 | passing |
| factorized stream vs fixed | 64 outputs / 1,024 updates exact; 14,366 LC / 158 DSP / 8 RAMB18 | passing; broader stimuli open |
| RTL LUT | 4,096 vectors bit-exact to fixed Python | passing |
| fixed chord/state vs float LUT circuit | -70.33 dB initial multitone; -34.58 dB at 5 mV/1 kHz | signal-dependent; low-level improvement required |
| low-level complete fixed model | 2-D: 0.0733%; factorized: 0.0188%; analytical: 0.0191% THD | device error improved; RTL/state-phase work open |
| interpolation/decimation | exact fixed/RTL streams; Python alias -137.81 dB | implemented; RTL alias capture open |
| ADC/front end/DAC | analytical requirements only | unvalidated |
| physical FPGA/audio chain | absent | unvalidated |

These errors are never collapsed into one “accuracy” number because they refer
to different upstream truths.
