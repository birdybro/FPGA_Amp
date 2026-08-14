`default_nettype none

// Formal contract for the modern output-safety ramp. The proof deliberately
// leaves every control and sample input arbitrary after one reset clock.
module output_mute_ramp_formal (
    input logic clk
);
    localparam int unsigned RAMP_SAMPLES = 4;
    localparam logic [15:0] GAIN_STEP = 16'd16384;

    (* anyseq *) logic rst_n;
    (* anyseq *) logic sample_valid;
    (* anyseq *) logic signed [31:0] sample_input_q24;
    (* anyseq *) logic mute_request;
    (* anyseq *) logic force_mute;

    logic signed [31:0] sample_output_q24;
    logic output_valid;
    logic [15:0] gain_q16;
    logic muted;
    logic ramping;
    logic past_valid = 1'b0;

    output_mute_ramp #(
        .RAMP_SAMPLES(RAMP_SAMPLES)
    ) dut (.*);

    function automatic logic [15:0] expected_next_gain(
        input logic [15:0] current,
        input logic requested_mute
    );
        logic [16:0] changed;
        begin
            if (requested_mute) begin
                expected_next_gain = (current <= GAIN_STEP)
                    ? 16'd0 : current - GAIN_STEP;
            end else begin
                changed = {1'b0, current} + {1'b0, GAIN_STEP};
                expected_next_gain = (changed >= 17'd65535)
                    ? 16'hffff : changed[15:0];
            end
        end
    endfunction

    always_ff @(posedge clk) begin
        // Establish a non-vacuous, deterministic initial state, then release
        // reset permanently while leaving all functional inputs arbitrary.
        if (!past_valid)
            assume (!rst_n);
        else
            assume (rst_n);
        past_valid <= 1'b1;

        if (past_valid) begin
            if (!$past(rst_n)) begin
                assert (gain_q16 == 16'd0);
                assert (sample_output_q24 == 32'sd0);
                assert (!output_valid);
            end else begin
                assert (output_valid == $past(sample_valid));

                if ($past(force_mute)) begin
                    assert (gain_q16 == 16'd0);
                    assert (sample_output_q24 == 32'sd0);
                end else if ($past(sample_valid)) begin
                    assert (gain_q16 == expected_next_gain(
                        $past(gain_q16), $past(mute_request)
                    ));
                    if ($past(gain_q16) == 16'd0)
                        assert (sample_output_q24 == 32'sd0);
                    if ($past(gain_q16) == 16'hffff)
                        assert (sample_output_q24
                            == $past(sample_input_q24));
                    if ($past(mute_request))
                        assert (gain_q16 <= $past(gain_q16));
                    else
                        assert (gain_q16 >= $past(gain_q16));
                end else begin
                    assert (gain_q16 == $past(gain_q16));
                    assert (sample_output_q24
                        == $past(sample_output_q24));
                end
            end

            assert (muted == (gain_q16 == 16'd0));
            assert (ramping == (mute_request
                ? (gain_q16 != 16'd0)
                : (gain_q16 != 16'hffff)));
        end
    end

endmodule

`default_nettype wire
