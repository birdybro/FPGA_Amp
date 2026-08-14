`default_nettype none

// Reduced-parameter arbitrary-clock safety environment for the BCLK monitor.
module audio_clock_rate_monitor_formal (
    output logic ever_locked
);
    localparam int unsigned BCLK_COUNTER_WIDTH = 4;
    localparam int unsigned WINDOW_FABRIC_CLOCKS = 4;
    localparam int unsigned EXPECTED_BCLK_EDGES = 1;
    localparam int unsigned LOCK_WINDOWS = 2;

    (* anyseq *) logic i2s_bclk;
    (* anyseq *) logic fabric_clk;
    (* anyseq *) logic clear_diagnostics;

    logic [2:0] startup_phase = 3'd0;
    logic shared_rst_n;
    logic measurement_valid;
    logic [BCLK_COUNTER_WIDTH-1:0] measured_bclk_edges;
    logic [7:0] consecutive_good_windows;
    logic rate_locked;
    logic rate_error_sticky;

    assign shared_rst_n = startup_phase >= 3'd3;

    always @($global_clock) begin
        if (startup_phase < 3'd4)
            startup_phase <= startup_phase + 1'b1;
        case (startup_phase)
            3'd0: begin
                assume (!i2s_bclk);
                assume (!fabric_clk);
            end
            3'd1: begin
                assume (i2s_bclk);
                assume (fabric_clk);
            end
            3'd2, 3'd3: begin
                assume (!i2s_bclk);
                assume (!fabric_clk);
            end
            default: begin
            end
        endcase
    end

    audio_clock_rate_monitor #(
        .BCLK_COUNTER_WIDTH(BCLK_COUNTER_WIDTH),
        .WINDOW_FABRIC_CLOCKS(WINDOW_FABRIC_CLOCKS),
        .EXPECTED_BCLK_EDGES(EXPECTED_BCLK_EDGES),
        .EDGE_TOLERANCE(0),
        .LOCK_WINDOWS(LOCK_WINDOWS)
    ) dut (
        .i2s_bclk,
        .i2s_rst_n(shared_rst_n),
        .fabric_clk,
        .fabric_rst_n(shared_rst_n),
        .clear_diagnostics,
        .measurement_valid,
        .measured_bclk_edges,
        .consecutive_good_windows,
        .rate_locked,
        .rate_error_sticky
    );

    always_ff @(posedge fabric_clk) begin
        if (!shared_rst_n) begin
            ever_locked <= 1'b0;
        end else begin
            if (rate_locked)
                ever_locked <= 1'b1;

            assert (consecutive_good_windows <= 8'(LOCK_WINDOWS));
            if (rate_locked) begin
                assert (consecutive_good_windows == 8'(LOCK_WINDOWS));
                assert (measured_bclk_edges
                    == BCLK_COUNTER_WIDTH'(EXPECTED_BCLK_EDGES));
            end
        end
    end

endmodule

`default_nettype wire
