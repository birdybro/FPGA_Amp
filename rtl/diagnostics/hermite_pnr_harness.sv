`timescale 1ns/1ps
`default_nettype none

// Three-pin timing harness for the iterative Q0.16 Hermite kernel.  This is
// only a place-and-route measurement top, not a deployable audio design.
module hermite_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    logic rst_n;
    logic [31:0] stimulus_lfsr;
    logic signed [31:0] y0_stimulus;
    logic signed [31:0] y1_stimulus;
    logic signed [31:0] m0_stimulus;
    logic signed [31:0] m1_stimulus;
    logic start;
    logic signed [31:0] result;
    logic busy;
    logic valid;

    assign rst_n = !reset;
    assign start = !busy;
    assign y0_stimulus = stimulus_lfsr;
    assign y1_stimulus = {stimulus_lfsr[15:0], stimulus_lfsr[31:16]};
    assign m0_stimulus = {stimulus_lfsr[7:0], stimulus_lfsr[31:8]};
    assign m1_stimulus = ~stimulus_lfsr;

    always_ff @(posedge fabric_clk) begin
        if (!rst_n) begin
            stimulus_lfsr <= 32'h1ace_b00c;
            activity <= 1'b0;
        end else begin
            if (start) begin
                stimulus_lfsr <= {
                    stimulus_lfsr[30:0],
                    stimulus_lfsr[31] ^ stimulus_lfsr[21]
                    ^ stimulus_lfsr[1] ^ stimulus_lfsr[0]
                };
            end
            if (valid)
                activity <= activity ^ ^result;
        end
    end

    (* keep *) hermite_q16_pipeline kernel (
        .clk(fabric_clk),
        .rst_n,
        .start,
        .y0(y0_stimulus),
        .y1(y1_stimulus),
        .m0(m0_stimulus),
        .m1(m1_stimulus),
        .fraction(stimulus_lfsr[15:0]),
        .result,
        .busy,
        .valid
    );

endmodule

`default_nettype wire
