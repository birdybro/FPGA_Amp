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

`run_openxc7.py --pack-only` records exact named-part packing and utilization
without claiming placement or timing. `--place-only` continues through
placement, writes a separate placed netlist/log/report/summary, and records
placement Fmax without claiming a route. These stages exist for candidates
whose congestion makes the next implementation step impractical or whose
placement miss is too large to justify a long router run.
`analyze_openxc7_placement.py` groups a flattened placed JSON by the major
solver blocks and reports resource counts, bounding boxes, and hard-block
centroids. These diagnostic artifacts remain generated; their measured
conclusions are recorded here.

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
revised isolated KCL placement estimate improves from 14.95 to 33.92 MHz. A
router2 experiment reached 183 overused resources at iteration 57 before
diverging to 499 by iteration 114 and was stopped without a legal route. This
is a measured improvement, not timing closure, and the remaining gap requires
further staged arithmetic and a solver schedule that can absorb it.

### Parallel dual-triode schedule

The V1 circuit contains two physical 12AX7 sections whose currents depend only
on the candidate node-voltage vector for a solver pass. A selectable scheduling
mode therefore instantiates two identical factorized Hermite primitives and
launches both sections together. It does not share one result between stages,
alter the tube equations, or change any physical network state. Both the 512-
vector backward-Euler solver and the complete 512-vector trapezoidal/banked/
terminal solver remain bit-exact; their measured latencies fall from 116 to 84
clocks and from 127 to 95 clocks respectively. The latter recovers 32 of the
128 clocks available per 768 kHz sample for additional network pipelining.

Yosys 0.66 measures the complete parallel terminal harness at 15,887 estimated
logic cells, 7,360 flip-flops, 209 DSP48E1s, 16 RAMB18E1s, and two RAMB36E1s.
The comparable sequential harness after KCL restructuring is 14,354 cells,
7,000 flip-flops, 174 DSP48E1s, eight RAMB18E1s, and one RAMB36E1. Thus the
schedule recovery costs 1,533 cells, 360 flip-flops, 35 DSPs, and ten
RAMB18-equivalents while remaining below the XC7A100T's 240-DSP limit. The
parallel harness has a reproducible open-flow netlist but no placement or Fmax
claim yet. It is an implementation option, not a modern or creative circuit
mode.

### Bit-exact KCL and chord timing schedules

The recovered parallel-tube margin is now spent by three independent compile-
time schedule controls. KCL column products, rounded currents, and prior-column
accumulation overlap at one column per clock with two pipeline-fill clocks per
call. Two further KCL clocks separate physical-residual capture, fixed-point
format conversion, global fallback/diagnostic reduction, and saturation.
Finally, two clocks per chord separate scaled correction, updated-node/
diagnostic calculation, and saturation commit. All four nonlinear passes use
the same unchanged equations and arithmetic boundaries.

The pipelined chord is bit-exact across 1,024 vectors at 12 clocks rather than
10. Its isolated Arty-A7-100 harness routes legally at 100.92 MHz against the
98.304 MHz request, improving the original 46.40 MHz result. It uses nine
DSP48E1s and packs to 9,501 `SLICE_LUTX`, 2,865 `SLICE_FFX`, and 530 CARRY4s.
This is an experimental nextpnr `DEFAULT`-grade result, not qualified -1
speed-grade signoff.

The combined pipelined KCL remains bit-exact across 1,024 backward-Euler and
1,024 trapezoidal vectors at 15 early-current clocks rather than 11. A finish-
only candidate placed at 40.00 MHz, and a superseded one-stage column candidate
placed at 36.76 MHz. The selected two-fill-clock column pipeline plus finish
pipeline uses 72 DSP48E1s and packs to 32,006 `SLICE_LUTX`, 9,356 `SLICE_FFX`,
and 1,958 CARRY4s. Its initial 98.304 MHz placement reaches only 38.95 MHz. A
subsequent 40 MHz request routes legally in 25 router2 iterations and measures
42.07 MHz post-route. That route identifies four cascaded 63-bit comparisons
in the exact maximum-absolute-residual diagnostic as the critical path rather
than the physical accumulator.

The route-informed schedule adds a register before the accumulator feedback
and pipelines only the final solver pass's nine-row maximum diagnostic. Earlier
KCL passes bypass the three maximum clocks because the solver does not consume
that diagnostic until its final residual. The global Q30/Q34/Q40 fallback is
unchanged. Signed 25-bit fit is expressed as the exactly equivalent sign-
extension test on bits 62:24; Q34/Q40 saturation is known false after their
existing all-row fit qualification, so only the registered Q30 fallback needs
an overflow count. The standalone diagnostic-enabled KCL is bit-exact across
1,024 vectors per integration method at 19 clocks.

Successive legal routes measure 64.90 MHz after splitting the maximum tree,
72.31 MHz after moving Q30 overflow work before global selection, and 92.23 MHz
after using the exact sign-extension predicate. The selected seed-1 route packs
to 29,514 `SLICE_LUTX`, 10,436 `SLICE_FFX`, 1,814 CARRY4s, and 72 DSP48E1s. Its
10.84 ns critical path now forms a signed capacitor stamp and adds it to a
registered matrix current; 3.34 ns is logic and 7.50 ns is routing. It misses
the 98.304 MHz request by 6.6% under the experimental `DEFAULT` timing grade.
An algebraically collapsed one-adder source form was tested and rejected: it
placed at only 70.24 MHz and produced substantially worse router congestion.
The completed 92.23 MHz result remains the measured baseline.

The final maximum is a diagnostic, not an input to chord correction. A new
selectable schedule therefore emits the final correction after the first
maximum-tree boundary and completes the exact maximum on a separate
`max_valid` sideband two clocks later. The KCL engine remains busy until the
sideband commits, preventing a new request from overwriting its diagnostic
state. Both backward-Euler and trapezoidal tests remain bit-exact across 1,024
vectors: correction latency falls from 19 to 16 clocks while the maximum value
and its valid pulse remain exact. The integrated chord is already running
during those two clocks, so the complete solver falls from 126 to 123 clocks
without changing its output, state, or diagnostic counters. This leaves five
of 128 fabric clocks available for subsequent multiplier scheduling.

This schedule recovery is not timing closure. The isolated seed-1 harness uses
6,294 estimated logic cells and 72 DSP48E1s, packs to 29,569 `SLICE_LUTX`,
10,437 `SLICE_FFX`, and 1,814 CARRY4s, and routes legally at 87.07 MHz against
98.304 MHz. Its 11.48 ns critical path is a registered capacitor current
through the exact current-overflow comparison into the current-state result;
1.50 ns is logic and 9.99 ns is routing. A timing-weight-20 placement reaches
only 80.03 MHz, so its congested router run is deliberately not continued.
The complete 123-clock hierarchy packs to 59,188 LUTX, 13,459 FFX, 4,036
CARRY4s, and 209 DSPs, then places at only 31.97 MHz. These results keep the
decoupled schedule as cycle-budget infrastructure while rejecting it as a
standalone Fmax fix.

### KCL capacitor-multiplier sharing

The decoupled schedule permits a cycle-free reduction in simultaneous KCL hard
multipliers. On the accepting `start` edge, capacitor branch 9's exact Q0.47 by
Q30 product is formed directly from the request voltage and history buses and
captured before those buses are latched. The same explicitly muxed 48-by-44-bit
multiplier then serves branches 0--8 during the existing pipelined column
schedule. This removes one wide multiplier implementation, or nine DSP48E1s,
without changing a product, rounding boundary, state update, or latency.

Both 1,024-vector integration-mode KCL regressions remain bit-exact at the
16-clock correction latency with the exact maximum sideband two clocks later.
Yosys measures the isolated candidate at 6,422 estimated logic cells, 10,437
flip-flops, and 63 DSP48E1s instead of 72. It packs to 29,469 `SLICE_LUTX`,
10,437 `SLICE_FFX`, 1,783 CARRY4s, and 63 DSPs, but seed-1 placement reaches
only 72.95 MHz. Because this is below the 98.304 MHz request and the established
72-DSP KCL has already routed at 87.07 MHz under the same decoupled schedule,
routing is skipped. The candidate is an area result, not an isolated timing
improvement.

The complete solver remains exact for all 512 stateful vectors at 123 clocks.
Its structural result is 14,779 estimated logic cells, 13,459 flip-flops, 200
DSPs, 16 RAMB18E1s, and two RAMB36E1s. Default placement uses 58,885 LUTX,
13,459 FFX, 4,005 CARRY4s, and 200 DSPs and reaches 35.06 MHz, a small gain over
the otherwise matching 209-DSP decoupled hierarchy's 31.97 MHz. A controlled
timing-weight-20 placement instead falls to 29.05 MHz. Neither run justifies
routing or promotion as the timing architecture.

Composing this KCL sharing with the two-batch terminal-current engine removes
another 20 DSPs. The 180-DSP solver is bit-exact for 512 stateful vectors at
124 clocks and synthesizes to 14,975 estimated logic cells and 14,591
flip-flops. Default placement reaches 30.63 MHz; the existing overlapping
hierarchy floorplan and timing weight 20 reach 32.94 MHz while matching 36,180
KCL/RHS and 25,572 nonlinear cells. Both are slower than the prior 189-DSP
floorplanned candidate's 36.83 MHz. An attempted reuse of that floorplan for
the 200-DSP candidate over-constrained its larger nonlinear group and was
stopped before a timing result. Multiplier sharing is therefore retained as a
selectable, exact scheduling architecture, while the measured results direct
the next timing work toward broader registered data paths rather than DSP count
alone.

With parallel triodes, KCL column/finish/accumulator boundaries, the final-only
maximum pipeline, and chord-apply boundaries enabled, the complete trapezoidal/
banked/terminal solver remains bit-exact across 512 stateful vectors at 126
clocks, leaving two of the 128 clocks available per internal sample. Yosys 0.66
measures its harness at 14,990 estimated logic cells, 13,458 flip-flops, 209
DSP48E1s, 16 RAMB18E1s, and two RAMB36E1s. The structural check has zero
problems. A separately verified capacitor-current rounding boundary would use
127 clocks, but has not been promoted because the selected KCL route shows a
different limiter. This is a structurally fitting schedule, not timing closure:
the isolated KCL is still 6.6% short.

The complete 126-clock hierarchy packs to 59,027 `SLICE_LUTX`, 13,458
`SLICE_FFX`, 4,036 CARRY4s, 209 DSP48E1s, 16 RAMB18E1s, and two RAMB36E1s.
Seed-1 placement reaches only 34.20 MHz against 98.304 MHz, so routing is not
attempted. The result is reproducible with the placement-only target and is a
whole-design architecture failure, not a local KCL timing estimate.

Placed-hierarchy analysis explains why isolated-block results do not compose.
KCL's 72 DSPs span 91 by 202 device-coordinate units; its 36,090 placed cells
span nearly the full device. Terminal-current uses another 54 DSPs over a
31-by-182 hard-block region. The two exact tube engines each use 35 DSPs plus
eight RAMB18E1s and one RAMB36E1; their hard-block centroids are approximately
(98,104) and (52,39). Chord correction's nine DSPs center near (98,179).
Therefore the 209-DSP hierarchy necessarily crosses most available DSP rows and
columns. The next architecture decision must reduce simultaneous hard-block
occupancy, adopt a larger open-tool-supported target, or both; another isolated
KCL register alone cannot close the measured 2.87x full-placement gap.

### Terminal-current resource-sharing experiment

The first lower-simultaneous-hard-block candidate reuses five terminal-current
workers for lanes 0--4 and 5--9. The pipelined chord exposes its already
registered final node update one cycle before `valid`, allowing the first batch
to overlap that preview. The second batch and its exact saturation count are
registered, after which a dedicated terminal-commit state consumes the last
available internal-sample clock. This is a scheduling approximation only: all
rounding, saturation, terminal voltages, conductances, and current-history
subtractions remain unchanged.

A dynamic procedural lane index initially synthesized into wide mux trees. The
corrected implementation uses five explicit fixed lane-pair muxes and latches
only the second-batch inputs. The isolated candidate is exact against the
original all-lane arithmetic for 1,027 directed/random vectors. Its named-part
route uses 4,296 `SLICE_LUTX`, 2,412 `SLICE_FFX`, 334 CARRY4s, and 34 DSP48E1s,
reaching 90.50 MHz with the default heap timing weight under the experimental
`DEFAULT` grade. A second deterministic seed-1 route with heap timing weight 20
reaches 99.59 MHz and closes the 98.304 MHz isolated-block constraint. The
established all-lane block uses 54 DSPs and reaches 88.83 MHz, so sharing
removes 20 DSPs and can meet the isolated deadline when placement is instructed
to prioritize timing.

The complete selectable schedule remains bit-exact for all 512 stateful solver
vectors at 127 clocks. Yosys measures 15,072 estimated logic cells, 14,590
flip-flops, 189 DSP48E1s, 16 RAMB18E1s, and two RAMB36E1s. Packing reports
59,514 `SLICE_LUTX`, 14,590 `SLICE_FFX`, 3,964 CARRY4s, and 189/240 DSPs. Legal
seed-1 placement reaches only 25.02 MHz, worse than the 209-DSP schedule's
34.20 MHz, so routing is deliberately skipped and the candidate is not
promoted. Region analysis confirms terminal hard-block occupancy falls from 54
to 34 DSPs and its span contracts to 31 by 161 coordinate units, but KCL still
spans 60 by 202 and the full design remains globally dispersed. Reducing a
single hierarchy's DSP count is therefore insufficient by itself. The isolated
99.59 MHz result does not supersede the separately measured 25.02 MHz complete
hierarchy result.

A tagged timing-weight-20 placement raises the complete candidate to 32.56 MHz
but still misses 98.304 MHz by 66.9% and remains below the selected 209-DSP
schedule's 34.20 MHz default-weight result. That run packs 59,539 `SLICE_LUTX`,
14,590 `SLICE_FFX`, 3,964 CARRY4s, and 189 DSPs. Its terminal-current DSP region
actually expands to 91 by 167 coordinate units while KCL remains spread 60 by
197, so the timing preference does not create useful hierarchy locality.
Routing remains unjustified. The open-flow runner's `--run-tag` option retains
the netlist, placed design, logs, reports, and compact summary for tuning runs
without overwriting the untagged baseline evidence.

### Overlapping hierarchy-region experiment

The A100T exposes DSP columns at tile X coordinates 28, 88, and 119. A strict
left/right partition was over-constrained: forcing KCL plus RHS into 76 of the
left column's 80 DSP sites did not complete even its first heap iteration in
more than six minutes. That exploratory partition was stopped and is not a
timing result.

The retained V2 floorplan instead uses overlapping rectangular regions. KCL
plus RHS may use the left and center columns (76 of 160 DSP sites); the tube,
chord, and terminal-current blocks may use the center and right columns (113 of
160 sites). Solver control remains unconstrained. The pre-place hook matches
36,360 packed KCL/RHS cells and 25,574 nonlinear cells, proving the hierarchy
selectors are active after packing.

At seed 1 and timing weight 20, this placement reaches 36.83 MHz. It improves
the same candidate's unconstrained 32.56 MHz by 13.1% and the selected
209-DSP/default-weight baseline's 34.20 MHz by 7.7%, but still falls 62.5% below
98.304 MHz. KCL remains 60 by 197 hard-block coordinates, while the terminal
DSP span contracts from 91 by 167 to 31 by 161. Total annealed wire length falls
from 3,010,517 to 2,006,868 units. This validates explicit hierarchy placement
as a useful optimization, but its 2.67x remaining frequency gap requires a
broader arithmetic/scheduling change; routing is deliberately skipped.

### Soft KCL multiplier experiments

The KCL source contains eleven signed multipliers; their widths expand to 72
DSP48E1s in the selected isolated implementation. A reproducible Yosys branch
stops immediately before `map_dsp`, asserts that exactly those eleven `$mul`
cells exist under `network_kcl_v1_wide`, marks them for soft multiplication,
and then resumes the standard XC7 mapping flow. This is a technology-mapping
experiment: it changes neither RTL, fixed-point widths, rounding, saturation,
nor the 19-clock KCL schedule.

The isolated KCL maps from 72 DSPs to zero, but Yosys grows from the selected
implementation's compact hard-multiplier structure to 43,389 estimated logic
cells. Exact nextpnr packing consumes 71,592/126,800 `SLICE_LUTX`, 10,436
`SLICE_FFX`, and 1,843 CARRY4s. In the complete shared-terminal solver, KCL
softening reduces the DSP count from 189 to 117 but raises estimated logic from
15,072 to 51,475 cells. Exact packing consumes 101,479/126,800 LUT elements
(80%), 14,590 FFX, 3,993 CARRY4s, 117 DSPs, 16 RAMB18s, and two RAMB36s.

No Fmax is claimed. The isolated 56%-LUT candidate did not finish placement in
a useful diagnostic interval: the default run completed five analytical
iterations in about 7 minutes 20 seconds without reaching timing analysis, and
an eightfold tighter heap-attempt bound reproduced 81.39 and 77.29 second first
iterations because that option does not bound the dominant analytical phase.
Both exploratory placement runs were stopped. The retained `--pack-only` flow
finishes normally and labels placement/timing as incomplete. All-soft KCL is
therefore not promoted: it removes DSP pressure at the cost of severe LUT and
placement pressure. Partial multiplier sharing or a scheduled, explicitly
pipelined soft-multiply kernel remains a distinct future experiment.

A second mapping softens only the two 48-by-44-bit capacitor-current
multipliers, selected by cell type, hierarchy, and operand-width parameter with
an asserted count of two. The nine 41-by-40 matrix multipliers remain hard.
This removes 18 rather than 72 DSP48E1s. Isolated synthesis reports 12,710
estimated logic cells and 54 DSPs; exact packing uses 36,327 LUTX, 10,436 FFX,
1,798 CARRY4s, and 54 DSPs. Seed 1 fails strict legalization on one FFX after
the backend's 10,001-attempt minimum. Reducing the documented timeout divisor
from 8 to 4 reproduces the same minimum and failure, so this is not represented
as increased placement effort. Seed 2 legalizes and reaches only 37.57 MHz
after placement, versus the selected all-DSP KCL's completed 92.23 MHz route.
Routing is deliberately skipped after the 2.62x placement miss.

The partial mapping raises the complete shared-terminal solver from 15,072 to
21,333 estimated logic cells. It packs legally at 66,341 LUTX, 14,590 FFX,
3,948 CARRY4s, 171 DSPs, 16 RAMB18s, and two RAMB36s. This is a much smaller LUT
penalty than all-soft KCL, but it adds 6,827 LUT elements while the isolated
block loses 59.2% of its measured frequency. Complete placement is therefore
not justified. Static hard-block removal without an explicit registered
soft-multiply schedule is rejected for both tested scopes.

### XC7A200T capacity experiment

The pinned bootstrap now generates both `xc7a100t` and `xc7a200t` chip
databases. XC7A200T is exercised through the exact Nexys Video
`xc7a200tsbg484-1` package and a three-pin timing harness derived from
Digilent's master XDC. Device-qualified build/result paths prevent this run
from overwriting the A100T evidence. The RTL and synthesized netlist are
unchanged: 59,027 packed LUT elements, 13,458 flip-flops, 4,036 CARRY4s, 209
DSPs, 16 RAMB18s, and two RAMB36s. The larger part reduces packed DSP use from
87% to 28% and reports 21% LUT-element occupancy.

Capacity alone does not close placement. Seed 1 with nextpnr's default heap
timing weight reaches 23.83 MHz; seed 2 reaches 30.55 MHz. Retaining seed 1 and
raising the documented heap timing weight from 10 to 20 improves the estimate
to 35.22 MHz, still 2.79x short of 98.304 MHz and statistically comparable to
the A100T's 34.20 MHz baseline. Routing is deliberately skipped. All figures
remain experimental `DEFAULT`-grade estimates. The controlled experiment rules
out device capacity by itself as the remedy: the next implementation branch
must reduce cross-hierarchy combinational distance/simultaneous hard-block
coupling or introduce reproducible hierarchy placement constraints before a
larger device is reconsidered.

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

The last controlled 768 kHz complete trapezoidal banked terminal stream
measurement is 18,280 logic cells, 206 DSP48E1s, eight RAMB18E1s, and one
RAMB36E1 with zero structural check problems. Each half-band decimator spends
one additional MAC clock on its center product instead of instantiating a
second multiplier. The subsequently selected reset-masked circular histories
are bit-exact at 16×, reduce the standalone four-stage interpolator/decimator
to 1,417 LC / 1,229 FF / 16 DSP and 1,408 / 817 / 16, and reduce the complete
768 kHz stream to 16,062 LC / 9,033 FF / 206 DSP. This occupies 85.8% of the XC7A100T's DSPs,
leaving 34 blocks but still ruling out duplication for stereo. Its exact solver
latency remains 127 clocks; only named-part place-and-route can establish
whether the arithmetic meets 98.304 MHz.

The explicit 384 kHz candidate, including its three-stage converters, 19-bit
chord bank, and circular resampler histories, measures 15,716 logic cells,
8,547 flip-flops, 207 DSP48E1s, eight RAMB18E1s, and one RAMB36E1. The prior
shifting-history implementation measured 17,693 LC / 14,737 packed FFX. The
circuit arithmetic is unchanged and the cycle budget remains 256 clocks.

`stream_384khz_pnr_harness` preserves the complete candidate behind the same
three physical timing pins as the solver harness. On XC7A100T it packs to
63,902 `SLICE_LUTX`, 14,737 `SLICE_FFX`, 4,071 CARRY4s, 207 DSP48E1s, eight
RAMB18E1s, and one RAMB36E1. The default heap placement does not legalize; the
earlier 219-DSP form also fails with deeper heap search. On the larger
XC7A200T, heap seeds 1 and 2 fail legalization for the earlier 219-DSP form.
The independent static placer legally places the reduced 207-DSP netlist and
reports 34.40 MHz against 98.304 MHz under the experimental `DEFAULT` timing
grade. This is a 2.86x placement miss, so routing is deliberately skipped.
The result is not qualified -1 signoff, but it proves that neither raw A200T
capacity nor the 8× candidate's doubled cycle budget makes the present
combinational structure viable.

The separately named `stream_384khz_49mhz_pnr_harness` tests the same circuit
and arithmetic with a 49.152 MHz fabric clock: 1,024 clocks per external input
and 128 per internal update. Exact RTL verifies the 127-clock solver with one
clock of margin across 64 outputs / 512 updates and zero diagnostics. The A200T
pack is unchanged at 63,902 LUTX / 207 DSP, apart from two fewer phase-counter
flip-flops. Static placement improves to 38.34 MHz against 49.152 MHz, reducing
the timing ratio miss from 2.86x to 1.28x but not closing it. A timing-driven
heap attempt on the shifting-history netlist still fails legalization after
10,001 attempts at a stage-three decimator flip-flop. The selected circular
history reduces controlled synthesis to 16,315 LC / 10,520 FF and packs at
58,363 LUTX / 10,562 FFX / 4,099 CARRY4 / 207 DSP. Heap placement now
legalizes, proving that the decimator registers were a real congestion blocker,
but reaches only 22.79 MHz against 49.152 MHz. Static placement reaches 38.38
MHz, effectively unchanged from the old 38.34 MHz result. Converting the
interpolator history as well reduces controlled synthesis to 15,716 LC / 8,547
FF and the pack to 56,041 LUTX / 8,589 FFX / 4,116 CARRY4 / 207 DSP. Static
placement improves to 41.27 MHz, a remaining 19.1% frequency shortfall. A full
router2 run then completes legally in 15 iterations and emits FASM. Post-route
timing is 48.482 MHz versus 49.152 MHz: a 1.38% miss rather than closure. The
20.626 ns critical path contains 6.19 ns logic and 14.44 ns routing. It starts
at solver state selection, crosses the corrected/current voltage mux and the
stage-one plate-node subtraction/Q20 conversion, then traverses the
factorized-tube plate-coordinate range logic before ending at a tube-engine
register. This is the first completed full-stream route and the relevant
retiming evidence. It is not a qualified `-1` result, a generated bitstream,
or hardware readiness.

The separately named `stream_384khz_49mhz_pipelined_pnr_harness` composes the
existing parallel-tube, registered KCL/chord, and decoupled-diagnostic
schedules without changing equations or fixed-point operations. The complete
64-output regression remains bit-exact with zero diagnostics at 123 solver
clocks, leaving five clocks per internal update. That apparent margin is not a
timing win: Yosys measures 17,161 LC / 15,046 FF / 242 DSP / 20 RAMB18
equivalents, which exceeds the A100T DSP count, and the A200T pack is 66,658
LUTX / 15,046 FFX / 4,633 CARRY4 / 242 DSP. Static placement reaches only
39.62 MHz. Routing is therefore skipped and the profile is not promoted.

The route-guided `stream_384khz_49mhz_prefetched_pnr_harness` captures both
triode pin pairs from stable sample state and from the exact one-cycle-early
non-pipelined chord result. It leaves every numerical operation and the
127-clock schedule unchanged, but its first route reaches only 46.942 MHz. It
successfully removes the baseline state/voltage/tube path; the critical cone
moves to the exact KCL maximum diagnostic instead.

`stream_384khz_49mhz_retimed_pnr_harness` additionally releases the final KCL
correction at its original edge and computes the independent residual maximum
during the following chord interval. Backward-Euler and rate-specific
trapezoidal KCL tests each match 1,024 vectors exactly, and the persistent
solver and complete stream remain exact at 127 clocks. Routing showed why each
boundary matters: a shallow tree still reaches only 45.806 MHz through the
maximum cone; staging the tree while retaining an invalid-only combinational
output load reaches 44.524 MHz through that dead load. Suppressing the dead
load and registering absolute value, pair, quad, and final comparisons yields
15,852 LC / 9,793 FF / 207 DSP / 10 RAMB18 equivalents and packs at 58,322
LUTX / 9,793 FFX / 4,258 CARRY4 / 207 DSP. The final route is legal after 24
router2 iterations but reaches 47.07 MHz. Its 21.24 ns path contains 8.34 ns
logic and 12.90 ns routing from chord residual-format/update logic through the
early preview and tube-pin conversion to a tube input register. Because this
is slower than the 48.482 MHz baseline and another preview register would add
a clock to each correction pass, neither prefetch profile is promoted.

The zero-latency `stream_384khz_49mhz_late_select_pnr_harness` attacks the
baseline path without a preview register. It performs the existing exact node
subtractions and Q-format conversions independently on the current and
corrected stage-one values, then selects the already converted 32-bit `Vgk`
and `Vpk` buses. The complete 64-output/512-update regression remains bit-exact
with zero diagnostics at 127 clocks. Yosys measures 15,645 LC / 8,589 FF / 207
DSP / 10 RAMB18 equivalents; open packing measures 56,549 LUTX / 8,589 FFX /
4,181 CARRY4 / 207 DSP. Seed 1 routes legally in 28 router2 iterations at
48.700 MHz versus 49.152 MHz, a 0.92% shortfall. Its 20.53 ns path contains
8.84 ns logic and 11.70 ns routing and now lies entirely in the KCL residual
absolute-value/maximum diagnostic. Seed 2 routes legally in 25 iterations at
45.051 MHz. Seed 3 places at 41.55 MHz, but its router took several minutes per
iteration and was bounded after iteration 2; no routed seed-3 Fmax is claimed.

For context, the unchanged baseline seed sweep reaches 48.482, 46.326, and
46.970 MHz for seeds 1--3; seeds 2 and 3 legalize in 15 and 17 router2
iterations. Thus the seed-1 late-selector result is the best complete route,
but neither a single favorable seed nor the experimental backend's `DEFAULT`
grade constitutes closure. A combined late-selector/four-boundary-maximum
profile remains numerically exact and synthesizes to 16,120 LC / 9,665 FF /
207 DSP / 10 RAMB18 equivalents. Its 1,076 extra registers increase control
sets and routing pressure: the local run needed roughly twelve minutes for
router iteration 1, still had 45,484 overused wires, and was bounded during
iteration 2. It is rejected as a physical implementation, not reported as a
failed legal route.

`stream_384khz_49mhz_late_select_serial_max_pnr_harness` avoids that replicated
state. On the one KCL pass where the convergence diagnostic is enabled, it
releases the exact correction on the original edge, initializes a running
maximum from residual row 0, and scans rows 1--8 over the following eight
clocks. The residual registers remain stable while KCL holds `busy`, and the
scan completes inside the ten-clock terminal chord operation, so solver
latency remains 127 clocks. Both 1,024-vector KCL regressions and the complete
stream are exact. Yosys measures 15,208 LC / 8,657 FF / 207 DSP / 10 RAMB18
equivalents and open packing measures 54,699 LUTX / 8,657 FFX / 4,044 CARRY4 /
207 DSP. Seed 1 routes legally in 14 iterations at 47.567 MHz. The 21.02 ns
critical path contains 6.10 ns logic and 14.92 ns routing from a registered
chord-corrected node through stage-one pin conversion and the factorized-tube
input logic. Serializing the diagnostic is therefore a valid area/schedule
improvement, but does not close timing by itself.

`stream_384khz_49mhz_node_prefetch_serial_max_pnr_harness` adds the successful
register boundary. It captures stage-one and stage-two grid, plate, and cathode
nodes from the exact one-cycle-early chord preview; the original subtraction
and Q-format conversion then execute during the already available
preview-to-launch interval. Current-state nodes are captured at RHS start for
the first iteration. The numerical operations, update order, and solver latency
are unchanged: all 64 outputs / 512 nonlinear updates match the fixed model
exactly at 127 clocks with zero diagnostics.

Yosys 0.66 measures 15,220 logic cells, 8,855 flip-flops, 207 DSP48E1s, eight
RAMB18E1s, and one RAMB36E1. Open packing uses 54,280 `SLICE_LUTX`, 8,855
`SLICE_FFX`, 3,979 CARRY4s, and the same DSP/RAM count. Seed 1 with the static
placer and router2 completes a legal route in 23 iterations at 61.072 MHz
against 49.152 MHz. The 16.37 ns critical path begins at stored capacitor
current, crosses the terminal-current update and solver-state arithmetic, and
contains 6.44 ns logic plus 9.94 ns routing. Estimated positive margin is
3.97 ns. The prior chord-to-tube path is no longer critical. Seed 2 also
completes legally, in 14 router2 iterations at 51.080 MHz. Its limiting path
runs from a prefetched node through subtraction/conversion and the factorized
tube input logic in 19.58 ns (6.22 ns logic / 13.36 ns routing), leaving
0.77 ns positive estimated margin. The two successful seeds have different
critical paths.

This is the first complete-stream timing closure under the pinned open
nextpnr-Himbaechel backend's experimental `DEFAULT` grade. It is not qualified
XC7A200T-1 timing signoff or a board measurement. Those claims remain gated on
qualified timing and physical validation.

The same selected profile is now elaborated inside the real fabric and pin
hierarchies rather than only the timing harness. At 384 kHz / 49.152 MHz the
calibrated fabric adapter matches 64 mono frames exactly, and the asynchronous
I²S regression accepts all 64 serial inputs and matches 44 post-startup DAC
frames with all four local FIFO high-water marks equal to one. The
register-owned control and complete 15-frame mode-0 SPI tests also pass with
the 384 kHz branch selected. Yosys 0.66 out-of-context synthesis measures
15,699 estimated logic cells, 9,085 flip-flops, 217 DSP48E1s, and ten 18-kbit
BRAM equivalents for the adapter. The complete `phono_i2s_spi_top` measures
16,614 logic cells, 11,586 flip-flops, the same 217 DSPs and ten BRAM
equivalents. Both checks report zero structural problems.

These are hierarchy-integration and structural results, not a board image. The
clock-source part of that gap is now closed by `audio_clock_synth_xc7`. It
cascades two `MMCME2_BASE` instances from the real R4 100 MHz oscillator:

```text
100 MHz * 48 / 5 / 78.125 = 12.288 MHz codec MCLK
12.288 MHz * 50 / 1 / 12.5 = 49.152 MHz model fabric clock
```

The VCO frequencies are exactly 960 and 614.4 MHz. Both output dividers are on
the 7-series `CLKOUT0_DIVIDE_F` one-eighth grid. The generated
`audio_clock_plan_xc7.json` is computed with rational arithmetic and parsed
from the actual RTL, so a changed multiplier or divider fails the unit test.
This module is intentionally board/device specific; no XC7 primitive enters
the physical circuit or sample-processing RTL.

The R4 constraint now includes an explicit 10 ns `create_clock`. The pinned
nextpnr backend consequently derives 12.3 MHz and 49.2 MHz domains through the
two MMCMs instead of assigning the command-line 100 MHz target to the generated
activity logic. The clock-only A200T harness packs 74 LUTX, 24 FFX, six
CARRY4s, two BUFGs, two MMCMs, and five pads. Router2 reaches a legal route in
five iterations; the 24-bit activity counter is estimated at 305.06 MHz against
its correct 49.152 MHz constraint. This large counter margin only validates
the clock harness's synchronous load. It says nothing about complete phono-core
timing and remains an experimental `DEFAULT`-grade estimate rather than
qualified `-1` signoff.

The 50,091-byte routed FASM hashes to
`0152506daf8ae0609ec16772e42fb883b4bf5f11729c23eab241f1ef7fa48219`.
Project X-Ray converts it into 20,230 frame records and a reproducible
9,730,853-byte bitstream with SHA-256
`941a8c07ed55a651e3b861e74bc09bee311c410519c09daddf5615069e0ff656`;
`bitread -C` accepts 24,060 configuration frames / 2,432,650 words. No board
has been programmed and neither output clock has been physically measured.

The serial-clock leaf now divides the exact 49.152 MHz fabric clock by 16 and
promotes the 3.072 MHz output through one BUFG. This derived domain exists only
for the codec serial interface; all physical-circuit processing stays on the
fabric clock with enables. Separate three-stage reset pipelines assert
asynchronously and release synchronously in the fabric and BCLK domains. A
warning-free directed test checks every 16-clock BCLK period, both three-edge
release latencies, and asynchronous reassertion. Yosys reports ten FDCEs, one
CARRY4, one BUFG, zero structural problems, and no warnings.

A concrete audio board wrapper still needs the codec's single shared LRCLK
wired to both serial directions and ADAU1761 I2C initialization. The Nexys
Video's shared codec LRCLK must not be silently represented as independent
ADC-input and DAC-output pins. Until those items and physical measurement are
complete, the clock harness is not a functional audio image.

The codec-control foundation is now implemented as a device-neutral open-drain
I2C register writer. Each command emits the seven-bit target address plus write
bit, a 16-bit register address, and one byte of data. It samples ACK after every
byte, honors target SCL stretching while the line is released, and emits STOP
before reporting completion even after a NACK. A bus-level target test verifies
the exact four bytes, deliberate NACK capture, and recovery on a subsequent
transaction. Warning-free Yosys XC7 synthesis uses 43 estimated logic cells,
59 flip-flops, three CARRY4s, and no DSP/BRAM. The fixed startup use case does
not require reads, arbitration, or multi-main operation; those capabilities are
not implemented or claimed.

### ADAU1761 bootstrap contract

The startup table follows the ADAU1761 Rev. F register definitions and the
Nexys Video's proven analog route, with clock ownership deliberately changed
from Digilent's older demo: the FPGA is main for BCLK/LRCLK, so R15 is `00` and
only CLK0 is enabled in R66. The codec PLL is unnecessary at exact 12.288 MHz.
The full tested order is:

| Index | Register | Data | Purpose |
|---:|---:|---:|---|
| 0 | `4000` | `01` | direct MCLK, core enable |
| 1--2 | `4025`, `4026` | `E4`, `E4` | line L/R at 0 dB, muted |
| 3--6 | `4015`, `4016`, `4017`, `40F8` | `00`, `00`, `00`, `00` | subordinate I2S, 64-bit frame, 48 kHz converters/port |
| 7--10 | `400A`--`400D` | `01`, `05`, `01`, `05` | symmetric L/R input mixers, AUX 0 dB, differential inputs muted |
| 11--13 | `4019`, `402A`, `4029` | `13`, `03`, `03` | enable stereo ADC, DAC, and playback paths |
| 14--15 | `40F2`, `40F3` | `01`, `01` | serial L0/R0 to DAC; ADC L0/R0 to serial |
| 16--19 | `401C`--`401F` | `21`, `00`, `41`, `00` | DAC playback mixers at documented -6 dB; bypasses muted |
| 20--21 | `4020`, `4021` | `03`, `09` | Nexys Video line-output mixer route |
| 22--24 | `40F4`, `40F9`, `40FA` | `00`, `7F`, `01` | serial pins, digital clocks, CLK0 only |
| 25--26 | `4025`, `4026` | `E6`, `E6` | unmute L/R line outputs last |

The production parameter waits 491,520 fabric clocks, 10 ms at 49.152 MHz,
before issuing the first transaction. An I2C quarter-period divider of 32 gives
384 kHz nominal SCL. All 27 writes are byte-exact in the target-model test. A
forced NACK at index five completes STOP, latches `failed_index=5`, and issues
no later transaction. Because the final left/right unmute cannot be atomic on
I2C, the board wrapper must hold transmitted PCM at zero until the entire table
reports `configured`; a bus failure cannot by itself prove an analog mute.
Physical ACKs, converter clocks, and analog behavior remain unmeasured.

The following configuration stage is also fully open. The pinned bootstrap now
installs the Project X-Ray Python assembler dependencies, and
`generate_openxc7_bitstream.py` converts a chosen routed FASM through
`fasm2frames` and `xc7frames2bit`. It replaces only variable header date/time
metadata with a caller-controlled epoch (zero by default) and passes a
repository-relative frame name, making the artifact reproducible across runs
and clone paths. The script records input/frame/bitstream SHA-256 values and
both pinned Git revisions, then invokes `bitread -C`; successful parsing is a
required gate. It does not program a cable or set `hardware_validated`.

For the seed-1 timing-closed route, the 44,258,864-byte FASM hashes to
`af98f3fb...b51e9e32`. It assembles to 20,230 frame records / 22,698,060 bytes
and emits a 9,730,907-byte bitstream. Two end-to-end conversions produce the
same SHA-256, `98a53adf504a9a36669c34da59e6d1f185a4a67c8ba7de3aa4fab3c83a2b9dcb`.
Project X-Ray `bitread -C` accepts the result as 24,060 configuration frames and
2,432,650 configuration words. This proves reproducible artifact generation,
not successful configuration or functional hardware behavior.

The placement analyzer now recognizes complete-stream resampler hierarchy
instead of folding it into harness constants. In the 38.34 MHz static result,
the decimator accounts for 8,397 LUTX / 4,791 FFX / 12 DSP and spans 244x143
placement coordinates; the interpolator is 5,193 / 2,910 / 12 over 244x139.
For comparison, KCL is 19,609 / 2,920 / 72 over 190x185. The resampler history
registers and their nearly device-wide placement were therefore a first-class
congestion target, consistent with the heap failure occurring in decimator
stage three. The reset-masked circular implementation preserves every exact FIR
and complete-stream vector, maps the 8× histories into 30 `RAM32M` primitives,
and reduces that decimator to 961 LC / 618 FF / 12 DSP. Its successful heap
legalization closes the congestion diagnosis, while the 22.79 MHz result shows
that the complete timing problem remains elsewhere as well. In the refreshed
static placement, the decimator hierarchy is 2,725 LUTX / 618 FFX / 12 DSP
versus the old 8,397 / 4,791 / 12. It still spans 244x181 placement coordinates,
while the unchanged interpolator consumes 5,225 / 2,910 / 12 over 184x242 and
KCL consumes 19,616 / 2,920 / 72 over 211x160. The nearly unchanged static Fmax
despite the decimator reduction is direct evidence against continuing to treat
that history as the critical timing path. The circular interpolator maps to 12
`RAM32M` plus 11 `RAM64M` primitives and falls from 1,549 LC / 2,910 FF to 950
/ 938 at 8×. In the 41.27 MHz placement it occupies 2,806 LUTX / 937 FFX / 12
DSP over 234x45 coordinates; the decimator is 2,725 / 618 / 12 over 48x203,
and KCL is 19,627 / 2,920 / 72 over 230x153.

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
| estimated logic cells | 18,642 |
| flip-flops | 16,354 (15,878 FDRE + 476 FDSE) |
| DSP48E1 | 216 |
| RAMB18E1 / RAMB36E1 | 8 / 1 |
| RAMB18-equivalents | 10 |

The structural check reports zero problems. The 76 unique warnings are known
small local-array register expansions and Xilinx primitive output-port resize
notices retained in the full log; they are not mislabeled as a dual-clock FIFO
inference warning. This top includes frame scheduling, both runtime calibration
multipliers, the 127-clock trapezoidal/banked/terminal stream, and the two-DSP
modern output ramp. It excludes the asynchronous I²S bridge, atomic control
commit, and dedicated safety hardware. At 216/240 DSPs it leaves 24 DSP48E1s on
the provisional A7-100T. Structural fit does not prove that its one-clock
solver margin meets 98.304 MHz.

The resource reporter now records RAMB36E1 separately and publishes a
RAMB18-equivalent total. Earlier summaries silently omitted the one mapped
RAMB36E1 in every factorized-tube hierarchy; the corrected documents retain
both eight RAMB18E1s and one RAMB36E1 (ten 18-Kib equivalents). No numerical RTL
or memory implementation changed as a result of that reporting correction.

Adding the two asynchronous stereo FIFOs and I²S protocol blocks around the
adapter produces the pin-facing digital hierarchy:

| Resource | Count |
|---|---:|
| estimated logic cells | 19,156 |
| flip-flops | 17,669 |
| DSP48E1 | 216 |
| RAMB18E1 / RAMB36E1 | 8 / 1 |

The flip-flop total is 16,582 FDRE, 476 FDSE, 471 FDCE, 3 FDPE, 131
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
| estimated logic cells | 19,616 | 19,719 |
| flip-flops | 18,684 | 18,856 |
| DSP48E1 | 216 | 216 |
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
