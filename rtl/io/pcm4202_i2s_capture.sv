`timescale 1ns/1ps
`default_nettype none

// Receive-only clock-domain bridge for the Rev-A PCM4202 contract:
// 24-bit Philips I2S, 64 BCK periods per channel, 128 BCK periods per stereo
// frame. The ADC is the 48 kHz BCK/LRCK master. The receive-only boundary is
// intentional: a DAC with 32-BCK slots uses a separate serial clock domain.
module pcm4202_i2s_capture #(
    parameter int unsigned FIFO_ADDRESS_WIDTH = 3
) (
    input  logic                          adc_bclk,
    input  logic                          adc_rst_n,
    input  logic                          adc_lrclk,
    input  logic                          adc_serial_data,
    input  logic                          adc_clear_diagnostics,

    input  logic                          fabric_clk,
    input  logic                          fabric_rst_n,
    output logic [63:0]                   fabric_frame_data,
    output logic                          fabric_frame_valid,
    input  logic                          fabric_frame_ready,
    input  logic                          fabric_clear_diagnostics,

    output logic                          frame_error_sticky,
    output logic                          fifo_overflow_sticky,
    output logic                          fifo_underflow_sticky,
    output logic [FIFO_ADDRESS_WIDTH:0]   fifo_adc_level,
    output logic [FIFO_ADDRESS_WIDTH:0]   fifo_adc_high_water,
    output logic [FIFO_ADDRESS_WIDTH:0]   fifo_fabric_level,
    output logic [FIFO_ADDRESS_WIDTH:0]   fifo_fabric_high_water
);

    logic [63:0] serial_frame_data;
    logic serial_frame_valid;
    /* verilator lint_off UNUSEDSIGNAL */
    logic fifo_full;
    /* verilator lint_on UNUSEDSIGNAL */
    logic fifo_empty;
    logic [63:0] fifo_read_data;
    logic fifo_read_enable;
    logic fifo_read_valid;
    logic fifo_read_pending;
    logic [63:0] held_frame_data;
    logic held_frame_valid;

    i2s_receiver #(
        .SAMPLE_WIDTH(24),
        .SLOT_WIDTH(64)
    ) receiver (
        .bclk(adc_bclk),
        .rst_n(adc_rst_n),
        .lrclk(adc_lrclk),
        .serial_data(adc_serial_data),
        .clear_frame_error(adc_clear_diagnostics),
        .frame_data(serial_frame_data),
        .frame_valid(serial_frame_valid),
        .frame_error_sticky(frame_error_sticky)
    );

    async_fifo #(
        .DATA_WIDTH(64),
        .ADDRESS_WIDTH(FIFO_ADDRESS_WIDTH)
    ) receive_fifo (
        .wr_clk(adc_bclk),
        .wr_rst_n(adc_rst_n),
        .wr_enable(serial_frame_valid),
        .wr_data(serial_frame_data),
        .wr_clear_overflow(adc_clear_diagnostics),
        .wr_full(fifo_full),
        .wr_overflow_sticky(fifo_overflow_sticky),
        .wr_level(fifo_adc_level),
        .wr_high_water(fifo_adc_high_water),
        .rd_clk(fabric_clk),
        .rd_rst_n(fabric_rst_n),
        .rd_enable(fifo_read_enable),
        .rd_data(fifo_read_data),
        .rd_valid(fifo_read_valid),
        .rd_clear_underflow(fabric_clear_diagnostics),
        .rd_empty(fifo_empty),
        .rd_underflow_sticky(fifo_underflow_sticky),
        .rd_level(fifo_fabric_level),
        .rd_high_water(fifo_fabric_high_water)
    );

    always_comb begin
        fabric_frame_data = held_frame_data;
        fabric_frame_valid = held_frame_valid;
        fifo_read_enable =
            !fifo_empty
            && !fifo_read_pending
            && (!held_frame_valid || fabric_frame_ready);
    end

    // Convert the FIFO's registered read pulse into a held ready/valid source.
    always_ff @(posedge fabric_clk or negedge fabric_rst_n) begin
        if (!fabric_rst_n) begin
            fifo_read_pending <= 1'b0;
            held_frame_data <= '0;
            held_frame_valid <= 1'b0;
        end else begin
            if (held_frame_valid && fabric_frame_ready)
                held_frame_valid <= 1'b0;
            if (fifo_read_enable)
                fifo_read_pending <= 1'b1;
            if (fifo_read_valid) begin
                fifo_read_pending <= 1'b0;
                held_frame_data <= fifo_read_data;
                held_frame_valid <= 1'b1;
            end
        end
    end

endmodule

`default_nettype wire
