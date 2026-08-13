`timescale 1ns/1ps
`default_nettype none

// Wide-state V1 residual engine. The resistor/source conductance matrix is
// static; all ten backward-Euler capacitors are evaluated as cancellation-safe
// Q30 branch-voltage differences. A request chooses the maximum correction
// precision, and the block globally falls back through Q40/Q34/Q30 until every
// signed 25-bit correction operand fits.
module network_kcl_v1_wide #(
    parameter MATRIX_FILE = "model/generated/v1_static_matrix_q0_47.mem",
    parameter CAP_G_FILE = "model/generated/v1_cap_conductance_q0_47.mem"
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  start,
    input  logic [359:0]          voltage,
    input  logic [399:0]          capacitor_state_q30,
    input  logic [494:0]          rhs_q44,
    input  logic [5:0]            requested_residual_fractional_bits,
    input  logic                  tube_current_valid,
    input  logic [127:0]          tube_current_q31,
    output logic [224:0]          residual,
    output logic [5:0]            residual_fractional_bits,
    output logic [62:0]           max_abs_residual_q44,
    output logic                  correction_scale_fallback,
    output logic                  saturation_any,
    output logic [3:0]            saturation_count,
    output logic                  busy,
    output logic                  valid
);

    // Generated bounds prove 41 bits for the static resistor matrix and 47 for
    // the largest capacitor conductance. Retaining unused sign bits here costs
    // multiple DSP slices per row.
    logic signed [40:0] matrix [0:80];
    logic signed [46:0] capacitor_g [0:9];
    logic signed [39:0] voltage_latched [0:8];
    logic signed [39:0] capacitor_latched [0:9];
    logic signed [62:0] accumulator [0:8];
    logic signed [31:0] current_latched [0:3]; // ip1, ig1, ip2, ig2
    logic [5:0] requested_fraction_latched;
    logic [3:0] column;
    logic finish_pending;
    logic current_ready;

    initial begin
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
        input logic signed [89:0] product
    );
        logic signed [89:0] biased;
        begin
            biased = product + (90'sd1 <<< 32);
            rounded_capacitor_q44 = 63'($signed(biased) >>> 33);
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
                    summed_current = -$signed({ip1[31], ip1})
                                     - $signed({ig1[31], ig1});
                    tube_stamp = {{16{summed_current[33]}}, summed_current, 13'b0};
                end
                4: tube_stamp = {{18{ig2[31]}}, ig2, 13'b0};
                6: tube_stamp = {{18{ip2[31]}}, ip2, 13'b0};
                7: begin
                    summed_current = -$signed({ip2[31], ip2})
                                     - $signed({ig2[31], ig2});
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
        input logic signed [62:0] converted
    );
        begin
            correction_overflow = (converted > 63'sd16777215)
                                  || (converted < -63'sd16777216);
        end
    endfunction

    function automatic logic signed [24:0] saturate_correction(
        input logic signed [62:0] converted
    );
        begin
            if (converted > 63'sd16777215)
                saturate_correction = 25'sh0ffffff;
            else if (converted < -63'sd16777216)
                saturate_correction = 25'sh1000000;
            else
                saturate_correction = converted[24:0];
        end
    endfunction

    logic signed [80:0] matrix_product_by_row [0:8];
    logic signed [62:0] matrix_current_by_row [0:8];
    logic signed [41:0] cap_voltage_a_q30;
    logic signed [41:0] cap_voltage_b_q30;
    logic signed [42:0] cap_delta_q30;
    logic signed [89:0] cap_product;
    logic signed [62:0] cap_current_q44;
    logic signed [41:0] cap9_voltage_a_q30;
    logic signed [41:0] cap9_voltage_b_q30;
    logic signed [42:0] cap9_delta_q30;
    logic signed [89:0] cap9_product;
    logic signed [62:0] cap9_current_q44;
    logic signed [62:0] final_residual_by_row [0:8];
    logic signed [62:0] q30_by_row [0:8];
    logic signed [62:0] q34_by_row [0:8];
    logic signed [62:0] q40_by_row [0:8];
    logic signed [62:0] selected_by_row [0:8];
    logic q30_all_fit;
    logic q34_all_fit;
    logic q40_all_fit;
    logic [5:0] selected_fraction;
    logic [62:0] max_abs_combined;
    logic saturation_combined;
    logic [3:0] saturation_count_combined;

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
        cap_delta_q30 = $signed({cap_voltage_a_q30[41], cap_voltage_a_q30})
                         - $signed({cap_voltage_b_q30[41], cap_voltage_b_q30})
                         - $signed({{3{capacitor_latched[column][39]}},
                                    capacitor_latched[column]});
        cap_product = capacitor_g[column] * cap_delta_q30;
        cap_current_q44 = rounded_capacitor_q44(cap_product);

        cap9_voltage_a_q30 = node_voltage_q30(voltage_latched[6], 6);
        cap9_voltage_b_q30 = node_voltage_q30(voltage_latched[8], 8);
        cap9_delta_q30 = $signed({cap9_voltage_a_q30[41], cap9_voltage_a_q30})
                          - $signed({cap9_voltage_b_q30[41], cap9_voltage_b_q30})
                          - $signed({{3{capacitor_latched[9][39]}},
                                     capacitor_latched[9]});
        cap9_product = capacitor_g[9] * cap9_delta_q30;
        cap9_current_q44 = rounded_capacitor_q44(cap9_product);

        q30_all_fit = 1'b1;
        q34_all_fit = 1'b1;
        q40_all_fit = 1'b1;
        for (int row = 0; row < 9; row = row + 1) begin
            final_residual_by_row[row] = accumulator[row] + tube_stamp(
                row,
                current_latched[0], current_latched[1],
                current_latched[2], current_latched[3]
            ) + capacitor_stamp(9, row, cap9_current_q44);
            q30_by_row[row] = convert_residual(final_residual_by_row[row], 6'd30);
            q34_by_row[row] = convert_residual(final_residual_by_row[row], 6'd34);
            q40_by_row[row] = convert_residual(final_residual_by_row[row], 6'd40);
            q30_all_fit = q30_all_fit && !correction_overflow(q30_by_row[row]);
            q34_all_fit = q34_all_fit && !correction_overflow(q34_by_row[row]);
            q40_all_fit = q40_all_fit && !correction_overflow(q40_by_row[row]);
        end

        selected_fraction = 6'd30;
        if (requested_fraction_latched == 6'd40) begin
            if (q40_all_fit)
                selected_fraction = 6'd40;
            else if (q34_all_fit)
                selected_fraction = 6'd34;
        end else if (requested_fraction_latched == 6'd34 && q34_all_fit) begin
            selected_fraction = 6'd34;
        end

        max_abs_combined = '0;
        saturation_combined = 1'b0;
        saturation_count_combined = '0;
        for (int row = 0; row < 9; row = row + 1) begin
            case (selected_fraction)
                6'd40: selected_by_row[row] = q40_by_row[row];
                6'd34: selected_by_row[row] = q34_by_row[row];
                default: selected_by_row[row] = q30_by_row[row];
            endcase
            if (absolute_q44(final_residual_by_row[row]) > max_abs_combined)
                max_abs_combined = absolute_q44(final_residual_by_row[row]);
            saturation_combined = saturation_combined
                                  || correction_overflow(selected_by_row[row]);
            if (correction_overflow(selected_by_row[row]))
                saturation_count_combined = saturation_count_combined + 1'b1;
        end
    end

    integer lane;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            busy <= 1'b0;
            valid <= 1'b0;
            residual <= '0;
            residual_fractional_bits <= 6'd30;
            max_abs_residual_q44 <= '0;
            correction_scale_fallback <= 1'b0;
            saturation_any <= 1'b0;
            saturation_count <= '0;
            requested_fraction_latched <= 6'd30;
            column <= '0;
            finish_pending <= 1'b0;
            current_ready <= 1'b0;
            for (lane = 0; lane < 9; lane = lane + 1) begin
                voltage_latched[lane] <= '0;
                accumulator[lane] <= '0;
            end
            for (lane = 0; lane < 10; lane = lane + 1)
                capacitor_latched[lane] <= '0;
            for (lane = 0; lane < 4; lane = lane + 1)
                current_latched[lane] <= '0;
        end else begin
            valid <= 1'b0;
            if (!busy) begin
                if (start) begin
                    busy <= 1'b1;
                    column <= 4'd0;
                    finish_pending <= 1'b0;
                    current_ready <= tube_current_valid;
                    requested_fraction_latched <= requested_residual_fractional_bits;
                    correction_scale_fallback <= 1'b0;
                    saturation_any <= 1'b0;
                    saturation_count <= '0;
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
                end else if (current_ready) begin
                    for (lane = 0; lane < 9; lane = lane + 1)
                        residual[lane * 25 +: 25] <= saturate_correction(
                            selected_by_row[lane]
                        );
                    residual_fractional_bits <= selected_fraction;
                    max_abs_residual_q44 <= max_abs_combined;
                    correction_scale_fallback <=
                        selected_fraction != requested_fraction_latched;
                    saturation_any <= saturation_combined;
                    saturation_count <= saturation_count_combined;
                    busy <= 1'b0;
                    valid <= 1'b1;
                    finish_pending <= 1'b0;
                    current_ready <= 1'b0;
                end
            end
        end
    end
endmodule

`default_nettype wire
