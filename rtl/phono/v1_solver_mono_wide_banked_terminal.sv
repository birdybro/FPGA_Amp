`timescale 1ns/1ps
`default_nettype none

// Backward-Euler banked solver with one terminal Q40 chord correction.
// The correction reuses the three-pass diagnostic residual, commits at 127
// clocks, and intentionally reports convergence for the preterminal state.
module v1_solver_mono_wide_banked_terminal (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  ce_sample,
    input  logic signed [31:0]    input_q24,
    output logic signed [39:0]    output_q32,
    output logic                  output_valid,
    output logic                  busy,
    output logic [7:0]            sample_latency_cycles,
    output logic [31:0]           missed_request_count,
    output logic [31:0]           deadline_miss_count,
    output logic [31:0]           saturation_count,
    output logic [31:0]           lut_clip_count,
    output logic [31:0]           nonconvergence_count,
    output logic [31:0]           correction_scale_fallback_count,
    output logic [5:0]            minimum_correction_fractional_bits,
    output logic [62:0]           last_residual_q44,
    output logic [359:0]          node_voltage_debug,
    output logic [399:0]          capacitor_state_debug,
    output logic [479:0]          capacitor_current_state_debug
);

    v1_solver_mono_wide #(
        .CHORD_COEFFICIENT_FILE(
            "model/generated/v1_chord_inverse_banked_q17_1.mem"
        ),
        .CHORD_COEFFICIENT_SETS(4),
        .TERMINAL_CORRECTION(1'b1)
    ) core (.*);

endmodule

`default_nettype wire
