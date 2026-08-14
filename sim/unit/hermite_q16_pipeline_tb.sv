`timescale 1ns/1ps
`default_nettype none

module hermite_q16_pipeline_tb;
    logic clk;
    logic rst_n = 1'b0;
    logic start = 1'b0;
    logic signed [31:0] y0 = '0;
    logic signed [31:0] y1 = '0;
    logic signed [31:0] m0 = '0;
    logic signed [31:0] m1 = '0;
    logic [15:0] fraction = '0;
    logic signed [31:0] result;
    logic busy;
    logic valid;

    integer vector_file;
    integer scan_count;
    integer y0_vector;
    integer y1_vector;
    integer m0_vector;
    integer m1_vector;
    logic [15:0] fraction_vector;
    integer result_expected;
    integer vector_count = 0;
    integer error_count = 0;
    integer latency_cycles;
    string line;
    string vector_path;

    always #5 clk = ~clk;

    hermite_q16_pipeline dut (.*);

    // Preserve the exact combinational function formerly embedded in the
    // factorized tube as an independent compatibility oracle.
    function automatic logic signed [31:0] legacy_hermite_q16(
        input logic signed [31:0] value_y0,
        input logic signed [31:0] value_y1,
        input logic signed [31:0] value_m0,
        input logic signed [31:0] value_m1,
        input logic        [15:0] value_fraction
    );
        logic signed [31:0] delta;
        logic signed [31:0] coefficient_2;
        logic signed [31:0] coefficient_3;
        logic signed [48:0] product;
        logic signed [31:0] value_stage;
        logic signed [16:0] fraction_signed;
        begin
            fraction_signed = $signed({1'b0, value_fraction});
            delta = value_y1 - value_y0;
            coefficient_2 = 3 * delta - 2 * value_m0 - value_m1;
            coefficient_3 = -2 * delta + value_m0 + value_m1;
            product = coefficient_3 * fraction_signed;
            value_stage = 32'(($signed(product) + 49'sd32768) >>> 16)
                        + coefficient_2;
            product = value_stage * fraction_signed;
            value_stage = 32'(($signed(product) + 49'sd32768) >>> 16)
                        + value_m0;
            product = value_stage * fraction_signed;
            value_stage = 32'(($signed(product) + 49'sd32768) >>> 16)
                        + value_y0;
            legacy_hermite_q16 = value_stage;
        end
    endfunction

    initial begin
        clk = 1'b0;
        repeat (3) @(negedge clk);
        rst_n = 1'b1;
        @(negedge clk);

        if (!$value$plusargs("VECTORS=%s", vector_path))
            vector_path = "sim/vectors/generated/hermite_q16_random.txt";
        vector_file = $fopen(vector_path, "r");
        if (vector_file == 0)
            $fatal(1, "cannot open vectors: %s", vector_path);

        void'($fgets(line, vector_file));
        $display("Vector header: %s", line);
        while (!$feof(vector_file)) begin
            scan_count = $fscanf(
                vector_file,
                "%d %d %d %d %d %d\n",
                y0_vector,
                y1_vector,
                m0_vector,
                m1_vector,
                fraction_vector,
                result_expected
            );
            if (scan_count == 6) begin
                y0 = y0_vector;
                y1 = y1_vector;
                m0 = m0_vector;
                m1 = m1_vector;
                fraction = fraction_vector;
                if ($signed(legacy_hermite_q16(y0, y1, m0, m1, fraction))
                    !== result_expected) begin
                    $error("Python/legacy mismatch vector=%0d", vector_count);
                    error_count = error_count + 1;
                end
                start = 1'b1;
                @(negedge clk);
                start = 1'b0;
                if (!busy) begin
                    $error("busy did not assert for vector %0d", vector_count);
                    error_count = error_count + 1;
                end

                // A second request during the first transaction must be
                // ignored; the accepted operands and exact latency survive.
                if (vector_count == 0) begin
                    y0 = 32'sh7fff_ffff;
                    y1 = -32'sh7fff_ffff;
                    m0 = 32'sh5555_aaaa;
                    m1 = -32'sh1234_5678;
                    fraction = 16'hffff;
                    start = 1'b1;
                    @(negedge clk);
                    start = 1'b0;
                    latency_cycles = 1;
                end else begin
                    latency_cycles = 0;
                end
                do begin
                    @(negedge clk);
                    latency_cycles = latency_cycles + 1;
                end while (!valid && latency_cycles < 8);

                if (!valid) begin
                    $error("timeout at vector %0d", vector_count);
                    error_count = error_count + 1;
                end else begin
                    if ($signed(result) !== result_expected) begin
                        $error(
                            "result mismatch vector=%0d got=%0d expected=%0d",
                            vector_count, $signed(result), result_expected
                        );
                        error_count = error_count + 1;
                    end
                    if (latency_cycles != 3) begin
                        $error(
                            "latency=%0d expected=3 vector=%0d",
                            latency_cycles, vector_count
                        );
                        error_count = error_count + 1;
                    end
                    if (busy) begin
                        $error("busy remained set with valid");
                        error_count = error_count + 1;
                    end
                end
                vector_count = vector_count + 1;
            end
        end
        $fclose(vector_file);

        // Reset must cancel an in-flight operation without emitting valid.
        start = 1'b1;
        @(negedge clk);
        start = 1'b0;
        rst_n = 1'b0;
        @(negedge clk);
        rst_n = 1'b1;
        repeat (4) begin
            @(negedge clk);
            if (valid) begin
                $error("valid asserted after an in-flight reset");
                error_count = error_count + 1;
            end
        end
        if (busy) begin
            $error("busy remained set after reset");
            error_count = error_count + 1;
        end

        if (error_count != 0)
            $fatal(1, "FAIL: %0d errors across %0d vectors", error_count, vector_count);
        $display(
            "PASS: %0d bit-exact Hermite vectors, latency=3 clocks",
            vector_count
        );
        $finish;
    end
endmodule

`default_nettype wire
