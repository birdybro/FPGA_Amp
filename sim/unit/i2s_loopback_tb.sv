`timescale 1ns/1ps
`default_nettype none

module i2s_loopback_tb #(
    parameter int unsigned SLOT_WIDTH = 32
);
    localparam int FRAME_COUNT = 16;

    logic bclk;
    logic rst_n = 1'b0;
    logic [63:0] tx_frame_data = '0;
    logic tx_frame_valid = 1'b0;
    logic tx_frame_ready;
    logic tx_clear_underflow = 1'b0;
    logic tx_lrclk;
    logic tx_serial_data;
    logic tx_underflow_sticky;

    logic inject_lrclk_fault = 1'b0;
    logic rx_clear_frame_error = 1'b0;
    logic [63:0] rx_frame_data;
    logic rx_frame_valid;
    logic rx_frame_error_sticky;

    logic [63:0] expected [0:FRAME_COUNT-1];
    integer expected_index;
    integer scoreboard_errors;
    integer protocol_errors;
    integer errors;
    integer index;
    logic scoreboard_enable;
    logic monitor_lrclk_previous;
    logic monitor_locked;
    logic monitor_enable;
    integer stable_edges_since_lrclk;

    i2s_transmitter #(
        .SLOT_WIDTH(SLOT_WIDTH)
    ) tx (
        .bclk(bclk),
        .rst_n(rst_n),
        .frame_data(tx_frame_data),
        .frame_valid(tx_frame_valid),
        .frame_ready(tx_frame_ready),
        .clear_underflow(tx_clear_underflow),
        .lrclk(tx_lrclk),
        .serial_data(tx_serial_data),
        .underflow_sticky(tx_underflow_sticky)
    );

    i2s_receiver #(
        .SLOT_WIDTH(SLOT_WIDTH)
    ) rx (
        .bclk(bclk),
        .rst_n(rst_n),
        .lrclk(tx_lrclk ^ inject_lrclk_fault),
        .serial_data(tx_serial_data),
        .clear_frame_error(rx_clear_frame_error),
        .frame_data(rx_frame_data),
        .frame_valid(rx_frame_valid),
        .frame_error_sticky(rx_frame_error_sticky)
    );

    initial begin
        bclk = 1'b0;
        forever #10 bclk = ~bclk;
    end

    task automatic enqueue(input logic [63:0] value);
        begin
            @(posedge bclk);
            while (!tx_frame_ready)
                @(posedge bclk);
            tx_frame_data = value;
            tx_frame_valid = 1'b1;
            @(posedge bclk);
            tx_frame_valid = 1'b0;
        end
    endtask

    always @(posedge bclk) begin
        #1;
        if (rx_frame_valid && scoreboard_enable) begin
            if (expected_index >= FRAME_COUNT) begin
                $error("unexpected extra I2S frame %016x", rx_frame_data);
                scoreboard_errors <= scoreboard_errors + 1;
            end else if (rx_frame_data !== expected[expected_index]) begin
                $error("frame %0d got=%016x expected=%016x",
                       expected_index, rx_frame_data, expected[expected_index]);
                scoreboard_errors <= scoreboard_errors + 1;
            end
            expected_index <= expected_index + 1;
        end
    end

    // Independent protocol monitor: adjacent LRCLK transitions must have
    // SLOT_WIDTH-1 stable sampled edges between them, and the sampled bit on
    // the transition edge is the I2S one-bit delay/padding value.
    always @(posedge bclk) begin
        #1;
        if (!monitor_enable) begin
            monitor_lrclk_previous <= tx_lrclk;
            monitor_locked <= 1'b0;
            stable_edges_since_lrclk <= 0;
        end else if (tx_lrclk != monitor_lrclk_previous) begin
            if (monitor_locked
                && stable_edges_since_lrclk != SLOT_WIDTH - 1) begin
                $error("I2S slot had %0d stable edges, expected %0d",
                       stable_edges_since_lrclk, SLOT_WIDTH - 1);
                protocol_errors <= protocol_errors + 1;
            end
            if (tx_serial_data !== 1'b0) begin
                $error("I2S delay bit was not zero at LRCLK transition");
                protocol_errors <= protocol_errors + 1;
            end
            monitor_lrclk_previous <= tx_lrclk;
            monitor_locked <= 1'b1;
            stable_edges_since_lrclk <= 0;
        end else if (monitor_locked) begin
            stable_edges_since_lrclk <= stable_edges_since_lrclk + 1;
        end
    end

    initial begin
        expected_index = 0;
        scoreboard_errors = 0;
        protocol_errors = 0;
        errors = 0;
        scoreboard_enable = 1'b1;
        monitor_lrclk_previous = 1'b1;
        monitor_locked = 1'b0;
        monitor_enable = 1'b0;
        stable_edges_since_lrclk = 0;
        expected[0] = {32'h007fffff, 32'hff800000};
        expected[1] = {32'h00000000, 32'hffffffff};
        expected[2] = {32'hff923456, 32'h00123456};
        for (index = 3; index < FRAME_COUNT; index++) begin
            expected[index] = {
                8'h00, 24'(index * 24'h010203),
                8'hff, 24'(24'hffffff - index * 24'h010101)
            };
        end

        // Present the first frame before synchronous reset release so the
        // transmitter never inserts an initial zero/underflow frame.
        tx_frame_data = expected[0];
        tx_frame_valid = 1'b1;
        repeat (4) @(posedge bclk);
        #1;
        rst_n = 1'b1;
        monitor_enable = 1'b1;
        @(posedge bclk);
        tx_frame_valid = 1'b0;
        for (index = 1; index < FRAME_COUNT; index++)
            enqueue(expected[index]);

        wait (expected_index == FRAME_COUNT);
        scoreboard_enable = 1'b0;
        if (rx_frame_error_sticky || tx_underflow_sticky) begin
            $error("clean loopback diagnostics frame=%0b underflow=%0b",
                   rx_frame_error_sticky, tx_underflow_sticky);
            errors = errors + 1;
        end

        // With no next frame, the following left boundary must insert zeros
        // and retain a transmitter underflow diagnostic.
        repeat (4 * SLOT_WIDTH + 2) @(posedge bclk);
        if (!tx_underflow_sticky) begin
            $error("missing transmitter underflow diagnostic");
            errors = errors + 1;
        end
        tx_clear_underflow = 1'b1;
        @(negedge bclk);
        #1;
        tx_clear_underflow = 1'b0;
        if (tx_underflow_sticky) begin
            $error("transmitter underflow clear failed");
            errors = errors + 1;
        end

        // Disturb LRCLK for one sampled edge; framing must go sticky.
        @(negedge bclk);
        inject_lrclk_fault = 1'b1;
        @(negedge bclk);
        inject_lrclk_fault = 1'b0;
        repeat (2) @(posedge bclk);
        if (!rx_frame_error_sticky) begin
            $error("receiver did not record LRCLK framing fault");
            errors = errors + 1;
        end
        rx_clear_frame_error = 1'b1;
        @(posedge bclk);
        #1;
        rx_clear_frame_error = 1'b0;
        if (rx_frame_error_sticky) begin
            $error("receiver frame-error clear failed");
            errors = errors + 1;
        end

        errors = errors + scoreboard_errors + protocol_errors;
        if (errors != 0)
            $fatal(1, "FAIL: %0d I2S loopback errors", errors);
        $display("PASS: 16 I2S frames at %0d BCK/channel, signed endpoints, framing, and underflow",
                 SLOT_WIDTH);
        $finish;
    end
endmodule

`default_nettype wire
