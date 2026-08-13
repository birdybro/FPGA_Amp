`timescale 1ns/1ps
`default_nettype none

module async_fifo_tb;
    localparam int DATA_WIDTH = 32;
    localparam int ADDRESS_WIDTH = 3;
    localparam int DEPTH = 1 << ADDRESS_WIDTH;

    logic wr_clk;
    logic wr_rst_n = 1'b0;
    logic wr_enable = 1'b0;
    logic [DATA_WIDTH-1:0] wr_data = '0;
    logic wr_clear_overflow = 1'b0;
    logic wr_full;
    logic wr_overflow_sticky;

    logic rd_clk = 1'b0;
    logic rd_rst_n = 1'b0;
    logic rd_enable = 1'b0;
    logic [DATA_WIDTH-1:0] rd_data;
    logic rd_valid;
    logic rd_clear_underflow = 1'b0;
    logic rd_empty;
    logic rd_underflow_sticky;

    async_fifo #(
        .DATA_WIDTH(DATA_WIDTH),
        .ADDRESS_WIDTH(ADDRESS_WIDTH)
    ) dut (.*);

    initial begin
        wr_clk = 1'b0;
        forever #5 wr_clk = ~wr_clk;
    end
    initial begin
        #1;
        forever #7 rd_clk = ~rd_clk;
    end

    integer errors = 0;
    integer index;

    task automatic push(input logic [DATA_WIDTH-1:0] value);
        begin
            @(negedge wr_clk);
            while (wr_full)
                @(negedge wr_clk);
            wr_data = value;
            wr_enable = 1'b1;
            @(negedge wr_clk);
            wr_enable = 1'b0;
        end
    endtask

    task automatic pop_and_check(input logic [DATA_WIDTH-1:0] expected);
        begin
            @(negedge rd_clk);
            while (rd_empty)
                @(negedge rd_clk);
            rd_enable = 1'b1;
            @(posedge rd_clk);
            #1;
            rd_enable = 1'b0;
            if (!rd_valid || rd_data !== expected) begin
                $error("read got valid=%0b data=%08x expected=%08x",
                       rd_valid, rd_data, expected);
                errors = errors + 1;
            end
        end
    endtask

    initial begin
        repeat (3) @(posedge wr_clk);
        repeat (3) @(posedge rd_clk);
        // Deassert each reset away from its active edge, modeling an external
        // async-assert/synchronous-deassert reset conditioner per domain.
        @(negedge wr_clk);
        wr_rst_n = 1'b1;
        @(negedge rd_clk);
        rd_rst_n = 1'b1;

        // Fill exactly, reject one extra word, and retain all accepted data.
        for (index = 0; index < DEPTH; index++)
            push(32'h1000_0000 + index);
        if (!wr_full) begin
            $error("FIFO did not assert full after %0d writes", DEPTH);
            errors = errors + 1;
        end
        @(negedge wr_clk);
        wr_data = 32'hdead_beef;
        wr_enable = 1'b1;
        @(negedge wr_clk);
        wr_enable = 1'b0;
        if (!wr_overflow_sticky) begin
            $error("overflow attempt was not recorded");
            errors = errors + 1;
        end
        for (index = 0; index < DEPTH; index++)
            pop_and_check(32'h1000_0000 + index);

        // Underflow must pulse no valid and must not move the read pointer.
        @(negedge rd_clk);
        if (!rd_empty) begin
            $error("FIFO did not become empty after exact drain");
            errors = errors + 1;
        end
        rd_enable = 1'b1;
        @(posedge rd_clk);
        #1;
        rd_enable = 1'b0;
        if (rd_valid || !rd_underflow_sticky) begin
            $error("underflow valid/sticky behavior incorrect");
            errors = errors + 1;
        end

        // Clear each diagnostic in its owning clock domain.
        @(negedge wr_clk);
        wr_clear_overflow = 1'b1;
        @(negedge wr_clk);
        wr_clear_overflow = 1'b0;
        @(negedge rd_clk);
        rd_clear_underflow = 1'b1;
        @(negedge rd_clk);
        rd_clear_underflow = 1'b0;
        if (wr_overflow_sticky || rd_underflow_sticky) begin
            $error("sticky diagnostic clear failed");
            errors = errors + 1;
        end

        // Exercise many Gray-pointer wraps under unrelated read/write clocks.
        fork
            begin
                for (index = 0; index < 128; index++)
                    push(32'h5000_0000 + index);
            end
            begin
                integer read_index;
                for (read_index = 0; read_index < 128; read_index++)
                    pop_and_check(32'h5000_0000 + read_index);
            end
        join

        repeat (4) @(posedge rd_clk);
        if (!rd_empty || wr_overflow_sticky || rd_underflow_sticky) begin
            $error("final FIFO state/diagnostics incorrect");
            errors = errors + 1;
        end
        if (errors != 0)
            $fatal(1, "FAIL: %0d asynchronous FIFO errors", errors);
        $display("PASS: async FIFO ordering, wraps, full/empty, and sticky flags");
        $finish;
    end
endmodule

`default_nettype wire
