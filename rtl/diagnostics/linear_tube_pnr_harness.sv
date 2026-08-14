`timescale 1ns/1ps
`default_nettype none

// Three-pin named-part timing harness for the eight-clock value-only tube.
// This is a measurement top and not a deployable audio design.
module linear_tube_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    logic rst_n;
    logic [3:0] request_phase;
    logic signed [31:0] stimulus_lfsr;
    logic signed [31:0] plate_stimulus;
    logic ce;
    logic signed [31:0] i_p;
    logic signed [31:0] i_g;
    logic range_clipped;
    logic valid;

    assign rst_n = !reset;
    assign ce = request_phase == 4'd0;
    assign plate_stimulus = {1'b0, stimulus_lfsr[30:0]};

    always_ff @(posedge fabric_clk) begin
        if (!rst_n) begin
            request_phase <= '0;
            stimulus_lfsr <= 32'h1ace_b00c;
            activity <= 1'b0;
        end else begin
            request_phase <= request_phase + 1'b1;
            if (ce) begin
                stimulus_lfsr <= {
                    stimulus_lfsr[30:0],
                    stimulus_lfsr[31] ^ stimulus_lfsr[21]
                    ^ stimulus_lfsr[1] ^ stimulus_lfsr[0]
                };
            end
            if (valid)
                activity <= activity ^ ^i_p ^ ^i_g ^ range_clipped;
        end
    end

    (* keep *) triode_12ax7_factorized_linear tube (
        .clk(fabric_clk),
        .rst_n,
        .ce,
        .v_gk(stimulus_lfsr),
        .v_pk(plate_stimulus),
        .i_p,
        .i_g,
        .range_clipped,
        .valid
    );

endmodule

`default_nettype wire
