`default_nettype none

// Arbitrary-source contract for deterministic fabric audio-frame scheduling.
module audio_frame_scheduler_formal (
    input logic clk
);
    localparam int unsigned PERIOD_CLOCKS = 4;
    localparam int unsigned PREPROCESS_LATENCY_CLOCKS = 1;
    localparam logic [1:0] LAST_PHASE = 2'd3;
    localparam logic [1:0] LAUNCH_PHASE = 2'd3;

    (* anyseq *) logic rst_n;
    (* anyseq *) logic [63:0] frame_input_data;
    (* anyseq *) logic frame_input_valid;
    (* anyseq *) logic clear_diagnostics;

    logic frame_input_ready;
    logic [63:0] frame_output_data;
    logic frame_output_valid;
    logic frame_was_present;
    logic [31:0] underflow_count;
    logic [1:0] phase_counter;
    logic past_valid = 1'b0;

    audio_frame_scheduler #(
        .PERIOD_CLOCKS(PERIOD_CLOCKS),
        .PREPROCESS_LATENCY_CLOCKS(PREPROCESS_LATENCY_CLOCKS)
    ) dut (.*);

    always_ff @(posedge clk) begin
        if (!past_valid)
            assume (!rst_n);
        else
            assume (rst_n);
        past_valid <= 1'b1;

        if (past_valid) begin
            if (!$past(rst_n)) begin
                assert (phase_counter == 2'd0);
                assert (underflow_count == 32'd0);
            end else begin
                assert (phase_counter == (
                    ($past(phase_counter) == LAST_PHASE)
                        ? 2'd0 : $past(phase_counter) + 1'b1
                ));
                assert (underflow_count == $past(
                    clear_diagnostics
                        ? 32'd0
                        : (phase_counter == LAUNCH_PHASE
                           && !frame_input_valid
                           && underflow_count != 32'hffff_ffff)
                            ? underflow_count + 1'b1
                            : underflow_count
                ));
            end

            assert (frame_input_ready
                == (phase_counter == LAUNCH_PHASE));
            assert (frame_output_valid
                == (phase_counter == LAUNCH_PHASE));
            assert (frame_was_present == (
                phase_counter == LAUNCH_PHASE && frame_input_valid
            ));
            if (frame_output_valid) begin
                if (frame_input_valid)
                    assert (frame_output_data == frame_input_data);
                else
                    assert (frame_output_data == 64'd0);
            end
        end
    end

endmodule

`default_nettype wire
