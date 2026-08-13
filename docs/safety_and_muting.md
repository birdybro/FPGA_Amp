# Safety, reset, and muting

Reference circuit state and physical output safety are separate concerns. On
reset, the solver initializes to its computed DC operating point so coupling
capacitors do not begin at zero volts and create an artificial full-scale event.
ADC/DAC serial interfaces remain muted until clocks are stable, converter reset
is released, frames are valid, and the model has produced a configurable number
of valid samples.

The first implemented system-safety primitive is
`rtl/audio/output_mute_ramp.sv`. It is deliberately downstream of and outside
the historical model. At each valid 48 kHz output sample it moves a Q0.16 gain
by `ceil(65535 / RAMP_SAMPLES)`; the default 2,048-sample linear transition is
42.67 ms. The full-gain state bypasses the multiplier exactly, so reference
samples are bit-identical when unmuted. Intermediate products retain all 49
bits and use symmetric round-to-nearest, ties away from zero. Reset begins
muted. `force_mute` synchronously clears both the held output and gain even in
the absence of a new sample; it is a fast digital clamp, not a substitute for
independent analog protection.

Normal control sequencing ramps down before sample-rate, model, calibration,
or large parameter changes, reinitializes the affected state, then ramps up.
The control wrapper that enforces that sequence is not implemented yet. A
raised-cosine alternative remains a possible modern feature only after its
spectral residue and hardware cost are measured; the present linear behavior is
the explicit implementation contract.

For a future speaker-power path, independent hardware must provide DC detection,
overcurrent/short-circuit protection, overtemperature shutdown, supply
undervoltage/overvoltage handling, startup/shutdown sequencing, and a speaker
disconnect or equivalent safe output. FPGA fault reporting and gain control are
additional layers, not the only protection barrier. The present project has no
speaker output and makes no safety certification claim.
