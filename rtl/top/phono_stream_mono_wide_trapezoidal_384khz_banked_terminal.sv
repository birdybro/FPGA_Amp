`timescale 1ns/1ps
`default_nettype none

// Explicit non-reference 48 kHz stream candidate using three-stage 8x rate
// conversion and the exact 127-clock 384 kHz banked-terminal solver.
module phono_stream_mono_wide_trapezoidal_384khz_banked_terminal #(
    parameter int FABRIC_CLOCKS_PER_48K_INPUT = 2048,
    parameter bit PIPELINED_SOLVER_PROFILE = 1'b0,
    parameter bit PREFETCH_TUBE_INPUTS = 1'b0,
    parameter bit LATE_TUBE_INPUT_SELECT = 1'b0,
    parameter bit DECOUPLED_KCL_MAXIMUM_ONLY = 1'b0,
    parameter bit SERIAL_KCL_MAXIMUM_ONLY = 1'b0
) (
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
            "model/generated/v1_node_initial_wide_trapezoidal_384khz.mem"
        ),
        .CAP_INITIAL_FILE(
            "model/generated/v1_cap_initial_q30_wide_trapezoidal_384khz.mem"
        ),
        .CAP_CURRENT_INITIAL_FILE(
            "model/generated/v1_cap_current_initial_q4_44_trapezoidal_384khz.mem"
        ),
        .CAP_G_FILE(
            "model/generated/v1_cap_conductance_q0_47_trapezoidal_384khz.mem"
        ),
        .CHORD_COEFFICIENT_FILE(
            "model/generated/v1_chord_inverse_banked_q17_1_trapezoidal_384khz.mem"
        ),
        .CHORD_COEFFICIENT_SETS(5),
        .CHORD_COEFFICIENT_WIDTH(19),
        .SAMPLE_RATE_384KHZ(1'b1),
        .FABRIC_CLOCKS_PER_48K_INPUT(FABRIC_CLOCKS_PER_48K_INPUT),
        .TRAPEZOIDAL(1'b1),
        .TERMINAL_CORRECTION(1'b1),
        .PIPELINED_SOLVER_PROFILE(PIPELINED_SOLVER_PROFILE),
        .PREFETCH_TUBE_INPUTS(PREFETCH_TUBE_INPUTS),
        .LATE_TUBE_INPUT_SELECT(LATE_TUBE_INPUT_SELECT),
        .DECOUPLED_KCL_MAXIMUM_ONLY(DECOUPLED_KCL_MAXIMUM_ONLY),
        .SERIAL_KCL_MAXIMUM_ONLY(SERIAL_KCL_MAXIMUM_ONLY)
    ) core (.*);

endmodule

`default_nettype wire
