`timescale 1ns/1ps
`default_nettype none

// Stereo master attenuation outside the historical model. Gain is unsigned
// Q0.31: 0x00000000 is silence and 0x7fffffff is exact unity. A target commit
// computes a power-of-two-duration linear-gain slew without hardware division.
module master_volume_ramp #(
    parameter int unsigned SLEW_SHIFT = 10
) (
    input  logic                 clk,
    input  logic                 rst_n,

    input  logic                 sample_valid,
    input  logic signed [31:0]   sample_left_q24,
    input  logic signed [31:0]   sample_right_q24,
    output logic                 output_valid,
    output logic signed [31:0]   output_left_q24,
    output logic signed [31:0]   output_right_q24,

    input  logic                 target_valid,
    input  logic [31:0]          target_gain_q31,
    output logic                 target_accepted,
    input  logic                 diagnostic_clear,

    output logic [30:0]          active_gain_q31,
    output logic [30:0]          active_target_q31,
    output logic                 ramping,
    output logic                 invalid_target_sticky
);

    localparam logic [30:0] UNITY_GAIN_Q31 = 31'h7fffffff;
    localparam logic signed [63:0] POSITIVE_ROUND_BIAS = 64'sd1073741824;
    localparam logic signed [63:0] NEGATIVE_ROUND_BIAS = 64'sd1073741823;

    initial begin
        if (SLEW_SHIFT == 0 || SLEW_SHIFT > 30)
            $error("SLEW_SHIFT must be in the range 1..30");
    end

    function automatic logic [30:0] step_for_delta(
        input logic [30:0] delta
    );
        logic [31:0] rounded_delta;
        logic [31:0] bias;
        begin
            bias = (32'd1 << SLEW_SHIFT) - 1;
            rounded_delta = {1'b0, delta} + bias;
            // SLEW_SHIFT >= 1 proves the rounded maximum fits 31 bits.
            step_for_delta = 31'(rounded_delta >> SLEW_SHIFT);
        end
    endfunction

    function automatic logic [30:0] next_gain(
        input logic [30:0] current,
        input logic [30:0] target,
        input logic [30:0] step
    );
        logic [30:0] changed;
        logic [30:0] delta;
        begin
            next_gain = current;
            if (current < target) begin
                delta = target - current;
                if (delta <= step)
                    next_gain = target;
                else begin
                    // delta > step proves current + step remains below target.
                    changed = current + step;
                    next_gain = changed;
                end
            end else if (current > target) begin
                delta = current - target;
                if (delta <= step)
                    next_gain = target;
                else
                    next_gain = current - step;
            end
        end
    endfunction

    logic [30:0] slew_step_q31;
    logic [30:0] commit_delta;

    always_comb begin
        if (target_gain_q31[30:0] >= active_gain_q31)
            commit_delta = target_gain_q31[30:0] - active_gain_q31;
        else
            commit_delta = active_gain_q31 - target_gain_q31[30:0];
        ramping = (active_gain_q31 != active_target_q31);
    end

    logic signed [63:0] left_product;
    logic signed [63:0] right_product;
    /* verilator lint_off UNUSEDSIGNAL */
    logic signed [63:0] left_rounded;
    logic signed [63:0] right_rounded;
    /* verilator lint_on UNUSEDSIGNAL */
    logic signed [31:0] left_scaled;
    logic signed [31:0] right_scaled;

    always_comb begin
        left_product = $signed(sample_left_q24) * $signed({1'b0, active_gain_q31});
        right_product = $signed(sample_right_q24) * $signed({1'b0, active_gain_q31});
        left_rounded = left_product
            + ((left_product < 0) ? NEGATIVE_ROUND_BIAS : POSITIVE_ROUND_BIAS);
        right_rounded = right_product
            + ((right_product < 0) ? NEGATIVE_ROUND_BIAS : POSITIVE_ROUND_BIAS);
        left_scaled = left_rounded[62:31];
        right_scaled = right_rounded[62:31];
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            output_valid <= 1'b0;
            output_left_q24 <= '0;
            output_right_q24 <= '0;
            target_accepted <= 1'b0;
            active_gain_q31 <= '0;
            active_target_q31 <= '0;
            slew_step_q31 <= '0;
            invalid_target_sticky <= 1'b0;
        end else begin
            output_valid <= 1'b0;
            target_accepted <= 1'b0;

            if (diagnostic_clear)
                invalid_target_sticky <= 1'b0;

            if (target_valid) begin
                if (target_gain_q31[31]) begin
                    invalid_target_sticky <= 1'b1;
                end else begin
                    active_target_q31 <= target_gain_q31[30:0];
                    slew_step_q31 <= step_for_delta(commit_delta);
                    target_accepted <= 1'b1;
                end
            end

            if (sample_valid) begin
                output_valid <= 1'b1;
                if (active_gain_q31 == 31'd0) begin
                    output_left_q24 <= '0;
                    output_right_q24 <= '0;
                end else if (active_gain_q31 == UNITY_GAIN_Q31) begin
                    // Unity must preserve the reference stream bit exactly.
                    output_left_q24 <= sample_left_q24;
                    output_right_q24 <= sample_right_q24;
                end else begin
                    output_left_q24 <= left_scaled;
                    output_right_q24 <= right_scaled;
                end
                active_gain_q31 <= next_gain(
                    active_gain_q31,
                    active_target_q31,
                    slew_step_q31
                );
            end
        end
    end

endmodule

`default_nettype wire
