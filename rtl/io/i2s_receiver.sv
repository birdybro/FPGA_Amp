`timescale 1ns/1ps
`default_nettype none

// I2S receiver for two signed samples in fixed-width slots. LRCLK=0 is left.
// Serial data is sampled on BCLK rising edges. The first bit after an LRCLK
// transition is the I2S delay bit; the following SAMPLE_WIDTH bits are data,
// MSB first. Remaining slot bits are ignored.
module i2s_receiver #(
    parameter int unsigned SAMPLE_WIDTH = 24,
    parameter int unsigned SLOT_WIDTH = 32
) (
    input  logic                 bclk,
    input  logic                 rst_n,
    input  logic                 lrclk,
    input  logic                 serial_data,
    input  logic                 clear_frame_error,
    output logic [63:0]          frame_data,
    output logic                 frame_valid,
    output logic                 frame_error_sticky
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

    function automatic logic [31:0] sign_extend_sample(
        input logic [SAMPLE_WIDTH-1:0] value
    );
        sign_extend_sample = {
            {(32-SAMPLE_WIDTH){value[SAMPLE_WIDTH-1]}}, value
        };
    endfunction

    logic lrclk_previous;
    logic locked;
    logic [SLOT_COUNT_WIDTH-1:0] slot_position;
    logic [SAMPLE_WIDTH-2:0] sample_shift;
    logic [SAMPLE_WIDTH-1:0] completed_sample;
    logic [31:0] left_sample;
    logic left_seen;
    logic transition;

    always_comb begin
        transition = lrclk != lrclk_previous;
        completed_sample = {sample_shift, serial_data};
    end

    always_ff @(posedge bclk or negedge rst_n) begin
        if (!rst_n) begin
            lrclk_previous <= 1'b1;
            locked <= 1'b0;
            slot_position <= '0;
            sample_shift <= '0;
            left_sample <= '0;
            left_seen <= 1'b0;
            frame_data <= '0;
            frame_valid <= 1'b0;
            frame_error_sticky <= 1'b0;
        end else begin
            frame_valid <= 1'b0;
            lrclk_previous <= lrclk;
            if (clear_frame_error)
                frame_error_sticky <= 1'b0;

            if (transition) begin
                // Once locked, exactly SLOT_WIDTH BCLK rising edges must occur
                // from one observed transition through the next.
                if (locked && slot_position != SLOT_COUNT_WIDTH'(SLOT_WIDTH - 1))
                    frame_error_sticky <= 1'b1;
                if (!lrclk && left_seen) begin
                    // A new left slot arrived without a completed right sample.
                    left_seen <= 1'b0;
                    frame_error_sticky <= 1'b1;
                end
                locked <= 1'b1;
                slot_position <= '0;
                sample_shift <= '0;
            end else if (locked) begin
                if (slot_position == SLOT_COUNT_WIDTH'(SLOT_WIDTH - 1)) begin
                    // Missing or late LRCLK transition; hold position until it
                    // returns so the error cannot wrap into a false sample.
                    frame_error_sticky <= 1'b1;
                end else begin
                    slot_position <= slot_position + 1'b1;
                end

                if (slot_position < SLOT_COUNT_WIDTH'(SAMPLE_WIDTH)) begin
                    sample_shift <= completed_sample[SAMPLE_WIDTH-2:0];
                    if (slot_position == SLOT_COUNT_WIDTH'(SAMPLE_WIDTH - 1)) begin
                        if (!lrclk) begin
                            left_sample <= sign_extend_sample(completed_sample);
                            left_seen <= 1'b1;
                        end else if (left_seen) begin
                            frame_data <= {
                                left_sample,
                                sign_extend_sample(completed_sample)
                            };
                            frame_valid <= 1'b1;
                            left_seen <= 1'b0;
                        end
                    end
                end
            end
        end
    end

endmodule

`default_nettype wire
