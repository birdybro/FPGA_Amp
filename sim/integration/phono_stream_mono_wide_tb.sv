`timescale 1ns/1ps
`default_nettype none

module phono_stream_mono_wide_tb #(
    parameter bit TRAPEZOIDAL = 1'b0,
    parameter bit BANKED = 1'b0,
    parameter bit TERMINAL_CORRECTION = 1'b0
);
    localparam int MAX_VECTOR_COUNT = 8192;
    localparam int EXPECTED_SOLVER_LATENCY = TERMINAL_CORRECTION ? 127 : 116;

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
    logic signed [31:0] input_vector [0:MAX_VECTOR_COUNT-1];
    logic signed [31:0] expected_vector [0:MAX_VECTOR_COUNT-1];

    phono_stream_mono_wide #(
        .NODE_INITIAL_FILE(
            TRAPEZOIDAL
                ? "model/generated/v1_node_initial_wide_trapezoidal.mem"
                : "model/generated/v1_node_initial_wide.mem"
        ),
        .CAP_INITIAL_FILE(
            TRAPEZOIDAL
                ? "model/generated/v1_cap_initial_q30_wide_trapezoidal.mem"
                : "model/generated/v1_cap_initial_q30_wide.mem"
        ),
        .CAP_G_FILE(
            TRAPEZOIDAL
                ? "model/generated/v1_cap_conductance_q0_47_trapezoidal.mem"
                : "model/generated/v1_cap_conductance_q0_47.mem"
        ),
        .CHORD_COEFFICIENT_FILE(
            BANKED
                ? (TRAPEZOIDAL
                   ? "model/generated/v1_chord_inverse_banked_q17_1_trapezoidal.mem"
                   : "model/generated/v1_chord_inverse_banked_q17_1.mem")
                : (TRAPEZOIDAL
                   ? "model/generated/v1_chord_inverse_q17_1_trapezoidal.mem"
                   : "model/generated/v1_chord_inverse_q17_1.mem")
        ),
        .CHORD_COEFFICIENT_SETS(BANKED ? (TRAPEZOIDAL ? 5 : 4) : 1),
        .TRAPEZOIDAL(TRAPEZOIDAL),
        .TERMINAL_CORRECTION(TERMINAL_CORRECTION)
    ) dut (.*);
    always #5 clk = ~clk;

    integer file_handle;
    integer scan_count;
    integer input_index;
    integer output_index;
    integer error_count;
    integer clock_count;
    integer vector_count;
    integer capture_handle;
    string marker;
    string vector_path;
    string capture_path;

    initial begin
        clk = 1'b0;
        if (!$value$plusargs("VECTOR_COUNT=%d", vector_count))
            vector_count = 64;
        if (vector_count <= 0 || vector_count > MAX_VECTOR_COUNT)
            $fatal(1, "invalid vector count %0d", vector_count);
        if (!$value$plusargs("VECTORS=%s", vector_path)) begin
            if (TRAPEZOIDAL && BANKED)
                vector_path = "sim/vectors/generated/phono_stream_mono_wide_factorized_trapezoidal_banked.txt";
            else if (TRAPEZOIDAL)
                vector_path = "sim/vectors/generated/phono_stream_mono_wide_factorized_trapezoidal.txt";
            else if (BANKED && TERMINAL_CORRECTION)
                vector_path = "sim/vectors/generated/phono_stream_mono_wide_factorized_banked_terminal.txt";
            else if (BANKED)
                vector_path = "sim/vectors/generated/phono_stream_mono_wide_factorized_banked.txt";
            else
                vector_path =
                    "sim/vectors/generated/phono_stream_mono_wide_factorized.txt";
        end
        file_handle = $fopen(vector_path, "r");
        if (file_handle == 0)
            $fatal(1, "cannot open wide stream vectors");
        capture_handle = 0;
        if ($value$plusargs("CAPTURE=%s", capture_path)) begin
            capture_handle = $fopen(capture_path, "w");
            if (capture_handle == 0)
                $fatal(1, "cannot open capture output");
        end
        for (input_index = 0; input_index < vector_count; input_index++) begin
            scan_count = $fscanf(file_handle, "%d\n", input_vector[input_index]);
            if (scan_count != 1)
                $fatal(1, "malformed input %0d", input_index);
        end
        scan_count = $fscanf(file_handle, "%s\n", marker);
        if (scan_count != 1 || marker != "EXPECTED")
            $fatal(1, "missing marker");
        for (output_index = 0; output_index < vector_count; output_index++) begin
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

        while (output_index < vector_count) begin
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
                if (capture_handle != 0)
                    $fwrite(capture_handle, "%0d %0d\n", output_index,
                            sample_output_q24);
                output_index = output_index + 1;
            end
            if ((clock_count % 2048) == 0 && input_index + 1 < vector_count) begin
                input_index = input_index + 1;
                sample_input_q24 <= input_vector[input_index];
                ce_input_48k <= 1'b1;
            end
            if (clock_count > vector_count * 2300)
                $fatal(1, "stream timeout output=%0d", output_index);
        end

        if (capture_handle != 0)
            $fclose(capture_handle);

        if (resampler_saturation_count != 0 || resampler_overrun_count != 0
            || input_phase_error_count != 0
            || output_conversion_saturation_count != 0
            || solver_missed_request_count != 0
            || solver_deadline_miss_count != 0
            || solver_saturation_count != 0 || solver_lut_clip_count != 0
            || solver_nonconvergence_count != 0
            || solver_correction_scale_fallback_count != 0
            || solver_minimum_correction_fractional_bits != 0
            || solver_latency_cycles != EXPECTED_SOLVER_LATENCY[7:0]
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
        $display("PASS: %0d exact wide 48 kHz outputs, solver latency=%0d clocks",
                 output_index, EXPECTED_SOLVER_LATENCY);
        $finish;
    end
endmodule

`default_nettype wire
