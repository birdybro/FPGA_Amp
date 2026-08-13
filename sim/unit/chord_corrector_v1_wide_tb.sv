`timescale 1ns/1ps
`default_nettype none

module chord_corrector_v1_wide_tb;
    logic clk;
    logic rst_n = 1'b0;
    logic start = 1'b0;
    logic [359:0] voltage;
    logic [224:0] residual;
    logic [5:0] residual_fractional_bits;
    logic [359:0] corrected_voltage;
    logic saturation_any;
    logic [3:0] saturation_count;
    logic busy;
    logic valid;

    chord_corrector_v1_wide dut (.*);
    always #5 clk = ~clk;

    integer file_handle;
    integer scan_count;
    integer vector_count = 0;
    integer errors = 0;
    integer expected_saturation_count;
    integer latency;
    longint signed voltage_value [0:8];
    longint signed residual_value [0:8];
    longint signed expected_value [0:8];

    initial begin
        clk = 1'b0;
        file_handle = $fopen("sim/vectors/generated/wide_chord.txt", "r");
        if (file_handle == 0)
            $fatal(1, "cannot open wide chord vectors");
        repeat (3) @(posedge clk);
        rst_n = 1'b1;
        @(negedge clk);
        while (!$feof(file_handle)) begin
            scan_count = $fscanf(file_handle, "%d", residual_fractional_bits);
            if (scan_count != 1)
                break;
            for (integer lane = 0; lane < 9; lane = lane + 1)
                scan_count = scan_count + $fscanf(file_handle, "%d", voltage_value[lane]);
            for (integer lane = 0; lane < 9; lane = lane + 1)
                scan_count = scan_count + $fscanf(file_handle, "%d", residual_value[lane]);
            for (integer lane = 0; lane < 9; lane = lane + 1)
                scan_count = scan_count + $fscanf(file_handle, "%d", expected_value[lane]);
            scan_count = scan_count + $fscanf(file_handle, "%d\n", expected_saturation_count);
            if (scan_count != 29)
                $fatal(1, "malformed vector %0d, fields=%0d", vector_count, scan_count);
            for (integer lane = 0; lane < 9; lane = lane + 1) begin
                voltage[lane * 40 +: 40] = voltage_value[lane][39:0];
                residual[lane * 25 +: 25] = residual_value[lane][24:0];
            end
            start = 1'b1;
            @(posedge clk);
            #1;
            start = 1'b0;
            if (!busy)
                $fatal(1, "request was not accepted at vector %0d", vector_count);
            latency = 0;
            while (!valid) begin
                @(posedge clk);
                #1;
                latency = latency + 1;
                if (latency > 12)
                    $fatal(1, "timeout at vector %0d", vector_count);
            end
            if (latency != 10) begin
                $error("latency got=%0d expected=10 after acceptance edge", latency);
                errors = errors + 1;
            end
            for (integer lane = 0; lane < 9; lane = lane + 1) begin
                if ($signed(corrected_voltage[lane * 40 +: 40])
                    !== $signed(expected_value[lane][39:0])) begin
                    $error("vector=%0d lane=%0d got=%0d expected=%0d",
                           vector_count, lane,
                           $signed(corrected_voltage[lane * 40 +: 40]),
                           expected_value[lane]);
                    errors = errors + 1;
                end
            end
            if (saturation_count !== expected_saturation_count[3:0]
                || saturation_any !== (expected_saturation_count != 0)) begin
                $error("vector=%0d saturation got=%0d/%0b expected=%0d",
                       vector_count, saturation_count, saturation_any,
                       expected_saturation_count);
                errors = errors + 1;
            end
            vector_count = vector_count + 1;
            @(negedge clk);
        end
        $fclose(file_handle);
        if (errors != 0)
            $fatal(1, "FAIL: %0d wide chord errors", errors);
        $display("PASS: %0d wide chord vectors, latency=10 clocks", vector_count);
        $finish;
    end
endmodule

`default_nettype wire
