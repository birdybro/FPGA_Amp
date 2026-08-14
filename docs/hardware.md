# FPGA and synthesis baseline

## Reference development platform

The provisional FPGA is the Digilent Arty A7-100T (XC7A100T). It offers roughly
101,440 logic cells, 240 DSP48E1 blocks, and 4,860 Kib of block RAM. It is widely
available and Project X-Ray contains the exact `xc7a100tcsg324-1` database, but
has no precision audio converter on board; a short, controlled-interface
converter daughterboard is required. Core RTL stays device-neutral and Xilinx
primitives are not used in the tube module.

The required Linux implementation flow is fully open source: Yosys produces
the XC7 JSON netlist and nextpnr-Himbaechel performs packing, placement, and
routing against Project X-Ray data. The upstream nextpnr project labels its
7-series backend experimental. At the pinned revision it imports timing data
under a single `DEFAULT` grade rather than identifying XC7A100T-1, so a routed
frequency result is valuable engineering evidence but is not mislabeled as a
certified `-1` speed-grade limit. `scripts/bootstrap_openxc7.sh` builds the
pinned backend without root access; `make openxc7-probe` records the installed
versions and database. No Vivado step is part of the required flow.

## First named-part placement diagnosis

`solver_pnr_harness` wraps the complete 127-clock
trapezoidal/banked/terminal solver with an internal deterministic stimulus and
a one-bit registered signature. Only the Arty oscillator, one button, and one
LED are package pins, so wide debug buses cannot distort the I/O requirement.
Yosys 0.66 measures the harness at 14,967 estimated logic cells, 6,372
flip-flops, 174 DSP48E1s, eight RAMB18E1s, and one RAMB36E1. The open XC7
packer expands this to 50,789 `SLICE_LUTX` elements, including 29,653 LUT1s,
plus 3,770 CARRY4s and the same DSP/RAM count.

With seed 1, one thread, router2, and a 98.304 MHz request, nextpnr commit
`4d23515` reports only 13.90 MHz after placement. This is an experimental
`DEFAULT`-grade estimate, not a qualified -1 speed result, but the 7.07x miss is
too large to treat as a signoff nuance. The value-only tube substitution later
placed at 13.67 MHz despite its isolated 113.24 MHz result. That controlled
experiment falsifies the initial hypothesis that cubic Hermite is the dominant
complete-solver path. The historical circuit and numerical tolerances are not
changed to hide this timing failure. Router2 completion and post-route
critical-path extraction remain in progress for both full baselines.

### Bit-exact Hermite timing experiment

`hermite_q16_pipeline` preserves the factorized tube's exact cubic-Hermite
Horner arithmetic: signed 32-bit state wraps at the same boundaries, each
32-by-17-bit product is retained at 49 bits, and add-half arithmetic-shift
rounding is unchanged. It accepts one request while idle and emits the result
three clocks later, ignoring starts while busy. The test covers 4,096
deterministic directed/random full-range input tuples plus in-flight reset; the
existing 4,110-vector complete tube regression also remains exact.

Out-of-context Yosys synthesis reports 265 estimated logic cells, 198
flip-flops, two DSP48E1s, no RAM, no warnings, and no structural problems. The
three-pin `hermite_pnr_harness` packs to 886 `SLICE_LUTX`, 231 `SLICE_FFX`, 49
CARRY4, and two DSP48E1s. With the same part, XDC, seed, router, and 98.304 MHz
request as the solver baseline, routing completes in seven router2 iterations
and reports 132.54 MHz post-route. This demonstrates that the separated kernel
meets the open backend estimate; it does not establish qualified -1 timing or
complete-solver closure.

The kernel is intentionally not wired into the accuracy-first tube yet. The
three physical table evaluations are serially dependent, and the reciprocal
and softplus results each feed another multiplication. A direct substitution
therefore consumes more than the existing eight-clock tube contract and, when
repeated across solver passes, exceeds the 127-clock internal-sample deadline.
The next architecture step must budget those dependencies explicitly instead
of trading away the reference law or silently lowering oversampling.

### Value-only eight-clock tube candidate

`triode_12ax7_factorized_linear` takes a different, separately error-bounded
route: it spends memory on 1,024/8,192/4,096 value-only tables so each scalar
interpolation has one product, while preserving the original eight-clock tube
and 127-clock complete-solver schedules. Out-of-context Yosys reports 642
estimated logic cells, 27 DSP48E1s, 13 RAMB18E1s, and five RAMB36E1s. The
three-pin tube harness packs to 2,630 `SLICE_LUTX`, 373 `SLICE_FFX`, 246 CARRY4,
the same DSP/RAM count, and routes at 113.24 MHz against 98.304 MHz. As with all
current nextpnr-XC7 results, this is an experimental `DEFAULT`-grade estimate.

The complete accuracy-first terminal solver remains bit-exact to its matching
Python candidate at 127 clocks. Its named-part synthesis measures 14,140
estimated logic cells, 6,282 flip-flops, 166 DSP48E1s, 13 RAMB18E1s, and five
RAMB36E1s; packing expands it to 49,530 `SLICE_LUTX` and 3,710 CARRY4. This is
eight fewer DSPs and 1,259 fewer packed LUT elements than the Hermite harness,
at the cost of additional RAM. Placement reaches only 13.67 MHz, statistically
indistinguishable from and slightly below the Hermite solver's 13.90 MHz.
Therefore it is not a whole-solver timing solution and is not promoted to the
reference/default implementation. Full routing remains in progress only to
extract the detailed path and congestion evidence.

### Solver-block timing isolation

The ten simultaneous trapezoidal terminal-current recomputations are factored
into `terminal_current_update_v1` without changing their single-edge contract.
Both 512-vector solver regressions remain bit exact at 116 and 127 clocks. The
three-pin isolated harness measures 54 DSP48E1s, 5,442 packed `SLICE_LUTX`,
1,281 `SLICE_FFX`, and 612 CARRY4s. A literal serial overflow-count expression
initially limited post-route timing to 51.95 MHz. Replacing only that diagnostic
sum with an explicitly widened balanced popcount raises the measured result to
88.83 MHz. It still fails 98.304 MHz and does not claim full-solver closure,
but it converts a source-level suspicion into a measured, reproducible timing
target. The next experiment must separately route KCL and chord blocks, then
pipeline or reschedule the dominant physical paths without changing the V1
circuit law.

The isolated banked chord corrector uses nine DSP48E1s and routes at 46.40 MHz.
Its worst path is the final correction scaling, node subtraction, and
saturation commit, not the nine-cycle coefficient MAC itself. The original
wide trapezoidal KCL block uses 72 DSP48E1s and routes at only 16.64 MHz. Its
60.09 ns critical cone begins at a stored accumulator, performs the final tube
and capacitor-9 residual sum, propagates through the cross-row Q40/Q34/Q30
fallback decision, and ends at the saturated residual register. This matches
the whole-solver placement failure and establishes KCL as the primary limiter.

The first KCL correction captures invariant capacitor 9 on the first matrix
column and stages the complete physical residual when the second tube result
arrives. That edge was already an integrated-solver wait, so all 512 complete
solver vectors retain their exact 127-clock contract; a standalone request
with an early tube result now takes 11 rather than 10 clocks. Serial procedural
all-fit, maximum-residual, and saturation-count reductions were also replaced
with explicit balanced trees. All 1,024 backward-Euler and 1,024 trapezoidal
KCL vectors remain exact, including tube-result delays through 19 clocks. The
revised isolated KCL placement estimate improves from 14.95 to 33.92 MHz;
legal routing remains in progress. This is a measured improvement, not timing
closure, and the remaining gap requires further staged finish selection and a
solver schedule that can absorb it.

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
logic cells, 1,366 FDRE plus 282 FDSE, 120 DSP48E1s, eight RAMB18E1s, and one
RAMB36E1. Structural check reports zero problems and 61 techmap resize
warnings. Its 116-clock
simulation schedule leaves 12 clocks, versus two for the legacy hierarchy, but
no named-part Fmax or routing closure is claimed. The solver consumes 50.0% of
the Arty A7-100T's DSP count before resampling; this materially constrains stereo
duplication and makes a complete-stream resource measurement mandatory.

The optional cutoff-Jacobian-bank wrappers retain the same tube engines,
network, and 116-clock schedule. The generated coefficient selector adds no DSP
or block RAM; measured structural resources are:

| Solver | Logic cells | DSP48E1 | RAMB18E1 | RAMB36E1 | Delta logic vs nominal |
|---|---:|---:|---:|---:|---:|
| backward Euler, banked | 13,302 | 120 | 8 | 1 | +758 |
| backward Euler, banked terminal correction | 13,296 | 120 | 8 | 1 | +752 |
| trapezoidal, banked | 13,840 | 120 | 8 | 1 | +1,054 |
| trapezoidal, banked terminal correction | 14,945 | 174 | 8 | 1 | +2,159 |

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

The complete wide stream measures 17,492 logic cells, 168 DSP48E1s, eight
RAMB18E1s, and one RAMB36E1, with zero structural check problems and 67
techmap resize warnings. This is 17.2% of nominal A7-100T logic cells, 70.0% of
DSPs, and 3.7% of its 270 RAMB18-equivalents. The mono design fits structurally,
but two identical channels
would require 336 DSPs and therefore cannot be naively duplicated on this part.
Stereo needs filter/KCL resource sharing, a larger device, or a separately
measured arithmetic trade; none is silently selected here.

The complete banked terminal-correction stream measures 18,466 logic cells,
168 DSP48E1s, eight RAMB18E1s, and one RAMB36E1, with zero structural check
problems and 72 techmap resize warnings. Relative to the nominal wide stream, the coefficient
selector and terminal control add 974 estimated logic cells but no DSP or block
RAM. Its 127-clock solver latency leaves one clock between 768 kHz deadlines at
98.304 MHz. This structural fit does not establish that the one-clock margin
will close routing on XC7A100T; the named-part open-source place/route flow must
close before this mode can be selected for hardware.

The complete trapezoidal banked terminal stream measures 20,241 logic cells,
222 DSP48E1s, eight RAMB18E1s, and one RAMB36E1 with zero structural check
problems. It occupies 92.5% of the XC7A100T's DSPs, leaving 18 blocks and ruling out duplication for
stereo. Its exact simulation latency is 127 clocks, but the terminal edge now
contains constant-multiply current updates. Only named-part place-and-route can
establish whether that path and the one-clock sample margin meet 98.304 MHz.

The device-neutral asynchronous FIFO has a separately measured depth-8 × 32-bit
configuration:

| Resource | Count |
|---|---:|
| estimated logic cells | 127 |
| flip-flops | 331 (256 FDRE + 74 FDCE + 1 FDPE) |
| DSP48E1 / RAMB18E1 | 0 / 0 |

The structural check reports zero problems. Yosys emits one source-level warning
that it replaces the small dual-clock memory with registers; this is consistent
with the reported 256 data plus 67 control/synchronizer and eight watermark
flip-flops and is retained, not mislabeled as a techmap resize warning. Deeper hardware FIFOs need a named-part inference/IP
comparison before assuming block-RAM mapping. This result has no CDC timing or
metastability MTBF claim without the placed design and clock constraints.

The 24-bit/32-slot I²S protocol blocks have independent warning-free structural
results:

| Block | Logic cells | Flip-flops | DSP / RAM |
|---|---:|---:|---:|
| receiver, rising-edge BCLK | 35 | 105 | 0 / 0 |
| transmitter, falling-edge BCLK | 97 | 137 | 0 / 0 |

Both checks report zero structural problems. The `_1` falling-edge Xilinx cell
variants are now included in the reproducible resource parser; the earlier
zero-flop intermediate transmitter report was a reporting defect and is not
retained as evidence. BCLK edge timing, I/O delay, and converter setup/hold need
named-part constraints and place-and-route.

The composed bidirectional I²S/CDC bridge has this flattened structural result:

| Resource | Count |
|---|---:|
| estimated logic cells | 571 |
| flip-flops | 1,547 |
| DSP48E1 / RAMB18E1 | 0 / 0 |

The flip-flop total includes 1,024 data registers for two depth-8 × 64-bit
FIFOs; Yosys reports their register expansion explicitly. Post-map flattening
was added to the resource script after a rejected intermediate hierarchy report
omitted instantiated primitive registers. The final total is 1,024 FDRE, 383
FDCE, 3 FDPE, 131 falling-edge FDCE, and 6 falling-edge FDPE. Structural check
finds zero problems. This remains an unplaced interface estimate: Gray-pointer
CDC constraints, synchronizer placement, opposite-edge BCLK timing, and all
board I/O delays still require the named FPGA and converter.

Each FIFO now exports an occupancy estimate and high-water mark in both local
clock domains. Gray-to-binary conversion uses only the already synchronized
remote pointer. Write-side occupancy may conservatively lag reads high and
read-side occupancy may lag writes low, so the four values are diagnostics, not
a coherent cross-domain snapshot. Their watermarks clear with the existing
owning-domain diagnostic clear. The locked-rate pin test measures one frame in
all four views; directed bridge backpressure reaches RX 3/3 and TX 4/4 frames;
the standalone test reaches the exact depth of eight.

The standalone BCLK/fabric rate monitor has this warning-free structural
result:

| Resource | Count |
|---|---:|
| estimated logic cells | 68 |
| flip-flops | 125 FDCE |
| DSP48E1 / RAMB18E1 | 0 / 0 |

This includes the 16-bit BCLK binary/Gray counter, two-stage Gray and active
synchronizers, 15-bit 32,768-clock window counter, measurement/baseline state,
three-window lock qualification, and sticky rate error. Structural check finds
zero problems. It does not prove Gray-bus skew constraints, metastability MTBF,
or absolute clock accuracy.

The dynamic converter calibration primitives synthesize independently as:

| Direction | Logic cells | Flip-flops | DSP48E1 | RAMB18E1 |
|---|---:|---:|---:|---:|
| PCM24 to input Q8.24 volts | 95 | 66 | 4 | 0 |
| output Q8.24 volts to PCM24 | 86 | 58 | 4 | 0 |

Both structural checks are warning-free and report zero problems. The
coefficients are runtime inputs, so these are general multiplier baselines.
They are not arithmetically added to the 222-DSP stream claim. The integrated
mono adapter below provides the measured combined hierarchy. No Fmax is claimed.

The protocol-neutral atomic calibration guard independently measures 14 logic
cells / 67 asynchronous-clear flip-flops / no DSP or RAM. Its warning-free
structural check reports zero problems. These registers hold both active Q8.24
coefficients, the acknowledgment, and invalid/unsafe sticky diagnostics.

The default 2,048-clock audio-frame scheduler is 41 estimated logic cells and
43 flip-flops with no DSP or RAM. Its warning-free structural check reports zero
problems. This number covers phase count, the single launch comparator, and the
saturating underflow counter; frame storage remains in the asynchronous bridge.

The accuracy-first fabric mono adapter has the flattened combined result:

| Resource | Count |
|---|---:|
| estimated logic cells | 20,489 |
| flip-flops | 15,592 (15,116 FDRE + 476 FDSE) |
| DSP48E1 | 232 |
| RAMB18E1 / RAMB36E1 | 8 / 1 |
| RAMB18-equivalents | 10 |

The structural check reports zero problems. The 76 unique warnings are known
small local-array register expansions and Xilinx primitive output-port resize
notices retained in the full log; they are not mislabeled as a dual-clock FIFO
inference warning. This top includes frame scheduling, both runtime calibration
multipliers, the 127-clock trapezoidal/banked/terminal stream, and the two-DSP
modern output ramp. It excludes the asynchronous I²S bridge, atomic control
commit, and dedicated safety hardware. At 232/240 DSPs it leaves only eight DSP48E1s on the
provisional A7-100T. Structural fit does not prove that its one-clock solver
margin meets 98.304 MHz.

The resource reporter now records RAMB36E1 separately and publishes a
RAMB18-equivalent total. Earlier summaries silently omitted the one mapped
RAMB36E1 in every factorized-tube hierarchy; the corrected documents retain
both eight RAMB18E1s and one RAMB36E1 (ten 18-Kib equivalents). No numerical RTL
or memory implementation changed as a result of that reporting correction.

Adding the two asynchronous stereo FIFOs and I²S protocol blocks around the
adapter produces the pin-facing digital hierarchy:

| Resource | Count |
|---|---:|
| estimated logic cells | 21,014 |
| flip-flops | 16,907 |
| DSP48E1 | 232 |
| RAMB18E1 / RAMB36E1 | 8 / 1 |

The flip-flop total is 15,820 FDRE, 476 FDSE, 471 FDCE, 3 FDPE, 131
falling-edge FDCE, and 6 falling-edge FDPE. Structural check reports zero
problems; the 77 unique warnings retain local-array/FIFO register expansion and
primitive resize notices. The result has no clock constraints, synchronizer
placement, BCLK opposite-edge timing, board I/O delays, or named-part Fmax. It
therefore proves structural composition, not a deployable converter interface.
This hierarchy includes the atomic muted calibration commit guard, four
local-domain FIFO levels/watermarks, and the BCLK/fabric rate monitor; candidate
register transport and coherent multi-domain diagnostic CDC are intentionally
outside the top.

The subsequently composed control hierarchy adds a 22-word retained diagnostic
snapshot, a coherent held-bus capture of I²S-domain FIFO occupancy, safe
synchronization of retained I²S fault bits, atomic calibration register
ownership, and a toggle command crossing for I²S diagnostic clear.
Adding the complete oversampled mode-0 SPI transport gives the current digital
pin hierarchy:

| Resource | Register-controlled | SPI-controlled |
|---|---:|---:|
| estimated logic cells | 21,466 | 21,589 |
| flip-flops | 17,922 | 18,094 |
| DSP48E1 | 232 | 232 |
| RAMB18E1 / RAMB36E1 | 8 / 1 | 8 / 1 |

Both flattened structural checks report zero problems. These current totals
include the fail-closed BCLK guard, 22-word atomic image, held-bus I²S capture,
and snapshot timeout. The SPI result also includes
the fixed 80-bit register transaction, frame/response diagnostics, and
saturating completed-frame counter. It still has no package assignment, I/O
delay, synchronizer placement, named-part timing, or physical converter claim.

On XC7A100T, this single table engine consumes about 6.7% of DSPs and 17.4% of
18 Kib RAM blocks. The accuracy-first 128 × 256 plate table is memory-dominant.
Time-multiplexing it across triodes/channels is therefore favored over blind
duplication. The 64 × 128 study cuts raw table bits to 0.262 Mbit but raises
worst operating-region error from 1.43 µA to 5.85 µA; no smaller table is adopted
without an end-to-end error/resource comparison.

## Required next implementation evidence

1. Run Yosys and nextpnr-Himbaechel on the exact Arty part and record achieved
   frequency, clocks, utilization, routing status, and every timing exception.
   Treat the backend's `DEFAULT` timing grade separately from a qualified
   XC7A100T-1 signoff claim.
2. Establish a stereo resource strategy within the measured 168-DSP mono budget.
3. Capture FPGA results and compare bit-for-bit with the fixed model before any
   analog loopback claim.

The Arty is a development reference, not a production platform selection. A
final device must also support low-noise clock/power integration, enough I/O for
converter/control/fault lines, configuration security/recovery, and lifecycle.
