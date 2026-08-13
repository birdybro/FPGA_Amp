`timescale 1ns/1ps
`default_nettype none

// Complete digital V1 reference stream at a 98.304 MHz fabric clock.
// Input and output are physical volts in signed Q8.24 at 48 kHz. The circuit
// runs at 768 kHz. Volume, mute, converter framing, and modern enhancements are
// intentionally outside this reference-mode boundary.
module phono_stream_mono (
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
    output logic [54:0]          solver_last_residual_q44,
    output logic [7:0]           solver_latency_cycles
);

    logic signed [31:0] interpolated_q24;
    logic interpolated_valid;
    logic [31:0] interpolation_saturation_count;
    logic [31:0] interpolation_overrun_count;

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

    logic signed [31:0] solver_output_q20;
    logic solver_output_valid;
    logic solver_busy;
    logic [287:0] unused_node_voltage_debug;
    logic [319:0] unused_capacitor_state_debug;

    v1_solver_mono solver (
        .clk,
        .rst_n,
        .ce_sample(interpolated_valid),
        .input_q24(interpolated_q24),
        .output_q20(solver_output_q20),
        .output_valid(solver_output_valid),
        .busy(solver_busy),
        .sample_latency_cycles(solver_latency_cycles),
        .missed_request_count(solver_missed_request_count),
        .deadline_miss_count(solver_deadline_miss_count),
        .saturation_count(solver_saturation_count),
        .lut_clip_count(solver_lut_clip_count),
        .nonconvergence_count(solver_nonconvergence_count),
        .last_residual_q44(solver_last_residual_q44),
        .node_voltage_debug(unused_node_voltage_debug),
        .capacitor_state_debug(unused_capacitor_state_debug)
    );

    logic signed [35:0] solver_output_q24_wide;
    logic signed [31:0] solver_output_q24;
    logic output_conversion_overflow;
    always_comb begin
        solver_output_q24_wide = $signed(solver_output_q20) <<< 4;
        output_conversion_overflow =
            (solver_output_q24_wide > 36'sd2147483647) ||
            (solver_output_q24_wide < -36'sd2147483648);
        if (solver_output_q24_wide > 36'sd2147483647)
            solver_output_q24 = 32'sh7fffffff;
        else if (solver_output_q24_wide < -36'sd2147483648)
            solver_output_q24 = 32'sh80000000;
        else
            solver_output_q24 = solver_output_q24_wide[31:0];
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            output_conversion_saturation_count <= '0;
        end else if (solver_output_valid && output_conversion_overflow) begin
            output_conversion_saturation_count <=
                output_conversion_saturation_count + 1'b1;
        end
    end

    logic [31:0] decimation_saturation_count;
    logic [31:0] decimation_overrun_count;
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

    always_comb begin
        resampler_saturation_count = interpolation_saturation_count +
                                     decimation_saturation_count;
        resampler_overrun_count = interpolation_overrun_count +
                                  decimation_overrun_count;
    end

    logic unused_solver_busy;
    always_comb unused_solver_busy = solver_busy;
endmodule

`default_nettype wire
