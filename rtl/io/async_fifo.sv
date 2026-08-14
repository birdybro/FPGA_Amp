`timescale 1ns/1ps
`default_nettype none

// Device-neutral dual-clock FIFO using binary local pointers and two-flop
// synchronized Gray pointers. Resets may assert asynchronously but must be
// deasserted synchronously to their respective domains by the caller.
module async_fifo #(
    parameter int unsigned DATA_WIDTH = 32,
    parameter int unsigned ADDRESS_WIDTH = 3
) (
    input  logic                       wr_clk,
    input  logic                       wr_rst_n,
    input  logic                       wr_enable,
    input  logic [DATA_WIDTH-1:0]      wr_data,
    input  logic                       wr_clear_overflow,
    output logic                       wr_full,
    output logic                       wr_overflow_sticky,
    output logic [ADDRESS_WIDTH:0]     wr_level,
    output logic [ADDRESS_WIDTH:0]     wr_high_water,

    input  logic                       rd_clk,
    input  logic                       rd_rst_n,
    input  logic                       rd_enable,
    output logic [DATA_WIDTH-1:0]      rd_data,
    output logic                       rd_valid,
    input  logic                       rd_clear_underflow,
    output logic                       rd_empty,
    output logic                       rd_underflow_sticky,
    output logic [ADDRESS_WIDTH:0]     rd_level,
    output logic [ADDRESS_WIDTH:0]     rd_high_water
);

    localparam int unsigned DEPTH = 1 << ADDRESS_WIDTH;
    localparam int unsigned POINTER_WIDTH = ADDRESS_WIDTH + 1;

    function automatic logic [POINTER_WIDTH-1:0] gray_to_binary(
        input logic [POINTER_WIDTH-1:0] gray_value
    );
        integer bit_index;
        begin
            gray_to_binary[POINTER_WIDTH-1] = gray_value[POINTER_WIDTH-1];
            for (bit_index = POINTER_WIDTH - 2; bit_index >= 0; bit_index--)
                gray_to_binary[bit_index] =
                    gray_to_binary[bit_index + 1] ^ gray_value[bit_index];
        end
    endfunction

    initial begin
        if (DATA_WIDTH == 0)
            $error("DATA_WIDTH must be nonzero");
        if (ADDRESS_WIDTH < 2)
            $error("ADDRESS_WIDTH must be at least two (depth >= 4)");
    end

    logic [DATA_WIDTH-1:0] memory [0:DEPTH-1];

    logic [POINTER_WIDTH-1:0] wr_binary;
    logic [POINTER_WIDTH-1:0] wr_binary_next;
    logic [POINTER_WIDTH-1:0] wr_gray;
    logic [POINTER_WIDTH-1:0] wr_gray_next;
    logic [POINTER_WIDTH-1:0] rd_binary;
    logic [POINTER_WIDTH-1:0] rd_binary_next;
    logic [POINTER_WIDTH-1:0] rd_gray;
    logic [POINTER_WIDTH-1:0] rd_gray_next;

    (* async_reg = "true" *) logic [POINTER_WIDTH-1:0] rd_gray_wr_sync1;
    (* async_reg = "true" *) logic [POINTER_WIDTH-1:0] rd_gray_wr_sync2;
    (* async_reg = "true" *) logic [POINTER_WIDTH-1:0] wr_gray_rd_sync1;
    (* async_reg = "true" *) logic [POINTER_WIDTH-1:0] wr_gray_rd_sync2;

    logic wr_accept;
    logic rd_accept;
    logic wr_full_next;
    logic rd_empty_next;
    logic [POINTER_WIDTH-1:0] rd_binary_wr_sync;
    logic [POINTER_WIDTH-1:0] wr_binary_rd_sync;
    logic [POINTER_WIDTH-1:0] wr_level_next;
    logic [POINTER_WIDTH-1:0] rd_level_next;

    always_comb begin
        rd_binary_wr_sync = gray_to_binary(rd_gray_wr_sync2);
        wr_binary_rd_sync = gray_to_binary(wr_gray_rd_sync2);
        // Each estimate is conservative in its local domain: write-side
        // occupancy can lag reads high, while read-side occupancy can lag
        // writes low. Neither value is a cross-domain coherent snapshot.
        wr_level = wr_binary - rd_binary_wr_sync;
        rd_level = wr_binary_rd_sync - rd_binary;

        wr_accept = wr_enable && !wr_full;
        wr_binary_next = wr_binary + POINTER_WIDTH'(wr_accept);
        wr_gray_next = (wr_binary_next >> 1) ^ wr_binary_next;
        wr_level_next = wr_binary_next - rd_binary_wr_sync;
        // A write pointer is one complete ring ahead when its two MSBs differ
        // from the synchronized read pointer and every lower bit is equal.
        wr_full_next = wr_gray_next == {
            ~rd_gray_wr_sync2[POINTER_WIDTH-1:POINTER_WIDTH-2],
            rd_gray_wr_sync2[POINTER_WIDTH-3:0]
        };

        rd_accept = rd_enable && !rd_empty;
        rd_binary_next = rd_binary + POINTER_WIDTH'(rd_accept);
        rd_gray_next = (rd_binary_next >> 1) ^ rd_binary_next;
        rd_level_next = wr_binary_rd_sync - rd_binary_next;
        rd_empty_next = rd_gray_next == wr_gray_rd_sync2;
    end

    always_ff @(posedge wr_clk or negedge wr_rst_n) begin
        if (!wr_rst_n) begin
            wr_binary <= '0;
            wr_gray <= '0;
            wr_full <= 1'b0;
            rd_gray_wr_sync1 <= '0;
            rd_gray_wr_sync2 <= '0;
            wr_overflow_sticky <= 1'b0;
            wr_high_water <= '0;
        end else begin
            rd_gray_wr_sync1 <= rd_gray;
            rd_gray_wr_sync2 <= rd_gray_wr_sync1;
            wr_binary <= wr_binary_next;
            wr_gray <= wr_gray_next;
            wr_full <= wr_full_next;
            if (wr_accept)
                memory[wr_binary[ADDRESS_WIDTH-1:0]] <= wr_data;
            if (wr_clear_overflow)
                wr_overflow_sticky <= 1'b0;
            else if (wr_enable && wr_full)
                wr_overflow_sticky <= 1'b1;
            if (wr_clear_overflow)
                wr_high_water <= wr_level_next;
            else if (wr_level_next > wr_high_water)
                wr_high_water <= wr_level_next;
        end
    end

    always_ff @(posedge rd_clk or negedge rd_rst_n) begin
        if (!rd_rst_n) begin
            rd_binary <= '0;
            rd_gray <= '0;
            rd_empty <= 1'b1;
            wr_gray_rd_sync1 <= '0;
            wr_gray_rd_sync2 <= '0;
            rd_data <= '0;
            rd_valid <= 1'b0;
            rd_underflow_sticky <= 1'b0;
            rd_high_water <= '0;
        end else begin
            wr_gray_rd_sync1 <= wr_gray;
            wr_gray_rd_sync2 <= wr_gray_rd_sync1;
            rd_binary <= rd_binary_next;
            rd_gray <= rd_gray_next;
            rd_empty <= rd_empty_next;
            rd_valid <= rd_accept;
            if (rd_accept)
                rd_data <= memory[rd_binary[ADDRESS_WIDTH-1:0]];
            if (rd_clear_underflow)
                rd_underflow_sticky <= 1'b0;
            else if (rd_enable && rd_empty)
                rd_underflow_sticky <= 1'b1;
            if (rd_clear_underflow)
                rd_high_water <= rd_level_next;
            else if (rd_level_next > rd_high_water)
                rd_high_water <= rd_level_next;
        end
    end

`ifdef FORMAL
    always_ff @(posedge wr_clk) begin
        if (wr_rst_n && $past(wr_rst_n)) begin
            assert ($onehot0(wr_gray ^ $past(wr_gray)));
            if ($past(wr_enable && wr_full))
                assert (wr_binary == $past(wr_binary));
            assert (wr_level <= POINTER_WIDTH'(DEPTH));
        end
    end
    always_ff @(posedge rd_clk) begin
        if (rd_rst_n && $past(rd_rst_n)) begin
            assert ($onehot0(rd_gray ^ $past(rd_gray)));
            if ($past(rd_enable && rd_empty))
                assert (rd_binary == $past(rd_binary));
            assert (rd_level <= POINTER_WIDTH'(DEPTH));
        end
    end
`endif

endmodule

`default_nettype wire
