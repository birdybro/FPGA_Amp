`default_nettype none

module audio_sample_calibration_formal (
    input logic clk,
    output logic [31:0] pcm_endpoint_count,
    output logic [31:0] saturation_count,
    output logic input_configuration_error_sticky,
    output logic output_configuration_error_sticky
);
    (* anyseq *) logic rst_n;
    (* anyseq *) logic input_valid;
    (* anyseq *) logic signed [23:0] sample_input_pcm24;
    (* anyseq *) logic signed [31:0] full_scale_peak_volts_q24;
    (* anyseq *) logic clear_input_diagnostics;
    (* anyseq *) logic output_input_valid;
    (* anyseq *) logic signed [31:0] sample_input_q24;
    (* anyseq *) logic signed [31:0] reciprocal_full_scale_per_volt_q24;
    (* anyseq *) logic clear_output_diagnostics;

    logic signed [31:0] sample_output_q24;
    logic input_output_valid;
    logic signed [23:0] sample_output_pcm24;
    logic output_output_valid;
    logic past_valid = 1'b0;

    always_ff @(posedge clk) begin
        if (!past_valid)
            assume (!rst_n);
        else
            assume (rst_n);
        past_valid <= 1'b1;
    end

    pcm24_to_q8_24 input_calibration (
        .clk,
        .rst_n,
        .input_valid,
        .sample_input_pcm24,
        .full_scale_peak_volts_q24,
        .clear_diagnostics(clear_input_diagnostics),
        .sample_output_q24,
        .output_valid(input_output_valid),
        .pcm_endpoint_count,
        .configuration_error_sticky(
            input_configuration_error_sticky
        )
    );

    q8_24_to_pcm24 output_calibration (
        .clk,
        .rst_n,
        .input_valid(output_input_valid),
        .sample_input_q24,
        .reciprocal_full_scale_per_volt_q24,
        .clear_diagnostics(clear_output_diagnostics),
        .sample_output_pcm24,
        .output_valid(output_output_valid),
        .saturation_count,
        .configuration_error_sticky(
            output_configuration_error_sticky
        )
    );

endmodule

`default_nettype wire
