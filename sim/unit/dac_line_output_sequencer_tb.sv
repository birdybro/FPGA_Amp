`timescale 1ns/1ps
`default_nettype none

module dac_line_output_sequencer_tb;

    /* verilator lint_off PROCASSINIT */
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic release_request = 1'b0;
    logic emergency_mute = 1'b0;
    logic line_relay_enable_ctl;
    logic dac_soft_unmute_ctl;
    logic output_released;
    logic [2:0] sequence_state;

    always #5 clk = !clk;

    dac_line_output_sequencer #(
        .RELAY_SETTLE_CYCLES(4),
        .DAC_MUTE_SETTLE_CYCLES(3)
    ) dut (.*);

    task automatic expect_outputs(
        input logic expected_relay,
        input logic expected_xsmt,
        input logic expected_released,
        input logic [2:0] expected_state
    );
        begin
            #1;
            if (line_relay_enable_ctl !== expected_relay ||
                dac_soft_unmute_ctl !== expected_xsmt ||
                output_released !== expected_released ||
                sequence_state !== expected_state)
                $fatal(1, "sequencer output/state mismatch");
        end
    endtask

    initial begin
        #2;
        expect_outputs(1'b0, 1'b0, 1'b0, 3'd0);
        repeat (2) @(posedge clk);
        rst_n = 1'b1;

        @(negedge clk);
        release_request = 1'b1;
        @(posedge clk);
        expect_outputs(1'b1, 1'b0, 1'b0, 3'd1);
        repeat (3) begin
            @(posedge clk);
            expect_outputs(1'b1, 1'b0, 1'b0, 3'd1);
        end
        @(posedge clk);
        expect_outputs(1'b1, 1'b1, 1'b1, 3'd2);

        @(negedge clk);
        release_request = 1'b0;
        @(posedge clk);
        expect_outputs(1'b1, 1'b0, 1'b0, 3'd3);
        repeat (2) begin
            @(posedge clk);
            expect_outputs(1'b1, 1'b0, 1'b0, 3'd3);
        end
        @(posedge clk);
        expect_outputs(1'b0, 1'b0, 1'b0, 3'd0);

        @(negedge clk);
        release_request = 1'b1;
        @(posedge clk);
        expect_outputs(1'b1, 1'b0, 1'b0, 3'd1);
        @(negedge clk);
        release_request = 1'b0;
        @(posedge clk);
        expect_outputs(1'b0, 1'b0, 1'b0, 3'd0);

        @(negedge clk);
        release_request = 1'b1;
        repeat (5) @(posedge clk);
        expect_outputs(1'b1, 1'b1, 1'b1, 3'd2);
        @(negedge clk);
        emergency_mute = 1'b1;
        @(posedge clk);
        expect_outputs(1'b0, 1'b0, 1'b0, 3'd4);
        repeat (5) begin
            @(posedge clk);
            expect_outputs(1'b0, 1'b0, 1'b0, 3'd4);
        end

        @(negedge clk);
        emergency_mute = 1'b0;
        release_request = 1'b0;
        @(posedge clk);
        expect_outputs(1'b0, 1'b0, 1'b0, 3'd0);

        $display("PASS DAC line sequencer: relay-first release, XSMT-first mute, and emergency drop");
        $finish;
    end

    /* verilator lint_on PROCASSINIT */

endmodule

`default_nettype wire
