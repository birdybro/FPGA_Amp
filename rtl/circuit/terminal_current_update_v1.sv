`timescale 1ns/1ps
`default_nettype none

// Recompute all ten trapezoidal companion currents after the terminal chord
// correction changes the committed capacitor voltages.  This block preserves
// the existing single-edge combinational contract so it can first be timed in
// isolation; any later pipelining must be an explicit solver-schedule change.
module terminal_current_update_v1 (
    input  logic [399:0] terminal_voltage_q30,
    input  logic [399:0] previous_voltage_q30,
    input  logic [479:0] previous_current_q44,
    output logic [479:0] next_current_q44,
    output logic [3:0]   saturation_count
);

`include "model/generated/v1_cap_conductance_q0_47_trapezoidal.svh"

    function automatic logic signed [62:0] rounded_current_q44(
        input logic signed [91:0] product
    );
        logic signed [91:0] biased;
        begin
            biased = product + (92'sd1 <<< 32);
            rounded_current_q44 = 63'($signed(biased) >>> 33);
        end
    endfunction

    function automatic logic signed [47:0] saturate_current_q44(
        input logic signed [62:0] value
    );
        begin
            if (value > 63'sd140737488355327)
                saturate_current_q44 = 48'sh7fffffffffff;
            else if (value < -63'sd140737488355328)
                saturate_current_q44 = 48'sh800000000000;
            else
                saturate_current_q44 = value[47:0];
        end
    endfunction

    function automatic logic current_exceeds_48(
        input logic signed [62:0] value
    );
        begin
            current_exceeds_48 = (value > 63'sd140737488355327)
                                 || (value < -63'sd140737488355328);
        end
    endfunction

    // An explicit balanced tree avoids turning ten independent overflow
    // comparisons into a serial chain on the terminal commit edge.
    function automatic logic [3:0] popcount10(input logic [9:0] bits);
        logic [1:0] pair_0;
        logic [1:0] pair_1;
        logic [1:0] pair_2;
        logic [1:0] pair_3;
        logic [1:0] pair_4;
        logic [2:0] group_0;
        logic [2:0] group_1;
        begin
            pair_0 = {1'b0, bits[0]} + {1'b0, bits[1]};
            pair_1 = {1'b0, bits[2]} + {1'b0, bits[3]};
            pair_2 = {1'b0, bits[4]} + {1'b0, bits[5]};
            pair_3 = {1'b0, bits[6]} + {1'b0, bits[7]};
            pair_4 = {1'b0, bits[8]} + {1'b0, bits[9]};
            group_0 = {1'b0, pair_0} + {1'b0, pair_1};
            group_1 = {1'b0, pair_2} + {1'b0, pair_3};
            popcount10 = {1'b0, group_0} + {1'b0, group_1}
                         + {2'b00, pair_4};
        end
    endfunction

    logic signed [43:0] voltage_delta [0:9];
    logic signed [91:0] product [0:9];
    logic signed [62:0] current_value [0:9];
    logic [9:0] overflow_by_lane;

    always_comb begin
        for (int lane = 0; lane < 10; lane = lane + 1) begin
            voltage_delta[lane] =
                $signed({{4{terminal_voltage_q30[lane * 40 + 39]}},
                          terminal_voltage_q30[lane * 40 +: 40]})
                - $signed({{4{previous_voltage_q30[lane * 40 + 39]}},
                            previous_voltage_q30[lane * 40 +: 40]});
            product[lane] = v1_terminal_cap_g_q47(lane)
                            * voltage_delta[lane];
            current_value[lane] = rounded_current_q44(product[lane])
                - $signed({{15{previous_current_q44[lane * 48 + 47]}},
                            previous_current_q44[lane * 48 +: 48]});
            next_current_q44[lane * 48 +: 48] =
                saturate_current_q44(current_value[lane]);
            overflow_by_lane[lane] = current_exceeds_48(
                current_value[lane]
            );
        end
        saturation_count = popcount10(overflow_by_lane);
    end

endmodule

`default_nettype wire
