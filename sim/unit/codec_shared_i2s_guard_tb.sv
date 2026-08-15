`timescale 1ns/1ps
`default_nettype none

module codec_shared_i2s_guard_tb;

    /* verilator lint_off PROCASSINIT */
    logic bclk = 1'b0;
    logic rst_n = 1'b0;
    logic codec_configured = 1'b0;
    logic digital_dac_lrclk = 1'b0;
    logic digital_dac_serial_data = 1'b1;
    logic digital_adc_lrclk;
    logic digital_adc_serial_data;
    logic codec_lrclk;
    logic codec_dac_serial_data;
    logic codec_adc_serial_data = 1'b1;
    logic codec_ready_bclk;
    logic codec_transport_rst_n;

    always #5 bclk = !bclk;

    codec_shared_i2s_guard dut (.*);

    initial begin
        #2;
        if (codec_dac_serial_data || codec_ready_bclk
            || codec_transport_rst_n)
            $fatal(1, "reset did not force zero DAC data");
        if (digital_adc_serial_data !== 1'b1)
            $fatal(1, "ADC serial data did not pass through");

        digital_dac_lrclk = 1'b1;
        #1;
        if (!codec_lrclk || !digital_adc_lrclk)
            $fatal(1, "shared LRCLK was not identical in both directions");

        rst_n = 1'b1;
        codec_configured = 1'b1;
        @(posedge bclk);
        #1;
        if (codec_ready_bclk || codec_dac_serial_data
            || codec_transport_rst_n)
            $fatal(1, "DAC data released before two BCLK synchronizer edges");
        @(posedge bclk);
        #1;
        if (!codec_ready_bclk || !codec_dac_serial_data
            || !codec_transport_rst_n)
            $fatal(1, "configured DAC data was not released");

        digital_dac_serial_data = 1'b0;
        #1;
        if (codec_dac_serial_data)
            $fatal(1, "released DAC data did not follow digital source");

        rst_n = 1'b0;
        #1;
        digital_dac_serial_data = 1'b1;
        if (codec_ready_bclk || codec_dac_serial_data
            || codec_transport_rst_n)
            $fatal(1, "asynchronous reset did not immediately force zero");

        $display("PASS shared I2S guard: LRCLK, data, and transport reset gate");
        $finish;
    end

    /* verilator lint_on PROCASSINIT */

endmodule

`default_nettype wire
