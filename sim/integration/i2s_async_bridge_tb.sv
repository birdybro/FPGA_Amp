`timescale 1ns/1ps
`default_nettype none

module i2s_async_bridge_tb;
    localparam int FRAME_COUNT = 20;

    logic i2s_bclk;
    logic i2s_rst_n = 1'b0;
    logic fabric_clk;
    logic fabric_rst_n = 1'b0;

    logic [63:0] adc_frame_data = '0;
    logic adc_frame_valid = 1'b0;
    logic adc_frame_ready;
    logic adc_lrclk;
    logic adc_serial_data;
    logic adc_underflow;

    logic dac_lrclk;
    logic dac_serial_data;
    logic [63:0] dac_frame_data;
    logic dac_frame_valid;
    logic dac_frame_error;

    logic [63:0] fabric_rx_data;
    logic fabric_rx_valid;
    logic fabric_rx_ready;
    logic [63:0] fabric_tx_data;
    logic fabric_tx_valid;
    logic fabric_tx_ready;
    logic i2s_clear_diagnostics = 1'b0;
    logic fabric_clear_diagnostics = 1'b0;

    logic rx_frame_error;
    logic rx_fifo_overflow;
    logic rx_fifo_underflow;
    logic tx_fifo_overflow;
    logic tx_fifo_underflow;
    logic tx_serial_underflow;

    logic [63:0] expected [0:FRAME_COUNT-1];
    integer fabric_rx_index;
    integer dac_index;
    integer fabric_errors;
    integer dac_errors;
    integer fabric_cycle_count;
    integer errors;
    integer index;
    logic dac_scoreboard_started;
    logic stalled_rx_valid;
    logic [63:0] stalled_rx_data;

    i2s_transmitter adc_source (
        .bclk(i2s_bclk),
        .rst_n(i2s_rst_n),
        .frame_data(adc_frame_data),
        .frame_valid(adc_frame_valid),
        .frame_ready(adc_frame_ready),
        .clear_underflow(i2s_clear_diagnostics),
        .lrclk(adc_lrclk),
        .serial_data(adc_serial_data),
        .underflow_sticky(adc_underflow)
    );

    i2s_async_bridge bridge (
        .i2s_bclk(i2s_bclk),
        .i2s_rst_n(i2s_rst_n),
        .i2s_adc_lrclk(adc_lrclk),
        .i2s_adc_serial_data(adc_serial_data),
        .i2s_dac_lrclk(dac_lrclk),
        .i2s_dac_serial_data(dac_serial_data),
        .i2s_clear_diagnostics(i2s_clear_diagnostics),
        .fabric_clk(fabric_clk),
        .fabric_rst_n(fabric_rst_n),
        .fabric_rx_frame_data(fabric_rx_data),
        .fabric_rx_frame_valid(fabric_rx_valid),
        .fabric_rx_frame_ready(fabric_rx_ready),
        .fabric_tx_frame_data(fabric_tx_data),
        .fabric_tx_frame_valid(fabric_tx_valid),
        .fabric_tx_frame_ready(fabric_tx_ready),
        .fabric_clear_diagnostics(fabric_clear_diagnostics),
        .rx_frame_error_sticky(rx_frame_error),
        .rx_fifo_overflow_sticky(rx_fifo_overflow),
        .rx_fifo_underflow_sticky(rx_fifo_underflow),
        .tx_fifo_overflow_sticky(tx_fifo_overflow),
        .tx_fifo_underflow_sticky(tx_fifo_underflow),
        .tx_serial_underflow_sticky(tx_serial_underflow)
    );

    i2s_receiver dac_sink (
        .bclk(i2s_bclk),
        .rst_n(i2s_rst_n),
        .lrclk(dac_lrclk),
        .serial_data(dac_serial_data),
        .clear_frame_error(i2s_clear_diagnostics),
        .frame_data(dac_frame_data),
        .frame_valid(dac_frame_valid),
        .frame_error_sticky(dac_frame_error)
    );

    initial begin
        i2s_bclk = 1'b0;
        forever #10 i2s_bclk = ~i2s_bclk;
    end
    initial begin
        fabric_clk = 1'b0;
        #3;
        forever #6.5 fabric_clk = ~fabric_clk;
    end

    task automatic enqueue_adc(input logic [63:0] value);
        begin
            @(posedge i2s_bclk);
            while (!adc_frame_ready)
                @(posedge i2s_bclk);
            adc_frame_data = value;
            adc_frame_valid = 1'b1;
            @(posedge i2s_bclk);
            adc_frame_valid = 1'b0;
        end
    endtask

    // Fabric loopback preserves each complete stereo frame. The one-cycle
    // valid pulse is accepted only when the transmit FIFO is ready.
    always @(posedge fabric_clk or negedge fabric_rst_n) begin
        if (!fabric_rst_n) begin
            fabric_tx_valid <= 1'b0;
            fabric_tx_data <= '0;
            fabric_rx_index <= 0;
            fabric_cycle_count <= 0;
            fabric_rx_ready <= 1'b0;
            stalled_rx_valid <= 1'b0;
            stalled_rx_data <= '0;
        end else begin
            fabric_cycle_count <= fabric_cycle_count + 1;
            // Deliberate one-in-four backpressure verifies that the bridge
            // holds a complete frame stable until ready returns.
            fabric_rx_ready <= fabric_cycle_count[1:0] != 2'b01;
            fabric_tx_valid <= 1'b0;
            if (stalled_rx_valid) begin
                if (!fabric_rx_valid || fabric_rx_data !== stalled_rx_data) begin
                    $error("fabric RX changed while backpressured");
                    fabric_errors <= fabric_errors + 1;
                end
                if (fabric_rx_ready)
                    stalled_rx_valid <= 1'b0;
            end else if (fabric_rx_valid && !fabric_rx_ready) begin
                stalled_rx_data <= fabric_rx_data;
                stalled_rx_valid <= 1'b1;
            end
            if (fabric_rx_valid && fabric_rx_ready
                && fabric_rx_index < FRAME_COUNT) begin
                if (fabric_rx_data !== expected[fabric_rx_index]) begin
                    $error("fabric RX frame %0d got=%016x",
                           fabric_rx_index, fabric_rx_data);
                    fabric_errors <= fabric_errors + 1;
                end
                if (!fabric_tx_ready) begin
                    $error("fabric TX FIFO unexpectedly full");
                    fabric_errors <= fabric_errors + 1;
                end else begin
                    fabric_tx_data <= fabric_rx_data;
                    fabric_tx_valid <= 1'b1;
                end
                fabric_rx_index <= fabric_rx_index + 1;
            end
        end
    end

    // Ignore zero frames emitted during deliberate startup starvation. Once
    // the first nonzero expected frame arrives, require a contiguous sequence.
    always @(posedge i2s_bclk) begin
        #1;
        if (dac_frame_valid) begin
            if (!dac_scoreboard_started && dac_frame_data == 64'd0) begin
                dac_scoreboard_started <= 1'b0;
            end else begin
                dac_scoreboard_started <= 1'b1;
                if (dac_index >= FRAME_COUNT
                    || dac_frame_data !== expected[dac_index]) begin
                    $error("DAC frame %0d got=%016x expected=%016x",
                           dac_index,
                           dac_frame_data,
                           (dac_index < FRAME_COUNT) ? expected[dac_index] : 64'd0);
                    dac_errors <= dac_errors + 1;
                end
                dac_index <= dac_index + 1;
            end
        end
    end

    initial begin
        errors = 0;
        fabric_errors = 0;
        dac_errors = 0;
        fabric_cycle_count = 0;
        fabric_rx_index = 0;
        dac_index = 0;
        dac_scoreboard_started = 1'b0;
        stalled_rx_valid = 1'b0;
        stalled_rx_data = '0;
        for (index = 0; index < FRAME_COUNT; index++) begin
            expected[index] = {
                8'h00, 24'(24'h100001 + index * 24'h010203),
                8'hff, 24'(24'hefffff - index * 24'h010102)
            };
        end

        adc_frame_data = expected[0];
        adc_frame_valid = 1'b1;
        repeat (4) @(posedge i2s_bclk);
        #1;
        i2s_rst_n = 1'b1;
        // Release fabric reset at an unrelated phase.
        #4;
        fabric_rst_n = 1'b1;
        @(posedge i2s_bclk);
        adc_frame_valid = 1'b0;
        for (index = 1; index < FRAME_COUNT; index++)
            enqueue_adc(expected[index]);

        wait (dac_index == FRAME_COUNT);
        #1;
        if (fabric_rx_index != FRAME_COUNT) begin
            $error("fabric received %0d frames, expected %0d",
                   fabric_rx_index, FRAME_COUNT);
            errors = errors + 1;
        end
        if (rx_frame_error || rx_fifo_overflow || rx_fifo_underflow
            || tx_fifo_overflow || tx_fifo_underflow || dac_frame_error) begin
            $error("unexpected bridge/sink diagnostic");
            errors = errors + 1;
        end
        // Startup starvation is expected because the ADC path must first fill
        // and cross; clear it, then ensure the clear reaches the BCLK block.
        if (!tx_serial_underflow) begin
            $error("expected startup DAC underflow was not recorded");
            errors = errors + 1;
        end
        i2s_clear_diagnostics = 1'b1;
        @(negedge i2s_bclk);
        #1;
        i2s_clear_diagnostics = 1'b0;
        if (tx_serial_underflow) begin
            $error("DAC underflow diagnostic did not clear");
            errors = errors + 1;
        end
        if (adc_underflow) begin
            $error("ADC source underflow diagnostic did not clear");
            errors = errors + 1;
        end

        errors = errors + fabric_errors + dac_errors;
        if (errors != 0)
            $fatal(1, "FAIL: %0d I2S asynchronous bridge errors", errors);
        $display("PASS: 20 stereo frames across BCLK/fabric FIFOs and back");
        $finish;
    end
endmodule

`default_nettype wire
