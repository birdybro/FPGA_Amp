`timescale 1ns/1ps
`default_nettype none

// Bidirectional stereo I2S bridge between a potentially asynchronous BCLK and
// fabric domain. Two independent asynchronous FIFOs preserve frame atomicity.
// This block performs no gain, channel mixing, or physical-unit calibration.
module i2s_async_bridge #(
    parameter int unsigned FIFO_ADDRESS_WIDTH = 3
) (
    input  logic                 i2s_bclk,
    input  logic                 i2s_rst_n,
    input  logic                 i2s_adc_lrclk,
    input  logic                 i2s_adc_serial_data,
    output logic                 i2s_dac_lrclk,
    output logic                 i2s_dac_serial_data,
    input  logic                 i2s_clear_diagnostics,

    input  logic                 fabric_clk,
    input  logic                 fabric_rst_n,
    output logic [63:0]          fabric_rx_frame_data,
    output logic                 fabric_rx_frame_valid,
    input  logic                 fabric_rx_frame_ready,
    input  logic [63:0]          fabric_tx_frame_data,
    input  logic                 fabric_tx_frame_valid,
    output logic                 fabric_tx_frame_ready,
    input  logic                 fabric_clear_diagnostics,

    output logic                 rx_frame_error_sticky,
    output logic                 rx_fifo_overflow_sticky,
    output logic                 rx_fifo_underflow_sticky,
    output logic                 tx_fifo_overflow_sticky,
    output logic                 tx_fifo_underflow_sticky,
    output logic                 tx_serial_underflow_sticky,

    // Local-domain occupancy estimates and watermarks. Write-side values may
    // conservatively lag reads high; read-side values may lag writes low.
    output logic [FIFO_ADDRESS_WIDTH:0] rx_fifo_i2s_level,
    output logic [FIFO_ADDRESS_WIDTH:0] rx_fifo_i2s_high_water,
    output logic [FIFO_ADDRESS_WIDTH:0] rx_fifo_fabric_level,
    output logic [FIFO_ADDRESS_WIDTH:0] rx_fifo_fabric_high_water,
    output logic [FIFO_ADDRESS_WIDTH:0] tx_fifo_fabric_level,
    output logic [FIFO_ADDRESS_WIDTH:0] tx_fifo_fabric_high_water,
    output logic [FIFO_ADDRESS_WIDTH:0] tx_fifo_i2s_level,
    output logic [FIFO_ADDRESS_WIDTH:0] tx_fifo_i2s_high_water
);

    logic [63:0] rx_serial_frame_data;
    logic rx_serial_frame_valid;
    // The serial source cannot be backpressured. Full is intentionally not a
    // flow-control input here; overflow_sticky records any lost ADC frame.
    /* verilator lint_off UNUSEDSIGNAL */
    logic rx_fifo_full;
    /* verilator lint_on UNUSEDSIGNAL */
    logic rx_fifo_empty;
    logic [63:0] rx_fifo_read_data;
    logic rx_fifo_read_enable;
    logic rx_fifo_read_valid;
    logic rx_fifo_read_pending;
    logic [63:0] rx_hold_data;
    logic rx_hold_valid;

    logic tx_fifo_full;
    logic tx_fifo_empty;
    logic [63:0] tx_fifo_read_data;
    logic tx_fifo_read_enable;
    logic tx_fifo_read_valid;
    logic tx_fifo_read_pending;
    logic tx_protocol_frame_ready;

    i2s_receiver receiver (
        .bclk(i2s_bclk),
        .rst_n(i2s_rst_n),
        .lrclk(i2s_adc_lrclk),
        .serial_data(i2s_adc_serial_data),
        .clear_frame_error(i2s_clear_diagnostics),
        .frame_data(rx_serial_frame_data),
        .frame_valid(rx_serial_frame_valid),
        .frame_error_sticky(rx_frame_error_sticky)
    );

    async_fifo #(
        .DATA_WIDTH(64),
        .ADDRESS_WIDTH(FIFO_ADDRESS_WIDTH)
    ) receive_fifo (
        .wr_clk(i2s_bclk),
        .wr_rst_n(i2s_rst_n),
        .wr_enable(rx_serial_frame_valid),
        .wr_data(rx_serial_frame_data),
        .wr_clear_overflow(i2s_clear_diagnostics),
        .wr_full(rx_fifo_full),
        .wr_overflow_sticky(rx_fifo_overflow_sticky),
        .wr_level(rx_fifo_i2s_level),
        .wr_high_water(rx_fifo_i2s_high_water),
        .rd_clk(fabric_clk),
        .rd_rst_n(fabric_rst_n),
        .rd_enable(rx_fifo_read_enable),
        .rd_data(rx_fifo_read_data),
        .rd_valid(rx_fifo_read_valid),
        .rd_clear_underflow(fabric_clear_diagnostics),
        .rd_empty(rx_fifo_empty),
        .rd_underflow_sticky(rx_fifo_underflow_sticky),
        .rd_level(rx_fifo_fabric_level),
        .rd_high_water(rx_fifo_fabric_high_water)
    );

    // Convert the FIFO's registered read pulse into a held ready/valid source.
    always_comb begin
        fabric_rx_frame_data = rx_hold_data;
        fabric_rx_frame_valid = rx_hold_valid;
        rx_fifo_read_enable =
            !rx_fifo_empty
            && !rx_fifo_read_pending
            && (!rx_hold_valid || fabric_rx_frame_ready);
    end

    always_ff @(posedge fabric_clk or negedge fabric_rst_n) begin
        if (!fabric_rst_n) begin
            rx_fifo_read_pending <= 1'b0;
            rx_hold_data <= '0;
            rx_hold_valid <= 1'b0;
        end else begin
            if (rx_hold_valid && fabric_rx_frame_ready)
                rx_hold_valid <= 1'b0;
            if (rx_fifo_read_enable)
                rx_fifo_read_pending <= 1'b1;
            if (rx_fifo_read_valid) begin
                rx_fifo_read_pending <= 1'b0;
                rx_hold_data <= rx_fifo_read_data;
                rx_hold_valid <= 1'b1;
            end
        end
    end

    always_comb begin
        fabric_tx_frame_ready = !tx_fifo_full;
        tx_fifo_read_enable =
            !tx_fifo_empty
            && !tx_fifo_read_pending
            && tx_protocol_frame_ready;
    end

    async_fifo #(
        .DATA_WIDTH(64),
        .ADDRESS_WIDTH(FIFO_ADDRESS_WIDTH)
    ) transmit_fifo (
        .wr_clk(fabric_clk),
        .wr_rst_n(fabric_rst_n),
        .wr_enable(fabric_tx_frame_valid),
        .wr_data(fabric_tx_frame_data),
        .wr_clear_overflow(fabric_clear_diagnostics),
        .wr_full(tx_fifo_full),
        .wr_overflow_sticky(tx_fifo_overflow_sticky),
        .wr_level(tx_fifo_fabric_level),
        .wr_high_water(tx_fifo_fabric_high_water),
        .rd_clk(i2s_bclk),
        .rd_rst_n(i2s_rst_n),
        .rd_enable(tx_fifo_read_enable),
        .rd_data(tx_fifo_read_data),
        .rd_valid(tx_fifo_read_valid),
        .rd_clear_underflow(i2s_clear_diagnostics),
        .rd_empty(tx_fifo_empty),
        .rd_underflow_sticky(tx_fifo_underflow_sticky),
        .rd_level(tx_fifo_i2s_level),
        .rd_high_water(tx_fifo_i2s_high_water)
    );

    always_ff @(posedge i2s_bclk or negedge i2s_rst_n) begin
        if (!i2s_rst_n) begin
            tx_fifo_read_pending <= 1'b0;
        end else begin
            if (tx_fifo_read_enable)
                tx_fifo_read_pending <= 1'b1;
            if (tx_fifo_read_valid)
                tx_fifo_read_pending <= 1'b0;
        end
    end

    i2s_transmitter transmitter (
        .bclk(i2s_bclk),
        .rst_n(i2s_rst_n),
        .frame_data(tx_fifo_read_data),
        .frame_valid(tx_fifo_read_valid),
        .frame_ready(tx_protocol_frame_ready),
        .clear_underflow(i2s_clear_diagnostics),
        .lrclk(i2s_dac_lrclk),
        .serial_data(i2s_dac_serial_data),
        .underflow_sticky(tx_serial_underflow_sticky)
    );

endmodule

`default_nettype wire
