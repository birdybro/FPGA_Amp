`timescale 1ns/1ps
`default_nettype none

module pcm4202_i2s_capture_tb;
    localparam int FRAME_COUNT = 16;
    localparam int INITIAL_BACKPRESSURE_CYCLES = 4000;

    logic adc_bclk;
    logic adc_rst_n = 1'b0;
    logic fabric_clk;
    logic fabric_rst_n = 1'b0;

    logic [63:0] source_frame_data = '0;
    logic source_frame_valid = 1'b0;
    logic source_frame_ready;
    logic source_lrclk;
    logic source_serial_data;
    /* verilator lint_off UNUSEDSIGNAL */
    logic source_underflow;
    /* verilator lint_on UNUSEDSIGNAL */
    logic inject_lrclk_fault = 1'b0;
    logic adc_clear_diagnostics = 1'b0;

    logic [63:0] fabric_frame_data;
    logic fabric_frame_valid;
    logic fabric_frame_ready;
    logic fabric_clear_diagnostics = 1'b0;
    logic frame_error_sticky;
    logic fifo_overflow_sticky;
    logic fifo_underflow_sticky;
    logic [3:0] fifo_adc_level;
    logic [3:0] fifo_adc_high_water;
    logic [3:0] fifo_fabric_level;
    logic [3:0] fifo_fabric_high_water;

    logic [63:0] expected [0:FRAME_COUNT-1];
    integer expected_index;
    integer fabric_cycle_count;
    integer errors;
    integer index;
    logic stalled_valid;
    logic [63:0] stalled_data;
    logic [3:0] observed_adc_high_water;
    logic [3:0] observed_fabric_high_water;

    i2s_transmitter #(
        .SAMPLE_WIDTH(24),
        .SLOT_WIDTH(64)
    ) pcm4202_source (
        .bclk(adc_bclk),
        .rst_n(adc_rst_n),
        .frame_data(source_frame_data),
        .frame_valid(source_frame_valid),
        .frame_ready(source_frame_ready),
        .clear_underflow(adc_clear_diagnostics),
        .lrclk(source_lrclk),
        .serial_data(source_serial_data),
        .underflow_sticky(source_underflow)
    );

    pcm4202_i2s_capture capture (
        .adc_bclk,
        .adc_rst_n,
        .adc_lrclk(source_lrclk ^ inject_lrclk_fault),
        .adc_serial_data(source_serial_data),
        .adc_clear_diagnostics,
        .fabric_clk,
        .fabric_rst_n,
        .fabric_frame_data,
        .fabric_frame_valid,
        .fabric_frame_ready,
        .fabric_clear_diagnostics,
        .frame_error_sticky,
        .fifo_overflow_sticky,
        .fifo_underflow_sticky,
        .fifo_adc_level,
        .fifo_adc_high_water,
        .fifo_fabric_level,
        .fifo_fabric_high_water
    );

    // 6.144 MHz is the PCM4202's fixed 128-fS BCK at 48 kHz. Rounded to
    // simulator resolution, it remains asynchronous to the 49.152 MHz fabric.
    initial begin
        adc_bclk = 1'b0;
        forever #81.380208ns adc_bclk = !adc_bclk;
    end
    initial begin
        fabric_clk = 1'b0;
        #2.137ns;
        forever #10.172526ns fabric_clk = !fabric_clk;
    end

    task automatic enqueue_source(input logic [63:0] value);
        begin
            @(posedge adc_bclk);
            while (!source_frame_ready)
                @(posedge adc_bclk);
            source_frame_data = value;
            source_frame_valid = 1'b1;
            @(posedge adc_bclk);
            source_frame_valid = 1'b0;
        end
    endtask

    always @(posedge fabric_clk or negedge fabric_rst_n) begin
        if (!fabric_rst_n) begin
            fabric_cycle_count <= 0;
            expected_index <= 0;
            fabric_frame_ready <= 1'b0;
            stalled_valid <= 1'b0;
            stalled_data <= '0;
        end else begin
            fabric_cycle_count <= fabric_cycle_count + 1;
            fabric_frame_ready <=
                fabric_cycle_count >= INITIAL_BACKPRESSURE_CYCLES
                && fabric_cycle_count % 7 != 3;

            if (stalled_valid) begin
                if (!fabric_frame_valid || fabric_frame_data !== stalled_data) begin
                    $error("PCM4202 capture changed held data while backpressured");
                    errors <= errors + 1;
                end
                if (fabric_frame_ready)
                    stalled_valid <= 1'b0;
            end else if (fabric_frame_valid && !fabric_frame_ready) begin
                stalled_data <= fabric_frame_data;
                stalled_valid <= 1'b1;
            end

            if (fabric_frame_valid && fabric_frame_ready) begin
                if (expected_index >= FRAME_COUNT
                    || fabric_frame_data !== expected[expected_index]) begin
                    $error("PCM4202 frame %0d got=%016x expected=%016x",
                           expected_index, fabric_frame_data,
                           (expected_index < FRAME_COUNT)
                               ? expected[expected_index] : 64'd0);
                    errors <= errors + 1;
                end
                expected_index <= expected_index + 1;
            end
        end
    end

    initial begin
        errors = 0;
        expected_index = 0;
        fabric_cycle_count = 0;
        stalled_valid = 1'b0;
        stalled_data = '0;
        observed_adc_high_water = '0;
        observed_fabric_high_water = '0;
        for (index = 0; index < FRAME_COUNT; index++) begin
            expected[index] = {
                8'h00, 24'(24'h300001 + index * 24'h010203),
                8'hff, 24'(24'hdfffff - index * 24'h010102)
            };
        end

        source_frame_data = expected[0];
        source_frame_valid = 1'b1;
        repeat (4) @(posedge adc_bclk);
        #1ps;
        adc_rst_n = 1'b1;
        #7.111ns;
        fabric_rst_n = 1'b1;
        @(posedge adc_bclk);
        source_frame_valid = 1'b0;
        for (index = 1; index < FRAME_COUNT; index++)
            enqueue_source(expected[index]);

        wait (expected_index == FRAME_COUNT);
        #1ns;
        if (frame_error_sticky || fifo_overflow_sticky
            || fifo_underflow_sticky) begin
            $error("unexpected PCM4202 capture diagnostic frame=%0b overflow=%0b underflow=%0b",
                   frame_error_sticky, fifo_overflow_sticky,
                   fifo_underflow_sticky);
            errors = errors + 1;
        end
        if (fifo_adc_high_water < 3 || fifo_adc_high_water > 8
            || fifo_fabric_high_water > 8
            || fifo_adc_level > 8 || fifo_fabric_level > 8) begin
            $error("invalid PCM4202 FIFO occupancy/high-water adc=%0d/%0d fabric=%0d/%0d",
                   fifo_adc_level, fifo_adc_high_water,
                   fifo_fabric_level, fifo_fabric_high_water);
            errors = errors + 1;
        end
        observed_adc_high_water = fifo_adc_high_water;
        observed_fabric_high_water = fifo_fabric_high_water;

        // A one-edge LRCK fault must be retained and explicitly clearable.
        @(negedge adc_bclk);
        inject_lrclk_fault = 1'b1;
        @(negedge adc_bclk);
        inject_lrclk_fault = 1'b0;
        repeat (2) @(posedge adc_bclk);
        if (!frame_error_sticky) begin
            $error("PCM4202 capture did not retain LRCK frame error");
            errors = errors + 1;
        end
        adc_clear_diagnostics = 1'b1;
        @(posedge adc_bclk);
        #1ps;
        adc_clear_diagnostics = 1'b0;
        if (frame_error_sticky) begin
            $error("PCM4202 frame-error clear failed");
            errors = errors + 1;
        end

        if (errors != 0)
            $fatal(1, "FAIL: %0d PCM4202 I2S capture errors", errors);
        $display("PASS: %0d PCM4202 frames at 6.144 MHz BCK; FIFO high-water adc/fabric=%0d/%0d",
                 FRAME_COUNT, observed_adc_high_water,
                 observed_fabric_high_water);
        $finish;
    end
endmodule

`default_nettype wire
