`timescale 1ns/1ps
`default_nettype none

module cdc_word_snapshot_tb;
    logic source_clk;
    logic source_rst_n = 1'b0;
    logic source_request = 1'b0;
    logic source_available;
    logic source_snapshot_valid;
    logic [15:0] source_snapshot_data;
    logic destination_clk;
    logic destination_rst_n = 1'b0;
    logic [15:0] destination_live_data = 16'h1234;
    integer valid_count;
    integer errors = 0;

    initial begin
        source_clk = 1'b0;
        forever #5 source_clk = ~source_clk;
    end

    initial begin
        destination_clk = 1'b0;
        forever #7 destination_clk = ~destination_clk;
    end

    cdc_word_snapshot #(
        .WIDTH(16)
    ) dut (.*);

    always_ff @(posedge source_clk or negedge source_rst_n) begin
        if (!source_rst_n)
            valid_count <= 0;
        else if (source_snapshot_valid)
            valid_count <= valid_count + 1;
    end

    task automatic request_and_expect(input logic [15:0] expected_data);
        begin
            wait (source_available);
            @(negedge source_clk);
            source_request = 1'b1;
            @(negedge source_clk);
            source_request = 1'b0;
            wait (source_snapshot_valid);
            #1;
            if (source_snapshot_data != expected_data) begin
                $error("snapshot=%04x expected=%04x",
                       source_snapshot_data, expected_data);
                errors = errors + 1;
            end
            wait (source_available);
        end
    endtask

    initial begin
        repeat (3) @(posedge source_clk);
        source_rst_n = 1'b1;
        repeat (2) @(posedge destination_clk);
        destination_rst_n = 1'b1;

        request_and_expect(16'h1234);
        destination_live_data = 16'h5678;
        request_and_expect(16'h5678);
        if (valid_count != 2) begin
            $error("snapshot valid count=%0d expected=2", valid_count);
            errors = errors + 1;
        end

        // A destination reset during an active request must re-arm rather than
        // losing the request or fabricating a completion.
        destination_live_data = 16'hbeef;
        wait (source_available);
        @(negedge source_clk);
        source_request = 1'b1;
        @(negedge source_clk);
        source_request = 1'b0;
        destination_rst_n = 1'b0;
        repeat (4) @(posedge source_clk);
        if (source_snapshot_valid) begin
            $error("snapshot completed while destination was reset");
            errors = errors + 1;
        end
        @(negedge destination_clk);
        destination_rst_n = 1'b1;
        wait (source_snapshot_valid);
        @(posedge source_clk);
        #1;
        if (source_snapshot_data != 16'hbeef || valid_count != 3) begin
            $error("post-reset snapshot=%04x count=%0d",
                   source_snapshot_data, valid_count);
            errors = errors + 1;
        end

        if (errors != 0)
            $fatal(1, "FAIL: %0d CDC snapshot errors", errors);
        $display("PASS: three coherent snapshots across unrelated clocks/reset");
        $finish;
    end

    initial begin
        #20_000;
        $fatal(1, "CDC snapshot timed out");
    end

endmodule

`default_nettype wire
