`timescale 1ns/1ps
`default_nettype none

module network_kcl_v1_wide_tb;
    logic clk;
    logic rst_n = 1'b0;
    logic start = 1'b0;
    logic [359:0] voltage;
    logic [399:0] capacitor_state_q30;
    logic [479:0] capacitor_current_state_q44 = '0;
    logic [494:0] rhs_q44;
    logic [5:0] requested_residual_fractional_bits;
    logic tube_current_valid = 1'b0;
    logic [127:0] tube_current_q31;
    logic [224:0] residual;
    logic [5:0] residual_fractional_bits;
    logic [62:0] max_abs_residual_q44;
    logic correction_scale_fallback;
    logic saturation_any;
    logic [3:0] saturation_count;
    logic [479:0] capacitor_current_next_q44;
    logic [3:0] capacitor_current_saturation_count;
    logic busy;
    logic valid;

    network_kcl_v1_wide dut (
        .clk,
        .rst_n,
        .start,
        .voltage,
        .capacitor_state_q30,
        .capacitor_current_state_q44,
        .rhs_q44,
        .requested_residual_fractional_bits,
        .tube_current_valid,
        .tube_current_q31,
        .residual,
        .residual_fractional_bits,
        .max_abs_residual_q44,
        .correction_scale_fallback,
        .saturation_any,
        .saturation_count,
        .capacitor_current_next_q44,
        .capacitor_current_saturation_count,
        .busy,
        .valid
    );

    always #5 clk = ~clk;

    integer file_handle;
    integer scan_count;
    integer vector_count = 0;
    integer errors = 0;
    integer latency;
    integer tube_delay;
    integer expected_latency;
    logic [5:0] requested_fraction;
    integer expected_fraction;
    integer expected_saturation_count;
    integer expected_fallback;
    longint signed voltage_value [0:8];
    longint signed capacitor_value [0:9];
    longint signed rhs_value [0:8];
    longint signed current_value [0:3];
    longint signed expected_residual [0:8];
    longint unsigned expected_max_abs;

    initial begin
        clk = 1'b0;
        file_handle = $fopen("sim/vectors/generated/network_kcl_wide.txt", "r");
        if (file_handle == 0)
            $fatal(1, "cannot open wide KCL vectors");
        repeat (3) @(posedge clk);
        rst_n = 1'b1;
        @(negedge clk);
        while (!$feof(file_handle)) begin
            scan_count = $fscanf(file_handle, "%d", requested_fraction);
            if (scan_count != 1)
                break;
            for (integer lane = 0; lane < 9; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d", voltage_value[lane]);
            for (integer lane = 0; lane < 10; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d", capacitor_value[lane]);
            for (integer lane = 0; lane < 9; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d", rhs_value[lane]);
            for (integer lane = 0; lane < 4; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d", current_value[lane]);
            scan_count += $fscanf(file_handle, "%d", expected_fraction);
            for (integer lane = 0; lane < 9; lane = lane + 1)
                scan_count += $fscanf(file_handle, "%d", expected_residual[lane]);
            scan_count += $fscanf(
                file_handle, "%d %d %d\n", expected_saturation_count,
                expected_max_abs, expected_fallback
            );
            if (scan_count != 46)
                $fatal(1, "malformed vector %0d, fields=%0d", vector_count, scan_count);

            requested_residual_fractional_bits = requested_fraction;
            for (integer lane = 0; lane < 9; lane = lane + 1) begin
                voltage[lane * 40 +: 40] = voltage_value[lane][39:0];
                rhs_q44[lane * 55 +: 55] = rhs_value[lane][54:0];
            end
            for (integer lane = 0; lane < 10; lane = lane + 1)
                capacitor_state_q30[lane * 40 +: 40] = capacitor_value[lane][39:0];
            for (integer lane = 0; lane < 4; lane = lane + 1)
                tube_current_q31[lane * 32 +: 32] = current_value[lane][31:0];

            tube_delay = vector_count % 20;
            tube_current_valid = (tube_delay == 0);
            start = 1'b1;
            @(posedge clk);
            #1;
            start = 1'b0;
            if (tube_delay == 0)
                tube_current_valid = 1'b0;
            if (!busy)
                $fatal(1, "request was not accepted at vector %0d", vector_count);
            latency = 0;
            while (!valid) begin
                @(negedge clk);
                if (latency + 1 == tube_delay)
                    tube_current_valid = 1'b1;
                @(posedge clk);
                #1;
                latency = latency + 1;
                tube_current_valid = 1'b0;
                if (latency > 22)
                    $fatal(1, "timeout at vector %0d delay=%0d",
                           vector_count, tube_delay);
            end
            // An early tube current now leaves one explicit finish-staging
            // clock. Delayed currents use the pre-existing KCL wait window.
            expected_latency = tube_delay <= 9 ? 11 : tube_delay + 1;
            if (latency != expected_latency) begin
                $error("latency got=%0d expected=%0d delay=%0d",
                       latency, expected_latency, tube_delay);
                errors = errors + 1;
            end
            if (residual_fractional_bits !== expected_fraction[5:0]) begin
                $error("vector=%0d fraction got=%0d expected=%0d",
                       vector_count, residual_fractional_bits, expected_fraction);
                errors = errors + 1;
            end
            for (integer lane = 0; lane < 9; lane = lane + 1) begin
                if ($signed(residual[lane * 25 +: 25])
                    !== $signed(expected_residual[lane][24:0])) begin
                    $error("vector=%0d lane=%0d got=%0d expected=%0d",
                           vector_count, lane,
                           $signed(residual[lane * 25 +: 25]),
                           expected_residual[lane]);
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
            if (max_abs_residual_q44 !== expected_max_abs[62:0]) begin
                $error("vector=%0d max got=%0d expected=%0d",
                       vector_count, max_abs_residual_q44, expected_max_abs);
                errors = errors + 1;
            end
            if (correction_scale_fallback !== expected_fallback[0]) begin
                $error("vector=%0d fallback got=%0b expected=%0d",
                       vector_count, correction_scale_fallback, expected_fallback);
                errors = errors + 1;
            end
            if ((^capacitor_current_next_q44) === 1'bx
                || (^capacitor_current_saturation_count) === 1'bx) begin
                $error("vector=%0d auxiliary current output contains X", vector_count);
                errors = errors + 1;
            end
            vector_count = vector_count + 1;
            @(negedge clk);
        end
        $fclose(file_handle);
        if (errors != 0)
            $fatal(1, "FAIL: %0d wide KCL errors", errors);
        $display("PASS: %0d wide KCL vectors, early-current latency=11 clocks",
                 vector_count);
        $finish;
    end
endmodule

`default_nettype wire
