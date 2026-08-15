`timescale 1ns/1ps
`default_nettype none

module v1_solver_mono_wide_tb #(
    parameter bit TRAPEZOIDAL = 1'b0,
    parameter bit SAMPLE_RATE_384KHZ = 1'b0,
    parameter bit BANKED = 1'b0,
    parameter bit TERMINAL_CORRECTION = 1'b0,
    parameter bit LINEAR_TUBE = 1'b0,
    parameter bit PARALLEL_TUBES = 1'b0,
    parameter bit PIPELINED_KCL_FINISH = 1'b0,
    parameter bit PIPELINED_KCL_COLUMNS = 1'b0,
    parameter bit PIPELINED_KCL_ACCUMULATOR = 1'b0,
    parameter bit PIPELINED_KCL_CAPACITOR_CURRENT = 1'b0,
    parameter bit PIPELINED_KCL_MAXIMUM = 1'b0,
    parameter bit DECOUPLED_KCL_MAXIMUM = 1'b0,
    parameter bit SHARED_KCL_CAPACITOR_MULTIPLIER = 1'b0,
    parameter bit PIPELINED_CHORD_APPLY = 1'b0,
    parameter bit HALF_PARALLEL_TERMINAL_CURRENT = 1'b0
);
    localparam integer BASE_LATENCY = PARALLEL_TUBES
        ? (TERMINAL_CORRECTION ? 95 : 84)
        : (TERMINAL_CORRECTION ? 127 : 116);
    localparam integer EXPECTED_LATENCY = BASE_LATENCY
        + (PIPELINED_KCL_FINISH ? 8 : 0)
        + (PIPELINED_KCL_COLUMNS ? 8 : 0)
        + ((PIPELINED_KCL_COLUMNS && PIPELINED_KCL_ACCUMULATOR) ? 4 : 0)
        + ((PIPELINED_KCL_COLUMNS
            && PIPELINED_KCL_CAPACITOR_CURRENT) ? 4 : 0)
        + ((PIPELINED_KCL_FINISH && PIPELINED_KCL_MAXIMUM
            && !DECOUPLED_KCL_MAXIMUM) ? 3 : 0)
        + (PIPELINED_CHORD_APPLY ? (TERMINAL_CORRECTION ? 8 : 6) : 0)
        + (HALF_PARALLEL_TERMINAL_CURRENT ? 1 : 0);
    logic clk;
    logic rst_n = 1'b0;
    logic ce_sample = 1'b0;
    logic signed [31:0] input_q24;
    logic signed [39:0] output_q32;
    logic output_valid;
    logic busy;
    logic [7:0] sample_latency_cycles;
    logic [31:0] missed_request_count;
    logic [31:0] deadline_miss_count;
    logic [31:0] saturation_count;
    logic [31:0] lut_clip_count;
    logic [31:0] nonconvergence_count;
    logic [31:0] correction_scale_fallback_count;
    logic [5:0] minimum_correction_fractional_bits;
    logic [62:0] last_residual_q44;
    logic [359:0] node_voltage_debug;
    logic [399:0] capacitor_state_debug;
    logic [479:0] capacitor_current_state_debug;

    v1_solver_mono_wide #(
        .NODE_INITIAL_FILE(
            TRAPEZOIDAL
                ? (SAMPLE_RATE_384KHZ
                   ? "model/generated/v1_node_initial_wide_trapezoidal_384khz.mem"
                   : "model/generated/v1_node_initial_wide_trapezoidal.mem")
                : "model/generated/v1_node_initial_wide.mem"
        ),
        .CAP_INITIAL_FILE(
            TRAPEZOIDAL
                ? (SAMPLE_RATE_384KHZ
                   ? "model/generated/v1_cap_initial_q30_wide_trapezoidal_384khz.mem"
                   : "model/generated/v1_cap_initial_q30_wide_trapezoidal.mem")
                : "model/generated/v1_cap_initial_q30_wide.mem"
        ),
        .CAP_CURRENT_INITIAL_FILE(
            SAMPLE_RATE_384KHZ
                ? "model/generated/v1_cap_current_initial_q4_44_trapezoidal_384khz.mem"
                : "model/generated/v1_cap_current_initial_q4_44_trapezoidal.mem"
        ),
        .CAP_G_FILE(
            TRAPEZOIDAL
                ? (SAMPLE_RATE_384KHZ
                   ? "model/generated/v1_cap_conductance_q0_47_trapezoidal_384khz.mem"
                   : "model/generated/v1_cap_conductance_q0_47_trapezoidal.mem")
                : "model/generated/v1_cap_conductance_q0_47.mem"
        ),
        .CHORD_COEFFICIENT_FILE(
            BANKED
                ? (TRAPEZOIDAL
                   ? (SAMPLE_RATE_384KHZ
                      ? "model/generated/v1_chord_inverse_banked_q17_1_trapezoidal_384khz.mem"
                      : "model/generated/v1_chord_inverse_banked_q17_1_trapezoidal.mem")
                   : "model/generated/v1_chord_inverse_banked_q17_1.mem")
                : (TRAPEZOIDAL
                   ? (SAMPLE_RATE_384KHZ
                      ? "model/generated/v1_chord_inverse_q17_1_trapezoidal_384khz.mem"
                      : "model/generated/v1_chord_inverse_q17_1_trapezoidal.mem")
                   : "model/generated/v1_chord_inverse_q17_1.mem")
        ),
        .CHORD_COEFFICIENT_SETS(BANKED ? (TRAPEZOIDAL ? 5 : 4) : 1),
        .CHORD_COEFFICIENT_WIDTH(SAMPLE_RATE_384KHZ ? 19 : 18),
        .SAMPLE_RATE_384KHZ(SAMPLE_RATE_384KHZ),
        .TRAPEZOIDAL(TRAPEZOIDAL),
        .TERMINAL_CORRECTION(TERMINAL_CORRECTION),
        .USE_LINEAR_FACTORIZED_TUBE(LINEAR_TUBE),
        .PARALLEL_TUBES(PARALLEL_TUBES),
        .PIPELINED_KCL_FINISH(PIPELINED_KCL_FINISH),
        .PIPELINED_KCL_COLUMNS(PIPELINED_KCL_COLUMNS),
        .PIPELINED_KCL_ACCUMULATOR(PIPELINED_KCL_ACCUMULATOR),
        .PIPELINED_KCL_CAPACITOR_CURRENT(PIPELINED_KCL_CAPACITOR_CURRENT),
        .PIPELINED_KCL_MAXIMUM(PIPELINED_KCL_MAXIMUM),
        .DECOUPLED_KCL_MAXIMUM(DECOUPLED_KCL_MAXIMUM),
        .SHARED_KCL_CAPACITOR_MULTIPLIER(
            SHARED_KCL_CAPACITOR_MULTIPLIER
        ),
        .PIPELINED_CHORD_APPLY(PIPELINED_CHORD_APPLY),
        .HALF_PARALLEL_TERMINAL_CURRENT(
            HALF_PARALLEL_TERMINAL_CURRENT
        )
    ) dut (.*);
    always #5 clk = ~clk;

    integer file_handle;
    integer capture_handle;
    integer scan_count;
    integer vector_count = 0;
    integer errors = 0;
    integer timeout;
    longint signed expected_node [0:8];
    longint signed expected_capacitor [0:9];
    longint signed expected_capacitor_current [0:9];
    logic [62:0] expected_residual;
    logic [31:0] expected_saturation_count;
    logic [31:0] expected_lut_clip_count;
    logic [31:0] expected_nonconvergence_count;
    logic [31:0] expected_fallback_count;
    logic [5:0] expected_minimum_fraction;
    string vector_path;
    string capture_path;

    initial begin
        clk = 1'b0;
        input_q24 = '0;
        if (SAMPLE_RATE_384KHZ && !TRAPEZOIDAL)
            $fatal(1, "384 kHz study requires trapezoidal state assets");
        if (!$value$plusargs("VECTORS=%s", vector_path)) begin
            if (SAMPLE_RATE_384KHZ && BANKED && TERMINAL_CORRECTION)
                vector_path = "sim/vectors/generated/v1_solver_wide_factorized_stream_trapezoidal_384khz_banked_terminal.txt";
            else if (SAMPLE_RATE_384KHZ && BANKED)
                vector_path = "sim/vectors/generated/v1_solver_wide_factorized_stream_trapezoidal_384khz_banked.txt";
            else if (SAMPLE_RATE_384KHZ && TERMINAL_CORRECTION)
                vector_path = "sim/vectors/generated/v1_solver_wide_factorized_stream_trapezoidal_384khz_terminal.txt";
            else if (SAMPLE_RATE_384KHZ)
                vector_path = "sim/vectors/generated/v1_solver_wide_factorized_stream_trapezoidal_384khz.txt";
            else if (TRAPEZOIDAL && BANKED && TERMINAL_CORRECTION)
                vector_path = "sim/vectors/generated/v1_solver_wide_factorized_stream_trapezoidal_banked_terminal.txt";
            else if (TRAPEZOIDAL && TERMINAL_CORRECTION)
                vector_path = "sim/vectors/generated/v1_solver_wide_factorized_stream_trapezoidal_terminal.txt";
            else if (TRAPEZOIDAL && BANKED)
                vector_path = "sim/vectors/generated/v1_solver_wide_factorized_stream_trapezoidal_banked.txt";
            else if (TRAPEZOIDAL)
                vector_path = "sim/vectors/generated/v1_solver_wide_factorized_stream_trapezoidal.txt";
            else if (BANKED && TERMINAL_CORRECTION)
                vector_path = "sim/vectors/generated/v1_solver_wide_factorized_stream_banked_terminal.txt";
            else if (BANKED)
                vector_path = "sim/vectors/generated/v1_solver_wide_factorized_stream_banked.txt";
            else if (TERMINAL_CORRECTION)
                vector_path = "sim/vectors/generated/v1_solver_wide_factorized_stream_terminal.txt";
            else
                vector_path = "sim/vectors/generated/v1_solver_wide_factorized_stream.txt";
        end
        file_handle = $fopen(vector_path, "r");
        if (file_handle == 0)
            $fatal(1, "cannot open wide solver vectors");
        capture_handle = 0;
        if ($value$plusargs("CAPTURE=%s", capture_path)) begin
            capture_handle = $fopen(capture_path, "w");
            if (capture_handle == 0)
                $fatal(1, "cannot open capture output");
        end
        repeat (3) @(posedge clk);
        rst_n = 1'b1;
        @(posedge clk);

        while (!$feof(file_handle)) begin
            scan_count = $fscanf(file_handle, "%d", input_q24);
            if (scan_count != 1)
                break;
            for (integer lane = 0; lane < 9; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d", expected_node[lane]);
            for (integer lane = 0; lane < 10; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d", expected_capacitor[lane]);
            if (TRAPEZOIDAL)
                for (integer lane = 0; lane < 10; lane = lane + 1)
                    scan_count += $fscanf(
                        file_handle, "%d", expected_capacitor_current[lane]
                    );
            scan_count += $fscanf(
                file_handle, "%d %d %d %d %d %d\n",
                expected_residual, expected_saturation_count,
                expected_lut_clip_count, expected_nonconvergence_count,
                expected_fallback_count, expected_minimum_fraction
            );
            if (scan_count != (TRAPEZOIDAL ? 36 : 26))
                $fatal(1, "malformed vector %0d fields=%0d", vector_count, scan_count);

            if (busy)
                $fatal(1, "solver busy before sample %0d request", vector_count);
            ce_sample <= 1'b1;
            @(posedge clk);
            #1;
            ce_sample <= 1'b0;
            if (!busy)
                $fatal(1, "sample %0d was not accepted", vector_count);
            timeout = 0;
            while (!output_valid) begin
                @(posedge clk);
                #1;
                timeout = timeout + 1;
                if (timeout > 140)
                    $fatal(1, "sample %0d timed out", vector_count);
            end
            if (sample_latency_cycles != EXPECTED_LATENCY[7:0]) begin
                $error("sample %0d latency got=%0d expected=%0d",
                       vector_count, sample_latency_cycles, EXPECTED_LATENCY);
                errors = errors + 1;
            end
            for (integer lane = 0; lane < 9; lane = lane + 1) begin
                if ($signed(node_voltage_debug[lane * 40 +: 40])
                    !== $signed(expected_node[lane][39:0])) begin
                    $error("sample=%0d node=%0d got=%0d expected=%0d",
                           vector_count, lane,
                           $signed(node_voltage_debug[lane * 40 +: 40]),
                           expected_node[lane]);
                    errors = errors + 1;
                end
            end
            for (integer lane = 0; lane < 10; lane = lane + 1) begin
                if ($signed(capacitor_state_debug[lane * 40 +: 40])
                    !== $signed(expected_capacitor[lane][39:0])) begin
                    $error("sample=%0d capacitor=%0d got=%0d expected=%0d",
                           vector_count, lane,
                           $signed(capacitor_state_debug[lane * 40 +: 40]),
                           expected_capacitor[lane]);
                    errors = errors + 1;
                end
                if (TRAPEZOIDAL
                    && $signed(capacitor_current_state_debug[lane * 48 +: 48])
                       !== $signed(expected_capacitor_current[lane][47:0])) begin
                    $error("sample=%0d capacitor_current=%0d got=%0d expected=%0d",
                           vector_count, lane,
                           $signed(capacitor_current_state_debug[lane * 48 +: 48]),
                           expected_capacitor_current[lane]);
                    errors = errors + 1;
                end
            end
            if (output_q32 !== $signed(expected_node[8][39:0])) begin
                $error("sample=%0d output got=%0d expected=%0d",
                       vector_count, output_q32, expected_node[8]);
                errors = errors + 1;
            end
            if (capture_handle != 0)
                $fwrite(capture_handle, "%0d %0d\n", vector_count, output_q32);
            if (last_residual_q44 !== expected_residual
                || saturation_count !== expected_saturation_count
                || lut_clip_count !== expected_lut_clip_count
                || nonconvergence_count !== expected_nonconvergence_count
                || correction_scale_fallback_count
                   !== expected_fallback_count
                || minimum_correction_fractional_bits
                   !== expected_minimum_fraction) begin
                $error("sample=%0d diagnostics got residual=%0d sat=%0d lut=%0d conv=%0d fallback=%0d min=%0d",
                       vector_count, last_residual_q44, saturation_count,
                       lut_clip_count, nonconvergence_count,
                       correction_scale_fallback_count,
                       minimum_correction_fractional_bits);
                errors = errors + 1;
            end
            vector_count = vector_count + 1;
            @(posedge clk);
            #1;
        end
        $fclose(file_handle);
        if (capture_handle != 0)
            $fclose(capture_handle);
        if (missed_request_count != 0 || deadline_miss_count != 0) begin
            $error("scheduler counters missed=%0d deadline=%0d",
                   missed_request_count, deadline_miss_count);
            errors = errors + 1;
        end
        if (errors != 0)
            $fatal(1, "FAIL: %0d wide solver errors", errors);
        $display("PASS: %0d wide solver vectors, latency=%0d clocks",
                 vector_count, EXPECTED_LATENCY);
        $finish;
    end
endmodule

`default_nettype wire
