`timescale 1ns/1ps
`default_nettype none

module network_rhs_v1_wide_tb;
    logic clk;
    logic rst_n = 1'b0;
    logic start = 1'b0;
    logic signed [31:0] input_q24;
    logic [494:0] rhs_q44;
    logic busy;
    logic valid;

    network_rhs_v1_wide dut (.*);
    always #5 clk = ~clk;

    integer file_handle;
    integer scan_count;
    integer vector_count = 0;
    integer errors = 0;
    integer latency;
    integer input_value;
    longint signed expected_rhs [0:8];

    initial begin
        clk = 1'b0;
        file_handle = $fopen("sim/vectors/generated/network_rhs_wide.txt", "r");
        if (file_handle == 0)
            $fatal(1, "cannot open wide RHS vectors");
        repeat (3) @(posedge clk);
        rst_n = 1'b1;
        @(negedge clk);
        while (!$feof(file_handle)) begin
            scan_count = $fscanf(file_handle, "%d", input_value);
            if (scan_count != 1)
                break;
            for (integer lane = 0; lane < 9; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d", expected_rhs[lane]);
            if (scan_count != 10)
                $fatal(1, "malformed vector %0d", vector_count);
            input_q24 = input_value[31:0];
            start = 1'b1;
            @(posedge clk);
            #1;
            start = 1'b0;
            if (!busy)
                $fatal(1, "request was not accepted");
            latency = 0;
            while (!valid) begin
                @(posedge clk);
                #1;
                latency = latency + 1;
                if (latency > 4)
                    $fatal(1, "timeout vector %0d", vector_count);
            end
            if (latency != 2) begin
                $error("latency got=%0d expected=2", latency);
                errors = errors + 1;
            end
            for (integer lane = 0; lane < 9; lane = lane + 1) begin
                if ($signed(rhs_q44[lane * 55 +: 55])
                    !== $signed(expected_rhs[lane][54:0])) begin
                    $error("vector=%0d lane=%0d got=%0d expected=%0d",
                           vector_count, lane,
                           $signed(rhs_q44[lane * 55 +: 55]),
                           expected_rhs[lane]);
                    errors = errors + 1;
                end
            end
            vector_count = vector_count + 1;
            @(negedge clk);
        end
        $fclose(file_handle);
        if (errors != 0)
            $fatal(1, "FAIL: %0d wide RHS errors", errors);
        $display("PASS: %0d wide RHS vectors, latency=2 clocks", vector_count);
        $finish;
    end
endmodule

`default_nettype wire
