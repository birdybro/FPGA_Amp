`timescale 1ns/1ps
`default_nettype none

// Trapezoidal wide solver with five Vgk-selected chord banks and one terminal
// Q40 correction.  The final edge commits both corrected capacitor voltages
// and their recomputed Q4.44 companion-current histories in 127 clocks with
// one shared tube engine or 95 clocks with two parallel tube engines. Enabling
// all optional KCL/chord timing boundaries with parallel tubes takes 119 clocks.
module v1_solver_mono_wide_trapezoidal_banked_terminal #(
    parameter bit USE_LINEAR_FACTORIZED_TUBE = 1'b0,
    parameter bit PARALLEL_TUBES = 1'b0,
    parameter bit PIPELINED_KCL_FINISH = 1'b0,
    parameter bit PIPELINED_KCL_COLUMNS = 1'b0,
    parameter bit PIPELINED_KCL_ACCUMULATOR = 1'b0,
    parameter bit PIPELINED_KCL_CAPACITOR_CURRENT = 1'b0,
    parameter bit PIPELINED_KCL_MAXIMUM = 1'b0,
    parameter bit PIPELINED_CHORD_APPLY = 1'b0
) (
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
        .TERMINAL_CORRECTION(1'b1),
        .USE_LINEAR_FACTORIZED_TUBE(USE_LINEAR_FACTORIZED_TUBE),
        .PARALLEL_TUBES(PARALLEL_TUBES),
        .PIPELINED_KCL_FINISH(PIPELINED_KCL_FINISH),
        .PIPELINED_KCL_COLUMNS(PIPELINED_KCL_COLUMNS),
        .PIPELINED_KCL_ACCUMULATOR(PIPELINED_KCL_ACCUMULATOR),
        .PIPELINED_KCL_CAPACITOR_CURRENT(PIPELINED_KCL_CAPACITOR_CURRENT),
        .PIPELINED_KCL_MAXIMUM(PIPELINED_KCL_MAXIMUM),
        .PIPELINED_CHORD_APPLY(PIPELINED_CHORD_APPLY)
    ) core (.*);

endmodule

`default_nettype wire
