`timescale 1ns/1ps
`default_nettype none

// Convert Q8.24 physical volts into signed PCM24. The coefficient is the
// reciprocal DAC peak voltage, in Q8.24 per volt, and is supplied by the
// calibrated control plane. The precomputed reciprocal avoids hardware divide.
module q8_24_to_pcm24 (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 input_valid,
    input  logic signed [31:0]   sample_input_q24,
    input  logic signed [31:0]   reciprocal_full_scale_per_volt_q24,
    input  logic                 clear_diagnostics,
    output logic signed [23:0]   sample_output_pcm24,
    output logic                 output_valid,
    output logic [31:0]          saturation_count,
    output logic                 configuration_error_sticky
);

    // Q8.24 volts times Q8.24 reciprocal full scale produces a Q16.48
    // normalized fraction. Shift by 25 to form a signed Q0.23 PCM code.
    logic signed [63:0] scale_product;
    logic signed [63:0] rounded_product;
    logic signed [63:0] scaled_pcm_wide;
    logic signed [23:0] saturated_pcm24;
    logic output_saturated;
    logic coefficient_invalid;
    always_comb begin
        scale_product = $signed(sample_input_q24)
                        * $signed(reciprocal_full_scale_per_volt_q24);
        rounded_product = scale_product
            + ((scale_product < 0) ? 64'sd16777215 : 64'sd16777216);
        scaled_pcm_wide = rounded_product >>> 25;
        coefficient_invalid = reciprocal_full_scale_per_volt_q24 <= 0;
        output_saturated = (scaled_pcm_wide > 64'sd8388607)
                           || (scaled_pcm_wide < -64'sd8388608);
        if (scaled_pcm_wide > 64'sd8388607)
            saturated_pcm24 = 24'sh7fffff;
        else if (scaled_pcm_wide < -64'sd8388608)
            saturated_pcm24 = 24'sh800000;
        else
            saturated_pcm24 = scaled_pcm_wide[23:0];
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sample_output_pcm24 <= '0;
            output_valid <= 1'b0;
            saturation_count <= '0;
            configuration_error_sticky <= 1'b0;
        end else begin
            output_valid <= 1'b0;
            if (clear_diagnostics) begin
                saturation_count <= '0;
                configuration_error_sticky <= 1'b0;
            end else if (input_valid) begin
                if (!coefficient_invalid && output_saturated
                    && saturation_count != 32'hffffffff)
                    saturation_count <= saturation_count + 1'b1;
                if (coefficient_invalid)
                    configuration_error_sticky <= 1'b1;
            end

            if (input_valid) begin
                sample_output_pcm24 <= coefficient_invalid
                    ? 24'sd0 : saturated_pcm24;
                output_valid <= 1'b1;
            end
        end
    end

endmodule

`default_nettype wire
