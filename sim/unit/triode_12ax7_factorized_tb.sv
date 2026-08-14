`timescale 1ns/1ps
`default_nettype none

module triode_12ax7_factorized_tb;
    logic clk;
    logic rst_n = 1'b0;
    logic ce = 1'b0;
    logic signed [31:0] v_gk = '0;
    logic signed [31:0] v_pk = '0;
    logic signed [31:0] i_p;
    logic signed [31:0] i_g;
    logic range_clipped;
    logic valid;

    integer vector_file;
    integer scan_count;
    integer vg_vector;
    integer vp_vector;
    integer ip_expected;
    integer ig_expected;
    integer clipped_expected;
    integer vector_count = 0;
    integer clipped_count = 0;
    integer error_count = 0;
    integer latency_cycles;
    string line;
    string vector_path;

    always #5 clk = ~clk;

`ifdef LINEAR_FACTORIZED
    triode_12ax7_factorized_linear dut (
`else
    triode_12ax7_factorized dut (
`endif
        .clk,
        .rst_n,
        .ce,
        .v_gk,
        .v_pk,
        .i_p,
        .i_g,
        .range_clipped,
        .valid
    );

    initial begin
        clk = 1'b0;
        repeat (3) @(negedge clk);
        rst_n = 1'b1;
        @(negedge clk);

        if (!$value$plusargs("VECTORS=%s", vector_path)) begin
`ifdef LINEAR_FACTORIZED
            vector_path = "sim/vectors/generated/triode_factorized_linear_random.txt";
`else
            vector_path = "sim/vectors/generated/triode_factorized_random.txt";
`endif
        end
        vector_file = $fopen(vector_path, "r");
        if (vector_file == 0)
            $fatal(1, "cannot open vectors: %s", vector_path);

        void'($fgets(line, vector_file));
        $display("Vector header: %s", line);
        while (!$feof(vector_file)) begin
            scan_count = $fscanf(
                vector_file,
                "%d %d %d %d %d\n",
                vg_vector,
                vp_vector,
                ip_expected,
                ig_expected,
                clipped_expected
            );
            if (scan_count == 5) begin
                v_gk = vg_vector;
                v_pk = vp_vector;
                ce = 1'b1;
                @(negedge clk);
                ce = 1'b0;
                latency_cycles = 0;
                do begin
                    @(negedge clk);
                    latency_cycles = latency_cycles + 1;
                end while (!valid && latency_cycles < 16);

                if (!valid) begin
                    $error("timeout at vector %0d", vector_count);
                    error_count = error_count + 1;
                end else begin
                    if ($signed(i_p) !== ip_expected) begin
                        $error(
                            "i_p mismatch vector=%0d got=%0d expected=%0d",
                            vector_count, $signed(i_p), ip_expected
                        );
                        error_count = error_count + 1;
                    end
                    if ($signed(i_g) !== ig_expected) begin
                        $error(
                            "i_g mismatch vector=%0d got=%0d expected=%0d",
                            vector_count, $signed(i_g), ig_expected
                        );
                        error_count = error_count + 1;
                    end
                    if ((range_clipped ? 1 : 0) != clipped_expected) begin
                        $error("clip mismatch vector=%0d", vector_count);
                        error_count = error_count + 1;
                    end
                    if (latency_cycles != 8) begin
                        $error("latency=%0d expected=8", latency_cycles);
                        error_count = error_count + 1;
                    end
                end
                clipped_count = clipped_count + clipped_expected;
                vector_count = vector_count + 1;
            end
        end
        $fclose(vector_file);

        if (clipped_count == 0) begin
            $error("vector set did not exercise range clipping");
            error_count = error_count + 1;
        end
        if (error_count != 0)
            $fatal(1, "FAIL: %0d errors across %0d vectors", error_count, vector_count);
        $display(
            "PASS: %0d factorized bit-exact vectors, clips=%0d, latency=8 clocks",
            vector_count, clipped_count
        );
        $finish;
    end
endmodule

`default_nettype wire
