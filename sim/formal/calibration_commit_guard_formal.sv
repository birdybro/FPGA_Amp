`default_nettype none

// Arbitrary-input contract for atomic converter-calibration ownership.
module calibration_commit_guard_formal (
    input logic clk
);
    (* anyseq *) logic rst_n;
    (* anyseq *) logic signed [31:0] candidate_input_peak_q24;
    (* anyseq *) logic signed [31:0] candidate_output_reciprocal_q24;
    (* anyseq *) logic update_valid;
    (* anyseq *) logic output_muted;
    (* anyseq *) logic clear_diagnostics;

    logic signed [31:0] active_input_peak_q24;
    logic signed [31:0] active_output_reciprocal_q24;
    logic update_ack;
    logic invalid_update_sticky;
    logic unsafe_update_sticky;
    logic past_valid = 1'b0;

    calibration_commit_guard dut (.*);

    always_ff @(posedge clk) begin
        if (!past_valid)
            assume (!rst_n);
        else
            assume (rst_n);
        past_valid <= 1'b1;

        if (past_valid) begin
            if (!$past(rst_n)) begin
                assert (active_input_peak_q24 == 32'sd0);
                assert (active_output_reciprocal_q24 == 32'sd0);
                assert (!update_ack);
                assert (!invalid_update_sticky);
                assert (!unsafe_update_sticky);
            end else begin
                assert (update_ack == $past(
                    update_valid
                    && candidate_input_peak_q24 > 0
                    && candidate_output_reciprocal_q24 > 0
                    && output_muted
                ));

                if ($past(
                    update_valid
                    && candidate_input_peak_q24 > 0
                    && candidate_output_reciprocal_q24 > 0
                    && output_muted
                )) begin
                    assert (active_input_peak_q24
                        == $past(candidate_input_peak_q24));
                    assert (active_output_reciprocal_q24
                        == $past(candidate_output_reciprocal_q24));
                end else begin
                    assert (active_input_peak_q24
                        == $past(active_input_peak_q24));
                    assert (active_output_reciprocal_q24
                        == $past(active_output_reciprocal_q24));
                end

                assert (invalid_update_sticky == $past(
                    clear_diagnostics
                        ? 1'b0
                        : invalid_update_sticky || (
                            update_valid && (
                                candidate_input_peak_q24 <= 0
                                || candidate_output_reciprocal_q24 <= 0
                            )
                        )
                ));
                assert (unsafe_update_sticky == $past(
                    clear_diagnostics
                        ? 1'b0
                        : unsafe_update_sticky || (
                            update_valid
                            && candidate_input_peak_q24 > 0
                            && candidate_output_reciprocal_q24 > 0
                            && !output_muted
                        )
                ));
            end
        end
    end

endmodule

`default_nettype wire
