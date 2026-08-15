`timescale 1ns/1ps
`default_nettype none

module audio_serial_clock_tb;

    // Blocking scoreboard counters deliberately make edge counts visible to
    // the BCLK observer in the same simulation time step. Declaration
    // initialization is testbench-only and avoids an artificial reset writer.
    /* verilator lint_off BLKSEQ */
    /* verilator lint_off PROCASSINIT */
    logic fabric_clk = 1'b0;
    logic async_reset = 1'b1;
    logic fabric_rst_n;
    logic bclk_raw;
    logic i2s_rst_n;
    integer fabric_edge_count = 0;
    integer previous_bclk_rise = 0;
    integer bclk_rise_count = 0;

    always #5 fabric_clk = !fabric_clk;

    reset_release_sync fabric_reset_release (
        .clk(fabric_clk),
        .async_reset,
        .rst_n(fabric_rst_n)
    );

    audio_i2s_clock_divider #(
        .FABRIC_TO_BCLK_DIVIDE(16)
    ) divider (
        .fabric_clk,
        .fabric_rst_n,
        .bclk_raw
    );

    reset_release_sync i2s_reset_release (
        .clk(bclk_raw),
        .async_reset,
        .rst_n(i2s_rst_n)
    );

    always @(posedge fabric_clk)
        fabric_edge_count = fabric_edge_count + 1;

    always @(posedge bclk_raw) begin
        bclk_rise_count = bclk_rise_count + 1;
        if (previous_bclk_rise != 0 &&
            fabric_edge_count - previous_bclk_rise != 16)
            $fatal(1, "BCLK period was %0d fabric clocks",
                   fabric_edge_count - previous_bclk_rise);
        previous_bclk_rise = fabric_edge_count;
    end

    initial begin
        repeat (3) @(posedge fabric_clk);
        #1;
        if (fabric_rst_n || i2s_rst_n || bclk_raw)
            $fatal(1, "reset outputs were not held inactive");

        @(negedge fabric_clk);
        async_reset = 1'b0;
        repeat (2) begin
            @(posedge fabric_clk);
            #1;
            if (fabric_rst_n)
                $fatal(1, "fabric reset released before three clocks");
        end
        @(posedge fabric_clk);
        #1;
        if (!fabric_rst_n)
            $fatal(1, "fabric reset did not release on clock three");

        wait (bclk_rise_count == 2);
        #1;
        if (i2s_rst_n)
            $fatal(1, "I2S reset released before three BCLK edges");
        wait (bclk_rise_count == 3);
        #1;
        if (!i2s_rst_n)
            $fatal(1, "I2S reset did not release on BCLK edge three");

        wait (bclk_rise_count == 7);
        #2;
        async_reset = 1'b1;
        #1;
        if (fabric_rst_n || i2s_rst_n || bclk_raw)
            $fatal(1, "asynchronous assertion did not clear all domains");

        $display("PASS audio serial clock: /16 BCLK and 3-edge reset release");
        $finish;
    end

    /* verilator lint_on PROCASSINIT */
    /* verilator lint_on BLKSEQ */

endmodule

`default_nettype wire
