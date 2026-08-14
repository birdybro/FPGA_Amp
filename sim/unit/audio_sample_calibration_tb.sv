`timescale 1ns/1ps
`default_nettype none

module audio_sample_calibration_tb;
    logic clk;
    logic rst_n = 1'b0;
    logic clear_diagnostics = 1'b0;

    logic input_valid = 1'b0;
    logic signed [23:0] sample_input_pcm24 = '0;
    logic signed [31:0] full_scale_peak_volts_q24 = '0;
    logic signed [31:0] sample_output_q24;
    logic input_output_valid;
    logic [31:0] pcm_endpoint_count;
    logic input_configuration_error;

    logic output_input_valid = 1'b0;
    logic signed [31:0] output_sample_input_q24 = '0;
    logic signed [31:0] reciprocal_full_scale_per_volt_q24 = '0;
    logic signed [23:0] sample_output_pcm24;
    logic output_output_valid;
    logic [31:0] saturation_count;
    logic output_configuration_error;

    integer errors;
    integer input_vector_count;
    integer output_vector_count;
    integer expected_endpoint_count;
    integer expected_saturation_count;
    logic expected_input_configuration_error;
    logic expected_output_configuration_error;
    integer input_file;
    integer output_file;
    integer scan_count;
    integer sample_value;
    integer coefficient_value;
    integer expected_value;
    integer expected_event;
    integer expected_invalid;
    string input_path;
    string output_path;
    string line;

    pcm24_to_q8_24 input_calibration (
        .clk,
        .rst_n,
        .input_valid,
        .sample_input_pcm24,
        .full_scale_peak_volts_q24,
        .clear_diagnostics,
        .sample_output_q24,
        .output_valid(input_output_valid),
        .pcm_endpoint_count,
        .configuration_error_sticky(input_configuration_error)
    );

    q8_24_to_pcm24 output_calibration (
        .clk,
        .rst_n,
        .input_valid(output_input_valid),
        .sample_input_q24(output_sample_input_q24),
        .reciprocal_full_scale_per_volt_q24,
        .clear_diagnostics,
        .sample_output_pcm24,
        .output_valid(output_output_valid),
        .saturation_count,
        .configuration_error_sticky(output_configuration_error)
    );

    always #5 clk = ~clk;

    task automatic check_input_vector;
        begin
            @(negedge clk);
            sample_input_pcm24 = 24'(sample_value);
            full_scale_peak_volts_q24 = coefficient_value;
            input_valid = 1'b1;
            @(posedge clk);
            #1;
            if (!input_output_valid) begin
                $error("missing PCM-to-volts valid at vector %0d", input_vector_count);
                errors = errors + 1;
            end
            if ($signed(sample_output_q24) !== expected_value) begin
                $error("PCM-to-volts vector %0d got=%0d expected=%0d",
                       input_vector_count, $signed(sample_output_q24), expected_value);
                errors = errors + 1;
            end
            expected_endpoint_count = expected_endpoint_count + expected_event;
            if (expected_invalid != 0)
                expected_input_configuration_error = 1;
            input_vector_count = input_vector_count + 1;
            @(negedge clk);
            input_valid = 1'b0;
            @(posedge clk);
            #1;
            if (input_output_valid) begin
                $error("PCM-to-volts valid did not pulse");
                errors = errors + 1;
            end
        end
    endtask

    task automatic check_output_vector;
        begin
            @(negedge clk);
            output_sample_input_q24 = sample_value;
            reciprocal_full_scale_per_volt_q24 = coefficient_value;
            output_input_valid = 1'b1;
            @(posedge clk);
            #1;
            if (!output_output_valid) begin
                $error("missing volts-to-PCM valid at vector %0d", output_vector_count);
                errors = errors + 1;
            end
            if (32'($signed(sample_output_pcm24)) !== expected_value) begin
                $error("volts-to-PCM vector %0d got=%0d expected=%0d",
                       output_vector_count, $signed(sample_output_pcm24), expected_value);
                errors = errors + 1;
            end
            expected_saturation_count = expected_saturation_count + expected_event;
            if (expected_invalid != 0)
                expected_output_configuration_error = 1;
            output_vector_count = output_vector_count + 1;
            @(negedge clk);
            output_input_valid = 1'b0;
            @(posedge clk);
            #1;
            if (output_output_valid) begin
                $error("volts-to-PCM valid did not pulse");
                errors = errors + 1;
            end
        end
    endtask

    initial begin
        clk = 1'b0;
        errors = 0;
        input_vector_count = 0;
        output_vector_count = 0;
        expected_endpoint_count = 0;
        expected_saturation_count = 0;
        expected_input_configuration_error = 1'b0;
        expected_output_configuration_error = 1'b0;
        repeat (3) @(posedge clk);
        #1;
        rst_n = 1'b1;

        if (!$value$plusargs("INPUT_VECTORS=%s", input_path))
            input_path = "sim/vectors/generated/pcm24_to_q8_24.txt";
        input_file = $fopen(input_path, "r");
        if (input_file == 0)
            $fatal(1, "cannot open vectors: %s", input_path);
        void'($fgets(line, input_file));
        $display("Input vector header: %s", line);
        while (!$feof(input_file)) begin
            scan_count = $fscanf(
                input_file,
                "%d %d %d %d %d\n",
                sample_value,
                coefficient_value,
                expected_value,
                expected_event,
                expected_invalid
            );
            if (scan_count == 5)
                check_input_vector();
        end
        $fclose(input_file);

        if (pcm_endpoint_count !== expected_endpoint_count) begin
            $error("endpoint count got=%0d expected=%0d",
                   pcm_endpoint_count, expected_endpoint_count);
            errors = errors + 1;
        end
        if (input_configuration_error
            !== expected_input_configuration_error) begin
            $error("input configuration diagnostic mismatch");
            errors = errors + 1;
        end

        if (!$value$plusargs("OUTPUT_VECTORS=%s", output_path))
            output_path = "sim/vectors/generated/q8_24_to_pcm24.txt";
        output_file = $fopen(output_path, "r");
        if (output_file == 0)
            $fatal(1, "cannot open vectors: %s", output_path);
        void'($fgets(line, output_file));
        $display("Output vector header: %s", line);
        while (!$feof(output_file)) begin
            scan_count = $fscanf(
                output_file,
                "%d %d %d %d %d\n",
                sample_value,
                coefficient_value,
                expected_value,
                expected_event,
                expected_invalid
            );
            if (scan_count == 5)
                check_output_vector();
        end
        $fclose(output_file);

        if (saturation_count !== expected_saturation_count) begin
            $error("saturation count got=%0d expected=%0d",
                   saturation_count, expected_saturation_count);
            errors = errors + 1;
        end
        if (output_configuration_error
            !== expected_output_configuration_error) begin
            $error("output configuration diagnostic mismatch");
            errors = errors + 1;
        end

        clear_diagnostics = 1'b1;
        @(posedge clk);
        #1;
        clear_diagnostics = 1'b0;
        if (pcm_endpoint_count != 0 || saturation_count != 0
            || input_configuration_error || output_configuration_error) begin
            $error("calibration diagnostics did not clear");
            errors = errors + 1;
        end

        if (errors != 0)
            $fatal(1, "FAIL: %0d calibration errors", errors);
        $display(
            "PASS: %0d PCM-to-volts and %0d volts-to-PCM exact vectors",
            input_vector_count,
            output_vector_count
        );
        $finish;
    end
endmodule

`default_nettype wire
