`timescale 1ns/1ps
`default_nettype none

module v1_solver_mono_wide_trapezoidal_tb #(
    parameter bit BANKED = 1'b0
);
    v1_solver_mono_wide_tb #(
        .TRAPEZOIDAL(1'b1),
        .BANKED(BANKED)
    ) testbench();
endmodule

`default_nettype wire
