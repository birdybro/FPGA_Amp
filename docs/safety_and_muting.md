# Safety, reset, and muting

Reference circuit state and physical output safety are separate concerns. On
reset, the solver initializes to its computed DC operating point so coupling
capacitors do not begin at zero volts and create an artificial full-scale event.
ADC/DAC serial interfaces remain muted until clocks are stable, converter reset
is released, frames are valid, and the model has produced a configurable number
of valid samples.

Unmute uses a deterministic gain ramp after the reference model. A default
raised-cosine or linear 20 ms ramp will be compared for spectral residue; the
chosen coefficients and exact latency become part of the control contract.
Mute ramps down before sample-rate, model, calibration, or large parameter
changes, reinitializes the affected state, then ramps up. Emergency faults force
mute immediately even if a graceful ramp is incomplete.

For a future speaker-power path, independent hardware must provide DC detection,
overcurrent/short-circuit protection, overtemperature shutdown, supply
undervoltage/overvoltage handling, startup/shutdown sequencing, and a speaker
disconnect or equivalent safe output. FPGA fault reporting and gain control are
additional layers, not the only protection barrier. The present project has no
speaker output and makes no safety certification claim.
