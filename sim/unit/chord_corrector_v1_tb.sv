`timescale 1ns/1ps
`default_nettype none

module chord_corrector_v1_tb;
    logic clk;
    logic rst_n = 1'b0;
    logic start = 1'b0;
    logic signed [31:0] voltage [0:8];
    logic signed [24:0] residual [0:8];
    logic signed [31:0] corrected [0:8];
    logic [287:0] voltage_flat;
    logic [224:0] residual_flat;
    logic [287:0] corrected_flat;
    logic saturation_any;
    logic busy;
    logic valid;

    chord_corrector_v1 dut (
        .clk,
        .rst_n,
        .start,
        .voltage(voltage_flat),
        .residual_q30(residual_flat),
        .corrected_voltage(corrected_flat),
        .saturation_any,
        .busy,
        .valid
    );

    always #5 clk = ~clk;

    always_comb begin
        for (int pack_row = 0; pack_row < 9; pack_row = pack_row + 1) begin
            voltage_flat[pack_row * 32 +: 32] = voltage[pack_row];
            residual_flat[pack_row * 25 +: 25] = residual[pack_row];
            corrected[pack_row] = $signed(
                corrected_flat[pack_row * 32 +: 32]
            );
        end
    end

    integer file_handle;
    integer scan_count;
    integer vector_count;
    integer error_count;
    integer row;
    integer latency;
    integer expected [0:8];
    integer expected_saturation;
    string vector_path;

    initial begin
        clk = 1'b0;
        if (!$value$plusargs("VECTORS=%s", vector_path))
            vector_path = "sim/vectors/generated/chord_corrector_random.txt";
        file_handle = $fopen(vector_path, "r");
        if (file_handle == 0) $fatal(1, "cannot open %s", vector_path);
        vector_count = 0;
        error_count = 0;
        repeat (3) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);

        while (!$feof(file_handle)) begin
            scan_count = 0;
            for (row = 0; row < 9; row = row + 1)
                scan_count += $fscanf(file_handle, "%d ", voltage[row]);
            for (row = 0; row < 9; row = row + 1)
                scan_count += $fscanf(file_handle, "%d ", residual[row]);
            for (row = 0; row < 9; row = row + 1)
                scan_count += $fscanf(file_handle, "%d ", expected[row]);
            scan_count += $fscanf(file_handle, "%d\n", expected_saturation);
            if (scan_count != 28) begin
                if (!$feof(file_handle)) $fatal(1, "malformed vector %0d", vector_count);
            end else begin
                start <= 1'b1;
                @(posedge clk);
                #1;
                start <= 1'b0;
                if (!busy) $fatal(1, "request was not accepted");
                latency = 0;
                while (!valid) begin
                    @(posedge clk);
                    #1;
                    latency = latency + 1;
                    if (latency > 12) $fatal(1, "timeout at vector %0d", vector_count);
                end
                if (latency != 10) begin
                    $error("latency vector %0d: got %0d expected 10", vector_count, latency);
                    error_count = error_count + 1;
                end
                for (row = 0; row < 9; row = row + 1) begin
                    if (corrected[row] !== expected[row]) begin
                        $error("vector %0d row %0d: got %0d expected %0d",
                               vector_count, row, corrected[row], expected[row]);
                        error_count = error_count + 1;
                    end
                end
                if (saturation_any !== expected_saturation[0]) begin
                    $error("vector %0d saturation: got %0b expected %0d",
                           vector_count, saturation_any, expected_saturation);
                    error_count = error_count + 1;
                end
                vector_count = vector_count + 1;
                @(posedge clk);
                #1;
            end
        end
        $fclose(file_handle);
        if (error_count != 0) $fatal(1, "FAIL: %0d errors", error_count);
        $display("PASS: %0d chord vectors, latency=10 clocks", vector_count);
        $finish;
    end
endmodule

`default_nettype wire
