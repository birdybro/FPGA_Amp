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
-80.54 dBc, but also has a 1.402 mV finite-window projection at 3 kHz before the
decimator. The raw captured output's -74.59 dBc 3 kHz bin therefore remains an
invalid direct alias measurement.

The automated phase-coherent decomposition resolves that confound. It fits all
16 internal frequencies that map to ±3 kHz after 16× downsampling (3, 45, 51,
..., 381 kHz), decimates each through the exact fixed chain, and captures the
combined out-of-band projection in RTL. The isolated 45 kHz component produces
exactly zero Q8.24 output samples in the analysis window. The independent
phase-sum of all out-of-band components is -166.18 dBc; subtracting their input
projection from the original nonstationary trajectory changes the captured
3 kHz output by only 10.77 nV, or -176.96 dBc relative to the 15 kHz output.
That difference is below the 18.96 nV fixed-rounding superposition closure, so
it is treated as a quantization-floor bound rather than a more precise physical
alias claim. The family-removed 3 kHz output is 102.37 dB above the observed
fold effect. Regression gates require at least 150 dB rejection and 90 dB
dominance, with zero saturation and exact fixed/RTL combined projection.

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

The separately named 8× architecture candidate uses only stages 1--3 and
preserves the same 48 kHz input phase contract. Its staggered stage-3 output is
384 kHz, one pulse every 256 fabric clocks. The measured scheduling delay is
eight 384 kHz samples (20.83 µs) beyond the FIR state latency. Exact regression
matches 1,024 interpolation and 128 decimation outputs with zero saturation,
overrun, or phase errors. This establishes the converter arithmetic and clock-
enable schedule. The converter also composes bit-exactly with the 384 kHz
nonlinear core for 64 external outputs / 512 internal updates, with zero
converter, solver, or deadline diagnostics. A longer paired fixed-stream study
then finds the overload-recovery trajectory close but a -15.18 dB aligned
record-pop residual and 85.6 mV peak difference. This aggregate includes the
rate-specific integrator and fixed circuit as well as the converters. It blocks
8× promotion rather than silently accepting the smaller converter.
Direct long-vector RTL matches each rate's corresponding fixed trajectory for
4,096 pop and 8,192 overload/recovery outputs, totaling 24,576 outputs and
294,912 nonlinear updates. This rules out a converter/solver RTL mismatch; it
does not reduce the measured rate-to-rate transient error.

Stage-1 unit tests match 256 input pairs exactly in each direction. Complete
chain tests match 2,048 interpolation outputs and 128 decimation outputs exactly,
with zero saturation, overrun, or input-phase errors. The decimator bench also
supports 131,072 custom inputs / 8,192 captured outputs for spectral tests.
Generic XC7 synthesis
reports 2,053 estimated logic cells / 16 DSP48E1s for interpolation and 3,002 /
32 DSP48E1s for decimation. No Fmax is claimed without place-and-route.

The three-stage candidate synthesizes to 1,549 estimated logic cells / 12
DSP48E1s for interpolation and 2,355 / 24 for decimation. Relative to the
four-stage blocks this removes 504/647 estimated cells and 4/8 DSPs. These are
Yosys structural measurements, not timing results.

Stage tap counts shrink as physical image transitions widen. Symmetry can reduce
resource use further; the present serial cores exploit zeros but do not pre-add
symmetric samples. `design_resampler.py` regenerates the response/alias report,
and `generate_halfband_rtl_vectors.py` regenerates ROMs and exact streams; no
hand-edited coefficient asset exists.
