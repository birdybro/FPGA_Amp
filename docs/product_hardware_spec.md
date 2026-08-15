# Product hardware specification — V1 platform

Status: architecture baseline, not a released schematic or production claim.  
Machine-readable requirements: `hardware/product_v1/requirements.json`.  
Signal/contact budget: `hardware/product_v1/interface_budget.csv`.  
Last reviewed: 2026-08-15.

This specification turns the existing phono-model prototype into a product
platform with a TV input, premium local controls, and a motorized volume dial.
It deliberately does not change the frozen two-stage 12AX7 passive-RIAA
circuit. HDMI eARC, asynchronous rate conversion, master volume, display,
remote control, muting, and protection are modern system functions outside the
historical model (`SYS-002`).

The product is a line-level component in V1. A later clean physical power
amplifier may be attached, but speaker power and speaker protection are not
provided by the FPGA or by the V1 line-output boards.

## 1. Decisions and release gates

### 1.1 Frozen architecture decisions

- Use five cooperating PCBs rather than one mixed-signal board (`SYS-001`).
- Keep phono input/RIAA modeling, TV audio, and safety/UX layers explicitly
  separated (`SYS-002`, `SYS-004`).
- Use a local low-jitter 48 kHz-family clock for ADC, FPGA output, and DAC;
  cross TV audio through an asynchronous sample-rate converter (`CLK-001`,
  `EARC-005`).
- Advertise only stereo LPCM in V1. Do not claim or expose compressed-audio,
  Atmos, DTS, DSD, or multichannel decoding (`EARC-002`, `EARC-004`).
- Use the volume dial only as a position/control transducer. It carries no
  audio (`VOL-002`).
- Provide local mute and standby controls that work without the LCD
  (`UI-004`).
- Build and program FPGA images with Yosys, nextpnr/Project X-Ray, and
  openFPGALoader; a vendor-IDE-only device is not an acceptable production
  substitution (`FPGA-001`).

### 1.2 Provisional component selections

| Function | Baseline candidate | Reason and open gate |
|---|---|---|
| eARC/ARC receiver | Lattice SiI9437 | Audio-device eARC receiver with four-lane I2S and S/PDIF output. Selection is conditional on current supply, full documentation, vendor software terms, licensed reference design, and adopter/compliance access. |
| full HDMI contingency | Analog Devices ADV7671A | Current 48 Gbit/s transceiver with eARC receiver support, but its video/HDCP complexity, 108-LFCSP package, licensed high-level API, and adopter requirements make it an expensive fallback rather than the audio-only baseline. |
| asynchronous SRC | TI SRC4392 | Active two-channel converter, host control/diagnostics, 24-bit words, and rates through 216 kHz. ADI AD1896 is the no-programming alternate. Bench comparison must measure lock behavior, group delay, spur floor, and recovery. |
| FPGA | XC7A200T resource class, SBG484 prototype baseline | Existing mono hierarchy openly routes on this device. The exact production package and speed grade remain provisional until stereo/full-path synthesis, power analysis, SI, and sourcing close. |
| front-panel MCU | STM32H753ZIT6-class Cortex-M7 | LTDC, external-memory interface, Ethernet MAC, timers/ADCs, 2 MiB flash, and hardware cryptography in a serviceable LQFP-class package. Firmware shall use an open GCC/Clang build even if manufacturer configuration tools assist bring-up. |
| LCD/touch | Newhaven NHD-5.0-800480AF-ASXP-CTP | 5-inch, 800 x 480, 24-bit RGB, IPS, capacitive FT5426G touch over I2C, cover glass, EMI-shielded FPC, and high-brightness backlight. Lifecycle and backlight thermal tests remain gates. |
| motorized rotary prototype | Bourns PRM16 dual-track motorized control | Available rotary prototype part with manual/motor operation. Its 15,000-cycle rating is not acceptable as the unqualified production life claim. |
| production volume mechanism | supported metal shaft + position sensor + back-drivable gearmotor, or qualified motor-pot | Must pass the mechanical feel, acoustic, stall, manual override, and at least 100,000 full-range-cycle qualification in `VOL-006`. A front bearing/coupler carries the large knob load. |
| volume motor driver | TI DRV8874 | Bidirectional H-bridge with current regulation, proportional current feedback, fault indication, and supply range compatible with prototype motor rails. Current limit is set for the selected mechanism, not for the driver's maximum rating. |
| other rotary controls | Grayhill 62H or Bourns EM14 optical encoder | Metal shaft/bushing, quadrature output, push option, and long published rotational life. Final detent torque and resolution are selected by a physical human-factors trial. |

The parts table is not permission to copy a public data brief into a schematic.
In particular, the HDMI connector network and receiver layout shall come from
the licensed specification and vendor reference design after `EARC-008` is
closed.

### 1.3 Production stop conditions

Do not order a production PCB or advertise eARC until all of these are true:

1. the manufacturer is operating under the required HDMI adopter agreement;
2. the receiver vendor has supplied the complete register/API, schematic,
   layout, firmware, errata, and compliance package;
3. the selected receiver and approved connector have a credible production
   supply path;
4. stereo FPGA processing meets numerical, timing, resource, and thermal gates
   (`SYS-003`);
5. a pre-layout power-integrity and signal-integrity review is complete;
6. the eARC design passes analyzer tests and multi-vendor TV interoperability;
7. HDMI compliance is completed for the finished product (`EARC-008`,
   `TEST-002`); and
8. the full board set passes the noise, mute, motor, ESD, thermal, and analog
   acceptance tests in section 18.

An HDMI receiver component does not license the finished device. HDMI LA states
that the finished product must be made by an adopter and satisfy compliance
requirements even if it contains licensed components.

## 2. System partition

```text
                            PRODUCT CHASSIS

  MM RCA L/R + ground                          TV eARC/ARC
          |                                         |
          v                                         v
  +----------------+       local I2S       +-----------------------+
  | AB: PHONO/ADC  |---------------------->| DB: eARC + ASRC + FPGA|
  | termination    |                       | source router          |
  | flat gain      |                       | physical models        |
  | anti-alias     |                       | volume/mute/diagnostics |
  +----------------+                       +-----------+-----------+
                                                      |
                                            local I2S |
                                                      v
  +----------------+       control SPI     +-----------------------+
  | FP: LCD/TOUCH  |<--------------------->| OB: DAC + LINE OUTPUT |
  | encoders       |                       | reconstruction/filter  |
  | motor volume   |                       | analog mute/line driver|
  | remote host    |                       +-----------------------+
  +-------+--------+
          |
          | power-good / hard-mute / fault
          v
  +---------------------------------------------------------------+
  | PB: DC INPUT + RAIL SEQUENCING + SUPERVISION + PROTECTION     |
  +---------------------------------------------------------------+
```

The phono/ADC board occupies the quiet rear corner immediately behind the RCA
jacks. The HDMI connector and eARC receiver occupy the opposite rear corner.
The FPGA and switching regulators remain between those zones only when plane
and enclosure current paths have been reviewed. The front-panel motor and
backlight are physically remote from the cartridge input (`EMC-002`).

### 2.1 DB — digital and eARC mainboard

Responsibilities:

- approved Type-A TV-audio connector, eARC/ARC receiver, CEC/control support,
  capability data, link diagnostics, and ESD network;
- incoming-TV-clock serial audio capture;
- stereo asynchronous rate conversion into the local audio domain;
- local master oscillator, FPGA clocks, ADC/DAC clocks, and reset sequencing;
- FPGA, configuration flash, JTAG, serial control, source routing, model
  processing, master volume, delay, muting, and diagnostic counters;
- board-identity/calibration EEPROM and temperature/rail monitors; and
- service USB/UART/JTAG headers that can be depopulated for production.

### 2.2 AB — shielded phono and ADC board

Responsibilities inherit the quantitative design in `analog_frontend.md`:

- two RCA inputs, turntable ground post, 47.5 kilohm termination, and
  selectable 0/47/100 pF installed input capacitance (`PHONO-001`,
  `PHONO-003`);
- low-capacitance ESD/RF protection whose capacitance is included in the total
  cartridge load;
- 20/26/32 dB relay- or low-leakage-switch-selected flat gain (`PHONO-002`);
- fully characterized input-referred noise and overload behavior;
- differential anti-alias drive and a stereo 24-bit-class ADC (`CONV-001`);
- a local low-noise post-regulator tree from separately supplied analog rails;
  and
- no display, motor, radio, HDMI, or high-current switching load.

The physical input loading is required even though the reference tube circuit
is digital. Cartridge inductance, cable capacitance, front-end capacitance, and
47.5 kilohm resistance form a real electrical network before the ADC.

### 2.3 OB — DAC and line-output board

Responsibilities:

- stereo 24-bit-class DAC clocked from the local audio domain;
- reconstruction filtering and a low-noise line driver;
- nominal consumer output near 2 V RMS and a balanced path with sufficient
  clean headroom for the documented 2.25 V RMS reference case;
- calibrated output scaling owned atomically with ADC calibration
  (`CONV-003`);
- balanced outputs preferred, plus protected single-ended outputs
  (`CONV-002`);
- hardware analog mute that defaults active when power, clocks, configuration,
  or supervisory state is invalid (`SAFE-001`, `SAFE-002`); and
- output DC/overload monitoring and test injection points.

Line muting may use an audio-qualified relay or a measured low-distortion solid
state arrangement. The release decision is based on THD+N, resistance,
charge-injection transient, fail state, and lifetime measurements, not on part
category alone.

### 2.4 FP — front-panel board

Responsibilities:

- MCU, external SDRAM/QSPI flash, LCD timing, touch input, encoder decoding,
  LEDs, ambient-light sensing, and local settings storage;
- volume position sensing, H-bridge control, current/stall detection, manual
  takeover, and motor fault reporting;
- protocol-neutral FPGA register access over SPI plus interrupt and heartbeat;
- optional Ethernet and a socketed/certified Wi-Fi/BLE module, with local-only
  operation always available (`UI-006`); and
- direct physical mute/standby paths that do not depend on the GUI task.

The MCU owns the GUI and user intent, not audio samples. If it resets, the FPGA
continues with the last valid settings only under the selected safe policy; an
invalid heartbeat, malformed transaction, or explicit safety event mutes
output (`UI-005`, `SAFE-002`).

### 2.5 PB — power and protection board

V1 uses an external safety-certified DC supply so mains does not enter the
development enclosure (`PWR-001`). PB provides input fuse/e-fuse, reverse and
surge protection, standby supply, sequenced main rails, rail monitoring,
thermal sensing, hard-mute logic, and keyed board distribution. A future
integrated speaker amplifier gets a separate high-current supply/protection
design and may not borrow this line-level protection argument (`SAFE-003`).

## 3. Source and processing modes

| Source | Clock boundary | Allowed processing | Forbidden implicit behavior |
|---|---|---|---|
| MM phono | local ADC clock | input calibration -> frozen V1 tube/RIAA model -> optional explicitly labeled modern subsonic -> master volume -> DAC | bypassing or retuning historical RIAA because another mode sounds better |
| TV eARC/ARC | TV clock -> ASRC -> local clock | bypass/line mode initially; later selected virtual line or complete-amplifier model -> master volume -> DAC | sending TV PCM through phono RIAA; silently discarding channels; claiming compressed decode |
| service digital generator | explicit local or asynchronous test clock | bypass or selected model with capture diagnostics | entering customer mode without an obvious test indication |

The first eARC firmware shall publish capability data for two-channel LPCM only
(`EARC-002`). V1 accepts 16/20/24-bit PCM containers at the rates proven during
bring-up, with a design target through 192 kHz (`EARC-003`). If the link presents
an unadvertised or unsupported format, the product mutes that source, records
the received status, and tells the user why. It does not interpret IEC 61937
payloads as PCM.

The UI may expose the following clearly labeled paths:

- **Phono Reference** — frozen phono circuit, no modern filter.
- **Phono Modern** — same reference model plus separately identified modern
  options.
- **TV Direct** — ASRC, delay, master volume, and DAC.
- **TV Amplifier** — future line/full-amplifier model, never the phono model.
- **Diagnostic Loop** — factory/service only.

## 4. eARC/ARC electrical and protocol architecture

### 4.1 Receiver choice and connector

The SiI9437 is the preferred audio-only receiver because its public brief
describes eARC/ARC reception, an eARC discovery/control channel, I2C control,
four I2S outputs, and an IEC 60958 output. The public brief also describes up to
eight-channel, 24-bit, 192 kHz transport capability. Those transport limits do
not authorize V1 to advertise decoders that do not exist.

The DB layout shall:

- use an HDMI-approved connector applicable to the licensed design;
- place receiver, prescribed common-mode/ESD components, and connector as a
  compact vendor-reviewed block;
- route eARC differential signals at the impedance, loss, skew, and reference
  plane required by the licensed reference design;
- connect DDC/CEC/HPD/5 V detection and every unused connector signal exactly
  as required by the licensed implementation, not by guesswork from a public
  pin summary;
- bond the connector shell to chassis at entry with the reviewed high-frequency
  return network (`EMC-001`); and
- place accessible link-status and bus test points without creating stubs on
  sensitive high-speed nets.

The ADV7671A is retained only if the product later needs a full video
transceiver. Its official page says purchase/sample access requires HDMI 2.1
and HDCP 2.x adopter status. Adding it would also add high-speed video lanes,
HDCP/key handling, API integration, power, BGA/LFCSP layout, and compliance
scope that an audio-only receiver avoids.

### 4.2 Capability and control policy

Capability data shall be generated from one versioned table shared by receiver
firmware and UI. Automated tests decode that table and fail if it advertises a
format absent from the audio router (`EARC-004`). Initial capability:

```text
channels:       2
encoding:       LPCM
word lengths:   advertise only receiver/ASRC/router combinations tested
sample rates:   32 / 44.1 / 48 / 88.2 / 96 / 176.4 / 192 kHz as qualified
compressed:     none
multichannel:   none
```

ARC fallback is a separate tested state. If a TV exposes only legacy ARC, V1
accepts the stereo PCM subset proven with that receiver. The UI reports
`eARC`, `ARC`, `no link`, `unsupported format`, or `receiver fault` rather than
presenting all failures as silence.

CEC or receiver-supported control messages may request volume, mute, standby,
or active source (`EARC-007`). They enter the same event queue as the physical
dial, touchscreen, Ethernet, and radio remote. No source writes FPGA gain
registers directly.

### 4.3 Clock boundary and ASRC

The TV/eARC receiver is an asynchronous audio source. Its I2S clocks enter only
the source side of the SRC4392-class boundary. The ASRC output is subordinate
to the local 48 kHz audio clock. This arrangement:

- prevents TV clock ppm error from filling or emptying a finite audio FIFO;
- attenuates incoming sample-clock jitter before the physical model and DAC;
- lets the phono ADC and DAC remain synchronous; and
- makes the FPGA model operate at one calibrated external rate.

A plain asynchronous FIFO is not a rate converter and is not accepted as the
steady-state clock-drift solution. The selected ASRC must be measured for pass
band, alias rejection, idle tones, THD+N, group delay, ratio-change transients,
lock time, and mute behavior. The AD1896 remains a pin-programmed alternate if
the SRC4392 host/control complexity proves unnecessary.

The ASRC output feeds the FPGA as stereo 24-bit I2S at local 48 kHz. A bypass
relay in firmware is permitted only when input and local clocks are proven
synchronous and the transition occurs under mute. Normal eARC operation keeps
ASRC enabled.

### 4.4 TV latency and diagnostics

DB exposes at least (`EARC-006`):

- connector 5 V/HPD state;
- receiver reset/boot/API version;
- discovery result and eARC versus ARC mode;
- capability exchange completion;
- incoming coding type, word length, channel count, and measured sample rate;
- I2S framing error, receiver interrupt/fault, and CEC error counters;
- ASRC lock, ratio class, input/output mute, and overflow/underflow evidence;
- source-to-DAC sample count and measured analog latency; and
- the last rejected-format reason.

Provide a user TV-delay control after ASRC and before master volume. Initial
storage reserves 0–250 ms in 1 ms user steps, but the actual range and step are
frozen only after memory sizing and lip-sync tests. Changing delay is
cross-faded or performed while muted; it may not drop/duplicate a sample
without an explicit discontinuity diagnostic.

## 5. Audio clocks and reset domains

The local clock family is based on a low-phase-noise 24.576 MHz or 12.288 MHz
audio oscillator. The selected FPGA plan derives the exact fabric and internal
sample enables documented in `adc_dac.md`; no fractional PLL approximation is
accepted without measured jitter and rate error. The current Nexys path uses
12.288 MHz MCLK, 3.072 MHz BCLK, 48 kHz LRCLK, 49.152 MHz fabric, and a 384 kHz
model enable.

Clock ownership:

| Domain | Owner | Crossings |
|---|---|---|
| local audio serial | DB oscillator/FPGA clock leaf | AB ADC in, OB DAC out, ASRC output |
| FPGA fabric | DB FPGA clock manager | clock enables only for model/resampler |
| eARC input audio | TV through eARC receiver | terminates at ASRC input |
| front-panel control | FP MCU | oversampled SPI plus explicit IRQ/heartbeat synchronizers |
| touch/encoder/motor | FP MCU timers/GPIO | never enters FPGA as raw edges |
| power supervisor | PB asynchronous logic | fail-safe static inputs and qualified synchronizers |

Every reset asserts asynchronously where required for safety and releases
synchronously in the owning domain (`CLK-002`). Startup order is:

1. PB asserts hard analog mute and holds main reset.
2. Standby and monitored rails become valid.
3. Local oscillator and FPGA configuration become valid.
4. FPGA rate monitors acquire lock; ADC, ASRC, and DAC remain muted/reset.
5. Control firmware identifies every board and checks compatible versions.
6. Converter configuration and readback complete.
7. ADC/DAC calibration commits as a muted atomic pair.
8. Model state initializes at its DC operating point and consumes stable frames.
9. Digital output ramps from zero.
10. OB analog mute releases last.

Shutdown reverses the audible portion: analog mute first, digital ramp/reset
second, rails last. Brownout and watchdog faults jump immediately to analog
mute (`PWR-003`).

## 6. FPGA and memory architecture

The current `XC7A200T-SBG484` implementation is a prototype sizing baseline,
not a production-package freeze (`FPGA-002`). It openly routes the mono 384 kHz
phono top using 217 DSP48E1 blocks and has not yet proven stereo or a complete
amplifier. Before DB schematic freeze:

- synthesize and place/route the exact stereo product hierarchy;
- include eARC router, stereo ASRC interface, delay RAM, source crossfades,
  volume, control, diagnostic snapshots, configuration, and both audio ports;
- reserve measured headroom for the selected full-amplifier milestone rather
  than assuming unused headline resources are routable;
- generate switching activity and size the core/auxiliary regulators and
  thermal path from measured implementation data; and
- retain the exact open-source tool/database revisions and reproducible
  bitstream manifest.

DB provides nonvolatile configuration flash supported by the open programming
flow, JTAG pads/header, a recoverable golden image or external recovery path,
board ID EEPROM, and sufficient block/external memory for TV delay and future
model assets. External memory is outside the real-time solver unless its worst
case latency is bounded.

The current protocol-neutral 32-bit register bus remains the audio control ABI.
FP receives no direct internal-node write access outside labeled creative or
service modes. Runtime counters include saturation, solver residual failure,
iteration count, deadline miss, FIFO errors, converter clipping, invalid
control commit, rate/link fault, and mute cause (`FPGA-003`).

## 7. Front-panel display and touch

The baseline display is 5-inch, 800 x 480, IPS, capacitive touch, and 24-bit
parallel RGB (`UI-001`). The candidate Newhaven module's official product page
identifies a 900-nit backlight, FT5426G I2C touch controller, cover glass,
3.3 V logic, and EMI-shielded FPC. The production build shall add:

- MCU LTDC output with series damping selected from edge-rate/SI measurements;
- local framebuffer in at least 16 MiB SDRAM, with 32 MiB preferred;
- QSPI asset/firmware flash sized after UI assets are frozen;
- backlight constant-current driver with >25 kHz PWM or measured DC dimming;
- ambient-light input and a user-set maximum brightness;
- touch interrupt/reset, ESD protection, and production calibration;
- a shield/back plate bonded through the intended chassis return; and
- a replaceable FFC/interposer arrangement that does not require replacing DB.

The front-panel MCU renders the display (`UI-002`). The FPGA neither scans
touch nor generates pixels. The screen shows source/link format, active model
and category (reference/variation/modern/creative), volume, mute, clock/link
faults, and a diagnostics page. It never hides an unsupported TV format behind
a generic spinner.

The LCD is not a safety interface. Mute, standby, and volume remain usable when
the display cable is disconnected. Touch targets are sized for finger use,
critical destructive actions require confirmation, and reference-mode changes
remain visibly labeled.

## 8. Physical controls

The proposed front-panel control set is:

| Control | Mechanical function | Electrical function |
|---|---|---|
| volume | large 50 mm-class aluminum dial, smooth rotation, motor follow | absolute position request, never analog audio |
| source/select | premium detented optical encoder with push | source selection and confirm |
| model | premium detented optical encoder with push | reference model/variation selection |
| parameter | premium detented optical encoder with push | context-sensitive parameter, balance, or tone function |
| mute | dedicated illuminated momentary button | MCU event plus independent hard-mute request path |
| standby | dedicated button | PB-supervised standby request |

Grayhill 62H and Bourns EM14 are current encoder candidates (`UI-003`). Both
offer metal shaft/bushing optical construction; published configurations and
life differ. Order multiple detent/torque samples and perform a blind tactile
trial with the final knob inertia. The electrical design provides Schmitt
inputs, pull resistors per manufacturer guidance, ESD protection at panel
cables, hardware timer decoding where available, and impossible-transition
counters.

Knob shafts must be panel supported. Encoder/volume bushings locate the control
but do not carry cantilever loads from a heavy cosmetic knob. The volume
assembly uses a front bearing or supported coupler, anti-rotation structure,
and serviceable connector (`MECH-002`).

## 9. Motorized volume system

### 9.1 Signal ownership

There is one authoritative `volume_target` in signed decibels. Physical,
touchscreen, CEC/TV, Ethernet, Wi-Fi/BLE, and restore-on-boot events are
serialized by the front-panel MCU. The MCU commits target plus monotonic
sequence number to the FPGA. The FPGA applies click-free gain outside the
reference model and returns the accepted sequence/effective gain. Only the
accepted effective gain drives the motor target and display (`VOL-005`).

Suggested UI mapping is -96 dB through 0 dB with a distinct hard-mute state.
User steps may be 0.5 dB while internal gain and remote ramps use finer
resolution. The exact law is frozen after listening and level-resolution tests,
but it remains a modern output control and cannot modify tube operating points.

### 9.2 Position sensor and prototype mechanism

For the PRM16 prototype, one resistive section is excited from the filtered MCU
ADC reference and read ratiometrically; the second section may be used for
plausibility or left available for evaluation. Neither section carries audio
(`VOL-002`). Production may replace it with a supported shaft, absolute
magnetic/optical angle sensor, and back-drivable gearmotor if that produces
better feel and life.

At manufacturing calibration, the MCU learns safe low/high endpoints, maps the
usable span to volume, and stores values with CRC plus board serial number.
Endpoint calibration is clamped inside mechanical stops and may not be run by
normal users.

### 9.3 Servo and motor driver

The DRV8874-class H-bridge receives a separately filtered motor rail, 25 kHz or
higher PWM, direction/enable, sleep, current-limit setting, proportional
current feedback, and fault feedback (`VOL-003`). The motor rail and return go
directly to PB/FP power entry rather than through touch/display ground traces.
The MCU ADC samples position and motor current synchronously to PWM blanking.

The servo shall implement (`VOL-004`):

- position-dependent speed so large remote moves are quick and the final
  approach is quiet;
- a deadband that removes hunting and leaves the bridge in coast/sleep;
- soft endpoints inside calibrated hard stops;
- a bounded movement timeout and accumulated motor-on-time diagnostic;
- current-limited stall detection with immediate coast, latched fault, and UI
  report;
- reversal dead time and command slew;
- local manual movement detection while the bridge is idle;
- manual override/current rise handling while driven; and
- no automatic retry against a mechanical stop.

The mechanism-independent portion is now implemented in
`firmware/front_panel/volume_servo.c` with a warning-as-error host regression.
It explicitly retains command intent through reversal dead time; without that
state, the idle-manual detector can mistake a pending remote reversal for a
back-driven knob and cancel it. The core is not a physical motor validation or
an STM32 peripheral implementation. PWM timing, ADC/current filtering, grip
detection, and exact tick parameters are closed on the FP prototype.

The motor is normally unpowered. Grabbing the dial must not expose unsafe
torque or cause the control loop to fight continuously. A production prototype
should evaluate a capacitive grip electrode or clutch if current-limited
back-drive does not feel natural.

### 9.4 Motor acceptance

Prototype Bourns/Alps-class motor pots commonly publish roughly 15,000-cycle
life. Therefore the production assembly must complete at least 100,000
full-range remote cycles under representative knob inertia and enclosure
temperature, followed by position-linearity, backlash, acoustic-noise, stall,
and manual-feel checks (`VOL-006`). The test logs motor current and travel time
to identify wear trends. This is a design qualification requirement, not a
claim that the current candidate passes it.

## 10. Remote-control architecture

Remote operation is additive:

- CEC/TV control through the selected eARC receiver when supported;
- wired 10/100 Ethernet through the front-panel MCU MAC/PHY;
- optional certified Wi-Fi/BLE module on FP, isolated from the phono zone and
  able to be depopulated or disabled; and
- USB-C service/configuration with no requirement for a cloud account.

All transports call the same settings API. Authentication is mandatory on IP
control, remote access is disabled by default until commissioned, and network
services bind only as configured. Firmware update uses signed images, an
anti-rollback policy appropriate to release state, and a recovery image or
physical recovery path (`FW-001`). Audio remains locally usable without any
network (`UI-006`).

Hardware revision, FPGA ABI, UI firmware, eARC firmware/API, converter setup,
and model asset versions are reported together. Incompatible combinations stay
muted and show a precise error (`FW-002`).

## 11. Power architecture

The line-level product accepts a locking external DC input from a certified
supply. A 24 V distribution voltage is preferred because it supports efficient
distribution and future line-driver headroom, but connector, input range, and
wattage are frozen only after measured FPGA/display/motor load and 30% design
margin are available.

Preliminary rail tree:

```text
external DC
   |
   +-- always-on standby -> supervisor / power button / hard mute
   |
   +-- digital preregulator -> FPGA core / auxiliary / I/O post-regulators
   |                       -> eARC receiver rails
   |                       -> ASRC and digital clock rails
   |
   +-- UI preregulator ------> MCU / SDRAM / QSPI / touch
   |                       -> constant-current LCD backlight
   |
   +-- motor rail -----------> current-limited H-bridge (normally asleep)
   |
   +-- low-noise analog -----> AB ADC/front-end local post-regulators
                           -> OB DAC/line-driver local post-regulators
```

Motor, backlight, FPGA, converter digital, converter analog, phono analog, and
line-driver rails are separate at the impedance-sensitive level (`PWR-002`).
This does not mean arbitrary split grounds. Each board uses a continuous local
reference plane, deliberate connector returns, and controlled chassis/signal
bonding. Switching nodes remain compact and outside the phono enclosure zone.

Every rail has design-min/max load, startup monotonicity, soft start,
sequencing dependency, ripple/noise mask, test point, and fault response before
schematic release. FPGA rail current comes from a post-route activity-based
estimate with margin and is verified on hardware; headline typical current is
not adequate.

## 12. Grounding, EMC, and physical layout

### 12.1 Chassis and signal reference

- Conductive chassis panels bond at low impedance; paint/anodizing is removed
  or pierced at designated bonds (`MECH-001`).
- HDMI shell, USB shield, Ethernet magnetics/shield, XLR pin-1/shield, and ESD
  return at their entry zones, with the exact DC/RF bond selected in EMC test.
- Turntable ground gets a dedicated binding post adjacent to phono RCAs and a
  documented connection to chassis/signal reference.
- Phono RCA grounds do not carry display, motor, eARC, or DC-input currents.
- Balanced internal audio is preferred when a cable leaves a board.
- Board-to-board connectors assign return pins beside each fast clock/data
  group and do not share one remote ground pin for high-current and phono
  returns.

### 12.2 Noise zoning

The AB board gets a shielding can or compartment. HDMI/eARC, FPGA clocks,
configuration flash, display RGB, backlight switch node, radio antenna, and
motor/motor cable remain outside it (`EMC-002`). Motor wires are a close
twisted pair with local suppression selected after motor emissions testing.
Backlight and motor PWM run above the audio band, but frequency placement alone
does not prove absence of intermodulation (`EMC-003`).

Worst-case phono tests exercise full-white/display-pattern changes, maximum
backlight PWM, Ethernet traffic, radio transmit, FPGA stress activity, repeated
motor moves, and eARC link changes individually and together (`TEST-003`).

### 12.3 ESD/RF

External ports use protectors selected for the port impedance and capacitance.
Protection returns to chassis before sensitive traces. The MM protector's
capacitance is measured and counted in selectable cartridge load. The exact
eARC protector and common-mode parts come from receiver reference/compliance
guidance. Pre-compliance includes contact/air ESD, EFT on the DC input where
applicable, conducted/radiated emissions, RF immunity, and graceful recovery.

## 13. Connectors and service access

Rear-panel baseline:

- 1 x approved Type-A TV eARC/ARC connector;
- 2 x phono RCA plus turntable ground post;
- 2 x balanced line outputs, with 2 x RCA line outputs preferred;
- locking DC power input;
- 10/100 Ethernet where fitted;
- USB-C service/configuration, explicitly not assumed to be USB-PD power;
- optional 12 V trigger in/out after protection review; and
- an expansion connector for a future clean power amplifier, carrying
  differential audio, mute, fault, standby, and low-current control—not raw
  speaker current through the line-level stack.

Internal connectors are keyed, locking, and pin-staggered where sequencing
matters. AB/OB audio clock and data connectors include local grounds and reset/
fault lines. FP control includes SPI, IRQ, heartbeat, and hard-mute request.
PB supervisory lines are electrically valid when destination rails are absent.

Production JTAG/SWD/UART and rail test pads remain accessible after assembly
but may require an authenticated/service fixture. Each board includes a read-
only identity/calibration EEPROM or equivalent (`TEST-001`).

## 14. Control plane and settings integrity

`IF-CTRL-FP-DB` carries the existing protocol-neutral register transactions
through SPI. FP is SPI main; DB oversamples the raw input in the fabric clock
and reports frame/underflow errors. Production timing is set below the placed
oversampling limit with at least the documented margin.

Settings update rules:

- active audio parameters use shadow/commit semantics;
- state-disruptive model/rate/source changes ramp down, reset or cross-fade,
  warm up, and ramp up;
- ADC/DAC calibration changes only while muted and commits atomically;
- reference mode exposes only values belonging to the frozen model;
- modern/creative settings carry their category in register snapshots and
  saved presets; and
- control sequence, source, volume, mute cause, model version, and diagnostic
  snapshot are captured with every hardware-comparison recording.

The UI heartbeat is not used as a high-frequency audio command. Its timeout and
safe action are explicit. A UI reboot cannot send uninitialized zeros as valid
configuration (`UI-005`).

## 15. Safety, mute, and fault behavior

There are three mute layers:

1. FPGA sample-domain ramp for click-free normal operations;
2. DAC mute/configuration state; and
3. independent OB/PB analog mute, asserted by hardware default.

The dedicated front mute button requests both normal digital mute and a direct
hardware-safe path. Normal user action may ramp before opening the analog path;
a rail, clock, watchdog, overtemperature, DC, or control-integrity fault asserts
hardware mute immediately (`UI-004`, `SAFE-001`).

Fault state is latched with a cause and cannot silently clear merely because a
clock returned. Recovery verifies rails, clocks, receiver/converter state,
model initialization, calibration, and digital zero before controlled unmute
(`SAFE-002`).

If a later physical speaker amplifier is installed, dedicated hardware owns
speaker DC disconnect, overcurrent, overtemperature, and power-stage fault.
FPGA/UI diagnostics may observe or request protection but cannot be the only
protector (`SAFE-003`).

## 16. Thermal and mechanical design

The target is fanless line-level operation at the specified ambient. DB uses a
four-or-more-layer stackup appropriate to the FPGA/eARC SI and power planes;
the exact layer counts of AB and OB are selected from noise and manufacturing
review rather than forced to match DB. FPGA thermal vias/spreader and chassis
coupling are sized after placed-design power estimates and verified with
thermocouples or calibrated thermal imaging.

Temperature sensors cover FPGA vicinity, eARC/ASRC area, phono compartment,
line driver, regulator hot spots, display enclosure, and any later power stage.
Firmware exposes temperatures and maximums; PB supplies an independent critical
shutdown where required.

The display mounts without FPC strain and is replaceable. The front glass and
metalwork do not load the LCD active area. Knobs have controlled panel gaps,
ESD paths, and replaceable couplers. Board removal does not require disturbing
the phono input wiring unless AB itself is serviced (`MECH-001`).

## 17. Manufacturing and calibration

Each board records:

- product/board ID, assembly revision, serial, and manufacture date;
- BOM variant and fitted options;
- bootloader/application/API compatibility versions;
- ADC/DAC scale and DC offset calibration;
- volume endpoint/linearity calibration;
- phono capacitance/gain variant and measured input capacitance; and
- final test result hash or database key.

Factory sequence:

1. boundary-scan/short/open and rail-current test;
2. program recovery, FPGA, UI, receiver, and board identity;
3. verify every rail, reset, oscillator, and supervisory fault;
4. calibrate volume endpoints and exercise servo/stall response;
5. configure eARC analyzer modes and verify capability data;
6. calibrate converter gains under mute;
7. run stereo digital/analog loopback, crosstalk, noise, gain, phase, THD+N,
   clipping, and mute transient tests (`TEST-004`);
8. run phono cartridge-emulator loading/noise/gain tests;
9. save coherent FPGA diagnostics and firmware versions; and
10. complete button, touch, display, encoder, network, and standby test.

Calibration never edits reference-model constants to conceal analog hardware
error. Converter calibration maps PCM to physical volts; model changes remain
versioned assets.

## 18. Verification and acceptance matrix

These are design targets until measured reports are committed.

| Subsystem | Required evidence before DVT release |
|---|---|
| eARC | analyzer discovery/capability/PCM sweep; ARC fallback; CEC volume/mute where implemented; link interruption/recovery; at least five TV families from multiple vendors; finished-product compliance (`TEST-002`) |
| ASRC | 32–192 kHz supported-rate matrix; 24-bit stereo; passband and stopband; THD+N and residual spectrum; lock/group delay; ppm offset; rate change and unplug transient |
| phono | exact 47.5 kilohm and installed capacitance; 20/26/32 dB gain; cartridge-emulator sweep; overload; input-referred noise; hum/RF/ESD recovery |
| converters/output | at least 115 dB(A) target dynamic range at 2 V RMS class, output noise below 4 microvolt RMS target, gain/phase/crosstalk, line-load drive, THD+N, DC, clipping and reconstruction spectrum |
| FPGA | stereo bit-accurate regressions, open synthesis/P&R/bitstream, no deadline miss, resource/power report, clock/CDC review, hardware capture versus fixed model (`SYS-003`) |
| UI | 24-hour animation/touch stress, unplug/reset behavior, backlight thermal/EMI test, all operations possible without network, safety controls with LCD disconnected |
| motor volume | endpoint/stall/manual override, target/effective-position coherence, acoustic noise, conducted/radiated coupling, 100,000-cycle production qualification (`VOL-006`) |
| system noise | phono and line noise with every aggressor idle and worst-case active; no hidden mute during test (`TEST-003`) |
| power/mute | cold/hot plug, rapid cycling, brownout, stuck clock, receiver/MCU/FPGA reset, invalid firmware, unplugged board, and output transient capture |
| EMC/thermal | pre-compliance emissions/immunity/ESD and worst-case ambient steady state before formal certification |

For the motor/display aggressor test, record both integrated input-referred
phono noise and spectra. A threshold is frozen after quiet-board baseline data,
but any deterministic spur or audible transient correlated with motor/backlight
activity is a release failure requiring root-cause analysis—not a candidate for
masking with digital noise or reference-model changes.

## 19. Development sequence

### EVT-0 — evaluation interconnect

- Obtain receiver/vendor access and eARC evaluation hardware.
- Evaluate SiI9437 versus any current supported successor before schematic
  commitment.
- Compare SRC4392 and AD1896 evaluation paths with asynchronous TV/audio clocks.
- Bring up STM32H753-class MCU, selected LCD/touch, optical controls, PRM16, and
  DRV8874 on a front-panel bench harness.
- Implement the authoritative volume event/servo state machine and instrument
  current, position, faults, and travel time.

### EVT-1 — first board set

- Spin FP and PB first because their interfaces are stable and their emissions
  can be characterized against the existing FPGA platform.
- Spin AB/OB from the completed analog requirements and converter evaluation.
- Keep eARC as a receiver mezzanine on the first DB if vendor/supply risk is not
  fully closed; do not contaminate every DB revision with an uncertain IC.
- Run full aggressor/noise and analog loopback characterization.

### EVT-2 — integrated digital board

- Integrate the selected eARC receiver only after licensed reference review.
- Route the exact stereo FPGA image with production I/O/package constraints.
- Complete multi-vendor TV, ASRC, CEC, latency, and recovery tests.
- Produce compliance-intent enclosure, grounding, and connector layout.

### DVT/PVT

- Close formal compliance, environmental/ESD/EMC, thermal, life, safety, and
  production-test coverage.
- Freeze component alternates only after electrical and firmware compatibility
  evidence.
- Publish measured rather than estimated performance.

## 20. Open issues

- Current mono RTL must become stereo and be openly placed/routed before DB
  FPGA/package freeze (`SYS-003`).
- SiI9437 lifecycle, access terms, current receiver successor, and full eARC
  software/reference package must be confirmed (`EARC-001`, `EARC-008`).
- SRC4392 versus AD1896 requires evaluation measurements, especially ratio
  change and mute/relock behavior.
- Production ADC/DAC parts remain deliberately unfrozen in `adc_dac.md`.
- PRM16 is a prototype mechanism; production volume feel/life is a mechanical
  development project, not a BOM assumption (`VOL-006`).
- Exact remote radio, antenna, and cybersecurity maintenance policy remain to
  be selected; Ethernet and offline local operation are the baseline.
- Enclosure dimensions, display viewing angle, knob spacing, and thermal path
  require industrial-design mockups.
- Numeric EMC, environmental, motor-coupling, and mute-transient limits must be
  frozen from EVT baseline data and applicable market standards.

## 21. Requirement traceability

The normative requirement records are machine checked from
`hardware/product_v1/requirements.json`. IDs covered by this specification are:

```text
SYS-001 SYS-002 SYS-003 SYS-004
EARC-001 EARC-002 EARC-003 EARC-004 EARC-005 EARC-006 EARC-007 EARC-008
CLK-001 CLK-002
PHONO-001 PHONO-002 PHONO-003
CONV-001 CONV-002 CONV-003
FPGA-001 FPGA-002 FPGA-003
UI-001 UI-002 UI-003 UI-004 UI-005 UI-006
VOL-001 VOL-002 VOL-003 VOL-004 VOL-005 VOL-006
PWR-001 PWR-002 PWR-003
EMC-001 EMC-002 EMC-003
SAFE-001 SAFE-002 SAFE-003
MECH-001 MECH-002
TEST-001 TEST-002 TEST-003 TEST-004
FW-001 FW-002
```
