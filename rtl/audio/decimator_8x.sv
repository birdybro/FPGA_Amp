`timescale 1ns/1ps
`default_nettype none

// Three-stage 384 kHz to 48 kHz Q8.24 architecture candidate. Downstream
// stages are enabled by valid pulses; no derived fabric clocks are used.
module decimator_8x (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 ce_input,
    input  logic signed [31:0]   sample_input_q24,
    output logic signed [31:0]   sample_output_q24,
    output logic                 output_valid,
    output logic [31:0]          saturation_count,
    output logic [31:0]          overrun_count
);

    logic signed [31:0] stage3_sample;
    logic signed [31:0] stage2_sample;
    logic stage3_valid;
    logic stage2_valid;
    logic stage3_busy;
    logic stage2_busy;
    logic stage1_busy;
    logic [31:0] saturation [0:2];
    logic [31:0] overrun [0:2];

    halfband_decimator_2x #(
        .TAPS(19),
        .COEFFICIENT_FILE("model/generated/halfband_stage3_q1_23.mem")
    ) stage3 (
        .clk,
        .rst_n,
        .ce_input,
        .sample_input_q24,
        .sample_output_q24(stage3_sample),
        .output_valid(stage3_valid),
        .busy(stage3_busy),
        .saturation_count(saturation[2]),
        .overrun_count(overrun[2])
    );

    halfband_decimator_2x #(
        .TAPS(31),
        .COEFFICIENT_FILE("model/generated/halfband_stage2_q1_23.mem")
    ) stage2 (
        .clk,
        .rst_n,
        .ce_input(stage3_valid),
        .sample_input_q24(stage3_sample),
        .sample_output_q24(stage2_sample),
        .output_valid(stage2_valid),
        .busy(stage2_busy),
        .saturation_count(saturation[1]),
        .overrun_count(overrun[1])
    );

    halfband_decimator_2x #(
        .TAPS(79),
        .COEFFICIENT_FILE("model/generated/halfband_stage1_q1_23.mem")
    ) stage1 (
        .clk,
        .rst_n,
        .ce_input(stage2_valid),
        .sample_input_q24(stage2_sample),
        .sample_output_q24,
        .output_valid,
        .busy(stage1_busy),
        .saturation_count(saturation[0]),
        .overrun_count(overrun[0])
    );

    always_comb begin
        saturation_count = saturation[0] + saturation[1] + saturation[2];
        overrun_count = overrun[0] + overrun[1] + overrun[2];
    end

    logic unused_busy;
    always_comb unused_busy = stage1_busy || stage2_busy || stage3_busy;
endmodule

`default_nettype wire
