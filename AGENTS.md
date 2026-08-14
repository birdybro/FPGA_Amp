# FPGA_Amp engineering instructions

These instructions apply to the entire repository.

## Reference hierarchy and truthfulness

- Published physical behavior and the frozen circuit artifact establish intent.
- SPICE is the analog-circuit golden reference.
- The Python floating-point model validates the mathematical and discrete-time implementation.
- The Python fixed-point model defines exact RTL numerical behavior.
- Synthesizable SystemVerilog is checked against the fixed-point model.
- Keep historical/reference behavior, approximation error, and modern/creative features separate and labeled.
- Never tune a downstream model to taste or hide a mismatch. Record errors and limitations.
- Never falsify resource, timing, accuracy, simulation, synthesis, or hardware-validation claims.

## RTL and arithmetic

- RTL must be synthesizable. Do not use floating point, `real`, or `shortreal` in synthesizable logic unless a later resource study explicitly justifies a floating-point IP core.
- Prefer one fabric clock with clock enables; do not create derived fabric clocks for sample timing.
- Use explicit CDC synchronizers, asynchronous FIFOs, or protocol handshakes at every clock-domain crossing.
- Prefer DSP-friendly arithmetic and avoid hardware division unless its measured cost is justified.
- Use explicit signed widths and preserve full multiplication results.
- Document every rounding rule. Saturate where wraparound is physically meaningless.
- Do not silently truncate or rely on implicit signed/unsigned promotion.
- Generated LUTs, coefficients, and vectors must be reproducible from versioned scripts and configurations.
- Treat lint, simulator, and synthesis warnings as engineering findings; suppress only a documented false positive.

## Verification and workflow

- Preserve regressions that expose real discrepancies. Every fixed bug should gain a test when practical.
- Run the narrowest relevant test while developing, then the full regression before claiming completion.
- Keep stochastic noise disabled in deterministic equivalence tests.
- Prefer checked-in compact source data over opaque generated binaries. Generated results go under `reference/results/` or `build/` and must identify their generator.
- Update `TASKS.md` and `CHANGELOG.md` continuously when milestones, discrepancies, circuit values, arithmetic, or measured results change.
- Do not stop merely because an intermediate milestone works while another meaningful, unblocked verification step is available.

## FPGA toolchain

- The required synthesis, place/route, bitstream, programming, and verification flow must use open-source tools and be runnable on Linux without Vivado or another proprietary FPGA suite.
- Use Yosys for synthesis and formal work. The provisional Artix-7 flow uses nextpnr-Himbaechel with Project X-Ray data; keep the backend's experimental status and timing-model limitations explicit.
- A routed result is not a speed-grade timing claim when the backend does not distinguish that speed grade. Preserve tool versions, constraints, seeds, reports, and logs for every physical result.
- Do not make a bitstream or hardware-readiness claim until the open bitstream generator, complete board constraints, clock generation, and programming/capture path have each been exercised.

## Physical engineering

- Do not imply that the FPGA or DAC can drive passive loudspeakers directly.
- Keep safety-critical protection in dedicated hardware where appropriate; FPGA control is not a sole safety barrier.
- Do not claim physical validation before actual converter, analog, and hardware measurements exist.
