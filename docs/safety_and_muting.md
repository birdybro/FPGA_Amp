# Safety, reset, and muting

Reference circuit state and physical output safety are separate concerns. On
reset, the solver initializes to its computed DC operating point so coupling
capacitors do not begin at zero volts and create an artificial full-scale event.
ADC/DAC serial interfaces remain muted until clocks are stable, converter reset
is released, frames are valid, and the model has produced a configurable number
of valid samples.

The routed PCM5242 line-output EVT board now implements the independent analog
half of this policy. Three signal relays use normally-open contacts. One
SN74LVC1G08 requires controller relay permission and `HARD_MUTE_N` before their
drivers can energize; a second independently requires controller soft-unmute
permission and `HARD_MUTE_N` before PCM5242 XSMT can rise. All three permission
inputs and XSMT default low. An external power/protection supervisor can
therefore force both mute mechanisms even with a controller output stuck high.
Firmware must configure and read back the DAC under XSMT mute, close relays,
then release XSMT; shutdown first ramps/mutes XSMT and only then opens relays.
This topology is checked for connectivity but its acoustic transient, brownout,
missing-clock, and fault timing remain unmeasured release gates.

The FPGA startup verifier now supplies the stronger digital prerequisite for
that sequence. It does not equate ACKed writes with safe state: it reads back
the masked critical PCM5242 configuration and requires the expected detected
48 kHz / 512-fS SCK / 64-fS BCK clocks, valid-clock flags, DSP boot, and run
state. A NACK or mismatch latches failure. Its `configuration_verified` output
is a one-shot startup snapshot and must still be combined with continuous clock
monitoring, system fault state, and `HARD_MUTE_N`; it is not by itself a
safety-rated output or permission for firmware to bypass the physical gates.

The integrated controller sequences the ACK-only writer, verifier, and periodic
health monitor without firmware races. `unmute_permitted` remains false across
the startup delay and all 48 release operations. It then polls clock-valid,
latched/live clock-error, active/sticky output-short, and DSP power state every
nominal 100 ms; any NACK or masked fault revokes permission and latches evidence
until reset. Simulation covers successful startup, both startup failure phases,
and an output-short indication after unmute. This permission should drive the
controller side of both board interlocks. The external supervisor input retains
independent veto authority and supplies the faster asynchronous safety path.

The controller permission is then split by `dac_line_output_sequencer` into the
two PCB inputs. Normal release asserts `LINE_RELAY_EN_CTL`, waits 491,520 clocks
(5 ms at the 98.304 MHz fabric rate), and only then asserts
`DAC_SOFT_UNMUTE_CTL`. Normal mute deasserts XSMT first, holds the relays closed
for the same conservative ramp interval, and opens them last. An explicit
emergency input deasserts both registered permissions on the next fabric edge;
the PCB supervisor's direct `HARD_MUTE_N` path remains faster and independent.
These digital intervals are starting values for bench measurement, not claims
about acoustic transient performance or relay contact settling.

The low-level pin top reports live BCLK/fabric rate lock after three good
measurement windows and latches any bad window. The register-controlled wrapper
now converts that evidence into a fail-closed digital output policy: it asserts
the existing immediate `force_mute` path until lock, reasserts it on one bad or
stopped-clock window, and holds it after rate reacquisition until the host
explicitly clears the sticky fault. It does not stop the model consumer during
the roughly 1 ms default acquisition, because doing so while a converter
streams would overflow the depth-8 receive FIFO. Thus the model may advance
silently while the output ramp is clamped at zero. A board startup controller
must still coordinate converter data enable, FIFO draining/discard, clock lock,
model initialization, DAC/analog mute, and unmute as one explicit sequence.

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

The control behavior is now formally checked with `make formal-mute`. A Yosys
SAT harness applies one reset clock and then makes every sample/control input
arbitrary. Fifteen assertions cover the synchronous clamp, valid pulse, held
state, exact saturating gain transition, endpoint output, monotonic ramping, and
status decode; temporal induction closes at depth 2. A separate reachability
witness traverses zero, `0x4000`, `0x8000`, `0xc000`, and `0xffff` gain in four
accepted unmute samples. This proof is limited to the digital primitive and
does not establish CDC behavior or physical speaker protection.

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

The clock-fault policy is a modern system-safety layer, not historical circuit
behavior. After lock returns, requiring an explicit diagnostic clear prevents a
transient recovered clock from silently restoring audio. The shortened-window
wrapper regression qualifies three exact-rate windows, stops BCLK, observes the
live lock drop and sticky fault, reacquires while remaining muted, snapshots the
evidence, and clears it through both fabric and I²S domains before the effective
force-mute signal can deassert.

The pin-facing top now places `calibration_commit_guard` in the fabric control
path. ADC and DAC coefficients reset inactive and commit as one pair only while
the digital ramp is fully muted; invalid and unmuted attempts are rejected with
sticky diagnostics. Startup therefore releases the bridge fabric reset,
commits measured coefficients while audio state remains reset/muted, and only
then releases audio state. This prevents mixed input/output scaling but does not
flush the transmit FIFO or replace the longer model-change reset/warmup
transaction.

`make formal-calibration-control` proves the guard's complete one-clock
transition contract for arbitrary candidates and controls. Twelve assertions
require reset inactivity, exact acknowledge, simultaneous two-coefficient
commit only for a positive pair while muted, preservation after invalid/unsafe
attempts, exact sticky accumulation, and diagnostic-clear precedence. Temporal
induction closes at depth 2, and a separate witness reaches invalid rejection,
accepted commit, and unsafe rejection in one trace. This does not prove the
upstream host transport or physical converter behavior.

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
