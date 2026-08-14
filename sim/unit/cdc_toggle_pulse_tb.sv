`timescale 1ns/1ps
`default_nettype none

module cdc_toggle_pulse_tb;
    logic source_clk;
    logic destination_clk;
    logic source_rst_n = 1'b0;
    logic destination_rst_n = 1'b0;
    logic source_pulse = 1'b0;
    logic destination_pulse;
    integer destination_pulse_count;
    integer errors = 0;

    initial begin
        source_clk = 1'b0;
        forever #5 source_clk = ~source_clk;
    end
    initial begin
        destination_clk = 1'b0;
        forever #17 destination_clk = ~destination_clk;
    end

    cdc_toggle_pulse dut (.*);

    always_ff @(posedge destination_clk or negedge destination_rst_n) begin
        if (!destination_rst_n)
            destination_pulse_count <= 0;
        else if (destination_pulse)
            destination_pulse_count <= destination_pulse_count + 1;
    end

    task automatic send_source_pulse;
        begin
            @(negedge source_clk);
            source_pulse = 1'b1;
            @(negedge source_clk);
            source_pulse = 1'b0;
        end
    endtask

    initial begin
        repeat (3) @(posedge source_clk);
        source_rst_n = 1'b1;
        repeat (2) @(posedge destination_clk);
        destination_rst_n = 1'b1;

        send_source_pulse();
        repeat (6) @(posedge destination_clk);
        #1;
        if (destination_pulse_count != 1 || destination_pulse) begin
            $error("first source event did not create exactly one pulse");
            errors = errors + 1;
        end

        // The primitive deliberately carries only a toggle, not an
        // acknowledged event count. Resetting the destination while the
        // source toggle is one replays the idempotent command after release.
        // This behavior must remain explicit at integration boundaries.
        @(negedge destination_clk);
        destination_rst_n = 1'b0;
        repeat (2) @(negedge destination_clk);
        destination_rst_n = 1'b1;
        repeat (6) @(posedge destination_clk);
        #1;
        if (destination_pulse_count != 1 || destination_pulse) begin
            $error("destination reset did not replay odd source toggle once");
            errors = errors + 1;
        end

        send_source_pulse();
        repeat (6) @(posedge destination_clk);
        #1;
        if (destination_pulse_count != 2 || destination_pulse) begin
            $error("second source event did not create exactly one pulse");
            errors = errors + 1;
        end

        if (errors != 0)
            $fatal(1, "FAIL: %0d toggle-pulse errors", errors);
        $display("PASS: two commands transferred once; odd-toggle reset replay explicit");
        $finish;
    end

endmodule

`default_nettype wire
