`timescale 1ns/1ps
`default_nettype none

module v1_solver_mono_tb #(
    parameter bit USE_FACTORIZED = 1'b0
);
    logic clk;
    logic rst_n = 1'b0;
    logic ce_sample = 1'b0;
    logic signed [31:0] input_q24;
    logic signed [31:0] output_q20;
    logic output_valid;
    logic busy;
    logic [7:0] sample_latency_cycles;
    logic [31:0] missed_request_count;
    logic [31:0] deadline_miss_count;
    logic [31:0] saturation_count;
    logic [31:0] lut_clip_count;
    logic [31:0] nonconvergence_count;
    logic [54:0] last_residual_q44;
    logic [287:0] node_voltage_debug;
    logic [319:0] capacitor_state_debug;

    v1_solver_mono #(
        .NODE_INITIAL_FILE(
            USE_FACTORIZED
                ? "model/generated/v1_node_initial_factorized.mem"
                : "model/generated/v1_node_initial.mem"
        ),
        .CAP_INITIAL_FILE(
            USE_FACTORIZED
                ? "model/generated/v1_cap_initial_factorized_q12_20.mem"
                : "model/generated/v1_cap_initial_q12_20.mem"
        ),
        .USE_FACTORIZED_TUBE(USE_FACTORIZED)
    ) dut (.*);

    always #5 clk = ~clk;

    integer file_handle;
    integer scan_count;
    integer vector_count;
    integer error_count;
    integer lane;
    integer timeout;
    logic signed [31:0] expected_node [0:8];
    logic signed [31:0] expected_capacitor [0:9];
    longint unsigned expected_residual;
    longint unsigned expected_saturation_count;
    longint unsigned expected_lut_clip_count;
    longint unsigned expected_nonconvergence_count;
    string vector_path;

    initial begin
        clk = 1'b0;
        if (!$value$plusargs("VECTORS=%s", vector_path)) begin
            if (USE_FACTORIZED)
                vector_path = "sim/vectors/generated/v1_solver_factorized_stream.txt";
            else
                vector_path = "sim/vectors/generated/v1_solver_stream.txt";
        end
        file_handle = $fopen(vector_path, "r");
        if (file_handle == 0) $fatal(1, "cannot open %s", vector_path);
        vector_count = 0;
        error_count = 0;
        input_q24 = '0;
        repeat (3) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);

        while (!$feof(file_handle)) begin
            scan_count = $fscanf(file_handle, "%d ", input_q24);
            for (lane = 0; lane < 9; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d ", expected_node[lane]);
            for (lane = 0; lane < 10; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d ", expected_capacitor[lane]);
            scan_count += $fscanf(
                file_handle, "%d %d %d %d\n", expected_residual,
                expected_saturation_count, expected_lut_clip_count,
                expected_nonconvergence_count
            );
            if (scan_count != 24) begin
                if (!$feof(file_handle))
                    $fatal(1, "malformed vector %0d fields=%0d", vector_count, scan_count);
            end else begin
                ce_sample <= 1'b1;
                @(posedge clk);
                #1;
                ce_sample <= 1'b0;
                if (!busy) $fatal(1, "sample %0d not accepted", vector_count);
                timeout = 0;
                while (!output_valid) begin
                    @(posedge clk);
                    #1;
                    timeout = timeout + 1;
                    if (timeout > 160)
                        $fatal(1, "sample %0d timed out", vector_count);
                end
                if (sample_latency_cycles > 8'd128) begin
                    $error("sample %0d missed deadline: latency %0d",
                           vector_count, sample_latency_cycles);
                    error_count = error_count + 1;
                end
                for (lane = 0; lane < 9; lane = lane + 1) begin
                    if ($signed(node_voltage_debug[lane * 32 +: 32]) !==
                        expected_node[lane]) begin
                        $error("sample %0d node %0d: got %0d expected %0d",
                               vector_count, lane,
                               $signed(node_voltage_debug[lane * 32 +: 32]),
                               expected_node[lane]);
                        error_count = error_count + 1;
                    end
                end
                for (lane = 0; lane < 10; lane = lane + 1) begin
                    if ($signed(capacitor_state_debug[lane * 32 +: 32]) !==
                        expected_capacitor[lane]) begin
                        $error("sample %0d capacitor %0d: got %0d expected %0d",
                               vector_count, lane,
                               $signed(capacitor_state_debug[lane * 32 +: 32]),
                               expected_capacitor[lane]);
                        error_count = error_count + 1;
                    end
                end
                if (output_q20 !== expected_node[8]) begin
                    $error("sample %0d output: got %0d expected %0d",
                           vector_count, output_q20, expected_node[8]);
                    error_count = error_count + 1;
                end
                if (last_residual_q44 !== expected_residual[54:0]) begin
                    $error("sample %0d residual: got %0d expected %0d",
                           vector_count, last_residual_q44, expected_residual);
                    error_count = error_count + 1;
                end
                if (saturation_count !== expected_saturation_count[31:0]) begin
                    $error("sample %0d saturation count: got %0d expected %0d",
                           vector_count, saturation_count, expected_saturation_count);
                    error_count = error_count + 1;
                end
                if (lut_clip_count !== expected_lut_clip_count[31:0]) begin
                    $error("sample %0d LUT clips: got %0d expected %0d",
                           vector_count, lut_clip_count, expected_lut_clip_count);
                    error_count = error_count + 1;
                end
                if (nonconvergence_count !== expected_nonconvergence_count[31:0]) begin
                    $error("sample %0d nonconvergence: got %0d expected %0d",
                           vector_count, nonconvergence_count,
                           expected_nonconvergence_count);
                    error_count = error_count + 1;
                end
                vector_count = vector_count + 1;
                @(posedge clk);
                #1;
            end
        end

        $fclose(file_handle);
        if (missed_request_count != 0 || deadline_miss_count != 0) begin
            $error("scheduler counters: missed=%0d deadline=%0d",
                   missed_request_count, deadline_miss_count);
            error_count = error_count + 1;
        end
        if (error_count != 0) $fatal(1, "FAIL: %0d errors", error_count);
        $display(
            "PASS: %0d sequential solver vectors, latency=%0d clocks",
            vector_count, sample_latency_cycles
        );
        $finish;
    end
endmodule

`default_nettype wire
