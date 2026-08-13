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

The separate `chord_corrector_v1` out-of-context result is:

| Resource | Count |
|---|---:|
| estimated logic cells | 1,109 |
| LUT2 / LUT3 / LUT4 / LUT5 / LUT6 | 858 / 12 / 34 / 112 / 545 |
| FDRE | 1,185 |
| DSP48E1 | 9 |
| RAMB18E1 | 0 |
| CARRY4 / MUXF7 | 240 / 57 |

Its structural check reports zero problems and six techmap resize warnings. The
measured nine DSPs confirm that Q17.1 × 25-bit-Q30 maps one native multiplier per
row; no timing claim is made. Tube plus corrector total 25 DSPs when composed,
before KCL/network/filter arithmetic.

The 40-bit Q28/Q32 candidate corrector keeps the same nine multipliers but
selects only constant Q30/Q34/Q40 scaling paths. Its separate result is:

| Resource | Count |
|---|---:|
| estimated logic cells | 1,701 |
| LUT2 / LUT3 / LUT4 / LUT5 / LUT6 | 952 / 29 / 33 / 122 / 1,072 |
| FDRE | 1,403 |
| DSP48E1 | 9 |
| RAMB18E1 | 0 |
| CARRY4 / MUXF7 | 431 / 60 |

The structural check reports zero problems and six techmap resize warnings.
This is a 592-cell increase over the 32-bit corrector. A first version allowing
an arbitrary runtime binary-point shift used 5,531 cells and was rejected; its
cost was not used as the selected design result. Complete wide KCL/solver
resources and 98.304 MHz timing remain unmeasured.

The branch-current wide network has these separate structural results:

| Block | Logic cells | DSP48E1 | RAMB18E1 | Latency |
|---|---:|---:|---:|---:|
| `network_rhs_v1_wide` | 31 | 4 | 0 | 2 clocks |
| `network_kcl_v1_wide` | 8,034 | 72 | 0 | 10 clocks |

The KCL result is after narrowing the generated static Q0.47 matrix to its
proven signed 41-bit bound and capacitor conductances to signed 47 bits. The
unbounded-width first pass used 99 DSPs; it was rejected. The selected KCL
structural check has zero problems and 12 primitive-resize warnings. RHS has
zero synthesis warnings. Subsystem counts were not added to form a hierarchy
claim.

Hierarchical synthesis of the integrated wide factorized solver measures 12,544
logic cells, 1,366 FDRE plus 282 FDSE, 120 DSP48E1s, and 8 RAMB18E1s. Structural
check reports zero problems and 61 techmap resize warnings. Its 116-clock
simulation schedule leaves 12 clocks, versus two for the legacy hierarchy, but
no named-part Fmax or routing closure is claimed. The solver consumes 50.0% of
the Arty A7-100T's DSP count before resampling; this materially constrains stereo
duplication and makes a complete-stream resource measurement mandatory.

The optional cutoff-Jacobian-bank wrappers retain the same tube engines,
network, and 116-clock schedule. The generated coefficient selector adds no DSP
or block RAM; measured structural resources are:

| Solver | Logic cells | DSP48E1 | RAMB18E1 | Delta logic vs nominal |
|---|---:|---:|---:|---:|
| backward Euler, banked | 13,302 | 120 | 8 | +758 |
| backward Euler, banked terminal correction | 13,296 | 120 | 8 | +752 |
| trapezoidal, banked | 13,840 | 120 | 8 | +1,054 |
| trapezoidal, banked terminal correction | 14,945 | 174 | 8 | +2,159 |

Both checks report zero structural problems and 61 primitive-resize warnings.
The selector includes a previous-Vgk slew comparison but adds no DSP or RAM.
The terminal wrapper reuses the existing chord datapath and adds no DSP or RAM;
its six-cell reduction relative to the ordinary banked wrapper is a synthesis-
optimization artifact, not an architectural saving. It measures 127 clocks and
therefore has only one scheduling clock of margin before place-and-route.
Full-Newton waveform error remains reported separately; no Fmax claim is
inferred from Yosys.

Trapezoidal terminal correction also updates ten Q4.44 companion-current
histories after the final chord. A first parallel version inferred ten full
48×44 variable multipliers and measured 210 DSP48E1s for the solver. The
reproducible conductance generator now emits the frozen V1 coefficients as
signed constants; bit-exact regression is unchanged and synthesis falls to 174
DSP48E1s. This is an accepted constant-multiplier implementation, not a change
to circuit values or numerical behavior.

The complete wide stream measures 17,492 logic cells, 168 DSP48E1s, and 8
RAMB18E1s, with zero structural check problems and 67 techmap resize warnings.
This is 17.2% of nominal A7-100T logic cells, 70.0% of DSPs, and about 3.3% of
18 Kib RAM blocks. The mono design fits structurally, but two identical channels
would require 336 DSPs and therefore cannot be naively duplicated on this part.
Stereo needs filter/KCL resource sharing, a larger device, or a separately
measured arithmetic trade; none is silently selected here.

The complete banked terminal-correction stream measures 18,466 logic cells,
168 DSP48E1s, and 8 RAMB18E1s, with zero structural check problems and 72
techmap resize warnings. Relative to the nominal wide stream, the coefficient
selector and terminal control add 974 estimated logic cells but no DSP or block
RAM. Its 127-clock solver latency leaves one clock between 768 kHz deadlines at
98.304 MHz. This structural fit does not establish that the one-clock margin
will close routing on XC7A100T; vendor place-and-route is required before this
mode can be selected for hardware.

The complete trapezoidal banked terminal stream measures 20,241 logic cells,
222 DSP48E1s, and 8 RAMB18E1s with zero structural check problems. It occupies
92.5% of the XC7A100T's DSPs, leaving 18 blocks and ruling out duplication for
stereo. Its exact simulation latency is 127 clocks, but the terminal edge now
contains constant-multiply current updates. Only named-part place-and-route can
establish whether that path and the one-clock sample margin meet 98.304 MHz.

On XC7A100T, this single table engine consumes about 6.7% of DSPs and 17.4% of
18 Kib RAM blocks. The accuracy-first 128 × 256 plate table is memory-dominant.
Time-multiplexing it across triodes/channels is therefore favored over blind
duplication. The 64 × 128 study cuts raw table bits to 0.262 Mbit but raises
worst operating-region error from 1.43 µA to 5.85 µA; no smaller table is adopted
without an end-to-end error/resource comparison.

## Required next implementation evidence

1. Run Vivado synthesis/place/route on the exact Arty part and record worst slack,
   clocks, utilization, power estimate, and all CDC/timing exceptions.
2. Establish a stereo resource strategy within the measured 168-DSP mono budget.
3. Capture FPGA results and compare bit-for-bit with the fixed model before any
   analog loopback claim.

The Arty is a development reference, not a production platform selection. A
final device must also support low-noise clock/power integration, enough I/O for
converter/control/fault lines, configuration security/recovery, and lifecycle.
