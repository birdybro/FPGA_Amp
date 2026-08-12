# Oversampling and decimation

The first measured reference uses four causal 2× half-band stages from 48 kHz
to 768 kHz and the reversed chain after nonlinear processing. Every stage is a
windowed-sinc FIR with exact zero alternate taps, exact 0.5 center coefficient,
unity DC gain, and symmetry. Interpolation applies gain two after zero stuffing;
decimation filters before retaining the even phase.

| Stage | Rates | Taps / nonzero | Kaiser β | Passband bound to 20 kHz | Worst image band, float / Q1.23 coefficients |
|---|---|---:|---:|---:|---:|
| 1 | 48→96 kHz | 79 / 41 | 9.5 | -0.000164…+0.000134 dB | -94.49 / -94.41 dB |
| 2 | 96→192 kHz | 31 / 17 | 9.5 | -0.000169…+0.000028 dB | -94.20 / -94.19 dB |
| 3 | 192→384 kHz | 19 / 11 | 8.6 | -0.000228…+0.000059 dB | -91.60 / -91.59 dB |
| 4 | 384→768 kHz | 19 / 11 | 8.6 | 0…+0.000059 dB | -103.32 / -103.54 dB |

The conservative sum of per-stage interpolation passband extrema is
-0.000562 to +0.000281 dB. Float group delay is 399 samples at 768 kHz
(0.5195 ms) one way. The full interpolation/decimation chain has 49.875 external
samples (1.0391 ms) theoretical delay with the current even decimation phases;
fractional-delay alignment must remain visible in null comparisons.

## Nonlinear alias test

A 0.8-peak 15 kHz sine is interpolated, processed at 768 kHz by
`y=x+0.5*x³`, and decimated. The cubic produces a real 45 kHz third harmonic
which would alias to 3 kHz if downsampled without filtering. Measured 3 kHz alias
is -144.34 dB relative to the 15 kHz fundamental with float coefficients and
-137.91 dB when coefficients are rounded to Q1.23 but MACs remain floating.
The bit-accurate Q8.24 sample/Q1.23 coefficient chain, with add-half shift after
every stage, gives -137.81 dB and zero saturation. The intended convolution
accumulator is signed 64 bit. The cubic itself remains floating and is requantized
to Q8.24 because it is only an alias stimulus; it is not tube-model arithmetic.
Polyphase RTL, cycle timing, and synthesis remain open.

Stage tap counts shrink as physical image transitions widen. Symmetry and
half-band zeros reduce unique multiply work further. `design_resampler.py`
regenerates coefficients and the complete report; no hand-edited coefficient
asset exists.
