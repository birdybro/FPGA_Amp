`timescale 1ns/1ps
`default_nettype none

// Glue for codecs, including the Nexys Video ADAU1761, that use one LRCLK for
// both ADC and DAC directions. The codec-ready bit crosses into BCLK before it
// can release DAC serial data; reset and incomplete initialization force zero.
module codec_shared_i2s_guard (
    input  logic bclk,
    input  logic rst_n,
    input  logic codec_configured,

    input  logic digital_dac_lrclk,
    input  logic digital_dac_serial_data,
    output logic digital_adc_lrclk,
    output logic digital_adc_serial_data,

    output logic codec_lrclk,
    output logic codec_dac_serial_data,
    input  logic codec_adc_serial_data,
    output logic codec_ready_bclk,
    output logic codec_transport_rst_n
);

    (* ASYNC_REG = "TRUE" *) logic [1:0] ready_pipeline;

    always_ff @(posedge bclk or negedge rst_n) begin
        if (!rst_n)
            ready_pipeline <= '0;
        else
            ready_pipeline <= {ready_pipeline[0], codec_configured};
    end

    always_comb begin
        codec_ready_bclk = ready_pipeline[1];
        // Hold the receiver/transmitter and both serial-side FIFO ports reset
        // until the codec can produce defined frames.  Deassertion is already
        // synchronous to BCLK because it comes from the second ready stage.
        codec_transport_rst_n = rst_n && codec_ready_bclk;
        codec_lrclk = digital_dac_lrclk;
        digital_adc_lrclk = digital_dac_lrclk;
        digital_adc_serial_data = codec_adc_serial_data;
        codec_dac_serial_data =
            codec_ready_bclk ? digital_dac_serial_data : 1'b0;
    end

endmodule

`default_nettype wire
