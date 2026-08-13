`timescale 1ns/1ps
`default_nettype none

module network_rhs_v1_tb;
    logic clk;
    logic rst_n = 1'b0;
    logic start = 1'b0;
    logic signed [31:0] input_q24;
    logic signed [31:0] capacitor_state [0:9];
    logic [319:0] capacitor_state_flat;
    logic [494:0] rhs_flat;
    logic signed [54:0] rhs [0:8];
    logic busy;
    logic valid;

    network_rhs_v1 dut (
        .clk,
        .rst_n,
        .start,
        .input_q24,
        .capacitor_state_q20(capacitor_state_flat),
        .rhs_q44(rhs_flat),
        .busy,
        .valid
    );

    always #5 clk = ~clk;
    always_comb begin
        for (int lane = 0; lane < 10; lane = lane + 1)
            capacitor_state_flat[lane * 32 +: 32] = capacitor_state[lane];
        for (int lane = 0; lane < 9; lane = lane + 1)
            rhs[lane] = $signed(rhs_flat[lane * 55 +: 55]);
    end

    integer file_handle;
    integer scan_count;
    integer vector_count;
    integer error_count;
    integer lane;
    integer latency;
    longint signed expected_rhs [0:8];
    string vector_path;

    initial begin
        clk = 1'b0;
        if (!$value$plusargs("VECTORS=%s", vector_path))
            vector_path = "sim/vectors/generated/network_rhs_random.txt";
        file_handle = $fopen(vector_path, "r");
        if (file_handle == 0) $fatal(1, "cannot open %s", vector_path);
        vector_count = 0;
        error_count = 0;
        repeat (3) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        while (!$feof(file_handle)) begin
            scan_count = $fscanf(file_handle, "%d ", input_q24);
            for (lane = 0; lane < 10; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d ", capacitor_state[lane]);
            for (lane = 0; lane < 9; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d ", expected_rhs[lane]);
            if (scan_count != 20) begin
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
                    if (latency > 14) $fatal(1, "timeout vector %0d", vector_count);
                end
                if (latency != 12) begin
                    $error("latency vector %0d: got %0d expected 12", vector_count, latency);
                    error_count = error_count + 1;
                end
                for (lane = 0; lane < 9; lane = lane + 1) begin
                    if ($signed({{9{rhs[lane][54]}}, rhs[lane]}) !==
                        expected_rhs[lane]) begin
                        $error("vector %0d lane %0d: got %0d expected %0d",
                               vector_count, lane, rhs[lane], expected_rhs[lane]);
                        error_count = error_count + 1;
                    end
                end
                vector_count = vector_count + 1;
                @(posedge clk);
                #1;
            end
        end
        $fclose(file_handle);
        if (error_count != 0) $fatal(1, "FAIL: %0d errors", error_count);
        $display("PASS: %0d RHS vectors, latency=12 clocks", vector_count);
        $finish;
    end
endmodule

`default_nettype wire
