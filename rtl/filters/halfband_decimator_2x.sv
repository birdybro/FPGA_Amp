`timescale 1ns/1ps
`default_nettype none

// Serial-multiply 2x half-band decimator for Q8.24 audio samples. An output is
// computed on each even input phase from the even-index taps plus the 0.5
// center tap. The next high-rate sample can arrive after the MAC completes.
module halfband_decimator_2x #(
    parameter int TAPS = 79,
    parameter COEFFICIENT_FILE = "model/generated/halfband_stage1_q1_23.mem"
) (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 ce_input,
    input  logic signed [31:0]   sample_input_q24,
    output logic signed [31:0]   sample_output_q24,
    output logic                 output_valid,
    output logic                 busy,
    output logic [31:0]          saturation_count,
    output logic [31:0]          overrun_count
);

    localparam int CENTER = (TAPS - 1) / 2;
    localparam int INDEX_WIDTH = $clog2(TAPS + 1);

    logic signed [23:0] coefficient [0:TAPS-1];
    logic signed [31:0] history [0:TAPS-1];
    logic input_phase;
    logic [INDEX_WIDTH-1:0] tap_index;
    logic signed [62:0] accumulator;

    initial begin
        if ((TAPS % 4) != 3)
            $error("halfband_decimator_2x requires TAPS=4m+3");
        $readmemh(COEFFICIENT_FILE, coefficient);
    end

    logic signed [55:0] product;
    logic signed [62:0] sum_with_product;
    always_comb begin
        product = coefficient[tap_index] * history[tap_index];
        sum_with_product = accumulator + {{7{product[55]}}, product};
    end

    function automatic logic signed [31:0] rounded_saturated(
        input logic signed [62:0] value
    );
        logic signed [62:0] rounded;
        begin
            rounded = (value + 63'sd4194304) >>> 23;
            if (rounded > 63'sd2147483647)
                rounded_saturated = 32'sh7fffffff;
            else if (rounded < -63'sd2147483648)
                rounded_saturated = 32'sh80000000;
            else
                rounded_saturated = rounded[31:0];
        end
    endfunction

    function automatic logic output_overflows(input logic signed [62:0] value);
        logic signed [62:0] rounded;
        begin
            rounded = (value + 63'sd4194304) >>> 23;
            output_overflows = (rounded > 63'sd2147483647) ||
                               (rounded < -63'sd2147483648);
        end
    endfunction

    integer lane;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sample_output_q24 <= '0;
            output_valid <= 1'b0;
            busy <= 1'b0;
            saturation_count <= '0;
            overrun_count <= '0;
            input_phase <= 1'b0;
            tap_index <= '0;
            accumulator <= '0;
            for (lane = 0; lane < TAPS; lane = lane + 1)
                history[lane] <= '0;
        end else begin
            output_valid <= 1'b0;
            if (ce_input) begin
                if (busy) begin
                    overrun_count <= overrun_count + 1'b1;
                end else begin
                    for (lane = TAPS - 1; lane > 0; lane = lane - 1)
                        history[lane] <= history[lane - 1];
                    history[0] <= sample_input_q24;
                    if (!input_phase) begin
                        accumulator <= $signed(coefficient[CENTER]) *
                                       $signed(history[CENTER - 1]);
                        tap_index <= '0;
                        busy <= 1'b1;
                    end
                    input_phase <= !input_phase;
                end
            end

            if (busy) begin
                if (tap_index == INDEX_WIDTH'(TAPS - 1)) begin
                    sample_output_q24 <= rounded_saturated(sum_with_product);
                    if (output_overflows(sum_with_product))
                        saturation_count <= saturation_count + 1'b1;
                    output_valid <= 1'b1;
                    busy <= 1'b0;
                end else begin
                    accumulator <= sum_with_product;
                    tap_index <= tap_index + 2;
                end
            end
        end
    end
endmodule

`default_nettype wire
