`timescale 1ns/1ps
`default_nettype none

module audio_clock_rate_monitor_tb;
    localparam int WINDOW_FABRIC_CLOCKS = 320;
    localparam int EXPECTED_BCLK_EDGES = 10;

    logic i2s_bclk;
    logic i2s_rst_n = 1'b0;
    logic fabric_clk;
    logic fabric_rst_n = 1'b0;
    logic clear_diagnostics = 1'b0;
    logic measurement_valid;
    logic [15:0] measured_bclk_edges;
    logic [7:0] consecutive_good_windows;
    logic rate_locked;
    logic rate_error_sticky;
    logic fast_bclk;
    logic bclk_running;
    logic [15:0] observed_bad_edges;

    audio_clock_rate_monitor #(
        .WINDOW_FABRIC_CLOCKS(WINDOW_FABRIC_CLOCKS),
        .EXPECTED_BCLK_EDGES(EXPECTED_BCLK_EDGES),
        .EDGE_TOLERANCE(0),
        .LOCK_WINDOWS(3)
    ) dut (.*);

    initial begin
        fabric_clk = 1'b0;
        forever #5 fabric_clk = ~fabric_clk;
    end
    initial begin
        i2s_bclk = 1'b0;
        #37;
        forever begin
            if (fast_bclk)
                #140;
            else
                #160;
            if (bclk_running)
                i2s_bclk = ~i2s_bclk;
            else
                i2s_bclk = 1'b0;
        end
    end

    integer errors;
    integer good_measurements;
    always @(posedge fabric_clk) begin
        #1;
        if (measurement_valid
            && measured_bclk_edges == 16'(EXPECTED_BCLK_EDGES))
            good_measurements <= good_measurements + 1;
    end

    initial begin
        errors = 0;
        good_measurements = 0;
        fast_bclk = 1'b0;
        bclk_running = 1'b1;
        observed_bad_edges = '0;
        repeat (3) @(posedge fabric_clk);
        @(negedge fabric_clk);
        fabric_rst_n = 1'b1;
        repeat (2) @(posedge i2s_bclk);
        @(negedge i2s_bclk);
        i2s_rst_n = 1'b1;

        wait (rate_locked);
        @(negedge fabric_clk);
        #1;
        if (good_measurements < 3 || consecutive_good_windows != 3
            || measured_bclk_edges != 16'(EXPECTED_BCLK_EDGES)
            || rate_error_sticky) begin
            $error("exact-rate lock failed count=%0d measured=%0d good=%0d",
                   consecutive_good_windows, measured_bclk_edges,
                   good_measurements);
            errors = errors + 1;
        end

        // Speed BCLK up enough that every complete window is out of tolerance.
        fast_bclk = 1'b1;
        wait (rate_error_sticky);
        #1;
        observed_bad_edges = measured_bclk_edges;
        if (rate_locked || observed_bad_edges != 16'd11) begin
            $error("rate error did not drop lock measured=%0d",
                   measured_bclk_edges);
            errors = errors + 1;
        end

        // Restore the exact ratio, require a fresh three-window acquisition,
        // then clear the retained evidence in the fabric domain.
        fast_bclk = 1'b0;
        wait (rate_locked);
        @(negedge fabric_clk);
        clear_diagnostics = 1'b1;
        @(posedge fabric_clk);
        #1;
        clear_diagnostics = 1'b0;
        if (rate_error_sticky || consecutive_good_windows != 3
            || measured_bclk_edges != 16'(EXPECTED_BCLK_EDGES)) begin
            $error("rate recovery/clear failed");
            errors = errors + 1;
        end

        // A physically stopped BCLK leaves the active qualifier high but
        // produces a zero-edge bad window, proving loss is detected.
        bclk_running = 1'b0;
        wait (rate_error_sticky);
        #1;
        if (rate_locked || measured_bclk_edges != 0) begin
            $error("stopped BCLK did not produce a zero-edge rate error");
            errors = errors + 1;
        end

        // Asserting BCLK-domain reset removes active-clock qualification after
        // synchronization and clears live state without fabric reset.
        i2s_rst_n = 1'b0;
        wait (!rate_locked);
        repeat (3) @(posedge fabric_clk);
        #1;
        if (consecutive_good_windows != 0 || measured_bclk_edges != 0) begin
            $error("inactive BCLK did not clear live monitor state");
            errors = errors + 1;
        end

        if (errors != 0)
            $fatal(1, "FAIL: %0d audio clock monitor errors", errors);
        $display("PASS: lock/rate error %0d/recovery/clear/stopped/inactive",
                 observed_bad_edges);
        $finish;
    end

    initial begin
        #100_000;
        $fatal(1, "audio clock monitor timed out");
    end
endmodule

`default_nettype wire
