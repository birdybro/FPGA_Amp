`timescale 1ns/1ps
`default_nettype none

module calibration_commit_guard_tb;
    logic clk;
    logic rst_n = 1'b0;
    logic signed [31:0] candidate_input_peak_q24 = '0;
    logic signed [31:0] candidate_output_reciprocal_q24 = '0;
    logic update_valid = 1'b0;
    logic output_muted = 1'b1;
    logic clear_diagnostics = 1'b0;
    logic signed [31:0] active_input_peak_q24;
    logic signed [31:0] active_output_reciprocal_q24;
    logic update_ack;
    logic invalid_update_sticky;
    logic unsafe_update_sticky;

    calibration_commit_guard dut (.*);
    always #5 clk = ~clk;

    integer errors;

    task automatic request_update(
        input integer input_coefficient,
        input integer output_coefficient
    );
        begin
            @(negedge clk);
            candidate_input_peak_q24 = input_coefficient;
            candidate_output_reciprocal_q24 = output_coefficient;
            update_valid = 1'b1;
            @(posedge clk);
            #1;
            @(negedge clk);
            update_valid = 1'b0;
        end
    endtask

    initial begin
        clk = 1'b0;
        errors = 0;
        repeat (3) @(posedge clk);
        #1;
        rst_n = 1'b1;

        request_update(335544, 0);
        if (update_ack || !invalid_update_sticky
            || active_input_peak_q24 != 0
            || active_output_reciprocal_q24 != 0) begin
            $error("invalid pair was not rejected atomically");
            errors = errors + 1;
        end

        request_update(335544, 2097152);
        if (!update_ack || active_input_peak_q24 != 335544
            || active_output_reciprocal_q24 != 2097152) begin
            $error("muted valid pair did not commit atomically");
            errors = errors + 1;
        end

        output_muted = 1'b0;
        request_update(123456, 654321);
        if (update_ack || !unsafe_update_sticky
            || active_input_peak_q24 != 335544
            || active_output_reciprocal_q24 != 2097152) begin
            $error("live update changed active calibration");
            errors = errors + 1;
        end

        clear_diagnostics = 1'b1;
        @(posedge clk);
        #1;
        clear_diagnostics = 1'b0;
        if (invalid_update_sticky || unsafe_update_sticky) begin
            $error("calibration diagnostics did not clear");
            errors = errors + 1;
        end

        // Valid cannot override unsafe: muting is an explicit prerequisite.
        request_update(444444, 555555);
        if (update_ack || !unsafe_update_sticky
            || active_input_peak_q24 != 335544
            || active_output_reciprocal_q24 != 2097152) begin
            $error("second live update was not rejected");
            errors = errors + 1;
        end

        if (errors != 0)
            $fatal(1, "FAIL: %0d calibration commit-guard errors", errors);
        $display("PASS: invalid, atomic muted, live reject, and clear");
        $finish;
    end
endmodule

`default_nettype wire
