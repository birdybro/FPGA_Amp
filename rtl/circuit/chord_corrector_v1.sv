`timescale 1ns/1ps
`default_nettype none

// Constant-Jacobian correction for the frozen nine-node V1 circuit.
//
// residual_q30 is signed amperes with 30 fractional bits (25-bit range).
// The inverse ROM is signed Q17.1 ohms. Node formats by index are:
//   Q8.24: 0=g1, 2=k1, 4=g2, 5=eq_low, 7=k2
//   Q12.20: 1=p1, 3=eq_pre, 6=p2, 8=out
//
// Nine row multipliers operate for nine columns. corrected_voltage and valid
// are produced ten clocks after an idle start request. Requests while busy are
// ignored by contract and should be counted by the caller.
module chord_corrector_v1 #(
    parameter COEFFICIENT_FILE = "model/generated/v1_chord_inverse_q17_1.mem"
) (
    input  logic                    clk,
    input  logic                    rst_n,
    input  logic                    start,
    input  logic [287:0]            voltage,
    input  logic [224:0]            residual_q30,
    output logic [287:0]            corrected_voltage,
    output logic                    saturation_any,
    output logic                    busy,
    output logic                    valid
);

    logic signed [17:0] coefficient [0:80];
    logic signed [24:0] residual_latched [0:8];
    logic signed [31:0] voltage_latched [0:8];
    logic signed [47:0] accumulator [0:8];
    logic [3:0] column;

    initial $readmemh(COEFFICIENT_FILE, coefficient);

    function automatic int node_fractional_bits(input int row);
        begin
            case (row)
                0, 2, 4, 5, 7: node_fractional_bits = 24;
                default:       node_fractional_bits = 20;
            endcase
        end
    endfunction

    function automatic logic signed [31:0] saturate_32(
        input logic signed [48:0] value
    );
        begin
            if (value > 49'sd2147483647)
                saturate_32 = 32'sh7fffffff;
            else if (value < -49'sd2147483648)
                saturate_32 = 32'sh80000000;
            else
                saturate_32 = value[31:0];
        end
    endfunction

    function automatic logic exceeds_32(input logic signed [48:0] value);
        begin
            exceeds_32 = (value > 49'sd2147483647) ||
                         (value < -49'sd2147483648);
        end
    endfunction

    function automatic logic signed [47:0] round_correction(
        input logic signed [47:0] value,
        input int row_index
    );
        int right_shift;
        logic signed [47:0] biased;
        begin
            right_shift = 31 - node_fractional_bits(row_index);
            biased = value + (48'sd1 <<< (right_shift - 1));
            round_correction = biased >>> right_shift;
        end
    endfunction

    function automatic logic signed [48:0] subtract_correction(
        input logic signed [31:0] node_voltage,
        input logic signed [47:0] correction
    );
        logic signed [48:0] voltage_extended;
        logic signed [48:0] correction_extended;
        begin
            voltage_extended = {{17{node_voltage[31]}}, node_voltage};
            correction_extended = {correction[47], correction};
            subtract_correction = voltage_extended - correction_extended;
        end
    endfunction

    integer row;
    logic apply_pending;
    logic signed [42:0] product_by_row [0:8];
    logic signed [47:0] correction_by_row [0:8];
    logic signed [48:0] updated_by_row [0:8];
    logic saturation_combined;

    always_comb begin
        saturation_combined = 1'b0;
        for (int comb_row = 0; comb_row < 9; comb_row = comb_row + 1) begin
            product_by_row[comb_row] =
                coefficient[comb_row * 9 + int'(column)] *
                residual_latched[column];
            correction_by_row[comb_row] = round_correction(
                accumulator[comb_row], comb_row
            );
            updated_by_row[comb_row] = subtract_correction(
                voltage_latched[comb_row], correction_by_row[comb_row]
            );
            saturation_combined = saturation_combined ||
                                  exceeds_32(updated_by_row[comb_row]);
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            busy           <= 1'b0;
            valid          <= 1'b0;
            saturation_any <= 1'b0;
            column         <= '0;
            apply_pending  <= 1'b0;
            for (row = 0; row < 9; row = row + 1) begin
                accumulator[row]       <= '0;
                corrected_voltage[row * 32 +: 32] <= '0;
                residual_latched[row]  <= '0;
                voltage_latched[row]   <= '0;
            end
        end else begin
            valid <= 1'b0;
            if (!busy) begin
                if (start) begin
                    busy           <= 1'b1;
                    column         <= 4'd0;
                    apply_pending  <= 1'b0;
                    saturation_any <= 1'b0;
                    for (row = 0; row < 9; row = row + 1) begin
                        accumulator[row]      <= '0;
                        residual_latched[row] <= $signed(
                            residual_q30[row * 25 +: 25]
                        );
                        voltage_latched[row] <= $signed(
                            voltage[row * 32 +: 32]
                        );
                    end
                end
            end else if (!apply_pending) begin
                for (row = 0; row < 9; row = row + 1) begin
                    accumulator[row] <= accumulator[row] +
                                        {{5{product_by_row[row][42]}},
                                         product_by_row[row]};
                end
                if (column == 4'd8) begin
                    apply_pending <= 1'b1;
                end else begin
                    column <= column + 1'b1;
                end
            end else begin
                for (row = 0; row < 9; row = row + 1) begin
                    corrected_voltage[row * 32 +: 32] <=
                        saturate_32(updated_by_row[row]);
                end
                saturation_any <= saturation_combined;
                busy          <= 1'b0;
                valid         <= 1'b1;
                apply_pending <= 1'b0;
            end
        end
    end

endmodule

`default_nettype wire
