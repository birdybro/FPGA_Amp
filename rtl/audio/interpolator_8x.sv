`timescale 1ns/1ps
`default_nettype none

// Three-stage 48 kHz to 384 kHz Q8.24 architecture candidate at a 98.304 MHz
// fabric clock. ce_input occurs once every 2048 clocks at phase zero. This is
// separate from the four-stage 16x reference path so selecting it is explicit.
module interpolator_8x (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 ce_input,
    input  logic signed [31:0]   sample_input_q24,
    output logic signed [31:0]   sample_output_q24,
    output logic                 output_valid,
    output logic [31:0]          saturation_count,
    output logic [31:0]          overrun_count,
    output logic [31:0]          input_phase_error_count
);

    logic [10:0] phase_counter;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            phase_counter <= '0;
            input_phase_error_count <= '0;
        end else begin
            phase_counter <= phase_counter + 1'b1;
            if (ce_input && (phase_counter != 11'd0))
                input_phase_error_count <= input_phase_error_count + 1'b1;
        end
    end

    logic ce_stage1_output;
    logic ce_stage2_output;
    logic ce_stage3_output;
    always_comb begin
        ce_stage1_output = phase_counter[9:0] == 10'd0;
        ce_stage2_output = phase_counter[8:0] == 9'd64;
        ce_stage3_output = phase_counter[7:0] == 8'd128;
    end

    logic signed [31:0] stage1_sample;
    logic signed [31:0] stage2_sample;
    logic stage1_valid;
    logic stage2_valid;
    logic stage1_busy;
    logic stage2_busy;
    logic stage3_busy;
    logic [31:0] saturation [0:2];
    logic [31:0] overrun [0:2];

    halfband_interpolator_2x #(
        .TAPS(79),
        .COEFFICIENT_FILE("model/generated/halfband_stage1_q1_23.mem")
    ) stage1 (
        .clk,
        .rst_n,
        .ce_input,
        .ce_output(ce_stage1_output),
        .sample_input_q24,
        .sample_output_q24(stage1_sample),
        .output_valid(stage1_valid),
        .busy(stage1_busy),
        .saturation_count(saturation[0]),
        .overrun_count(overrun[0])
    );

    halfband_interpolator_2x #(
        .TAPS(31),
        .COEFFICIENT_FILE("model/generated/halfband_stage2_q1_23.mem")
    ) stage2 (
        .clk,
        .rst_n,
        .ce_input(stage1_valid),
        .ce_output(ce_stage2_output),
        .sample_input_q24(stage1_sample),
        .sample_output_q24(stage2_sample),
        .output_valid(stage2_valid),
        .busy(stage2_busy),
        .saturation_count(saturation[1]),
        .overrun_count(overrun[1])
    );

    halfband_interpolator_2x #(
        .TAPS(19),
        .COEFFICIENT_FILE("model/generated/halfband_stage3_q1_23.mem")
    ) stage3 (
        .clk,
        .rst_n,
        .ce_input(stage2_valid),
        .ce_output(ce_stage3_output),
        .sample_input_q24(stage2_sample),
        .sample_output_q24,
        .output_valid,
        .busy(stage3_busy),
        .saturation_count(saturation[2]),
        .overrun_count(overrun[2])
    );

    always_comb begin
        saturation_count = saturation[0] + saturation[1] + saturation[2];
        overrun_count = overrun[0] + overrun[1] + overrun[2];
    end

    logic unused_busy;
    always_comb unused_busy = stage1_busy || stage2_busy || stage3_busy;
endmodule

`default_nettype wire
