`timescale 1ns/1ps
`default_nettype none

// System-safety output ramp, deliberately outside the historical model core.
// `mute_request` ramps toward silence at valid-sample boundaries. `force_mute`
// synchronously zeros the output and ramp state for fault/shutdown handling.
module output_mute_ramp #(
    parameter int unsigned RAMP_SAMPLES = 2048
) (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 sample_valid,
    input  logic signed [31:0]   sample_input_q24,
    input  logic                 mute_request,
    input  logic                 force_mute,
    output logic signed [31:0]   sample_output_q24,
    output logic                 output_valid,
    output logic [15:0]          gain_q16,
    output logic                 muted,
    output logic                 ramping
);

    localparam int unsigned GAIN_MAX = 32'd65535;
    localparam int unsigned GAIN_STEP =
        (GAIN_MAX + RAMP_SAMPLES - 1) / RAMP_SAMPLES;

    initial begin
        if (RAMP_SAMPLES == 0)
            $error("RAMP_SAMPLES must be nonzero");
        if (GAIN_STEP == 0 || GAIN_STEP > GAIN_MAX)
            $error("RAMP_SAMPLES produces an unsupported Q0.16 gain step");
    end

    function automatic logic [15:0] next_gain(
        input logic [15:0] current,
        input logic requested_mute
    );
        logic [31:0] current_wide;
        logic [31:0] changed;
        begin
            current_wide = {16'd0, current};
            changed = 32'd0;
            if (requested_mute) begin
                if (current_wide <= GAIN_STEP)
                    next_gain = 16'd0;
                else begin
                    changed = current_wide - GAIN_STEP;
                    next_gain = changed[15:0];
                end
            end else begin
                changed = current_wide + GAIN_STEP;
                if (changed >= GAIN_MAX)
                    next_gain = 16'hffff;
                else
                    next_gain = changed[15:0];
            end
        end
    endfunction

    // The positive Q0.16 operand is widened with a zero sign bit.  Preserve the
    // complete 32 x 17-bit signed product before the documented symmetric
    // round-to-nearest (ties away from zero) shift.
    logic signed [48:0] gain_product;
    // Bits discarded by the Q0.16 rescale are intentionally consumed by the
    // documented rounding operation; the sign-extension bit proves range.
    /* verilator lint_off UNUSEDSIGNAL */
    logic signed [48:0] rounded_product;
    /* verilator lint_on UNUSEDSIGNAL */
    logic signed [31:0] scaled_sample;
    always_comb begin
        gain_product = $signed(sample_input_q24) * $signed({1'b0, gain_q16});
        rounded_product = gain_product
            + ((gain_product < 0) ? 49'sd32767 : 49'sd32768);
        scaled_sample = rounded_product[47:16];
        muted = (gain_q16 == 16'd0);
        ramping = mute_request ? (gain_q16 != 16'd0) : (gain_q16 != 16'hffff);
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sample_output_q24 <= '0;
            output_valid <= 1'b0;
            gain_q16 <= '0;
        end else begin
            output_valid <= 1'b0;
            if (force_mute) begin
                gain_q16 <= '0;
                sample_output_q24 <= '0;
                if (sample_valid) begin
                    output_valid <= 1'b1;
                end
            end else if (sample_valid) begin
                // Full scale bypasses multiply quantization exactly.
                if (gain_q16 == 16'hffff)
                    sample_output_q24 <= sample_input_q24;
                else if (gain_q16 == 16'd0)
                    sample_output_q24 <= '0;
                else
                    sample_output_q24 <= scaled_sample;
                output_valid <= 1'b1;
                gain_q16 <= next_gain(gain_q16, mute_request);
            end
        end
    end

endmodule

`default_nettype wire
