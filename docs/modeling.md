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
| RTL LUT | 4,096 vectors bit-exact to fixed Python | passing |
| fixed chord/state vs float LUT circuit | -70.33 dB normalized residual, initial multitone | implemented DSP-friendly candidate; wider sweeps open |
| interpolation/decimation | not implemented | open |
| ADC/front end/DAC | analytical requirements only | unvalidated |
| physical FPGA/audio chain | absent | unvalidated |

These errors are never collapsed into one “accuracy” number because they refer
to different upstream truths.
