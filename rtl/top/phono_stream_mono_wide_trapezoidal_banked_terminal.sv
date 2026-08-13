`timescale 1ns/1ps
`default_nettype none

// Complete 48 kHz stream using the exact 127-clock trapezoidal banked terminal
// solver, including corrected companion-current history on the terminal edge.
module phono_stream_mono_wide_trapezoidal_banked_terminal (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 ce_input_48k,
    input  logic signed [31:0]   sample_input_q24,
    output logic signed [31:0]   sample_output_q24,
    output logic                 output_valid,
    output logic [31:0]          resampler_saturation_count,
    output logic [31:0]          resampler_overrun_count,
    output logic [31:0]          input_phase_error_count,
    output logic [31:0]          output_conversion_saturation_count,
    output logic [31:0]          solver_missed_request_count,
    output logic [31:0]          solver_deadline_miss_count,
    output logic [31:0]          solver_saturation_count,
    output logic [31:0]          solver_lut_clip_count,
    output logic [31:0]          solver_nonconvergence_count,
    output logic [31:0]          solver_correction_scale_fallback_count,
    output logic [5:0]           solver_minimum_correction_fractional_bits,
    output logic [62:0]          solver_last_residual_q44,
    output logic [7:0]           solver_latency_cycles
);

    phono_stream_mono_wide #(
        .NODE_INITIAL_FILE(
            "model/generated/v1_node_initial_wide_trapezoidal.mem"
        ),
        .CAP_INITIAL_FILE(
            "model/generated/v1_cap_initial_q30_wide_trapezoidal.mem"
        ),
        .CAP_CURRENT_INITIAL_FILE(
            "model/generated/v1_cap_current_initial_q4_44_trapezoidal.mem"
        ),
        .CAP_G_FILE(
            "model/generated/v1_cap_conductance_q0_47_trapezoidal.mem"
        ),
        .CHORD_COEFFICIENT_FILE(
            "model/generated/v1_chord_inverse_banked_q17_1_trapezoidal.mem"
        ),
        .CHORD_COEFFICIENT_SETS(5),
        .TRAPEZOIDAL(1'b1),
        .TERMINAL_CORRECTION(1'b1)
    ) core (.*);

endmodule

`default_nettype wire
