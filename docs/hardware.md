# FPGA and synthesis baseline

## Reference development platform

The provisional FPGA is the Digilent Arty A7-100T (XC7A100T). It offers roughly
101,440 logic cells, 240 DSP48E1 blocks, and 4,860 Kib of block RAM. It is widely
supported by Vivado and Yosys, but has no precision audio converter on board; a
short, controlled-interface converter daughterboard is required. Core RTL stays
device-neutral and Xilinx primitives are not used in the tube module.

## Measured out-of-context result

Yosys 0.66 `synth_xilinx -family xc7`, without I/O pads or clock buffer, reports
for `triode_12ax7`:

| Resource | Count |
|---|---:|
| estimated logic cells | 414 |
| LUT2 / LUT3 / LUT4 / LUT5 / LUT6 | 365 / 15 / 56 / 38 / 158 |
| FDRE / FDSE | 422 / 52 |
| DSP48E1 | 16 |
| RAMB18E1 | 47 |
| CARRY4 | 169 |

The design check reports zero structural problems. Yosys emits 188 unique
Xilinx-techmap primitive output-resize warnings; the full generated log is kept
outside version control and must be reviewed on tool upgrades. Verilator lint of
the source/testbench is warning-free. No Fmax is reported because generic
structural synthesis is not place-and-route on a named speed grade.

On XC7A100T, this single table engine consumes about 6.7% of DSPs and 17.4% of
18 Kib RAM blocks. The accuracy-first 128 × 256 plate table is memory-dominant.
Time-multiplexing it across triodes/channels is therefore favored over blind
duplication. The 64 × 128 study cuts raw table bits to 0.262 Mbit but raises
worst operating-region error from 1.43 µA to 5.85 µA; no smaller table is adopted
without an end-to-end error/resource comparison.

## Required next implementation evidence

1. Synthesize fixed-point matrix/network arithmetic with two solver passes.
2. Demonstrate the complete mono 768 kHz cycle schedule at 98.304 MHz.
3. Run Vivado synthesis/place/route on the exact Arty part and record worst slack,
   clocks, utilization, power estimate, and all CDC/timing exceptions.
4. Add stereo time-multiplexing only if the measured 128-clock deadline closes.
5. Capture FPGA results and compare bit-for-bit with the fixed model before any
   analog loopback claim.

The Arty is a development reference, not a production platform selection. A
final device must also support low-noise clock/power integration, enough I/O for
converter/control/fault lines, configuration security/recovery, and lifecycle.
