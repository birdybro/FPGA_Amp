# Front-panel firmware cores

`volume_servo.c` is the mechanism-independent safety and position controller
for the motorized volume dial. It contains no STM32 HAL calls and builds under a
host C11 compiler so command, reversal, timeout, and fault behavior can be
regressed before a front-panel PCB exists.

The integration task calls `volume_servo_step()` at one fixed period (a 1 ms
initial target), after synchronously sampling:

- ratiometric absolute dial position;
- filtered DRV8874-class current feedback;
- the motor-driver fault pin;
- optional grip/manual-override detection; and
- the latest serialized authoritative volume-position command.

The returned `drive` and `duty_per_mille` command the H-bridge. Hardware current
regulation remains mandatory; software is not a safety substitute for the
driver's cycle-level limit. The core adds soft endpoints, approach-speed
reduction, deadband/coast, reversal dead time, retained overcurrent/stall,
bounded travel time, driver/sensor faults, explicit safe fault clear, manual
override, and idle back-drive takeover. A fault clear resets the target to the
present safe position, so it cannot automatically retry against a mechanical
stop.

`target_changed` tells the UI event owner to propagate a manual position change
back through the same authoritative volume sequence used by touchscreen, CEC,
and network commands. The target maps to decibels outside this core. No
potentiometer track or position value is part of the audio path.

Run:

```sh
make volume-servo-test
```

The host regression builds with C11, `-Wall -Wextra -Werror -pedantic`, then
checks configuration rejection, endpoint clamping, fast/approach duty,
deadband, exact reversal coast, explicit and inferred manual takeover, retained
stall, safe clear/no retry, travel timeout, driver fault, and sensor fault. This
is digital behavioral evidence only. PWM/ADC timing, motor torque, EMI, acoustic
noise, touch safety, and mechanism lifetime require the physical FP prototype.
