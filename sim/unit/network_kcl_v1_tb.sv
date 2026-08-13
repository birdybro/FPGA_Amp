`timescale 1ns/1ps
`default_nettype none

module network_kcl_v1_tb;
    logic clk;
    logic rst_n = 1'b0;
    logic start = 1'b0;
    logic signed [31:0] voltage [0:8];
    logic signed [54:0] rhs [0:8];
    logic signed [31:0] current [0:3];
    logic [287:0] voltage_flat;
    logic [494:0] rhs_flat;
    logic [127:0] current_flat;
    logic [224:0] residual_flat;
    logic signed [24:0] residual [0:8];
    logic [54:0] max_abs_residual;
    logic saturation_any;
    logic [3:0] saturation_count;
    logic busy;
    logic valid;

    network_kcl_v1 dut (
        .clk,
        .rst_n,
        .start,
        .voltage(voltage_flat),
        .rhs_q44(rhs_flat),
        .tube_current_valid(start),
        .tube_current_q31(current_flat),
        .residual_q30(residual_flat),
        .max_abs_residual_q44(max_abs_residual),
        .saturation_any,
        .saturation_count,
        .busy,
        .valid
    );

    always #5 clk = ~clk;
    always_comb begin
        for (int lane = 0; lane < 9; lane = lane + 1) begin
            voltage_flat[lane * 32 +: 32] = voltage[lane];
            rhs_flat[lane * 55 +: 55] = rhs[lane];
            residual[lane] = $signed(residual_flat[lane * 25 +: 25]);
        end
        for (int lane = 0; lane < 4; lane = lane + 1)
            current_flat[lane * 32 +: 32] = current[lane];
    end

    integer file_handle;
    integer scan_count;
    integer vector_count;
    integer error_count;
    integer lane;
    integer latency;
    logic signed [24:0] expected_residual [0:8];
    integer expected_saturation;
    integer expected_saturation_count;
    longint unsigned expected_max_abs;
    string vector_path;

    initial begin
        clk = 1'b0;
        if (!$value$plusargs("VECTORS=%s", vector_path))
            vector_path = "sim/vectors/generated/network_kcl_random.txt";
        file_handle = $fopen(vector_path, "r");
        if (file_handle == 0) $fatal(1, "cannot open %s", vector_path);
        vector_count = 0;
        error_count = 0;
        repeat (3) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        while (!$feof(file_handle)) begin
            scan_count = 0;
            for (lane = 0; lane < 9; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d ", voltage[lane]);
            for (lane = 0; lane < 9; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d ", rhs[lane]);
            for (lane = 0; lane < 4; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d ", current[lane]);
            for (lane = 0; lane < 9; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d ", expected_residual[lane]);
            scan_count += $fscanf(
                file_handle, "%d %d %d\n", expected_saturation,
                expected_saturation_count, expected_max_abs
            );
            if (scan_count != 34) begin
                if (!$feof(file_handle)) $fatal(1, "malformed vector %0d", vector_count);
            end else begin
                start <= 1'b1;
                @(posedge clk);
                #1;
                start <= 1'b0;
                if (!busy) $fatal(1, "request not accepted");
                latency = 0;
                while (!valid) begin
                    @(posedge clk);
                    #1;
                    latency = latency + 1;
                    if (latency > 12) $fatal(1, "timeout vector %0d", vector_count);
                end
                if (latency != 10) begin
                    $error("latency vector %0d: got %0d expected 10", vector_count, latency);
                    error_count = error_count + 1;
                end
                for (lane = 0; lane < 9; lane = lane + 1) begin
                    if (residual[lane] !== expected_residual[lane]) begin
                        $error("vector %0d lane %0d: got %0d expected %0d",
                               vector_count, lane, residual[lane], expected_residual[lane]);
                        error_count = error_count + 1;
                    end
                end
                if (saturation_any !== expected_saturation[0]) begin
                    $error("vector %0d saturation: got %0b expected %0d",
                           vector_count, saturation_any, expected_saturation);
                    error_count = error_count + 1;
                end
                if (saturation_count !== expected_saturation_count[3:0]) begin
                    $error("vector %0d saturation count: got %0d expected %0d",
                           vector_count, saturation_count, expected_saturation_count);
                    error_count = error_count + 1;
                end
                if ($unsigned(max_abs_residual) !== expected_max_abs[54:0]) begin
                    $error("vector %0d max: got %0d expected %0d",
                           vector_count, max_abs_residual, expected_max_abs);
                    error_count = error_count + 1;
                end
                vector_count = vector_count + 1;
                @(posedge clk);
                #1;
            end
        end
        $fclose(file_handle);
        if (error_count != 0) $fatal(1, "FAIL: %0d errors", error_count);
        $display("PASS: %0d KCL vectors, latency=10 clocks", vector_count);
        $finish;
    end
endmodule

`default_nettype wire
