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
every stage, gives -137.81 dB and zero saturation. The convolution accumulator
is signed 63 bit. The cubic itself remains floating and is requantized to Q8.24
because it is only an alias stimulus; it is not tube-model arithmetic.

The same fixed cubic trajectory now drives the synthesizable complete 16×
decimator for 131,072 internal samples. All 8,192 captured 48 kHz outputs are
bit-exact to the fixed model. Over the final 4,096 samples, the measured 3 kHz
alias is -137.814 dB relative to the 15 kHz fundamental, with zero interpolation
or decimation saturation. The regression fails if rejection rises above
-120 dB.

An additional 8,192-output full phono-stream capture uses a 0.5 V / 15 kHz
stress tone. It is exact and produces an internal 45 kHz third harmonic at
-80.54 dBc, but also has a 1.402 mV component already at 3 kHz before the
decimator. The captured output's -74.59 dBc 3 kHz bin therefore cannot be used
as a pure alias measurement. That confound is retained in the report rather
than crediting the decimator with an invalid 1.82 dB rejection number.

## RTL implementation

The synthesizable implementation exploits half-band zeros. The interpolator
serially evaluates only the even-indexed off-center phase and implements the
other phase as the exact delayed center sample. The decimator evaluates the
even-indexed taps plus the exact center product. Both use Q8.24 samples, Q1.23
coefficients, add-half/arithmetic-shift rounding, output saturation, and explicit
overrun counters.

At 98.304 MHz the four interpolation output phases are staggered so all MACs
complete before consumption; all signals remain in one clock domain. The
hardware schedule adds 18 samples at 768 kHz (23.44 µs) beyond the FIR state
latency, and this delay is present in—not aligned out of—the exact regression.
The decimator is self-timed by upstream valid pulses.

Stage-1 unit tests match 256 input pairs exactly in each direction. Complete
chain tests match 2,048 interpolation outputs and 128 decimation outputs exactly,
with zero saturation, overrun, or input-phase errors. The decimator bench also
supports 131,072 custom inputs / 8,192 captured outputs for spectral tests.
Generic XC7 synthesis
reports 2,053 estimated logic cells / 16 DSP48E1s for interpolation and 3,002 /
32 DSP48E1s for decimation. No Fmax is claimed without place-and-route.

Stage tap counts shrink as physical image transitions widen. Symmetry can reduce
resource use further; the present serial cores exploit zeros but do not pre-add
symmetric samples. `design_resampler.py` regenerates the response/alias report,
and `generate_halfband_rtl_vectors.py` regenerates ROMs and exact streams; no
hand-edited coefficient asset exists.
