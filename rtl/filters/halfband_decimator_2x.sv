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
    // The physical storage is intentionally not reset so Yosys can infer
    // distributed RAM. valid_samples supplies the architectural zero fill
    // after reset and prevents retained memory bits from becoming visible.
    (* ram_style = "distributed" *)
    logic signed [31:0] history [0:TAPS-1];
    logic input_phase;
    logic center_pending;
    logic [INDEX_WIDTH-1:0] tap_index;
    logic [INDEX_WIDTH-1:0] write_index;
    logic [INDEX_WIDTH-1:0] newest_index;
    logic [INDEX_WIDTH-1:0] valid_samples;
    logic signed [62:0] accumulator;

    initial begin
        if ((TAPS % 4) != 3)
            $error("halfband_decimator_2x requires TAPS=4m+3");
        $readmemh(COEFFICIENT_FILE, coefficient);
    end

    logic signed [23:0] selected_coefficient;
    logic signed [31:0] selected_sample;
    logic [INDEX_WIDTH-1:0] selected_age;
    logic [INDEX_WIDTH-1:0] selected_history_index;
    logic signed [55:0] product;
    logic signed [62:0] sum_with_product;
    always_comb begin
        if (center_pending) begin
            selected_coefficient = coefficient[CENTER];
            selected_age = INDEX_WIDTH'(CENTER);
        end else begin
            selected_coefficient = coefficient[tap_index];
            selected_age = tap_index;
        end
        if (newest_index >= selected_age)
            selected_history_index = newest_index - selected_age;
        else
            selected_history_index =
                INDEX_WIDTH'(TAPS) - selected_age + newest_index;
        if (selected_age < valid_samples)
            selected_sample = history[selected_history_index];
        else
            selected_sample = '0;
        product = selected_coefficient * selected_sample;
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

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sample_output_q24 <= '0;
            output_valid <= 1'b0;
            busy <= 1'b0;
            saturation_count <= '0;
            overrun_count <= '0;
            input_phase <= 1'b0;
            center_pending <= 1'b0;
            tap_index <= '0;
            write_index <= '0;
            newest_index <= '0;
            valid_samples <= '0;
            accumulator <= '0;
        end else begin
            output_valid <= 1'b0;
            if (ce_input) begin
                if (busy) begin
                    overrun_count <= overrun_count + 1'b1;
                end else begin
                    history[write_index] <= sample_input_q24;
                    newest_index <= write_index;
                    if (write_index == INDEX_WIDTH'(TAPS - 1))
                        write_index <= '0;
                    else
                        write_index <= write_index + 1'b1;
                    if (valid_samples != INDEX_WIDTH'(TAPS))
                        valid_samples <= valid_samples + 1'b1;
                    if (!input_phase) begin
                        accumulator <= '0;
                        center_pending <= 1'b1;
                        tap_index <= '0;
                        busy <= 1'b1;
                    end
                    input_phase <= !input_phase;
                end
            end

            if (busy) begin
                if (center_pending) begin
                    accumulator <= sum_with_product;
                    center_pending <= 1'b0;
                end else if (tap_index == INDEX_WIDTH'(TAPS - 1)) begin
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
