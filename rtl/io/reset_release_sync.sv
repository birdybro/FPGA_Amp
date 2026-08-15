`timescale 1ns/1ps
`default_nettype none

// Asynchronous assertion and synchronous release for one clock domain. The
// reset input may be shared across domains; rst_n must remain local to clk.
module reset_release_sync #(
    parameter int unsigned STAGES = 3
) (
    input  logic clk,
    input  logic async_reset,
    output logic rst_n
);

    initial begin
        if (STAGES < 2)
            $error("STAGES must be at least two");
    end

    // The SYNCASYNCNET lint warning describes the intentional structure:
    // asynchronous clear and synchronous shifting are the reset contract.
    /* verilator lint_off SYNCASYNCNET */
    (* ASYNC_REG = "TRUE" *) logic [STAGES-1:0] release_pipeline;

    always_ff @(posedge clk or posedge async_reset) begin
        if (async_reset)
            release_pipeline <= '0;
        else
            release_pipeline <= {release_pipeline[STAGES-2:0], 1'b1};
    end

    always_comb rst_n = release_pipeline[STAGES-1];
    /* verilator lint_on SYNCASYNCNET */

endmodule

`default_nettype wire
