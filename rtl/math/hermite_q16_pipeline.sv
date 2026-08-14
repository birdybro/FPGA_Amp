`timescale 1ns/1ps
`default_nettype none

// Bit-exact cubic Hermite interpolation for a Q0.16 interval coordinate.
//
// y0/y1 and m0/m1 share an application-defined signed 32-bit format.  The
// slopes are already multiplied by the table interval, matching the packed
// factorized-tube ROM format.  Arithmetic wraps to 32 bits at the same points
// as the established triode_12ax7_factorized Horner implementation.  Each
// product is a full-width signed 32 x 17 multiply followed by add-half and an
// arithmetic right shift.  Negative ties therefore round toward +infinity;
// this intentionally preserves the existing fixed-point numerical contract.
//
// The block is iterative rather than fully throughput-pipelined: one request
// is accepted when start && !busy, and result/valid follows three clocks later.
// A start presented while busy is ignored.  This exposes a single multiplier
// to synthesis instead of a chain of three dependent multipliers in one cycle.
module hermite_q16_pipeline (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               start,
    input  logic signed [31:0] y0,
    input  logic signed [31:0] y1,
    input  logic signed [31:0] m0,
    input  logic signed [31:0] m1,
    input  logic        [15:0] fraction,
    output logic signed [31:0] result,
    output logic               busy,
    output logic               valid
);

    typedef enum logic [1:0] {
        IDLE,
        MULTIPLY_COEFFICIENT_3,
        MULTIPLY_STAGE_1,
        MULTIPLY_STAGE_2
    } state_t;

    state_t state;
    logic signed [31:0] coefficient_2;
    logic signed [31:0] coefficient_3;
    logic signed [31:0] m0_latched;
    logic signed [31:0] y0_latched;
    logic signed [31:0] stage;
    logic signed [16:0] fraction_latched;
    logic signed [31:0] multiplicand;
    logic signed [48:0] product;

    function automatic logic signed [31:0] coefficient_2_value(
        input logic signed [31:0] value_y0,
        input logic signed [31:0] value_y1,
        input logic signed [31:0] value_m0,
        input logic signed [31:0] value_m1
    );
        logic signed [31:0] delta;
        begin
            delta = value_y1 - value_y0;
            coefficient_2_value = delta + delta + delta
                                - (value_m0 <<< 1) - value_m1;
        end
    endfunction

    function automatic logic signed [31:0] coefficient_3_value(
        input logic signed [31:0] value_y0,
        input logic signed [31:0] value_y1,
        input logic signed [31:0] value_m0,
        input logic signed [31:0] value_m1
    );
        logic signed [31:0] delta;
        begin
            delta = value_y1 - value_y0;
            coefficient_3_value = -(delta <<< 1) + value_m0 + value_m1;
        end
    endfunction

    function automatic logic signed [31:0] rounded_product_q16(
        input logic signed [48:0] value
    );
        logic signed [48:0] rounded;
        begin
            rounded = value + 49'sd32768;
            rounded_product_q16 = 32'($signed(rounded) >>> 16);
        end
    endfunction

    always_comb begin
        unique case (state)
            MULTIPLY_COEFFICIENT_3: multiplicand = coefficient_3;
            MULTIPLY_STAGE_1,
            MULTIPLY_STAGE_2:       multiplicand = stage;
            default:                multiplicand = '0;
        endcase
        product = $signed(multiplicand) * $signed(fraction_latched);
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            coefficient_2 <= '0;
            coefficient_3 <= '0;
            m0_latched <= '0;
            y0_latched <= '0;
            stage <= '0;
            fraction_latched <= '0;
            result <= '0;
            busy <= 1'b0;
            valid <= 1'b0;
        end else begin
            valid <= 1'b0;
            unique case (state)
                IDLE: begin
                    busy <= 1'b0;
                    if (start) begin
                        coefficient_2 <= coefficient_2_value(y0, y1, m0, m1);
                        coefficient_3 <= coefficient_3_value(y0, y1, m0, m1);
                        m0_latched <= m0;
                        y0_latched <= y0;
                        fraction_latched <= $signed({1'b0, fraction});
                        busy <= 1'b1;
                        state <= MULTIPLY_COEFFICIENT_3;
                    end
                end

                MULTIPLY_COEFFICIENT_3: begin
                    stage <= rounded_product_q16(product) + coefficient_2;
                    state <= MULTIPLY_STAGE_1;
                end

                MULTIPLY_STAGE_1: begin
                    stage <= rounded_product_q16(product) + m0_latched;
                    state <= MULTIPLY_STAGE_2;
                end

                MULTIPLY_STAGE_2: begin
                    result <= rounded_product_q16(product) + y0_latched;
                    busy <= 1'b0;
                    valid <= 1'b1;
                    state <= IDLE;
                end

                default: begin
                    state <= IDLE;
                    busy <= 1'b0;
                end
            endcase
        end
    end

endmodule

`default_nettype wire
