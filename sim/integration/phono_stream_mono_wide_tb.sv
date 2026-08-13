`timescale 1ns/1ps
`default_nettype none

module phono_stream_mono_wide_tb;
    localparam int VECTOR_COUNT = 64;

    logic clk;
    logic rst_n = 1'b0;
    logic ce_input_48k = 1'b0;
    logic signed [31:0] sample_input_q24;
    logic signed [31:0] sample_output_q24;
    logic output_valid;
    logic [31:0] resampler_saturation_count;
    logic [31:0] resampler_overrun_count;
    logic [31:0] input_phase_error_count;
    logic [31:0] output_conversion_saturation_count;
    logic [31:0] solver_missed_request_count;
    logic [31:0] solver_deadline_miss_count;
    logic [31:0] solver_saturation_count;
    logic [31:0] solver_lut_clip_count;
    logic [31:0] solver_nonconvergence_count;
    logic [31:0] solver_correction_scale_fallback_count;
    logic [5:0] solver_minimum_correction_fractional_bits;
    logic [62:0] solver_last_residual_q44;
    logic [7:0] solver_latency_cycles;
    logic signed [31:0] input_vector [0:VECTOR_COUNT-1];
    logic signed [31:0] expected_vector [0:VECTOR_COUNT-1];

    phono_stream_mono_wide dut (.*);
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
            "sim/vectors/generated/phono_stream_mono_wide_factorized.txt", "r"
        );
        if (file_handle == 0)
            $fatal(1, "cannot open wide stream vectors");
        for (input_index = 0; input_index < VECTOR_COUNT; input_index++) begin
            scan_count = $fscanf(file_handle, "%d\n", input_vector[input_index]);
            if (scan_count != 1)
                $fatal(1, "malformed input %0d", input_index);
        end
        scan_count = $fscanf(file_handle, "%s\n", marker);
        if (scan_count != 1 || marker != "EXPECTED")
            $fatal(1, "missing marker");
        for (output_index = 0; output_index < VECTOR_COUNT; output_index++) begin
            scan_count = $fscanf(file_handle, "%d\n", expected_vector[output_index]);
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
        ce_input_48k <= 1'b1;

        while (output_index < VECTOR_COUNT) begin
            @(posedge clk);
            #1;
            clock_count = clock_count + 1;
            ce_input_48k <= 1'b0;
            if (output_valid) begin
                if (sample_output_q24 !== expected_vector[output_index]) begin
                    $error("output=%0d got=%0d expected=%0d", output_index,
                           sample_output_q24, expected_vector[output_index]);
                    error_count = error_count + 1;
                end
                output_index = output_index + 1;
            end
            if ((clock_count % 2048) == 0 && input_index + 1 < VECTOR_COUNT) begin
                input_index = input_index + 1;
                sample_input_q24 <= input_vector[input_index];
                ce_input_48k <= 1'b1;
            end
            if (clock_count > VECTOR_COUNT * 2300)
                $fatal(1, "stream timeout output=%0d", output_index);
        end

        if (resampler_saturation_count != 0 || resampler_overrun_count != 0
            || input_phase_error_count != 0
            || output_conversion_saturation_count != 0
            || solver_missed_request_count != 0
            || solver_deadline_miss_count != 0
            || solver_saturation_count != 0 || solver_lut_clip_count != 0
            || solver_nonconvergence_count != 0
            || solver_correction_scale_fallback_count != 0
            || solver_minimum_correction_fractional_bits != 0
            || solver_latency_cycles != 8'd116
            || solver_last_residual_q44 > 63'd35184372) begin
            $error("diagnostics rsat=%0d rover=%0d phase=%0d convsat=%0d smissed=%0d sdeadline=%0d ssat=%0d sclip=%0d snonconv=%0d fallback=%0d min=%0d latency=%0d residual=%0d",
                   resampler_saturation_count, resampler_overrun_count,
                   input_phase_error_count, output_conversion_saturation_count,
                   solver_missed_request_count, solver_deadline_miss_count,
                   solver_saturation_count, solver_lut_clip_count,
                   solver_nonconvergence_count,
                   solver_correction_scale_fallback_count,
                   solver_minimum_correction_fractional_bits,
                   solver_latency_cycles, solver_last_residual_q44);
            error_count = error_count + 1;
        end
        if (error_count != 0)
            $fatal(1, "FAIL: %0d wide stream errors", error_count);
        $display("PASS: %0d exact wide 48 kHz outputs, solver latency=116 clocks",
                 output_index);
        $finish;
    end
endmodule

`default_nettype wire
