`timescale 1ns/1ps
`default_nettype none

module v1_solver_mono_wide_trapezoidal_tb #(
    parameter bit BANKED = 1'b0,
    parameter bit TERMINAL_CORRECTION = 1'b0,
    parameter bit PARALLEL_TUBES = 1'b0,
    parameter bit PIPELINED_KCL_FINISH = 1'b0,
    parameter bit PIPELINED_KCL_COLUMNS = 1'b0,
    parameter bit PIPELINED_KCL_ACCUMULATOR = 1'b0,
    parameter bit PIPELINED_KCL_CAPACITOR_CURRENT = 1'b0,
    parameter bit PIPELINED_KCL_MAXIMUM = 1'b0,
    parameter bit PIPELINED_CHORD_APPLY = 1'b0
);
    v1_solver_mono_wide_tb #(
        .TRAPEZOIDAL(1'b1),
        .BANKED(BANKED),
        .TERMINAL_CORRECTION(TERMINAL_CORRECTION),
        .PARALLEL_TUBES(PARALLEL_TUBES),
        .PIPELINED_KCL_FINISH(PIPELINED_KCL_FINISH),
        .PIPELINED_KCL_COLUMNS(PIPELINED_KCL_COLUMNS),
        .PIPELINED_KCL_ACCUMULATOR(PIPELINED_KCL_ACCUMULATOR),
        .PIPELINED_KCL_CAPACITOR_CURRENT(PIPELINED_KCL_CAPACITOR_CURRENT),
        .PIPELINED_KCL_MAXIMUM(PIPELINED_KCL_MAXIMUM),
        .PIPELINED_CHORD_APPLY(PIPELINED_CHORD_APPLY)
    ) testbench();
endmodule

`default_nettype wire
