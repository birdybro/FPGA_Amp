`default_nettype none

// Multi-clock safety contract for the device-neutral asynchronous FIFO. Clock
// levels and functional inputs are arbitrary after a reset/deassert sequence;
// data ordering remains covered by the separate unrelated-clock simulation.
module async_fifo_formal;
    localparam int unsigned DATA_WIDTH = 1;
    localparam int unsigned ADDRESS_WIDTH = 2;
    localparam logic [ADDRESS_WIDTH:0] DEPTH = 3'd4;

    (* anyseq *) logic wr_clk;
    (* anyseq *) logic wr_enable;
    (* anyseq *) logic [DATA_WIDTH-1:0] wr_data;
    (* anyseq *) logic wr_clear_overflow;
    (* anyseq *) logic rd_clk;
    (* anyseq *) logic rd_enable;
    (* anyseq *) logic rd_clear_underflow;

    logic [2:0] startup_phase = 3'd0;
    logic shared_rst_n;
    logic wr_full;
    logic wr_overflow_sticky;
    logic [ADDRESS_WIDTH:0] wr_level;
    logic [ADDRESS_WIDTH:0] wr_high_water;
    logic [DATA_WIDTH-1:0] rd_data;
    logic rd_valid;
    logic rd_empty;
    logic rd_underflow_sticky;
    logic [ADDRESS_WIDTH:0] rd_level;
    logic [ADDRESS_WIDTH:0] rd_high_water;

    assign shared_rst_n = startup_phase >= 3'd3;

    // Exercise each reset on a real local rising edge, return both clocks low,
    // then release reset while low. Subsequent clock interleavings are free.
    always @($global_clock) begin
        if (startup_phase < 3'd4)
            startup_phase <= startup_phase + 1'b1;
        case (startup_phase)
            3'd0: begin
                assume (!wr_clk);
                assume (!rd_clk);
            end
            3'd1: begin
                assume (wr_clk);
                assume (rd_clk);
            end
            3'd2, 3'd3: begin
                assume (!wr_clk);
                assume (!rd_clk);
            end
            default: begin
            end
        endcase
    end

    async_fifo #(
        .DATA_WIDTH(DATA_WIDTH),
        .ADDRESS_WIDTH(ADDRESS_WIDTH)
    ) dut (
        .wr_clk,
        .wr_rst_n(shared_rst_n),
        .wr_enable,
        .wr_data,
        .wr_clear_overflow,
        .wr_full,
        .wr_overflow_sticky,
        .wr_level,
        .wr_high_water,
        .rd_clk,
        .rd_rst_n(shared_rst_n),
        .rd_enable,
        .rd_data,
        .rd_valid,
        .rd_clear_underflow,
        .rd_empty,
        .rd_underflow_sticky,
        .rd_level,
        .rd_high_water
    );

    always_ff @(posedge wr_clk) begin
        if (shared_rst_n && $past(shared_rst_n)) begin
            assert (wr_high_water <= DEPTH);
            if ($past(wr_clear_overflow))
                assert (!wr_overflow_sticky);
            else if ($past(wr_enable && wr_full))
                assert (wr_overflow_sticky);
        end
    end

    always_ff @(posedge rd_clk) begin
        if (shared_rst_n && $past(shared_rst_n)) begin
            assert (rd_high_water <= DEPTH);
            assert (rd_valid == $past(rd_enable && !rd_empty));
            if ($past(rd_clear_underflow))
                assert (!rd_underflow_sticky);
            else if ($past(rd_enable && rd_empty))
                assert (rd_underflow_sticky);
        end
    end

endmodule

`default_nettype wire
