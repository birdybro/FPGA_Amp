`timescale 1ns/1ps
`default_nettype none

module decimator_8x_tb;
    localparam int INPUT_COUNT = 1024;
    localparam int OUTPUT_COUNT = 128;

    logic clk;
    logic rst_n = 1'b0;
    logic ce_input = 1'b0;
    logic signed [31:0] sample_input_q24;
    logic signed [31:0] sample_output_q24;
    logic output_valid;
    logic [31:0] saturation_count;
    logic [31:0] overrun_count;
    logic signed [31:0] input_vector [0:INPUT_COUNT-1];
    logic signed [31:0] expected_vector [0:OUTPUT_COUNT-1];

    decimator_8x dut (.*);
    always #5 clk = ~clk;

    integer file_handle;
    integer scan_count;
    integer input_index;
    integer output_index;
    integer error_count;
    integer clock_count;
    string marker;

    initial begin
        clk = 1'b0;
        file_handle = $fopen(
            "sim/vectors/generated/decimator_8x_stream.txt", "r"
        );
        if (file_handle == 0)
            $fatal(1, "cannot open 8x decimation vectors");
        for (input_index = 0; input_index < INPUT_COUNT;
             input_index = input_index + 1) begin
            scan_count = $fscanf(file_handle, "%d\n", input_vector[input_index]);
            if (scan_count != 1)
                $fatal(1, "malformed input %0d", input_index);
        end
        scan_count = $fscanf(file_handle, "%s\n", marker);
        if (scan_count != 1 || marker != "EXPECTED")
            $fatal(1, "missing marker");
        for (output_index = 0; output_index < OUTPUT_COUNT;
             output_index = output_index + 1) begin
            scan_count = $fscanf(
                file_handle, "%d\n", expected_vector[output_index]
            );
            if (scan_count != 1)
                $fatal(1, "malformed output %0d", output_index);
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

        while (output_index < OUTPUT_COUNT) begin
            @(posedge clk);
            #1;
            clock_count = clock_count + 1;
            ce_input <= 1'b0;
            if (output_valid) begin
                if (sample_output_q24 !== expected_vector[output_index]) begin
                    $display(
                        "MISMATCH output %0d: got=%0d expected=%0d",
                        output_index, sample_output_q24,
                        expected_vector[output_index]
                    );
                    error_count = error_count + 1;
                end
                output_index = output_index + 1;
            end
            if ((clock_count % 256) == 0
                && input_index + 1 < INPUT_COUNT) begin
                input_index = input_index + 1;
                sample_input_q24 <= input_vector[input_index];
                ce_input <= 1'b1;
            end
            if (clock_count > INPUT_COUNT * 300)
                $fatal(1, "decimator timeout output=%0d", output_index);
        end
        if (saturation_count != 0 || overrun_count != 0) begin
            $display(
                "MISMATCH diagnostics saturation=%0d overrun=%0d",
                saturation_count, overrun_count
            );
            error_count = error_count + 1;
        end
        if (error_count != 0)
            $fatal(1, "FAIL: %0d errors", error_count);
        $display("PASS: %0d exact 8x decimation outputs", output_index);
        $finish;
    end
endmodule

`default_nettype wire
