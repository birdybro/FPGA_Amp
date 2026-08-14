# Safety, reset, and muting

Reference circuit state and physical output safety are separate concerns. On
reset, the solver initializes to its computed DC operating point so coupling
capacitors do not begin at zero volts and create an artificial full-scale event.
ADC/DAC serial interfaces remain muted until clocks are stable, converter reset
is released, frames are valid, and the model has produced a configurable number
of valid samples.

The pin top now reports live BCLK/fabric rate lock after three good measurement
windows and latches any bad window. It does not automatically gate audio reset:
holding the model consumer stopped for the roughly 1 ms acquisition while a
converter streams would overflow the depth-8 receive FIFO. A board startup
controller must coordinate converter data enable, FIFO draining/discard, clock
lock, model initialization, and analog mute as one explicit sequence.

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
`rtl/control/model_change_guard.sv` now enforces that sequence around the wide
stream. With the 98.304 MHz / 48 kHz clock plan it waits for a sample boundary,
holds reset through 2,047 clocks, and releases the core for the next boundary.
The default 64 valid-output warmup is 1.333 ms and remains at zero gain. The
acknowledgment means reset and warmup are complete and ramp-up has begun; the
separate `output_ready` flag means unity gain has actually been restored.
Requests are accepted only while ready and must return low before another
transaction. `force_mute` remains an independent immediate clamp and does not
implicitly change circuit state.

The fabric mono adapter separately holds its accuracy-first core in reset while
the frame scheduler acquires initial phase. This prevents unrequested
interpolator zeros from advancing virtual capacitor state before the first PCM
frame. The modern output ramp now follows that exact trapezoidal/banked/terminal
model and precedes DAC calibration. Reset begins muted, the default transition
is 2,048 valid outputs, and exact unity bypasses multiplication. The integration
test uses eight samples so unity is reached before the first nonzero fixture
output; all later reference samples remain bit-identical. A force-mute request
clears the ramp state synchronously, but it cannot revoke PCM frames already in
the adapter hold register or asynchronous transmit FIFO. Dedicated analog mute
remains required.

The pin-facing top now places `calibration_commit_guard` in the fabric control
path. ADC and DAC coefficients reset inactive and commit as one pair only while
the digital ramp is fully muted; invalid and unmuted attempts are rejected with
sticky diagnostics. Startup therefore releases the bridge fabric reset,
commits measured coefficients while audio state remains reset/muted, and only
then releases audio state. This prevents mixed input/output scaling but does not
flush the transmit FIFO or replace the longer model-change reset/warmup
transaction.

The integration regression uses four-sample ramps/warmup for tractable directed
coverage and proves that reset never becomes active before mute, held output
stays zero through reset/warmup, input phase diagnostics remain clear, exactly
one acknowledgment occurs, and unity output returns. Default parameter timing
is elaborated and structurally synthesized but has not been tested with physical
converters. A raised-cosine alternative remains a possible modern feature only after its
spectral residue and hardware cost are measured; the present linear behavior is
the explicit implementation contract.

For a future speaker-power path, independent hardware must provide DC detection,
overcurrent/short-circuit protection, overtemperature shutdown, supply
undervoltage/overvoltage handling, startup/shutdown sequencing, and a speaker
disconnect or equivalent safe output. FPGA fault reporting and gain control are
additional layers, not the only protection barrier. The present project has no
speaker output and makes no safety certification claim.
