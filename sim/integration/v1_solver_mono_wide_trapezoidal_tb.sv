`timescale 1ns/1ps
`default_nettype none

module v1_solver_mono_wide_trapezoidal_tb #(
    parameter bit BANKED = 1'b0,
    parameter bit TERMINAL_CORRECTION = 1'b0,
    parameter bit PARALLEL_TUBES = 1'b0
);
    v1_solver_mono_wide_tb #(
        .TRAPEZOIDAL(1'b1),
        .BANKED(BANKED),
        .TERMINAL_CORRECTION(TERMINAL_CORRECTION),
        .PARALLEL_TUBES(PARALLEL_TUBES)
    ) testbench();
endmodule

`default_nettype wire
