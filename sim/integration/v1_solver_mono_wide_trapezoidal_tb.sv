`timescale 1ns/1ps
`default_nettype none

module v1_solver_mono_wide_trapezoidal_tb;
    v1_solver_mono_wide_tb #(.TRAPEZOIDAL(1'b1)) testbench();
endmodule

`default_nettype wire
