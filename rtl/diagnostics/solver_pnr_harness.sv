`timescale 1ns/1ps
`default_nettype none

// Minimal physical-I/O wrapper used only for named-part place-and-route.
// It keeps the complete accuracy-first solver active without exposing its
// wide internal buses as package pins.  This is not an audio or bitstream top.
module solver_pnr_harness #(
    parameter bit USE_LINEAR_FACTORIZED_TUBE = 1'b0,
    parameter bit PARALLEL_TUBES = 1'b0,
    parameter bit PIPELINED_KCL_FINISH = 1'b0,
    parameter bit PIPELINED_KCL_COLUMNS = 1'b0,
    parameter bit PIPELINED_KCL_ACCUMULATOR = 1'b0,
    parameter bit PIPELINED_KCL_CAPACITOR_CURRENT = 1'b0,
    parameter bit PIPELINED_KCL_MAXIMUM = 1'b0,
    parameter bit PIPELINED_CHORD_APPLY = 1'b0,
    parameter bit HALF_PARALLEL_TERMINAL_CURRENT = 1'b0
) (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    logic rst_n;
    logic [6:0] sample_phase;
    logic signed [31:0] stimulus_lfsr;
    logic ce_sample;

    (* keep *) logic signed [39:0] output_q32;
    (* keep *) logic output_valid;
    (* keep *) logic busy;
    (* keep *) logic [7:0] sample_latency_cycles;
    (* keep *) logic [31:0] missed_request_count;
    (* keep *) logic [31:0] deadline_miss_count;
    (* keep *) logic [31:0] saturation_count;
    (* keep *) logic [31:0] lut_clip_count;
    (* keep *) logic [31:0] nonconvergence_count;
    (* keep *) logic [31:0] correction_scale_fallback_count;
    (* keep *) logic [5:0] minimum_correction_fractional_bits;
    (* keep *) logic [62:0] last_residual_q44;
    (* keep *) logic [359:0] node_voltage_debug;
    (* keep *) logic [399:0] capacitor_state_debug;
    (* keep *) logic [479:0] capacitor_current_state_debug;

    assign rst_n = !reset;
    assign ce_sample = (sample_phase == 7'd0);

    always_ff @(posedge fabric_clk) begin
        if (!rst_n) begin
            sample_phase <= '0;
            stimulus_lfsr <= 32'h1ace_b00c;
            activity <= 1'b0;
        end else begin
            sample_phase <= sample_phase + 1'b1;
            if (ce_sample) begin
                stimulus_lfsr <= {
                    stimulus_lfsr[30:0],
                    stimulus_lfsr[31] ^ stimulus_lfsr[21]
                    ^ stimulus_lfsr[1] ^ stimulus_lfsr[0]
                };
            end
            if (output_valid) begin
                // A small registered signature makes every externally useful
                // solver result observable while avoiding a wide package bus.
                activity <= activity
                            ^ output_q32[0]
                            ^ busy
                            ^ sample_latency_cycles[0]
                            ^ missed_request_count[0]
                            ^ deadline_miss_count[0]
                            ^ saturation_count[0]
                            ^ lut_clip_count[0]
                            ^ nonconvergence_count[0]
                            ^ correction_scale_fallback_count[0]
                            ^ minimum_correction_fractional_bits[0]
                            ^ last_residual_q44[0]
                            ^ node_voltage_debug[0]
                            ^ capacitor_state_debug[0]
                            ^ capacitor_current_state_debug[0];
            end
        end
    end

    (* keep *) v1_solver_mono_wide_trapezoidal_banked_terminal #(
        .USE_LINEAR_FACTORIZED_TUBE(USE_LINEAR_FACTORIZED_TUBE),
        .PARALLEL_TUBES(PARALLEL_TUBES),
        .PIPELINED_KCL_FINISH(PIPELINED_KCL_FINISH),
        .PIPELINED_KCL_COLUMNS(PIPELINED_KCL_COLUMNS),
        .PIPELINED_KCL_ACCUMULATOR(PIPELINED_KCL_ACCUMULATOR),
        .PIPELINED_KCL_CAPACITOR_CURRENT(PIPELINED_KCL_CAPACITOR_CURRENT),
        .PIPELINED_KCL_MAXIMUM(PIPELINED_KCL_MAXIMUM),
        .PIPELINED_CHORD_APPLY(PIPELINED_CHORD_APPLY),
        .HALF_PARALLEL_TERMINAL_CURRENT(
            HALF_PARALLEL_TERMINAL_CURRENT
        )
    ) solver (
        .clk(fabric_clk),
        .rst_n,
        .ce_sample,
        .input_q24(stimulus_lfsr),
        .output_q32,
        .output_valid,
        .busy,
        .sample_latency_cycles,
        .missed_request_count,
        .deadline_miss_count,
        .saturation_count,
        .lut_clip_count,
        .nonconvergence_count,
        .correction_scale_fallback_count,
        .minimum_correction_fractional_bits,
        .last_residual_q44,
        .node_voltage_debug,
        .capacitor_state_debug,
        .capacitor_current_state_debug
    );

endmodule

// Separately named candidate so baseline and timing-oriented reports cannot
// overwrite one another or silently select a different tube approximation.
module linear_solver_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    solver_pnr_harness #(
        .USE_LINEAR_FACTORIZED_TUBE(1'b1)
    ) harness (.*);

endmodule

// Scheduling candidate with two otherwise identical Hermite tube engines.
module parallel_solver_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    solver_pnr_harness #(
        .PARALLEL_TUBES(1'b1)
    ) harness (.*);

endmodule

// Timing candidate that spends 24 recovered solver clocks on two KCL column
// fill boundaries, two KCL finish boundaries, and two chord-apply boundaries
// in each of the four nonlinear passes. The complete terminal solve is 119
// clocks, leaving nine clocks before the 128-clock internal-sample deadline.
module parallel_pipelined_solver_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    solver_pnr_harness #(
        .PARALLEL_TUBES(1'b1),
        .PIPELINED_KCL_FINISH(1'b1),
        .PIPELINED_KCL_COLUMNS(1'b1),
        .PIPELINED_CHORD_APPLY(1'b1)
    ) harness (.*);

endmodule

// Add one registered column-contribution boundary to the 119-clock candidate.
// Four KCL calls make the resulting complete terminal latency 123 clocks.
module parallel_deep_pipelined_solver_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    solver_pnr_harness #(
        .PARALLEL_TUBES(1'b1),
        .PIPELINED_KCL_FINISH(1'b1),
        .PIPELINED_KCL_COLUMNS(1'b1),
        .PIPELINED_KCL_ACCUMULATOR(1'b1),
        .PIPELINED_CHORD_APPLY(1'b1)
    ) harness (.*);

endmodule

// Spend the final four clocks on capacitor rounding/history subtraction. The
// complete terminal solve uses the full 127-clock internal-sample budget.
module parallel_max_pipelined_solver_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    solver_pnr_harness #(
        .PARALLEL_TUBES(1'b1),
        .PIPELINED_KCL_FINISH(1'b1),
        .PIPELINED_KCL_COLUMNS(1'b1),
        .PIPELINED_KCL_ACCUMULATOR(1'b1),
        .PIPELINED_KCL_CAPACITOR_CURRENT(1'b1),
        .PIPELINED_CHORD_APPLY(1'b1)
    ) harness (.*);

endmodule

// Route-informed candidate: pipeline the exact maximum diagnostic only in the
// final KCL pass, and retain the accumulator split. Total latency is 126 clocks.
module parallel_diagnostic_pipelined_solver_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    solver_pnr_harness #(
        .PARALLEL_TUBES(1'b1),
        .PIPELINED_KCL_FINISH(1'b1),
        .PIPELINED_KCL_COLUMNS(1'b1),
        .PIPELINED_KCL_ACCUMULATOR(1'b1),
        .PIPELINED_KCL_MAXIMUM(1'b1),
        .PIPELINED_CHORD_APPLY(1'b1)
    ) harness (.*);

endmodule

// Reuse the terminal companion-current multipliers in two five-lane batches.
// The first batch overlaps the final chord preview, retaining the selected
// 126-clock contract while reducing simultaneous terminal hard blocks.
module parallel_shared_terminal_diagnostic_pipelined_solver_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    solver_pnr_harness #(
        .PARALLEL_TUBES(1'b1),
        .PIPELINED_KCL_FINISH(1'b1),
        .PIPELINED_KCL_COLUMNS(1'b1),
        .PIPELINED_KCL_ACCUMULATOR(1'b1),
        .PIPELINED_KCL_MAXIMUM(1'b1),
        .PIPELINED_CHORD_APPLY(1'b1),
        .HALF_PARALLEL_TERMINAL_CURRENT(1'b1)
    ) harness (.*);

endmodule

`default_nettype wire
