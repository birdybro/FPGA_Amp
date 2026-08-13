`timescale 1ns/1ps
`default_nettype none

// Evaluate G*v - rhs plus the two triode KCL stamps for frozen V1.
// Node voltages retain their heterogeneous 32-bit formats. Matrix coefficients
// are signed Q0.47 siemens, RHS and diagnostic residual are Q4.44 amperes, and
// the correction output is saturated signed 25-bit with 30 fractional bits.
module network_kcl_v1 #(
    parameter MATRIX_FILE = "model/generated/v1_dynamic_matrix_q0_47.mem"
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  start,
    input  logic [287:0]          voltage,
    input  logic [494:0]          rhs_q44,
    input  logic                  tube_current_valid,
    input  logic [127:0]          tube_current_q31,
    output logic [224:0]          residual_q30,
    output logic [54:0]           max_abs_residual_q44,
    output logic                  saturation_any,
    output logic [3:0]            saturation_count,
    output logic                  busy,
    output logic                  valid
);

    logic signed [47:0] matrix [0:80];
    logic signed [31:0] voltage_latched [0:8];
    logic signed [54:0] accumulator [0:8];
    logic signed [31:0] current_latched [0:3]; // ip1, ig1, ip2, ig2
    logic [3:0] column;
    logic finish_pending;
    logic current_ready;

    initial $readmemh(MATRIX_FILE, matrix);

    function automatic int voltage_fractional_bits(input logic [3:0] index);
        begin
            case (index)
                0, 2, 4, 5, 7: voltage_fractional_bits = 24;
                default:       voltage_fractional_bits = 20;
            endcase
        end
    endfunction

    function automatic logic signed [54:0] rounded_q44(
        input logic signed [79:0] product,
        input int shift
    );
        logic signed [79:0] biased;
        begin
            biased = product + (80'sd1 <<< (shift - 1));
            rounded_q44 = 55'($signed(biased) >>> shift);
        end
    endfunction

    function automatic logic signed [54:0] tube_stamp(
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
                0: tube_stamp = {{10{ig1[31]}}, ig1, 13'b0};
                1: tube_stamp = {{10{ip1[31]}}, ip1, 13'b0};
                2: begin
                    summed_current = -$signed({ip1[31], ip1}) -
                                     $signed({ig1[31], ig1});
                    tube_stamp = {{8{summed_current[33]}}, summed_current, 13'b0};
                end
                4: tube_stamp = {{10{ig2[31]}}, ig2, 13'b0};
                6: tube_stamp = {{10{ip2[31]}}, ip2, 13'b0};
                7: begin
                    summed_current = -$signed({ip2[31], ip2}) -
                                     $signed({ig2[31], ig2});
                    tube_stamp = {{8{summed_current[33]}}, summed_current, 13'b0};
                end
                default: tube_stamp = '0;
            endcase
        end
    endfunction

    function automatic logic [54:0] absolute_q44(
        input logic signed [54:0] value
    );
        begin
            if (value[54])
                absolute_q44 = $unsigned(-value);
            else
                absolute_q44 = $unsigned(value);
        end
    endfunction

    function automatic logic signed [24:0] saturate_q30(
        input logic signed [54:0] value_q44
    );
        logic signed [54:0] converted;
        begin
            converted = (value_q44 + 55'sd8192) >>> 14;
            if (converted > 55'sd16777215)
                saturate_q30 = 25'sh0ffffff;
            else if (converted < -55'sd16777216)
                saturate_q30 = 25'sh1000000;
            else
                saturate_q30 = converted[24:0];
        end
    endfunction

    function automatic logic q30_overflow(input logic signed [54:0] value_q44);
        logic signed [54:0] converted;
        begin
            converted = (value_q44 + 55'sd8192) >>> 14;
            q30_overflow = (converted > 55'sd16777215) ||
                           (converted < -55'sd16777216);
        end
    endfunction

    logic signed [79:0] product_by_row [0:8];
    logic signed [54:0] rounded_by_row [0:8];
    logic signed [54:0] final_residual_by_row [0:8];
    logic [54:0] max_abs_combined;
    logic saturation_combined;
    logic [3:0] saturation_count_combined;

    always_comb begin
        max_abs_combined = '0;
        saturation_combined = 1'b0;
        saturation_count_combined = '0;
        for (int row = 0; row < 9; row = row + 1) begin
            product_by_row[row] = matrix[row * 9 + int'(column)] *
                                  voltage_latched[column];
            rounded_by_row[row] = rounded_q44(
                product_by_row[row], voltage_fractional_bits(column) + 3
            );
            final_residual_by_row[row] = accumulator[row] + tube_stamp(
                row,
                current_latched[0],
                current_latched[1],
                current_latched[2],
                current_latched[3]
            );
            if (absolute_q44(final_residual_by_row[row]) > max_abs_combined)
                max_abs_combined = absolute_q44(final_residual_by_row[row]);
            saturation_combined = saturation_combined ||
                                  q30_overflow(final_residual_by_row[row]);
            if (q30_overflow(final_residual_by_row[row]))
                saturation_count_combined = saturation_count_combined + 1'b1;
        end
    end

    integer lane;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            busy <= 1'b0;
            valid <= 1'b0;
            saturation_any <= 1'b0;
            saturation_count <= '0;
            column <= '0;
            finish_pending <= 1'b0;
            current_ready <= 1'b0;
            residual_q30 <= '0;
            max_abs_residual_q44 <= '0;
            for (lane = 0; lane < 9; lane = lane + 1) begin
                voltage_latched[lane] <= '0;
                accumulator[lane] <= '0;
            end
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
                    saturation_any <= 1'b0;
                    saturation_count <= '0;
                    for (lane = 0; lane < 9; lane = lane + 1) begin
                        voltage_latched[lane] <= $signed(
                            voltage[lane * 32 +: 32]
                        );
                        accumulator[lane] <= -$signed(
                            rhs_q44[lane * 55 +: 55]
                        );
                    end
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
                        accumulator[lane] <= accumulator[lane] + rounded_by_row[lane];
                    if (column == 4'd8)
                        finish_pending <= 1'b1;
                    else
                        column <= column + 1'b1;
                end else if (current_ready) begin
                    for (lane = 0; lane < 9; lane = lane + 1)
                        residual_q30[lane * 25 +: 25] <=
                            saturate_q30(final_residual_by_row[lane]);
                    max_abs_residual_q44 <= max_abs_combined;
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
