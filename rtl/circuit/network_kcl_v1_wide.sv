`timescale 1ns/1ps
`default_nettype none

// Wide-state V1 residual engine. The resistor/source conductance matrix is
// static; all ten capacitors are evaluated as cancellation-safe Q30 branch-
// voltage differences. Optional trapezoidal mode subtracts explicit Q4.44
// previous branch current and returns the saturated current for state commit.
// A request chooses the maximum correction precision, and the block globally
// falls back through Q40/Q34/Q30 until every signed 25-bit operand fits.
module network_kcl_v1_wide #(
    parameter MATRIX_FILE = "model/generated/v1_static_matrix_q0_47.mem",
    parameter CAP_G_FILE = "model/generated/v1_cap_conductance_q0_47.mem",
    parameter bit TRAPEZOIDAL = 1'b0,
    // Optional timing schedule. Two finish registers split fixed-point format
    // conversion, global fallback selection, and output saturation. Arithmetic
    // is identical; the request/valid latency increases by two clocks.
    parameter bit PIPELINED_FINISH = 1'b0,
    // Register each issued product, round the previous product, and accumulate
    // the prior current concurrently. This adds two fill clocks per request.
    parameter bit PIPELINED_COLUMNS = 1'b0,
    // With PIPELINED_COLUMNS, register matrix-current plus capacitor-stamp
    // before adding it to the running residual. This adds one fill clock and
    // leaves only one 63-bit addition on the accumulator feedback path.
    parameter bit PIPELINED_ACCUMULATOR = 1'b0,
    // With PIPELINED_COLUMNS, separate 92-bit capacitor-product rounding from
    // trapezoidal history subtraction and delay matrix currents to match. This
    // adds one fill clock per request.
    parameter bit PIPELINED_CAPACITOR_CURRENT = 1'b0,
    // Pipeline the exact nine-row maximum diagnostic when
    // diagnostic_max_enable is asserted. With PIPELINED_FINISH, all four
    // comparator levels are registered. Without it, DECOUPLED_MAXIMUM may
    // launch the correction on time while registered absolute, pair, quad,
    // and final stages finish through the following chord operation.
    parameter bit PIPELINED_MAXIMUM = 1'b0,
    // Emit the correction result after the first maximum-pipeline boundary,
    // then complete the final-only diagnostic through a separate max_valid
    // sideband. The engine remains busy until that sideband is committed.
    parameter bit DECOUPLED_MAXIMUM = 1'b0,
    // Reuse the wide capacitor multiplier for branch 9 and branches 0--8.
    // Branch 9 is prefetched directly from the request buses on acceptance.
    parameter bit SHARED_CAPACITOR_MULTIPLIER = 1'b0
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  start,
    input  logic [359:0]          voltage,
    input  logic [399:0]          capacitor_state_q30,
    input  logic [479:0]          capacitor_current_state_q44,
    input  logic [494:0]          rhs_q44,
    input  logic [5:0]            requested_residual_fractional_bits,
    input  logic                  diagnostic_max_enable,
    input  logic                  tube_current_valid,
    input  logic [127:0]          tube_current_q31,
    output logic [224:0]          residual,
    output logic [5:0]            residual_fractional_bits,
    output logic [62:0]           max_abs_residual_q44,
    output logic                  max_valid,
    output logic                  correction_scale_fallback,
    output logic                  saturation_any,
    output logic [3:0]            saturation_count,
    output logic [479:0]          capacitor_current_next_q44,
    output logic [3:0]            capacitor_current_saturation_count,
    output logic                  busy,
    output logic                  valid
);

    // Generated bounds prove 41 bits for the static resistor matrix. Backward
    // Euler needs 47 capacitor-coefficient bits; trapezoidal doubles the
    // 470 nF companion and therefore requires all 48 signed Q0.47 bits.
    logic signed [40:0] matrix [0:80];
    logic signed [47:0] capacitor_g [0:9];
    logic signed [39:0] voltage_latched [0:8];
    logic signed [39:0] capacitor_latched [0:9];
    logic signed [47:0] capacitor_current_latched [0:9];
    logic signed [47:0] capacitor_current_result [0:8];
    logic signed [62:0] accumulator [0:8];
    logic signed [80:0] matrix_product_staged [0:8];
    logic signed [62:0] matrix_current_staged [0:8];
    logic signed [62:0] matrix_current_aligned [0:8];
    logic signed [91:0] capacitor_product_staged;
    logic signed [91:0] cap9_product_staged;
    logic signed [62:0] capacitor_current_staged;
    logic signed [62:0] capacitor_rounded_staged;
    logic signed [62:0] cap9_rounded_staged;
    logic signed [62:0] column_contribution_staged [0:8];
    logic signed [62:0] final_residual_latched [0:8];
    logic signed [31:0] current_latched [0:3]; // ip1, ig1, ip2, ig2
    logic [5:0] requested_fraction_latched;
    logic diagnostic_max_latched;
    logic [3:0] column;
    logic [3:0] product_column_staged;
    logic [3:0] column_staged;
    logic product_stage_valid;
    logic column_stage_valid;
    logic rounded_stage_valid;
    logic [3:0] rounded_column_staged;
    logic contribution_stage_valid;
    logic [3:0] contribution_column_staged;
    logic columns_issued;
    logic finish_pending;
    logic finish_result_staged;
    logic finish_conversion_staged;
    logic finish_selection_staged;
    logic current_ready;
    logic [3:0] current_saturation_running;

    initial begin
        if (SHARED_CAPACITOR_MULTIPLIER && !PIPELINED_COLUMNS)
            $error("SHARED_CAPACITOR_MULTIPLIER requires PIPELINED_COLUMNS");
        if (PIPELINED_MAXIMUM && !PIPELINED_FINISH
            && !DECOUPLED_MAXIMUM)
            $error("unpipelined finish requires DECOUPLED_MAXIMUM");
        if (DECOUPLED_MAXIMUM && !PIPELINED_MAXIMUM)
            $error("DECOUPLED_MAXIMUM requires PIPELINED_MAXIMUM");
        $readmemh(MATRIX_FILE, matrix);
        $readmemh(CAP_G_FILE, capacitor_g);
    end

    function automatic int voltage_fractional_bits(input int index);
        begin
            case (index)
                1, 3, 6: voltage_fractional_bits = 28;
                default: voltage_fractional_bits = 32;
            endcase
        end
    endfunction

    function automatic int cap_node_a(input int index);
        begin
            case (index)
                0, 1: cap_node_a = 0;
                2, 6: cap_node_a = 1;
                3, 4, 8: cap_node_a = 4;
                5, 9: cap_node_a = 6;
                7: cap_node_a = 5;
                default: cap_node_a = -1;
            endcase
        end
    endfunction

    function automatic int cap_node_b(input int index);
        begin
            case (index)
                0: cap_node_b = 2;
                1: cap_node_b = 1;
                2: cap_node_b = 2;
                3: cap_node_b = 7;
                4: cap_node_b = 6;
                5: cap_node_b = 7;
                6: cap_node_b = 3;
                9: cap_node_b = 8;
                default: cap_node_b = -1;
            endcase
        end
    endfunction

    function automatic logic signed [62:0] rounded_matrix_q44(
        input logic signed [80:0] product,
        input int shift
    );
        logic signed [80:0] biased;
        begin
            biased = product + (81'sd1 <<< (shift - 1));
            rounded_matrix_q44 = 63'($signed(biased) >>> shift);
        end
    endfunction

    function automatic logic signed [62:0] rounded_capacitor_q44(
        input logic signed [91:0] product
    );
        logic signed [91:0] biased;
        begin
            biased = product + (92'sd1 <<< 32);
            rounded_capacitor_q44 = 63'($signed(biased) >>> 33);
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

    function automatic logic current_overflow(
        input logic signed [62:0] value
    );
        begin
            current_overflow = (value > 63'sd140737488355327)
                               || (value < -63'sd140737488355328);
        end
    endfunction

    function automatic logic signed [41:0] node_voltage_q30(
        input logic signed [39:0] value,
        input int index
    );
        logic signed [41:0] extended;
        begin
            extended = {{2{value[39]}}, value};
            if (voltage_fractional_bits(index) == 28)
                node_voltage_q30 = extended <<< 2;
            else
                node_voltage_q30 = (extended + 42'sd2) >>> 2;
        end
    endfunction

    function automatic logic signed [62:0] tube_stamp(
        input int row,
        input logic signed [31:0] ip1,
        input logic signed [31:0] ig1,
        input logic signed [31:0] ip2,
        input logic signed [31:0] ig2
    );
        logic signed [33:0] summed_current;
        begin
            tube_stamp = '0;
            case (row)
                0: tube_stamp = {{18{ig1[31]}}, ig1, 13'b0};
                1: tube_stamp = {{18{ip1[31]}}, ip1, 13'b0};
                2: begin
                    // Widen before negation: (-INT32_MIN)+(-INT32_MIN) is
                    // +2^32 and cannot be represented by a 33-bit expression.
                    summed_current = -$signed({{2{ip1[31]}}, ip1})
                                     - $signed({{2{ig1[31]}}, ig1});
                    tube_stamp = {{16{summed_current[33]}}, summed_current, 13'b0};
                end
                4: tube_stamp = {{18{ig2[31]}}, ig2, 13'b0};
                6: tube_stamp = {{18{ip2[31]}}, ip2, 13'b0};
                7: begin
                    summed_current = -$signed({{2{ip2[31]}}, ip2})
                                     - $signed({{2{ig2[31]}}, ig2});
                    tube_stamp = {{16{summed_current[33]}}, summed_current, 13'b0};
                end
                default: tube_stamp = '0;
            endcase
        end
    endfunction

    function automatic logic signed [62:0] capacitor_stamp(
        input int capacitor_index,
        input int row,
        input logic signed [62:0] branch_current
    );
        begin
            capacitor_stamp = '0;
            if (cap_node_a(capacitor_index) == row)
                capacitor_stamp = capacitor_stamp + branch_current;
            if (cap_node_b(capacitor_index) == row)
                capacitor_stamp = capacitor_stamp - branch_current;
        end
    endfunction

    function automatic logic [62:0] absolute_q44(
        input logic signed [62:0] value
    );
        begin
            if (value[62])
                absolute_q44 = $unsigned(-value);
            else
                absolute_q44 = $unsigned(value);
        end
    endfunction

    function automatic logic signed [62:0] convert_residual(
        input logic signed [62:0] value_q44,
        input logic [5:0] fraction
    );
        begin
            case (fraction)
                6'd40: convert_residual = (value_q44 + 63'sd8) >>> 4;
                6'd34: convert_residual = (value_q44 + 63'sd512) >>> 10;
                default: convert_residual = (value_q44 + 63'sd8192) >>> 14;
            endcase
        end
    endfunction

    function automatic logic correction_overflow(
        input logic [38:0] converted_upper
    );
        begin
            // A value fits signed 25-bit exactly when every discarded bit is
            // a copy of bit 24. This is equivalent to the two numerical
            // bounds comparisons but maps to a reduction tree instead of a
            // pair of 63-bit carry chains.
            correction_overflow =
                converted_upper[38:1] != {38{converted_upper[0]}};
        end
    endfunction

    function automatic logic signed [24:0] saturate_correction(
        input logic signed [62:0] converted
    );
        begin
            if (!correction_overflow(converted[62:24]))
                saturate_correction = converted[24:0];
            else if (converted[62])
                saturate_correction = 25'sh1000000;
            else
                saturate_correction = 25'sh0ffffff;
        end
    endfunction

    logic signed [80:0] matrix_product_by_row [0:8];
    logic signed [62:0] matrix_current_by_row [0:8];
    logic signed [41:0] cap_voltage_a_q30;
    logic signed [41:0] cap_voltage_b_q30;
    // A branch can join two full-range Q28 nodes and subtract a full-range
    // Q30 history state.  After conversion, that exact difference requires
    // 44 signed bits; 43 bits would silently wrap at the declared limits.
    logic signed [43:0] cap_delta_q30;
    logic signed [47:0] capacitor_multiplier_g;
    logic signed [43:0] capacitor_multiplier_delta;
    logic signed [91:0] cap_product;
    logic signed [62:0] cap_current_q44;
    logic signed [41:0] cap9_voltage_a_q30;
    logic signed [41:0] cap9_voltage_b_q30;
    logic signed [43:0] cap9_delta_q30;
    logic signed [41:0] cap9_input_voltage_a_q30;
    logic signed [41:0] cap9_input_voltage_b_q30;
    logic signed [43:0] cap9_input_delta_q30;
    logic signed [91:0] cap9_product;
    logic signed [62:0] cap9_current_q44;
    logic signed [62:0] cap9_current_from_product_q44;
    logic signed [62:0] cap9_current_latched_q44;
    logic signed [31:0] finish_current_by_lane [0:3];
    logic signed [62:0] matrix_current_from_product_by_row [0:8];
    logic signed [62:0] capacitor_current_from_product;
    logic signed [62:0] capacitor_rounded_from_product;
    logic signed [62:0] capacitor_current_from_rounded;
    logic signed [62:0] cap9_rounded_from_product_q44;
    logic signed [62:0] cap9_current_from_rounded_q44;
    logic signed [62:0] final_residual_input_by_row [0:8];
    logic signed [62:0] q30_by_row [0:8];
    logic signed [62:0] q34_by_row [0:8];
    logic signed [62:0] q40_by_row [0:8];
    logic signed [62:0] q30_staged_by_row [0:8];
    logic signed [62:0] q34_staged_by_row [0:8];
    logic signed [62:0] q40_staged_by_row [0:8];
    logic signed [62:0] selected_by_row [0:8];
    logic signed [62:0] selected_staged_by_row [0:8];
    logic [8:0] q34_fit_by_row;
    logic [8:0] q40_fit_by_row;
    logic [8:0] q30_overflow_by_row;
    logic [8:0] q34_fit_staged_by_row;
    logic [8:0] q40_fit_staged_by_row;
    logic q30_saturation_combined;
    logic [3:0] q30_saturation_count_combined;
    logic [8:0] selected_overflow_by_row;
    logic [62:0] absolute_by_row [0:8];
    logic [62:0] absolute_staged_by_row [0:8];
    logic [62:0] maximum_pair [0:3];
    logic [62:0] maximum_quad [0:1];
    logic q34_all_fit;
    logic q40_all_fit;
    logic [5:0] selected_fraction;
    logic [62:0] max_abs_combined;
    logic saturation_combined;
    logic [3:0] saturation_count_combined;
    logic [5:0] selected_fraction_staged;
    logic [62:0] max_abs_staged;
    logic saturation_staged;
    logic [3:0] saturation_count_staged;
    logic [62:0] maximum_pair_staged [0:3];
    logic [62:0] maximum_quad_staged [0:1];
    logic [62:0] maximum_final_staged;
    logic [62:0] maximum_row8_staged;
    logic [2:0] maximum_pipeline_stage;

    function automatic logic [62:0] maximum_u63(
        input logic [62:0] left,
        input logic [62:0] right
    );
        begin
            maximum_u63 = left > right ? left : right;
        end
    endfunction

    function automatic logic [3:0] popcount9(input logic [8:0] bits);
        logic [1:0] pair_0;
        logic [1:0] pair_1;
        logic [1:0] pair_2;
        logic [1:0] pair_3;
        logic [2:0] group_0;
        logic [2:0] group_1;
        begin
            pair_0 = {1'b0, bits[0]} + {1'b0, bits[1]};
            pair_1 = {1'b0, bits[2]} + {1'b0, bits[3]};
            pair_2 = {1'b0, bits[4]} + {1'b0, bits[5]};
            pair_3 = {1'b0, bits[6]} + {1'b0, bits[7]};
            group_0 = {1'b0, pair_0} + {1'b0, pair_1};
            group_1 = {1'b0, pair_2} + {1'b0, pair_3};
            popcount9 = {1'b0, group_0} + {1'b0, group_1}
                        + {3'b000, bits[8]};
        end
    endfunction

    always_comb begin
        for (int row = 0; row < 9; row = row + 1) begin
            matrix_product_by_row[row] =
                matrix[row * 9 + int'(column)] * voltage_latched[column];
            matrix_current_by_row[row] = rounded_matrix_q44(
                matrix_product_by_row[row], voltage_fractional_bits(int'(column)) + 3
            );
        end

        cap_voltage_a_q30 = '0;
        cap_voltage_b_q30 = '0;
        if (cap_node_a(int'(column)) >= 0)
            cap_voltage_a_q30 = node_voltage_q30(
                voltage_latched[cap_node_a(int'(column))], cap_node_a(int'(column))
            );
        if (cap_node_b(int'(column)) >= 0)
            cap_voltage_b_q30 = node_voltage_q30(
                voltage_latched[cap_node_b(int'(column))], cap_node_b(int'(column))
            );
        cap_delta_q30 = $signed({{2{cap_voltage_a_q30[41]}}, cap_voltage_a_q30})
                         - $signed({{2{cap_voltage_b_q30[41]}}, cap_voltage_b_q30})
                         - $signed({{4{capacitor_latched[column][39]}},
                                    capacitor_latched[column]});
        cap9_voltage_a_q30 = node_voltage_q30(voltage_latched[6], 6);
        cap9_voltage_b_q30 = node_voltage_q30(voltage_latched[8], 8);
        cap9_delta_q30 = $signed({{2{cap9_voltage_a_q30[41]}}, cap9_voltage_a_q30})
                          - $signed({{2{cap9_voltage_b_q30[41]}}, cap9_voltage_b_q30})
                          - $signed({{4{capacitor_latched[9][39]}},
                                     capacitor_latched[9]});
        cap9_input_voltage_a_q30 = node_voltage_q30(
            $signed(voltage[6 * 40 +: 40]), 6
        );
        cap9_input_voltage_b_q30 = node_voltage_q30(
            $signed(voltage[8 * 40 +: 40]), 8
        );
        cap9_input_delta_q30 = $signed({
            {2{cap9_input_voltage_a_q30[41]}}, cap9_input_voltage_a_q30
        }) - $signed({
            {2{cap9_input_voltage_b_q30[41]}}, cap9_input_voltage_b_q30
        }) - $signed({
            {4{capacitor_state_q30[9 * 40 + 39]}},
            capacitor_state_q30[9 * 40 +: 40]
        });
        if (SHARED_CAPACITOR_MULTIPLIER && !busy) begin
            capacitor_multiplier_g = capacitor_g[9];
            capacitor_multiplier_delta = cap9_input_delta_q30;
        end else begin
            capacitor_multiplier_g = capacitor_g[column];
            capacitor_multiplier_delta = cap_delta_q30;
        end
        cap_product = capacitor_multiplier_g * capacitor_multiplier_delta;
        cap_current_q44 = rounded_capacitor_q44(cap_product);
        if (TRAPEZOIDAL)
            cap_current_q44 = cap_current_q44 - $signed({
                {15{capacitor_current_latched[column][47]}},
                capacitor_current_latched[column]
            });

        if (SHARED_CAPACITOR_MULTIPLIER)
            cap9_product = cap_product;
        else
            cap9_product = capacitor_g[9] * cap9_delta_q30;
        cap9_current_q44 = rounded_capacitor_q44(cap9_product);
        if (TRAPEZOIDAL)
            cap9_current_q44 = cap9_current_q44 - $signed({
                {15{capacitor_current_latched[9][47]}},
                capacitor_current_latched[9]
            });

        for (int row = 0; row < 9; row = row + 1)
            matrix_current_from_product_by_row[row] = rounded_matrix_q44(
                matrix_product_staged[row],
                voltage_fractional_bits(int'(product_column_staged)) + 3
            );
        capacitor_rounded_from_product = rounded_capacitor_q44(
            capacitor_product_staged
        );
        capacitor_current_from_product = capacitor_rounded_from_product;
        if (TRAPEZOIDAL)
            capacitor_current_from_product = capacitor_current_from_product
                - $signed({
                    {15{capacitor_current_latched[
                        product_column_staged
                    ][47]}},
                    capacitor_current_latched[product_column_staged]
                });
        cap9_rounded_from_product_q44 = rounded_capacitor_q44(
            cap9_product_staged
        );
        cap9_current_from_product_q44 = cap9_rounded_from_product_q44;
        if (TRAPEZOIDAL)
            cap9_current_from_product_q44 = cap9_current_from_product_q44
                - $signed({
                    {15{capacitor_current_latched[9][47]}},
                    capacitor_current_latched[9]
                });

        capacitor_current_from_rounded = capacitor_rounded_staged;
        if (TRAPEZOIDAL)
            capacitor_current_from_rounded = capacitor_current_from_rounded
                - $signed({
                    {15{capacitor_current_latched[
                        rounded_column_staged
                    ][47]}},
                    capacitor_current_latched[rounded_column_staged]
                });
        cap9_current_from_rounded_q44 = cap9_rounded_staged;
        if (TRAPEZOIDAL)
            cap9_current_from_rounded_q44 = cap9_current_from_rounded_q44
                - $signed({
                    {15{capacitor_current_latched[9][47]}},
                    capacitor_current_latched[9]
                });

        capacitor_current_next_q44 = '0;
        for (int capacitor_index = 0; capacitor_index < 9;
             capacitor_index = capacitor_index + 1)
            capacitor_current_next_q44[capacitor_index * 48 +: 48] =
                capacitor_current_result[capacitor_index];
        capacitor_current_next_q44[9 * 48 +: 48] =
            saturate_current_q44(cap9_current_latched_q44);
        capacitor_current_saturation_count = current_saturation_running;
        if (TRAPEZOIDAL && current_overflow(cap9_current_latched_q44))
            capacitor_current_saturation_count =
                capacitor_current_saturation_count + 1'b1;

        for (int current_index = 0; current_index < 4;
             current_index = current_index + 1) begin
            if (tube_current_valid)
                finish_current_by_lane[current_index] = $signed(
                    tube_current_q31[current_index * 32 +: 32]
                );
            else
                finish_current_by_lane[current_index] =
                    current_latched[current_index];
        end
        for (int row = 0; row < 9; row = row + 1)
            final_residual_input_by_row[row] = accumulator[row]
                + tube_stamp(
                    row,
                    finish_current_by_lane[0], finish_current_by_lane[1],
                    finish_current_by_lane[2], finish_current_by_lane[3]
                )
                + capacitor_stamp(9, row, cap9_current_latched_q44);

        for (int row = 0; row < 9; row = row + 1) begin
            q30_by_row[row] = convert_residual(
                final_residual_latched[row], 6'd30
            );
            q34_by_row[row] = convert_residual(
                final_residual_latched[row], 6'd34
            );
            q40_by_row[row] = convert_residual(
                final_residual_latched[row], 6'd40
            );
            if (PIPELINED_FINISH) begin
                q34_fit_by_row[row] = q34_fit_staged_by_row[row];
                q40_fit_by_row[row] = q40_fit_staged_by_row[row];
            end else begin
                q34_fit_by_row[row] =
                    !correction_overflow(q34_by_row[row][62:24]);
                q40_fit_by_row[row] =
                    !correction_overflow(q40_by_row[row][62:24]);
            end
            q30_overflow_by_row[row] = correction_overflow(
                PIPELINED_FINISH
                    ? q30_staged_by_row[row][62:24]
                    : q30_by_row[row][62:24]
            );
        end
        q30_saturation_combined = |q30_overflow_by_row;
        q30_saturation_count_combined = popcount9(q30_overflow_by_row);
        q34_all_fit = &q34_fit_by_row;
        q40_all_fit = &q40_fit_by_row;

        selected_fraction = 6'd30;
        if (requested_fraction_latched == 6'd40) begin
            if (q40_all_fit)
                selected_fraction = 6'd40;
            else if (q34_all_fit)
                selected_fraction = 6'd34;
        end else if (requested_fraction_latched == 6'd34 && q34_all_fit) begin
            selected_fraction = 6'd34;
        end

        for (int row = 0; row < 9; row = row + 1) begin
            case (selected_fraction)
                6'd40: selected_by_row[row] = PIPELINED_FINISH
                    ? q40_staged_by_row[row] : q40_by_row[row];
                6'd34: selected_by_row[row] = PIPELINED_FINISH
                    ? q34_staged_by_row[row] : q34_by_row[row];
                default: selected_by_row[row] = PIPELINED_FINISH
                    ? q30_staged_by_row[row] : q30_by_row[row];
            endcase
            absolute_by_row[row] = PIPELINED_FINISH
                ? absolute_staged_by_row[row]
                : absolute_q44(final_residual_latched[row]);
            if (PIPELINED_FINISH)
                selected_overflow_by_row[row] =
                    (selected_fraction == 6'd30)
                    && q30_overflow_by_row[row];
            else
                selected_overflow_by_row[row] = correction_overflow(
                    selected_by_row[row][62:24]
                );
        end
        maximum_pair[0] = maximum_u63(absolute_by_row[0], absolute_by_row[1]);
        maximum_pair[1] = maximum_u63(absolute_by_row[2], absolute_by_row[3]);
        maximum_pair[2] = maximum_u63(absolute_by_row[4], absolute_by_row[5]);
        maximum_pair[3] = maximum_u63(absolute_by_row[6], absolute_by_row[7]);
        maximum_quad[0] = maximum_u63(maximum_pair[0], maximum_pair[1]);
        maximum_quad[1] = maximum_u63(maximum_pair[2], maximum_pair[3]);
        max_abs_combined = maximum_u63(
            maximum_u63(maximum_quad[0], maximum_quad[1]),
            absolute_by_row[8]
        );
        if (PIPELINED_FINISH) begin
            // A Q34/Q40 result is selected only when every row has already
            // passed its fit test, so only the Q30 fallback can saturate.
            // Evaluating its overflow reduction from registered conversions
            // avoids putting nine generic 63-bit comparisons after the global
            // precision selection without changing the selected result.
            saturation_combined = (selected_fraction == 6'd30)
                && q30_saturation_combined;
            saturation_count_combined = (selected_fraction == 6'd30)
                ? q30_saturation_count_combined : 4'd0;
        end else begin
            saturation_combined = |selected_overflow_by_row;
            saturation_count_combined = popcount9(selected_overflow_by_row);
        end
    end

    integer lane;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            busy <= 1'b0;
            valid <= 1'b0;
            max_valid <= 1'b0;
            residual <= '0;
            residual_fractional_bits <= 6'd30;
            max_abs_residual_q44 <= '0;
            correction_scale_fallback <= 1'b0;
            saturation_any <= 1'b0;
            saturation_count <= '0;
            requested_fraction_latched <= 6'd30;
            diagnostic_max_latched <= 1'b0;
            column <= '0;
            product_column_staged <= '0;
            column_staged <= '0;
            product_stage_valid <= 1'b0;
            column_stage_valid <= 1'b0;
            rounded_stage_valid <= 1'b0;
            rounded_column_staged <= '0;
            contribution_stage_valid <= 1'b0;
            contribution_column_staged <= '0;
            columns_issued <= 1'b0;
            finish_pending <= 1'b0;
            finish_result_staged <= 1'b0;
            finish_conversion_staged <= 1'b0;
            finish_selection_staged <= 1'b0;
            current_ready <= 1'b0;
            current_saturation_running <= '0;
            cap9_current_latched_q44 <= '0;
            for (lane = 0; lane < 9; lane = lane + 1) begin
                voltage_latched[lane] <= '0;
                accumulator[lane] <= '0;
                matrix_product_staged[lane] <= '0;
                matrix_current_staged[lane] <= '0;
                matrix_current_aligned[lane] <= '0;
                column_contribution_staged[lane] <= '0;
                final_residual_latched[lane] <= '0;
                q30_staged_by_row[lane] <= '0;
                q34_staged_by_row[lane] <= '0;
                q40_staged_by_row[lane] <= '0;
                selected_staged_by_row[lane] <= '0;
                absolute_staged_by_row[lane] <= '0;
            end
            q34_fit_staged_by_row <= '0;
            q40_fit_staged_by_row <= '0;
            selected_fraction_staged <= 6'd30;
            max_abs_staged <= '0;
            saturation_staged <= 1'b0;
            saturation_count_staged <= '0;
            maximum_final_staged <= '0;
            maximum_row8_staged <= '0;
            maximum_pipeline_stage <= '0;
            for (lane = 0; lane < 4; lane = lane + 1)
                maximum_pair_staged[lane] <= '0;
            for (lane = 0; lane < 2; lane = lane + 1)
                maximum_quad_staged[lane] <= '0;
            capacitor_current_staged <= '0;
            capacitor_rounded_staged <= '0;
            cap9_rounded_staged <= '0;
            capacitor_product_staged <= '0;
            cap9_product_staged <= '0;
            for (lane = 0; lane < 10; lane = lane + 1)
                capacitor_latched[lane] <= '0;
            for (lane = 0; lane < 10; lane = lane + 1)
                capacitor_current_latched[lane] <= '0;
            for (lane = 0; lane < 9; lane = lane + 1)
                capacitor_current_result[lane] <= '0;
            for (lane = 0; lane < 4; lane = lane + 1)
                current_latched[lane] <= '0;
        end else begin
            valid <= 1'b0;
            max_valid <= 1'b0;
            if (!busy) begin
                if (start) begin
                    busy <= 1'b1;
                    column <= 4'd0;
                    product_column_staged <= '0;
                    column_staged <= '0;
                    product_stage_valid <= 1'b0;
                    column_stage_valid <= 1'b0;
                    rounded_stage_valid <= 1'b0;
                    rounded_column_staged <= '0;
                    contribution_stage_valid <= 1'b0;
                    contribution_column_staged <= '0;
                    columns_issued <= 1'b0;
                    finish_pending <= 1'b0;
                    finish_result_staged <= 1'b0;
                    finish_conversion_staged <= 1'b0;
                    finish_selection_staged <= 1'b0;
                    current_ready <= tube_current_valid;
                    requested_fraction_latched <= requested_residual_fractional_bits;
                    diagnostic_max_latched <= diagnostic_max_enable;
                    correction_scale_fallback <= 1'b0;
                    saturation_any <= 1'b0;
                    saturation_count <= '0;
                    current_saturation_running <= '0;
                    if (SHARED_CAPACITOR_MULTIPLIER)
                        cap9_product_staged <= cap_product;
                    maximum_pipeline_stage <= '0;
                    for (lane = 0; lane < 9; lane = lane + 1) begin
                        voltage_latched[lane] <= $signed(
                            voltage[lane * 40 +: 40]
                        );
                        accumulator[lane] <= -$signed({
                            {8{rhs_q44[lane * 55 + 54]}},
                            rhs_q44[lane * 55 +: 55]
                        });
                    end
                    for (lane = 0; lane < 10; lane = lane + 1)
                        capacitor_latched[lane] <= $signed(
                            capacitor_state_q30[lane * 40 +: 40]
                        );
                    for (lane = 0; lane < 10; lane = lane + 1)
                        capacitor_current_latched[lane] <= $signed(
                            capacitor_current_state_q44[lane * 48 +: 48]
                        );
                    if (tube_current_valid) begin
                        for (lane = 0; lane < 4; lane = lane + 1)
                            current_latched[lane] <= $signed(
                                tube_current_q31[lane * 32 +: 32]
                            );
                    end
                end
            end else begin
                if (tube_current_valid) begin
                    for (lane = 0; lane < 4; lane = lane + 1)
                        current_latched[lane] <= $signed(
                            tube_current_q31[lane * 32 +: 32]
                        );
                    current_ready <= 1'b1;
                end
                if (!finish_pending) begin
                    if (PIPELINED_COLUMNS) begin
                        // Issue one product column every clock, round the
                        // previous product column, and accumulate the prior
                        // current column. Nine columns therefore cost two
                        // fill clocks rather than tripling latency.
                        if (!columns_issued) begin
                            for (lane = 0; lane < 9; lane = lane + 1)
                                matrix_product_staged[lane] <=
                                    matrix_product_by_row[lane];
                            capacitor_product_staged <= cap_product;
                            product_column_staged <= column;
                            product_stage_valid <= 1'b1;
                            if (column == 4'd0
                                && !SHARED_CAPACITOR_MULTIPLIER)
                                cap9_product_staged <= cap9_product;
                            if (column == 4'd8)
                                columns_issued <= 1'b1;
                            else
                                column <= column + 1'b1;
                        end else begin
                            product_stage_valid <= 1'b0;
                        end
                        if (product_stage_valid) begin
                            for (lane = 0; lane < 9; lane = lane + 1)
                                matrix_current_staged[lane] <=
                                    matrix_current_from_product_by_row[lane];
                            if (PIPELINED_CAPACITOR_CURRENT) begin
                                capacitor_rounded_staged <=
                                    capacitor_rounded_from_product;
                                rounded_column_staged <= product_column_staged;
                                rounded_stage_valid <= 1'b1;
                                if (product_column_staged == 4'd0)
                                    cap9_rounded_staged <=
                                        cap9_rounded_from_product_q44;
                            end else begin
                                capacitor_current_staged <=
                                    capacitor_current_from_product;
                                column_staged <= product_column_staged;
                                column_stage_valid <= 1'b1;
                                if (product_column_staged == 4'd0)
                                    cap9_current_latched_q44 <=
                                        cap9_current_from_product_q44;
                            end
                        end else begin
                            if (PIPELINED_CAPACITOR_CURRENT)
                                rounded_stage_valid <= 1'b0;
                            else
                                column_stage_valid <= 1'b0;
                        end
                        if (PIPELINED_CAPACITOR_CURRENT) begin
                            if (rounded_stage_valid) begin
                                for (lane = 0; lane < 9; lane = lane + 1)
                                    matrix_current_aligned[lane] <=
                                        matrix_current_staged[lane];
                                capacitor_current_staged <=
                                    capacitor_current_from_rounded;
                                column_staged <= rounded_column_staged;
                                column_stage_valid <= 1'b1;
                                if (rounded_column_staged == 4'd0)
                                    cap9_current_latched_q44 <=
                                        cap9_current_from_rounded_q44;
                            end else begin
                                column_stage_valid <= 1'b0;
                            end
                        end
                        if (column_stage_valid) begin
                            capacitor_current_result[column_staged] <=
                                saturate_current_q44(
                                    capacitor_current_staged
                                );
                            if (TRAPEZOIDAL
                                && current_overflow(
                                    capacitor_current_staged
                                ))
                                current_saturation_running <=
                                    current_saturation_running + 1'b1;
                            if (PIPELINED_ACCUMULATOR) begin
                                for (lane = 0; lane < 9; lane = lane + 1)
                                    column_contribution_staged[lane] <=
                                        (PIPELINED_CAPACITOR_CURRENT
                                            ? matrix_current_aligned[lane]
                                            : matrix_current_staged[lane])
                                        + capacitor_stamp(
                                            int'(column_staged), lane,
                                            capacitor_current_staged
                                        );
                                contribution_column_staged <= column_staged;
                                contribution_stage_valid <= 1'b1;
                            end else begin
                                for (lane = 0; lane < 9; lane = lane + 1)
                                    accumulator[lane] <= accumulator[lane]
                                        + (PIPELINED_CAPACITOR_CURRENT
                                            ? matrix_current_aligned[lane]
                                            : matrix_current_staged[lane])
                                        + capacitor_stamp(
                                            int'(column_staged), lane,
                                            capacitor_current_staged
                                        );
                                if (column_staged == 4'd8)
                                    finish_pending <= 1'b1;
                            end
                        end else if (PIPELINED_ACCUMULATOR) begin
                            contribution_stage_valid <= 1'b0;
                        end
                        if (PIPELINED_ACCUMULATOR
                            && contribution_stage_valid) begin
                            for (lane = 0; lane < 9; lane = lane + 1)
                                accumulator[lane] <= accumulator[lane]
                                    + column_contribution_staged[lane];
                            if (contribution_column_staged == 4'd8)
                                finish_pending <= 1'b1;
                        end
                    end else begin
                        // Capacitor 9 is invariant throughout the nine matrix
                        // columns. Capture it on the first column so the
                        // finish path starts at a register instead of another
                        // wide multiply.
                        if (column == 4'd0)
                            cap9_current_latched_q44 <= cap9_current_q44;
                        capacitor_current_result[column] <=
                            saturate_current_q44(cap_current_q44);
                        if (TRAPEZOIDAL && current_overflow(cap_current_q44))
                            current_saturation_running <=
                                current_saturation_running + 1'b1;
                        for (lane = 0; lane < 9; lane = lane + 1)
                            accumulator[lane] <= accumulator[lane]
                                + matrix_current_by_row[lane]
                                + capacitor_stamp(
                                    int'(column), lane, cap_current_q44
                                );
                        if (column == 4'd8)
                            finish_pending <= 1'b1;
                        else
                            column <= column + 1'b1;
                    end
                end else if (!finish_result_staged
                             && (current_ready || tube_current_valid)) begin
                    // In the integrated solver the second tube result arrives
                    // after the column MACs. Stage the complete physical KCL
                    // residual on that otherwise-waiting edge, separating its
                    // 63-bit sum from global Q40/Q34/Q30 fallback selection
                    // without adding an integrated-solver clock.
                    for (lane = 0; lane < 9; lane = lane + 1)
                        final_residual_latched[lane] <=
                            final_residual_input_by_row[lane];
                    finish_result_staged <= 1'b1;
                end else if (PIPELINED_FINISH && finish_result_staged
                             && !finish_conversion_staged) begin
                    // First timing boundary: the three exact correction
                    // formats and physical residual magnitudes. The following
                    // edge performs only global fallback selection/reduction.
                    for (lane = 0; lane < 9; lane = lane + 1) begin
                        q30_staged_by_row[lane] <= q30_by_row[lane];
                        q34_staged_by_row[lane] <= q34_by_row[lane];
                        q40_staged_by_row[lane] <= q40_by_row[lane];
                        q34_fit_staged_by_row[lane] <=
                            !correction_overflow(q34_by_row[lane][62:24]);
                        q40_fit_staged_by_row[lane] <=
                            !correction_overflow(q40_by_row[lane][62:24]);
                        absolute_staged_by_row[lane] <= absolute_q44(
                            final_residual_latched[lane]
                        );
                    end
                    finish_conversion_staged <= 1'b1;
                end else if (PIPELINED_FINISH && finish_result_staged
                             && !finish_selection_staged) begin
                    // Second timing boundary: isolate the nine output
                    // saturators from global format choice and diagnostics.
                    for (lane = 0; lane < 9; lane = lane + 1)
                        selected_staged_by_row[lane] <= selected_by_row[lane];
                    selected_fraction_staged <= selected_fraction;
                    if (PIPELINED_MAXIMUM && diagnostic_max_latched) begin
                        for (lane = 0; lane < 4; lane = lane + 1)
                            maximum_pair_staged[lane] <= maximum_pair[lane];
                        maximum_row8_staged <= absolute_by_row[8];
                        maximum_pipeline_stage <= 3'd1;
                    end else begin
                        max_abs_staged <= PIPELINED_MAXIMUM
                            ? 63'd0 : max_abs_combined;
                    end
                    saturation_staged <= saturation_combined;
                    saturation_count_staged <= saturation_count_combined;
                    finish_selection_staged <= 1'b1;
                end else if (PIPELINED_MAXIMUM && diagnostic_max_latched
                             && !PIPELINED_FINISH
                             && finish_selection_staged
                             && maximum_pipeline_stage == 3'd4) begin
                    // In the zero-schedule-cost profile the correction was
                    // already released while the chord engine is busy.  Keep
                    // the exact absolute-value negation and every maximum-tree
                    // level on separate registered boundaries; otherwise the
                    // first sideband edge recreates the residual-to-global-max
                    // carry-chain path that this profile is intended to remove.
                    for (lane = 0; lane < 4; lane = lane + 1)
                        maximum_pair_staged[lane] <= maximum_u63(
                            absolute_staged_by_row[lane * 2],
                            absolute_staged_by_row[lane * 2 + 1]
                        );
                    maximum_row8_staged <= absolute_staged_by_row[8];
                    maximum_pipeline_stage <= 3'd1;
                end else if (PIPELINED_MAXIMUM && diagnostic_max_latched
                             && finish_selection_staged
                             && maximum_pipeline_stage == 3'd1) begin
                    maximum_quad_staged[0] <= maximum_u63(
                        maximum_pair_staged[0], maximum_pair_staged[1]
                    );
                    maximum_quad_staged[1] <= maximum_u63(
                        maximum_pair_staged[2], maximum_pair_staged[3]
                    );
                    maximum_pipeline_stage <= 3'd2;
                    if (DECOUPLED_MAXIMUM && PIPELINED_FINISH) begin
                        for (lane = 0; lane < 9; lane = lane + 1)
                            residual[lane * 25 +: 25] <=
                                saturate_correction(
                                    selected_staged_by_row[lane]
                                );
                        residual_fractional_bits <= selected_fraction_staged;
                        correction_scale_fallback <=
                            selected_fraction_staged
                            != requested_fraction_latched;
                        saturation_any <= saturation_staged;
                        saturation_count <= saturation_count_staged;
                        valid <= 1'b1;
                    end
                end else if (PIPELINED_MAXIMUM && diagnostic_max_latched
                             && finish_selection_staged
                             && maximum_pipeline_stage == 3'd2) begin
                    maximum_final_staged <= maximum_u63(
                        maximum_quad_staged[0], maximum_quad_staged[1]
                    );
                    maximum_pipeline_stage <= 3'd3;
                end else if (PIPELINED_MAXIMUM && diagnostic_max_latched
                             && finish_selection_staged
                             && maximum_pipeline_stage == 3'd3) begin
                    max_abs_staged <= maximum_u63(
                        maximum_final_staged, maximum_row8_staged
                    );
                    if (DECOUPLED_MAXIMUM) begin
                        max_abs_residual_q44 <= maximum_u63(
                            maximum_final_staged, maximum_row8_staged
                        );
                        max_valid <= 1'b1;
                        busy <= 1'b0;
                        finish_pending <= 1'b0;
                        finish_result_staged <= 1'b0;
                        finish_conversion_staged <= 1'b0;
                        finish_selection_staged <= 1'b0;
                        current_ready <= 1'b0;
                        maximum_pipeline_stage <= '0;
                    end else begin
                        maximum_pipeline_stage <= 3'd4;
                    end
                end else if (finish_result_staged) begin
                    for (lane = 0; lane < 9; lane = lane + 1)
                        residual[lane * 25 +: 25] <= saturate_correction(
                            PIPELINED_FINISH
                                ? selected_staged_by_row[lane]
                                : selected_by_row[lane]
                        );
                    residual_fractional_bits <= PIPELINED_FINISH
                        ? selected_fraction_staged : selected_fraction;
                    if (PIPELINED_MAXIMUM && DECOUPLED_MAXIMUM
                        && diagnostic_max_latched && !PIPELINED_FINISH) begin
                        // The correction result is independent of this
                        // diagnostic. Launch it at the original latency while
                        // registering only the exact absolute values. Four
                        // following sideband edges register pair, quad, final,
                        // and row-eight comparisons while the chord corrector
                        // is busy, so no solver clock is added.
                        for (lane = 0; lane < 9; lane = lane + 1)
                            absolute_staged_by_row[lane] <= absolute_q44(
                                final_residual_latched[lane]
                            );
                        maximum_pipeline_stage <= 3'd4;
                        finish_selection_staged <= 1'b1;
                    end else if (!(PIPELINED_MAXIMUM && DECOUPLED_MAXIMUM
                                   && !PIPELINED_FINISH)) begin
                        // The maximum output is don't-care when diagnostics are
                        // disabled. Avoid retaining the complete combinational
                        // tree in the sideband-only profile merely to update a
                        // register whose valid flag remains low.
                        max_abs_residual_q44 <= PIPELINED_FINISH
                            ? max_abs_staged : max_abs_combined;
                        max_valid <= diagnostic_max_latched;
                    end
                    correction_scale_fallback <=
                        (PIPELINED_FINISH
                            ? selected_fraction_staged : selected_fraction)
                        != requested_fraction_latched;
                    saturation_any <= PIPELINED_FINISH
                        ? saturation_staged : saturation_combined;
                    saturation_count <= PIPELINED_FINISH
                        ? saturation_count_staged : saturation_count_combined;
                    valid <= 1'b1;
                    if (!(PIPELINED_MAXIMUM && DECOUPLED_MAXIMUM
                          && diagnostic_max_latched
                          && !PIPELINED_FINISH)) begin
                        busy <= 1'b0;
                        finish_pending <= 1'b0;
                        finish_result_staged <= 1'b0;
                        finish_conversion_staged <= 1'b0;
                        finish_selection_staged <= 1'b0;
                        current_ready <= 1'b0;
                    end
                end
            end
        end
    end
endmodule

`default_nettype wire
