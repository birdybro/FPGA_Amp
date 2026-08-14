`timescale 1ns/1ps
`default_nettype none

// I2S transmitter for two sign-extended samples packed {left[31:0],right[31:0]}.
// LRCLK and serial data change only on BCLK falling edges. The LRCLK transition
// occurs one complete BCLK before the first sample bit, as required by I2S.
module i2s_transmitter #(
    parameter int unsigned SAMPLE_WIDTH = 24,
    parameter int unsigned SLOT_WIDTH = 32
) (
    input  logic                 bclk,
    input  logic                 rst_n,
    input  logic [63:0]          frame_data,
    input  logic                 frame_valid,
    output logic                 frame_ready,
    input  logic                 clear_underflow,
    output logic                 lrclk,
    output logic                 serial_data,
    output logic                 underflow_sticky
);

    localparam int unsigned SLOT_COUNT_WIDTH = $clog2(SLOT_WIDTH);

    initial begin
        if (SAMPLE_WIDTH < 2 || SAMPLE_WIDTH > 32)
            $error("SAMPLE_WIDTH must be within 2..32");
        if (SLOT_WIDTH < SAMPLE_WIDTH + 1)
            $error("SLOT_WIDTH must include the I2S delay plus sample bits");
        if ((1 << SLOT_COUNT_WIDTH) != SLOT_WIDTH)
            $error("SLOT_WIDTH must be a power of two");
    end

    logic [SLOT_COUNT_WIDTH-1:0] slot_position;
    logic channel_right;
    logic [63:0] active_frame;
    logic [63:0] pending_frame;
    logic pending_valid;
    logic entering_left_slot;
    logic [5:0] serial_bit_index;

    always_comb begin
        frame_ready = !pending_valid;
        entering_left_slot =
            slot_position == SLOT_COUNT_WIDTH'(SLOT_WIDTH - 1)
            && channel_right;
        serial_bit_index = 6'(SAMPLE_WIDTH - 1) - slot_position;
    end

    always_ff @(negedge bclk or negedge rst_n) begin
        if (!rst_n) begin
            // Begin one edge before a left slot so the first active edge emits
            // the LRCLK transition/delay interval.
            slot_position <= SLOT_COUNT_WIDTH'(SLOT_WIDTH - 1);
            channel_right <= 1'b1;
            lrclk <= 1'b1;
            serial_data <= 1'b0;
            active_frame <= '0;
            pending_frame <= '0;
            pending_valid <= 1'b0;
            underflow_sticky <= 1'b0;
        end else begin
            if (clear_underflow)
                underflow_sticky <= 1'b0;

            if (frame_valid && frame_ready) begin
                pending_frame <= frame_data;
                pending_valid <= 1'b1;
            end

            if (slot_position == SLOT_COUNT_WIDTH'(SLOT_WIDTH - 1)) begin
                // This edge is the one-bit delay interval. Toggle LRCLK now;
                // position zero emits the MSB on the next falling edge.
                slot_position <= '0;
                channel_right <= !channel_right;
                lrclk <= !channel_right;
                serial_data <= 1'b0;
                if (entering_left_slot) begin
                    if (pending_valid) begin
                        active_frame <= pending_frame;
                        pending_valid <= 1'b0;
                    end else if (frame_valid && frame_ready) begin
                        active_frame <= frame_data;
                        pending_valid <= 1'b0;
                    end else begin
                        active_frame <= '0;
                        underflow_sticky <= 1'b1;
                    end
                end
            end else begin
                slot_position <= slot_position + 1'b1;
                if (slot_position < SLOT_COUNT_WIDTH'(SAMPLE_WIDTH)) begin
                    if (channel_right)
                        serial_data <= active_frame[serial_bit_index];
                    else
                        serial_data <= active_frame[32 + serial_bit_index];
                end else begin
                    serial_data <= 1'b0;
                end
            end
        end
    end

endmodule

`default_nettype wire
