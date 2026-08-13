`timescale 1ns/1ps
`default_nettype none

module phono_stream_mono_wide_trapezoidal_tb;
    phono_stream_mono_wide_tb #(.TRAPEZOIDAL(1'b1)) testbench();
endmodule

`default_nettype wire
