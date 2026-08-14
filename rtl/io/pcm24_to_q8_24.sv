`timescale 1ns/1ps
`default_nettype none

// Convert signed PCM24 codes into the Q8.24 physical volts consumed by the
// circuit core. The coefficient is the physical input peak voltage at the
// negative PCM full-scale magnitude, also in Q8.24. It must be positive and
// stable in this clock domain while input_valid is asserted.
module pcm24_to_q8_24 (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 input_valid,
    input  logic signed [23:0]   sample_input_pcm24,
    input  logic signed [31:0]   full_scale_peak_volts_q24,
    input  logic                 clear_diagnostics,
    output logic signed [31:0]   sample_output_q24,
    output logic                 output_valid,
    output logic [31:0]          pcm_endpoint_count,
    output logic                 configuration_error_sticky
);

    // Signed 24 x signed 32 preserves the complete 56-bit product. Rescaling
    // by 2^23 uses round-to-nearest with exact ties away from zero. For a
    // positive signed-32 coefficient, the shifted result is provably signed-32.
    logic signed [55:0] scale_product;
    logic signed [55:0] rounded_product;
    logic signed [31:0] scaled_q24;
    logic coefficient_invalid;
    logic pcm_endpoint;
    always_comb begin
        scale_product = $signed(sample_input_pcm24)
                        * $signed(full_scale_peak_volts_q24);
        rounded_product = scale_product
            + ((scale_product < 0) ? 56'sd4194303 : 56'sd4194304);
        // The explicit cast consumes the proven sign-extension bits; there is
        // no implicit truncation at this physical-unit boundary.
        scaled_q24 = 32'($signed(rounded_product >>> 23));
        coefficient_invalid = full_scale_peak_volts_q24 <= 0;
        pcm_endpoint = (sample_input_pcm24 == 24'sh7fffff)
                       || (sample_input_pcm24 == 24'sh800000);
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sample_output_q24 <= '0;
            output_valid <= 1'b0;
            pcm_endpoint_count <= '0;
            configuration_error_sticky <= 1'b0;
        end else begin
            output_valid <= 1'b0;
            if (clear_diagnostics) begin
                pcm_endpoint_count <= '0;
                configuration_error_sticky <= 1'b0;
            end else if (input_valid) begin
                if (pcm_endpoint && pcm_endpoint_count != 32'hffffffff)
                    pcm_endpoint_count <= pcm_endpoint_count + 1'b1;
                if (coefficient_invalid)
                    configuration_error_sticky <= 1'b1;
            end

            if (input_valid) begin
                sample_output_q24 <= coefficient_invalid
                    ? 32'sd0 : scaled_q24;
                output_valid <= 1'b1;
            end
        end
    end

endmodule

`default_nettype wire
