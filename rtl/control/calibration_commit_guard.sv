`timescale 1ns/1ps
`default_nettype none

// Atomic control boundary for the two physical converter coefficients. Active
// values reset invalid/zero and may change only together while output is muted.
// This is protocol-neutral: a host register file, CPU, or SPI bridge may drive
// the candidate/valid interface later.
module calibration_commit_guard (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic signed [31:0]   candidate_input_peak_q24,
    input  logic signed [31:0]   candidate_output_reciprocal_q24,
    input  logic                 update_valid,
    input  logic                 output_muted,
    input  logic                 clear_diagnostics,
    output logic signed [31:0]   active_input_peak_q24,
    output logic signed [31:0]   active_output_reciprocal_q24,
    output logic                 update_ack,
    output logic                 invalid_update_sticky,
    output logic                 unsafe_update_sticky
);

    logic candidate_invalid;
    always_comb begin
        candidate_invalid = (candidate_input_peak_q24 <= 0)
                            || (candidate_output_reciprocal_q24 <= 0);
    end

    // This guard shares the fabric reset with CDC infrastructure in the pin
    // top, so reset assertion is asynchronous and deassertion is expected to
    // be synchronized by the board-level reset controller.
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            active_input_peak_q24 <= '0;
            active_output_reciprocal_q24 <= '0;
            update_ack <= 1'b0;
            invalid_update_sticky <= 1'b0;
            unsafe_update_sticky <= 1'b0;
        end else begin
            update_ack <= 1'b0;
            if (clear_diagnostics) begin
                invalid_update_sticky <= 1'b0;
                unsafe_update_sticky <= 1'b0;
            end
            if (update_valid) begin
                if (candidate_invalid) begin
                    if (!clear_diagnostics)
                        invalid_update_sticky <= 1'b1;
                end else if (!output_muted) begin
                    if (!clear_diagnostics)
                        unsafe_update_sticky <= 1'b1;
                end else begin
                    active_input_peak_q24 <= candidate_input_peak_q24;
                    active_output_reciprocal_q24 <=
                        candidate_output_reciprocal_q24;
                    update_ack <= 1'b1;
                end
            end
        end
    end

endmodule

`default_nettype wire
