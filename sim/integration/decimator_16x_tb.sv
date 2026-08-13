`timescale 1ns/1ps
`default_nettype none

module decimator_16x_tb;
    localparam int DEFAULT_INPUT_COUNT = 2048;
    localparam int DEFAULT_OUTPUT_COUNT = 128;
    localparam int MAX_INPUT_COUNT = 131072;
    localparam int MAX_OUTPUT_COUNT = 8192;

    logic clk;
    logic rst_n = 1'b0;
    logic ce_input = 1'b0;
    logic signed [31:0] sample_input_q24;
    logic signed [31:0] sample_output_q24;
    logic output_valid;
    logic [31:0] saturation_count;
    logic [31:0] overrun_count;
    logic signed [31:0] input_vector [0:MAX_INPUT_COUNT-1];
    logic signed [31:0] expected_vector [0:MAX_OUTPUT_COUNT-1];

    decimator_16x dut (.*);
    always #5 clk = ~clk;

    integer file_handle;
    integer scan_count;
    integer input_index;
    integer output_index;
    integer error_count;
    integer clock_count;
    integer input_count;
    integer output_count;
    integer capture_handle;
    string marker;
    string vector_path;
    string capture_path;

    initial begin
        clk = 1'b0;
        if (!$value$plusargs("INPUT_COUNT=%d", input_count))
            input_count = DEFAULT_INPUT_COUNT;
        if (!$value$plusargs("OUTPUT_COUNT=%d", output_count))
            output_count = DEFAULT_OUTPUT_COUNT;
        if (input_count <= 0 || input_count > MAX_INPUT_COUNT)
            $fatal(1, "invalid input count %0d", input_count);
        if (output_count <= 0 || output_count > MAX_OUTPUT_COUNT)
            $fatal(1, "invalid output count %0d", output_count);
        if (!$value$plusargs("VECTORS=%s", vector_path))
            vector_path = "sim/vectors/generated/decimator_16x_stream.txt";
        file_handle = $fopen(vector_path, "r");
        if (file_handle == 0) $fatal(1, "cannot open %s", vector_path);
        capture_handle = 0;
        if ($value$plusargs("CAPTURE=%s", capture_path)) begin
            capture_handle = $fopen(capture_path, "w");
            if (capture_handle == 0)
                $fatal(1, "cannot open capture output");
        end
        for (input_index = 0; input_index < input_count; input_index = input_index + 1) begin
            scan_count = $fscanf(file_handle, "%d\n", input_vector[input_index]);
            if (scan_count != 1) $fatal(1, "malformed input %0d", input_index);
        end
        scan_count = $fscanf(file_handle, "%s\n", marker);
        if (scan_count != 1 || marker != "EXPECTED") $fatal(1, "missing marker");
        for (output_index = 0; output_index < output_count; output_index = output_index + 1) begin
            scan_count = $fscanf(file_handle, "%d\n", expected_vector[output_index]);
            if (scan_count != 1) $fatal(1, "malformed output %0d", output_index);
        end
        $fclose(file_handle);

        input_index = 0;
        output_index = 0;
        error_count = 0;
        clock_count = 0;
        sample_input_q24 = input_vector[0];
        repeat (3) @(posedge clk);
        rst_n <= 1'b1;
        ce_input <= 1'b1;

        while (output_index < output_count) begin
            @(posedge clk);
            #1;
            clock_count = clock_count + 1;
            ce_input <= 1'b0;
            if (output_valid) begin
                if (sample_output_q24 !== expected_vector[output_index]) begin
                    $display("MISMATCH output %0d: got=%0d expected=%0d",
                             output_index, sample_output_q24, expected_vector[output_index]);
                    error_count = error_count + 1;
                end
                if (capture_handle != 0)
                    $fwrite(capture_handle, "%0d %0d\n", output_index,
                            sample_output_q24);
                output_index = output_index + 1;
            end
            if ((clock_count % 128) == 0 && input_index + 1 < input_count) begin
                input_index = input_index + 1;
                sample_input_q24 <= input_vector[input_index];
                ce_input <= 1'b1;
            end
            if (clock_count > input_count * 160)
                $fatal(1, "decimator timeout output=%0d", output_index);
        end
        if (capture_handle != 0)
            $fclose(capture_handle);
        if (saturation_count != 0 || overrun_count != 0) begin
            $display("MISMATCH diagnostics saturation=%0d overrun=%0d",
                     saturation_count, overrun_count);
            error_count = error_count + 1;
        end
        if (error_count != 0) $fatal(1, "FAIL: %0d errors", error_count);
        $display("PASS: %0d exact 16x decimation outputs", output_index);
        $finish;
    end
endmodule

`default_nettype wire
