`timescale 1ns/1ps
`default_nettype none

module halfband_decimator_2x_tb;
    logic clk;
    logic rst_n = 1'b0;
    logic ce_input = 1'b0;
    logic signed [31:0] sample_input_q24;
    logic signed [31:0] sample_output_q24;
    logic output_valid;
    logic busy;
    logic [31:0] saturation_count;
    logic [31:0] overrun_count;

    halfband_decimator_2x dut (.*);
    always #5 clk = ~clk;

    integer file_handle;
    integer scan_count;
    integer vector_count;
    integer error_count;
    integer timeout;
    logic signed [31:0] input_even;
    logic signed [31:0] input_odd;
    logic signed [31:0] expected_output;
    string vector_path;

    task automatic pulse_input(input logic signed [31:0] value);
        begin
            sample_input_q24 <= value;
            ce_input <= 1'b1;
            @(posedge clk);
            #1;
            ce_input <= 1'b0;
        end
    endtask

    initial begin
        clk = 1'b0;
        if (!$value$plusargs("VECTORS=%s", vector_path))
            vector_path = "sim/vectors/generated/halfband_decimator_stage1.txt";
        file_handle = $fopen(vector_path, "r");
        if (file_handle == 0) $fatal(1, "cannot open %s", vector_path);
        vector_count = 0;
        error_count = 0;
        sample_input_q24 = '0;
        repeat (3) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);

        while (!$feof(file_handle)) begin
            scan_count = $fscanf(
                file_handle, "%d %d %d\n", input_even, input_odd, expected_output
            );
            if (scan_count != 3) begin
                if (!$feof(file_handle)) $fatal(1, "malformed vector %0d", vector_count);
            end else begin
                pulse_input(input_even);
                timeout = 0;
                while (!output_valid) begin
                    @(posedge clk);
                    #1;
                    timeout = timeout + 1;
                    if (timeout > 44) $fatal(1, "timeout vector %0d", vector_count);
                end
                if (sample_output_q24 !== expected_output) begin
                    $error("vector %0d: got=%0d expected=%0d",
                           vector_count, sample_output_q24, expected_output);
                    error_count = error_count + 1;
                end
                repeat (8) @(posedge clk);
                pulse_input(input_odd);
                if (busy || output_valid) begin
                    $error("vector %0d odd phase launched a result", vector_count);
                    error_count = error_count + 1;
                end
                repeat (8) @(posedge clk);
                vector_count = vector_count + 1;
            end
        end
        $fclose(file_handle);

        // History storage is allowed to retain physical bits through reset,
        // but no stale sample may become architecturally visible afterward.
        rst_n <= 1'b0;
        @(posedge clk);
        #1;
        rst_n <= 1'b1;
        @(posedge clk);
        pulse_input(32'sd0);
        timeout = 0;
        while (!output_valid) begin
            @(posedge clk);
            #1;
            timeout = timeout + 1;
            if (timeout > 44) $fatal(1, "post-reset decimator timeout");
        end
        if (sample_output_q24 !== 32'sd0) begin
            $error("post-reset stale history: got=%0d", sample_output_q24);
            error_count = error_count + 1;
        end

        if (saturation_count != 0 || overrun_count != 0) begin
            $error("diagnostics saturation=%0d overrun=%0d",
                   saturation_count, overrun_count);
            error_count = error_count + 1;
        end
        if (error_count != 0) $fatal(1, "FAIL: %0d errors", error_count);
        $display("PASS: %0d stage-1 decimation outputs", vector_count);
        $finish;
    end
endmodule

`default_nettype wire
