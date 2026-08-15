`timescale 1ns/1ps
`default_nettype none

// Complete wide-state V1 reference stream. The external boundary stays signed
// Q8.24 at 48 kHz; the circuit output is rounded from Q8.32 before decimation.
module phono_stream_mono_wide #(
    parameter NODE_INITIAL_FILE = "model/generated/v1_node_initial_wide.mem",
    parameter CAP_INITIAL_FILE = "model/generated/v1_cap_initial_q30_wide.mem",
    parameter CAP_CURRENT_INITIAL_FILE =
        "model/generated/v1_cap_current_initial_q4_44_trapezoidal.mem",
    parameter CAP_G_FILE = "model/generated/v1_cap_conductance_q0_47.mem",
    parameter CHORD_COEFFICIENT_FILE =
        "model/generated/v1_chord_inverse_q17_1.mem",
    parameter integer CHORD_COEFFICIENT_SETS = 1,
    parameter integer CHORD_COEFFICIENT_WIDTH = 18,
    parameter bit SAMPLE_RATE_384KHZ = 1'b0,
    parameter int FABRIC_CLOCKS_PER_48K_INPUT = 2048,
    parameter bit TRAPEZOIDAL = 1'b0,
    parameter bit TERMINAL_CORRECTION = 1'b0,
    // Scheduling-only profile: duplicate the two physical triode evaluators
    // and enable the previously bit-exact registered KCL/chord boundaries.
    // The circuit equations and fixed-point operations are unchanged.
    parameter bit PIPELINED_SOLVER_PROFILE = 1'b0
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

    logic signed [31:0] interpolated_q24;
    logic interpolated_valid;
    logic [31:0] interpolation_saturation_count;
    logic [31:0] interpolation_overrun_count;

    generate
        if (SAMPLE_RATE_384KHZ) begin : generate_interpolator_8x
            interpolator_8x #(
                .FABRIC_CLOCKS_PER_48K_INPUT(
                    FABRIC_CLOCKS_PER_48K_INPUT
                )
            ) interpolator (
                .clk,
                .rst_n,
                .ce_input(ce_input_48k),
                .sample_input_q24,
                .sample_output_q24(interpolated_q24),
                .output_valid(interpolated_valid),
                .saturation_count(interpolation_saturation_count),
                .overrun_count(interpolation_overrun_count),
                .input_phase_error_count
            );
        end else begin : generate_interpolator_16x
            interpolator_16x interpolator (
                .clk,
                .rst_n,
                .ce_input(ce_input_48k),
                .sample_input_q24,
                .sample_output_q24(interpolated_q24),
                .output_valid(interpolated_valid),
                .saturation_count(interpolation_saturation_count),
                .overrun_count(interpolation_overrun_count),
                .input_phase_error_count
            );
        end
    endgenerate

    logic signed [39:0] solver_output_q32;
    logic solver_output_valid;
    logic solver_busy;
    logic [359:0] unused_node_voltage_debug;
    logic [399:0] unused_capacitor_state_debug;
    logic [479:0] unused_capacitor_current_state_debug;

    v1_solver_mono_wide #(
        .NODE_INITIAL_FILE(NODE_INITIAL_FILE),
        .CAP_INITIAL_FILE(CAP_INITIAL_FILE),
        .CAP_CURRENT_INITIAL_FILE(CAP_CURRENT_INITIAL_FILE),
        .CAP_G_FILE(CAP_G_FILE),
        .CHORD_COEFFICIENT_FILE(CHORD_COEFFICIENT_FILE),
        .CHORD_COEFFICIENT_SETS(CHORD_COEFFICIENT_SETS),
        .CHORD_COEFFICIENT_WIDTH(CHORD_COEFFICIENT_WIDTH),
        .SAMPLE_RATE_384KHZ(SAMPLE_RATE_384KHZ),
        .TRAPEZOIDAL(TRAPEZOIDAL),
        .TERMINAL_CORRECTION(TERMINAL_CORRECTION),
        .PARALLEL_TUBES(PIPELINED_SOLVER_PROFILE),
        .PIPELINED_KCL_FINISH(PIPELINED_SOLVER_PROFILE),
        .PIPELINED_KCL_COLUMNS(PIPELINED_SOLVER_PROFILE),
        .PIPELINED_KCL_ACCUMULATOR(PIPELINED_SOLVER_PROFILE),
        .PIPELINED_KCL_MAXIMUM(PIPELINED_SOLVER_PROFILE),
        .DECOUPLED_KCL_MAXIMUM(PIPELINED_SOLVER_PROFILE),
        .PIPELINED_CHORD_APPLY(PIPELINED_SOLVER_PROFILE)
    ) solver (
        .clk,
        .rst_n,
        .ce_sample(interpolated_valid),
        .input_q24(interpolated_q24),
        .output_q32(solver_output_q32),
        .output_valid(solver_output_valid),
        .busy(solver_busy),
        .sample_latency_cycles(solver_latency_cycles),
        .missed_request_count(solver_missed_request_count),
        .deadline_miss_count(solver_deadline_miss_count),
        .saturation_count(solver_saturation_count),
        .lut_clip_count(solver_lut_clip_count),
        .nonconvergence_count(solver_nonconvergence_count),
        .correction_scale_fallback_count(solver_correction_scale_fallback_count),
        .minimum_correction_fractional_bits(
            solver_minimum_correction_fractional_bits
        ),
        .last_residual_q44(solver_last_residual_q44),
        .node_voltage_debug(unused_node_voltage_debug),
        .capacitor_state_debug(unused_capacitor_state_debug),
        .capacitor_current_state_debug(unused_capacitor_current_state_debug)
    );

    logic signed [40:0] solver_output_biased;
    logic signed [40:0] solver_output_q24_wide;
    logic signed [31:0] solver_output_q24;
    logic output_conversion_overflow;
    always_comb begin
        solver_output_biased = $signed({solver_output_q32[39], solver_output_q32})
                               + 41'sd128;
        solver_output_q24_wide = solver_output_biased >>> 8;
        output_conversion_overflow =
            (solver_output_q24_wide > 41'sd2147483647)
            || (solver_output_q24_wide < -41'sd2147483648);
        if (solver_output_q24_wide > 41'sd2147483647)
            solver_output_q24 = 32'sh7fffffff;
        else if (solver_output_q24_wide < -41'sd2147483648)
            solver_output_q24 = 32'sh80000000;
        else
            solver_output_q24 = solver_output_q24_wide[31:0];
    end

    always_ff @(posedge clk) begin
        if (!rst_n)
            output_conversion_saturation_count <= '0;
        else if (solver_output_valid && output_conversion_overflow)
            output_conversion_saturation_count <=
                output_conversion_saturation_count + 1'b1;
    end

    logic [31:0] decimation_saturation_count;
    logic [31:0] decimation_overrun_count;
    generate
        if (SAMPLE_RATE_384KHZ) begin : generate_decimator_8x
            decimator_8x decimator (
                .clk,
                .rst_n,
                .ce_input(solver_output_valid),
                .sample_input_q24(solver_output_q24),
                .sample_output_q24,
                .output_valid,
                .saturation_count(decimation_saturation_count),
                .overrun_count(decimation_overrun_count)
            );
        end else begin : generate_decimator_16x
            decimator_16x decimator (
                .clk,
                .rst_n,
                .ce_input(solver_output_valid),
                .sample_input_q24(solver_output_q24),
                .sample_output_q24,
                .output_valid,
                .saturation_count(decimation_saturation_count),
                .overrun_count(decimation_overrun_count)
            );
        end
    endgenerate

    always_comb begin
        resampler_saturation_count = interpolation_saturation_count
                                     + decimation_saturation_count;
        resampler_overrun_count = interpolation_overrun_count
                                  + decimation_overrun_count;
    end

    logic unused_solver_busy;
    always_comb unused_solver_busy = solver_busy;
endmodule

`default_nettype wire
