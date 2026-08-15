`timescale 1ns/1ps
`default_nettype none

module halfband_interpolator_2x_tb;
    logic clk;
    logic rst_n = 1'b0;
    logic ce_input = 1'b0;
    logic ce_output = 1'b0;
    logic signed [31:0] sample_input_q24;
    logic signed [31:0] sample_output_q24;
    logic output_valid;
    logic busy;
    logic [31:0] saturation_count;
    logic [31:0] overrun_count;

    halfband_interpolator_2x dut (.*);
    always #5 clk = ~clk;

    integer file_handle;
    integer scan_count;
    integer vector_count;
    integer error_count;
    logic signed [31:0] expected_even;
    logic signed [31:0] expected_odd;
    logic signed [31:0] previous_even;
    logic signed [31:0] previous_odd;
    string vector_path;

    task automatic pulse_output_and_check(input logic signed [31:0] expected);
        begin
            ce_output <= 1'b1;
            @(posedge clk);
            #1;
            ce_output <= 1'b0;
            if (!output_valid || sample_output_q24 !== expected) begin
                $error("vector %0d output: valid=%0b got=%0d expected=%0d",
                       vector_count, output_valid, sample_output_q24, expected);
                error_count = error_count + 1;
            end
        end
    endtask

    initial begin
        clk = 1'b0;
        if (!$value$plusargs("VECTORS=%s", vector_path))
            vector_path = "sim/vectors/generated/halfband_interpolator_stage1.txt";
        file_handle = $fopen(vector_path, "r");
        if (file_handle == 0) $fatal(1, "cannot open %s", vector_path);
        vector_count = 0;
        error_count = 0;
        sample_input_q24 = '0;
        previous_even = '0;
        previous_odd = '0;
        repeat (3) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);

        while (!$feof(file_handle)) begin
            scan_count = $fscanf(
                file_handle, "%d %d %d\n", sample_input_q24,
                expected_even, expected_odd
            );
            if (scan_count != 3) begin
                if (!$feof(file_handle)) $fatal(1, "malformed vector %0d", vector_count);
            end else begin
                ce_input <= 1'b1;
                ce_output <= 1'b1;
                @(posedge clk);
                #1;
                ce_input <= 1'b0;
                ce_output <= 1'b0;
                if (!output_valid || sample_output_q24 !== previous_even) begin
                    $error("vector %0d even: got=%0d expected=%0d",
                           vector_count, sample_output_q24, previous_even);
                    error_count = error_count + 1;
                end
                repeat (48) @(posedge clk);
                pulse_output_and_check(previous_odd);
                repeat (48) @(posedge clk);
                if (busy) begin
                    $error("vector %0d MAC did not finish", vector_count);
                    error_count = error_count + 1;
                end
                previous_even = expected_even;
                previous_odd = expected_odd;
                vector_count = vector_count + 1;
            end
        end
        pulse_output_and_check(previous_even);
        repeat (48) @(posedge clk);
        pulse_output_and_check(previous_odd);
        $fclose(file_handle);

        // Retained distributed-memory bits must be hidden by reset masking in
        // both the computed phase and the pure-delay phase.
        rst_n <= 1'b0;
        @(posedge clk);
        #1;
        rst_n <= 1'b1;
        sample_input_q24 <= 32'sd0;
        ce_input <= 1'b1;
        ce_output <= 1'b1;
        @(posedge clk);
        #1;
        ce_input <= 1'b0;
        ce_output <= 1'b0;
        if (!output_valid || sample_output_q24 !== 32'sd0) begin
            $error("post-reset initial phase exposed stale state: got=%0d",
                   sample_output_q24);
            error_count = error_count + 1;
        end
        repeat (48) @(posedge clk);
        pulse_output_and_check(32'sd0);
        repeat (48) @(posedge clk);
        pulse_output_and_check(32'sd0);
        repeat (48) @(posedge clk);
        pulse_output_and_check(32'sd0);

        if (saturation_count != 0 || overrun_count != 0) begin
            $error("diagnostics saturation=%0d overrun=%0d",
                   saturation_count, overrun_count);
            error_count = error_count + 1;
        end
        if (error_count != 0) $fatal(1, "FAIL: %0d errors", error_count);
        $display("PASS: %0d stage-1 interpolation pairs", vector_count);
        $finish;
    end
endmodule

`default_nettype wire
