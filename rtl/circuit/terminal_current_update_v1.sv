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

// Two-batch terminal-current engine. Five physical wide multipliers evaluate
// lanes 0--4 on start and lanes 5--9 during the following cycle. Both batches
// are registered before `ready`; this cuts the rounding/saturation/popcount
// path at the cost of one solver clock. The arithmetic is identical to
// terminal_current_update_v1.
/* verilator lint_off DECLFILENAME */
module terminal_current_update_v1_half_parallel (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         start,
    input  logic [399:0] terminal_voltage_q30,
    input  logic [399:0] previous_voltage_q30,
    input  logic [479:0] previous_current_q44,
    output logic [479:0] next_current_q44,
    output logic [3:0]   saturation_count,
    output logic         ready
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

    logic active;
    logic [199:0] terminal_voltage_second_latched;
    logic [199:0] previous_voltage_second_latched;
    logic [239:0] previous_current_second_latched;
    logic [4:0] first_overflow;
    // The difference of two signed 40-bit terminal voltages fits exactly in
    // 41 signed bits. The legacy all-lane engine sign-extends it to 44 bits;
    // retaining only the non-redundant bits here is numerically identical and
    // prevents redundant sign columns from widening the shared multiplier.
    logic signed [40:0] worker_delta [0:4];
    logic signed [47:0] worker_conductance [0:4];
    logic signed [91:0] worker_product [0:4];
    logic signed [62:0] worker_current [0:4];
    logic [4:0] worker_overflow;
    logic [9:0] overflow_combined;
    logic signed [39:0] worker_terminal_voltage [0:4];
    logic signed [39:0] worker_previous_voltage [0:4];
    logic signed [47:0] worker_previous_current [0:4];

    always_comb begin
        overflow_combined = '0;
        for (int worker = 0; worker < 5; worker = worker + 1) begin
            // Explicit fixed lane pairs avoid a generic variable part-select
            // mux in front of every shared worker. Select the coefficient
            // before multiplication as well; calling the generated case
            // function with a dynamic lane lets synthesis distribute the
            // multiply over every case arm.
            case (worker)
                0: begin
                    worker_terminal_voltage[worker] = active
                        ? terminal_voltage_second_latched[0 * 40 +: 40]
                        : terminal_voltage_q30[0 * 40 +: 40];
                    worker_previous_voltage[worker] = active
                        ? previous_voltage_second_latched[0 * 40 +: 40]
                        : previous_voltage_q30[0 * 40 +: 40];
                    worker_previous_current[worker] = active
                        ? previous_current_second_latched[0 * 48 +: 48]
                        : previous_current_q44[0 * 48 +: 48];
                    worker_conductance[worker] = active
                        ? v1_terminal_cap_g_q47(5)
                        : v1_terminal_cap_g_q47(0);
                end
                1: begin
                    worker_terminal_voltage[worker] = active
                        ? terminal_voltage_second_latched[1 * 40 +: 40]
                        : terminal_voltage_q30[1 * 40 +: 40];
                    worker_previous_voltage[worker] = active
                        ? previous_voltage_second_latched[1 * 40 +: 40]
                        : previous_voltage_q30[1 * 40 +: 40];
                    worker_previous_current[worker] = active
                        ? previous_current_second_latched[1 * 48 +: 48]
                        : previous_current_q44[1 * 48 +: 48];
                    worker_conductance[worker] = active
                        ? v1_terminal_cap_g_q47(6)
                        : v1_terminal_cap_g_q47(1);
                end
                2: begin
                    worker_terminal_voltage[worker] = active
                        ? terminal_voltage_second_latched[2 * 40 +: 40]
                        : terminal_voltage_q30[2 * 40 +: 40];
                    worker_previous_voltage[worker] = active
                        ? previous_voltage_second_latched[2 * 40 +: 40]
                        : previous_voltage_q30[2 * 40 +: 40];
                    worker_previous_current[worker] = active
                        ? previous_current_second_latched[2 * 48 +: 48]
                        : previous_current_q44[2 * 48 +: 48];
                    worker_conductance[worker] = active
                        ? v1_terminal_cap_g_q47(7)
                        : v1_terminal_cap_g_q47(2);
                end
                3: begin
                    worker_terminal_voltage[worker] = active
                        ? terminal_voltage_second_latched[3 * 40 +: 40]
                        : terminal_voltage_q30[3 * 40 +: 40];
                    worker_previous_voltage[worker] = active
                        ? previous_voltage_second_latched[3 * 40 +: 40]
                        : previous_voltage_q30[3 * 40 +: 40];
                    worker_previous_current[worker] = active
                        ? previous_current_second_latched[3 * 48 +: 48]
                        : previous_current_q44[3 * 48 +: 48];
                    worker_conductance[worker] = active
                        ? v1_terminal_cap_g_q47(8)
                        : v1_terminal_cap_g_q47(3);
                end
                default: begin
                    worker_terminal_voltage[worker] = active
                        ? terminal_voltage_second_latched[4 * 40 +: 40]
                        : terminal_voltage_q30[4 * 40 +: 40];
                    worker_previous_voltage[worker] = active
                        ? previous_voltage_second_latched[4 * 40 +: 40]
                        : previous_voltage_q30[4 * 40 +: 40];
                    worker_previous_current[worker] = active
                        ? previous_current_second_latched[4 * 48 +: 48]
                        : previous_current_q44[4 * 48 +: 48];
                    worker_conductance[worker] = active
                        ? v1_terminal_cap_g_q47(9)
                        : v1_terminal_cap_g_q47(4);
                end
            endcase
            worker_delta[worker] =
                $signed({worker_terminal_voltage[worker][39],
                         worker_terminal_voltage[worker]})
                - $signed({worker_previous_voltage[worker][39],
                           worker_previous_voltage[worker]});
            worker_product[worker] = worker_conductance[worker]
                                     * worker_delta[worker];
            worker_current[worker] = rounded_current_q44(
                worker_product[worker]
            ) - $signed({{15{worker_previous_current[worker][47]}},
                          worker_previous_current[worker]});
            worker_overflow[worker] = current_exceeds_48(
                worker_current[worker]
            );
            overflow_combined[worker] = first_overflow[worker];
            overflow_combined[worker + 5] = worker_overflow[worker];
        end
    end

    integer worker;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            active <= 1'b0;
            terminal_voltage_second_latched <= '0;
            previous_voltage_second_latched <= '0;
            previous_current_second_latched <= '0;
            first_overflow <= '0;
            next_current_q44 <= '0;
            saturation_count <= '0;
            ready <= 1'b0;
        end else if (ready) begin
            ready <= 1'b0;
        end else if (active) begin
            for (worker = 0; worker < 5; worker = worker + 1)
                next_current_q44[(worker + 5) * 48 +: 48] <=
                    saturate_current_q44(worker_current[worker]);
            saturation_count <= popcount10(overflow_combined);
            active <= 1'b0;
            ready <= 1'b1;
        end else if (start) begin
            terminal_voltage_second_latched <=
                terminal_voltage_q30[200 +: 200];
            previous_voltage_second_latched <=
                previous_voltage_q30[200 +: 200];
            previous_current_second_latched <=
                previous_current_q44[240 +: 240];
            for (worker = 0; worker < 5; worker = worker + 1) begin
                next_current_q44[worker * 48 +: 48] <=
                    saturate_current_q44(worker_current[worker]);
                first_overflow[worker] <= worker_overflow[worker];
            end
            active <= 1'b1;
        end
    end

endmodule
/* verilator lint_on DECLFILENAME */

`default_nettype wire
