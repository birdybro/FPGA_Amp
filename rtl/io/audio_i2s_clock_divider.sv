`timescale 1ns/1ps
`default_nettype none

// Power-of-two divider for the externally visible I2S serial clock. This is a
// deliberate interface clock domain, not a sample-processing fabric clock.
module audio_i2s_clock_divider #(
    parameter int unsigned FABRIC_TO_BCLK_DIVIDE = 16
) (
    input  logic fabric_clk,
    input  logic fabric_rst_n,
    output logic bclk_raw
);

    localparam int unsigned PHASE_WIDTH = $clog2(FABRIC_TO_BCLK_DIVIDE);

    initial begin
        if (FABRIC_TO_BCLK_DIVIDE < 2)
            $error("FABRIC_TO_BCLK_DIVIDE must be at least two");
        if ((1 << PHASE_WIDTH) != FABRIC_TO_BCLK_DIVIDE)
            $error("FABRIC_TO_BCLK_DIVIDE must be a power of two");
    end

    logic [PHASE_WIDTH-1:0] phase;

    always_ff @(posedge fabric_clk or negedge fabric_rst_n) begin
        if (!fabric_rst_n)
            phase <= '0;
        else
            phase <= phase + 1'b1;
    end

    always_comb bclk_raw = phase[PHASE_WIDTH-1];

endmodule

`default_nettype wire
