`timescale 1ns/1ps
`default_nettype none

// Forty-bit state candidate for the frozen V1 constant-Jacobian correction.
// Residual values are signed 25-bit operands whose binary point is supplied
// per request (the measured schedule requests Q30, Q34, then Q40).
module chord_corrector_v1_wide #(
    parameter COEFFICIENT_FILE = "model/generated/v1_chord_inverse_q17_1.mem",
    parameter integer COEFFICIENT_SETS = 1,
    // Optional timing schedule. Register scaled corrections and updated node
    // values before saturation/commit, adding two clocks without changing any
    // arithmetic result.
    parameter bit PIPELINED_APPLY = 1'b0
) (
    input  logic                    clk,
    input  logic                    rst_n,
    input  logic                    start,
    input  logic [359:0]            voltage,
    input  logic [224:0]            residual,
    input  logic [5:0]              residual_fractional_bits,
    input  logic [2:0]              coefficient_set,
    output logic [359:0]            corrected_voltage,
    // During the final pipelined apply cycle this exposes the already
    // registered, saturated node update one clock before `valid`. It permits
    // independent terminal-state work to overlap without bypassing a timing
    // boundary or changing the corrected-voltage result.
    output logic [359:0]            preview_voltage,
    output logic                    preview_valid,
    output logic                    saturation_any,
    output logic [3:0]              saturation_count,
    output logic                    busy,
    output logic                    valid
);

    logic signed [17:0] coefficient [0:COEFFICIENT_SETS * 81 - 1];
    logic signed [24:0] residual_latched [0:8];
    logic signed [39:0] voltage_latched [0:8];
    logic signed [47:0] accumulator [0:8];
    logic [5:0] residual_fraction_latched;
    logic [2:0] coefficient_set_latched;
    logic [3:0] column;
    logic correction_staged;
    logic update_staged;

    initial $readmemh(COEFFICIENT_FILE, coefficient);

    function automatic int node_fractional_bits(input int row);
        begin
            case (row)
                1, 3, 6: node_fractional_bits = 28;
                default: node_fractional_bits = 32;
            endcase
        end
    endfunction

    function automatic int coefficient_set_base(input logic [2:0] set_index);
        begin
            case (set_index)
                3'd1: coefficient_set_base = 81;
                3'd2: coefficient_set_base = 162;
                3'd3: coefficient_set_base = 243;
                3'd4: coefficient_set_base = 324;
                default: coefficient_set_base = 0;
            endcase
        end
    endfunction

    function automatic logic signed [48:0] scale_correction(
        input logic signed [47:0] value,
        input int row_index,
        input logic [5:0] residual_fraction
    );
        logic signed [48:0] extended;
        logic signed [48:0] biased;
        begin
            extended = {value[47], value};
            biased = extended;
            if (node_fractional_bits(row_index) == 28) begin
                case (residual_fraction)
                    6'd30: begin
                        biased = extended + 49'sd4;
                        scale_correction = biased >>> 3;
                    end
                    6'd34: begin
                        biased = extended + 49'sd64;
                        scale_correction = biased >>> 7;
                    end
                    6'd40: begin
                        biased = extended + 49'sd4096;
                        scale_correction = biased >>> 13;
                    end
                    default: begin // Fail conservatively as Q30.
                        biased = extended + 49'sd4;
                        scale_correction = biased >>> 3;
                    end
                endcase
            end else begin
                case (residual_fraction)
                    6'd30: scale_correction = extended <<< 1;
                    6'd34: begin
                        biased = extended + 49'sd4;
                        scale_correction = biased >>> 3;
                    end
                    6'd40: begin
                        biased = extended + 49'sd256;
                        scale_correction = biased >>> 9;
                    end
                    default: scale_correction = extended <<< 1;
                endcase
            end
        end
    endfunction

    function automatic logic signed [39:0] saturate_40(
        input logic signed [49:0] value
    );
        begin
            if (value > 50'sd549755813887)
                saturate_40 = 40'sh7fffffffff;
            else if (value < -50'sd549755813888)
                saturate_40 = 40'sh8000000000;
            else
                saturate_40 = value[39:0];
        end
    endfunction

    function automatic logic exceeds_40(input logic signed [49:0] value);
        begin
            exceeds_40 = (value > 50'sd549755813887) ||
                         (value < -50'sd549755813888);
        end
    endfunction

    logic apply_pending;
    logic signed [42:0] product_by_row [0:8];
    logic signed [48:0] correction_by_row [0:8];
    logic signed [48:0] correction_staged_by_row [0:8];
    logic signed [49:0] updated_by_row [0:8];
    logic signed [49:0] updated_staged_by_row [0:8];
    logic [8:0] overflow_by_row;
    logic saturation_combined;
    logic [3:0] saturation_count_combined;

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
        preview_valid = PIPELINED_APPLY && busy && apply_pending
                        && correction_staged && update_staged;
        for (int row = 0; row < 9; row = row + 1) begin
            product_by_row[row] = coefficient[
                                      coefficient_set_base(
                                          coefficient_set_latched
                                      )
                                      + row * 9 + int'(column)
                                  ]
                                  * residual_latched[column];
            correction_by_row[row] = scale_correction(
                accumulator[row], row, residual_fraction_latched
            );
            updated_by_row[row] =
                $signed({{10{voltage_latched[row][39]}}, voltage_latched[row]})
                - $signed({
                    (PIPELINED_APPLY
                        ? correction_staged_by_row[row][48]
                        : correction_by_row[row][48]),
                    (PIPELINED_APPLY
                        ? correction_staged_by_row[row]
                        : correction_by_row[row])
                });
            overflow_by_row[row] = exceeds_40(updated_by_row[row]);
            preview_voltage[row * 40 +: 40] = saturate_40(
                updated_staged_by_row[row]
            );
        end
        saturation_combined = |overflow_by_row;
        saturation_count_combined = popcount9(overflow_by_row);
    end

    integer row;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            busy <= 1'b0;
            valid <= 1'b0;
            saturation_any <= 1'b0;
            saturation_count <= '0;
            residual_fraction_latched <= '0;
            coefficient_set_latched <= '0;
            column <= '0;
            apply_pending <= 1'b0;
            correction_staged <= 1'b0;
            update_staged <= 1'b0;
            for (row = 0; row < 9; row = row + 1) begin
                accumulator[row] <= '0;
                corrected_voltage[row * 40 +: 40] <= '0;
                residual_latched[row] <= '0;
                voltage_latched[row] <= '0;
                correction_staged_by_row[row] <= '0;
                updated_staged_by_row[row] <= '0;
            end
        end else begin
            valid <= 1'b0;
            if (!busy) begin
                if (start) begin
                    busy <= 1'b1;
                    column <= 4'd0;
                    apply_pending <= 1'b0;
                    correction_staged <= 1'b0;
                    update_staged <= 1'b0;
                    saturation_any <= 1'b0;
                    saturation_count <= '0;
                    residual_fraction_latched <= residual_fractional_bits;
                    coefficient_set_latched <= coefficient_set;
                    for (row = 0; row < 9; row = row + 1) begin
                        accumulator[row] <= '0;
                        residual_latched[row] <= $signed(
                            residual[row * 25 +: 25]
                        );
                        voltage_latched[row] <= $signed(
                            voltage[row * 40 +: 40]
                        );
                    end
                end
            end else if (!apply_pending) begin
                for (row = 0; row < 9; row = row + 1)
                    accumulator[row] <= accumulator[row]
                        + {{5{product_by_row[row][42]}}, product_by_row[row]};
                if (column == 4'd8)
                    apply_pending <= 1'b1;
                else
                    column <= column + 1'b1;
            end else if (PIPELINED_APPLY && !correction_staged) begin
                for (row = 0; row < 9; row = row + 1)
                    correction_staged_by_row[row] <= correction_by_row[row];
                correction_staged <= 1'b1;
            end else if (PIPELINED_APPLY && !update_staged) begin
                for (row = 0; row < 9; row = row + 1)
                    updated_staged_by_row[row] <= updated_by_row[row];
                saturation_any <= saturation_combined;
                saturation_count <= saturation_count_combined;
                update_staged <= 1'b1;
            end else begin
                for (row = 0; row < 9; row = row + 1)
                    corrected_voltage[row * 40 +: 40] <=
                        saturate_40(
                            PIPELINED_APPLY
                                ? updated_staged_by_row[row]
                                : updated_by_row[row]
                        );
                if (!PIPELINED_APPLY) begin
                    saturation_any <= saturation_combined;
                    saturation_count <= saturation_count_combined;
                end
                busy <= 1'b0;
                valid <= 1'b1;
                apply_pending <= 1'b0;
                correction_staged <= 1'b0;
                update_staged <= 1'b0;
            end
        end
    end

endmodule

`default_nettype wire
