`default_nettype none

// Bounded arbitrary-clock safety contract for the held-bus snapshot CDC.
module cdc_word_snapshot_formal;
    localparam int unsigned WIDTH = 4;

    (* anyseq *) logic source_clk;
    (* anyseq *) logic source_request;
    (* anyseq *) logic destination_clk;
    (* anyseq *) logic [WIDTH-1:0] destination_live_data;

    logic [2:0] startup_phase = 3'd0;
    logic shared_rst_n;
    logic source_available;
    logic source_snapshot_valid;
    logic [WIDTH-1:0] source_snapshot_data;
    logic [3:0] accepted_count;
    logic [3:0] completed_count;

    assign shared_rst_n = startup_phase >= 3'd3;

    always @($global_clock) begin
        if (startup_phase < 3'd4)
            startup_phase <= startup_phase + 1'b1;
        case (startup_phase)
            3'd0: begin
                assume (!source_clk);
                assume (!destination_clk);
            end
            3'd1: begin
                assume (source_clk);
                assume (destination_clk);
            end
            3'd2, 3'd3: begin
                assume (!source_clk);
                assume (!destination_clk);
            end
            default: begin
            end
        endcase
    end

    cdc_word_snapshot #(
        .WIDTH(WIDTH)
    ) dut (
        .source_clk,
        .source_rst_n(shared_rst_n),
        .source_request,
        .source_available,
        .source_snapshot_valid,
        .source_snapshot_data,
        .destination_clk,
        .destination_rst_n(shared_rst_n),
        .destination_live_data
    );

    always_ff @(posedge source_clk) begin
        if (!shared_rst_n) begin
            accepted_count <= '0;
            completed_count <= '0;
        end else begin
            if (source_request && source_available)
                accepted_count <= accepted_count + 1'b1;
            if (source_snapshot_valid)
                completed_count <= completed_count + 1'b1;

            assert (completed_count <= accepted_count);
            if (source_available)
                assert (completed_count == accepted_count);
        end
    end

endmodule

`default_nettype wire
