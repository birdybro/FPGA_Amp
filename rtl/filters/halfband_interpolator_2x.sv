`timescale 1ns/1ps
`default_nettype none

// Serial-multiply 2x half-band interpolator for Q8.24 audio samples.
// Coefficients are signed Q1.23. TAPS must be 4m+3: even-indexed taps form
// one output phase and the 0.5 center tap makes the other phase a pure delay.
// Output is delayed by one input pair so the serial MAC completes before use.
module halfband_interpolator_2x #(
    parameter int TAPS = 79,
    parameter COEFFICIENT_FILE = "model/generated/halfband_stage1_q1_23.mem"
) (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 ce_input,
    input  logic                 ce_output,
    input  logic signed [31:0]   sample_input_q24,
    output logic signed [31:0]   sample_output_q24,
    output logic                 output_valid,
    output logic                 busy,
    output logic [31:0]          saturation_count,
    output logic [31:0]          overrun_count
);

    localparam int INPUT_HISTORY = (TAPS + 1) / 2;
    localparam int CENTER_DELAY = (TAPS - 3) / 4;
    localparam int INDEX_WIDTH = $clog2(TAPS + 1);
    localparam int HISTORY_ADDRESS_WIDTH = $clog2(INPUT_HISTORY);
    localparam int VALID_COUNT_WIDTH = $clog2(INPUT_HISTORY + 1);
    localparam int ODD_PREWRITE_AGE =
        (CENTER_DELAY == 0) ? 0 : CENTER_DELAY - 1;

    logic signed [23:0] coefficient [0:TAPS-1];
    // Leave the physical bits unreset for distributed-RAM inference. The
    // valid-sample count below preserves the architectural zero history.
    (* ram_style = "distributed" *)
    logic signed [31:0] history [0:INPUT_HISTORY-1];
    logic signed [31:0] even_ready;
    logic signed [31:0] odd_ready;
    logic signed [31:0] odd_output_latched;
    logic output_phase;
    logic [INDEX_WIDTH-1:0] tap_index;
    logic [HISTORY_ADDRESS_WIDTH-1:0] write_index;
    logic [HISTORY_ADDRESS_WIDTH-1:0] newest_index;
    logic [VALID_COUNT_WIDTH-1:0] valid_samples;
    logic signed [62:0] accumulator;

    initial begin
        if ((TAPS % 4) != 3)
            $error("halfband_interpolator_2x requires TAPS=4m+3");
        $readmemh(COEFFICIENT_FILE, coefficient);
    end

    logic [HISTORY_ADDRESS_WIDTH-1:0] selected_age;
    logic [HISTORY_ADDRESS_WIDTH-1:0] selected_history_index;
    logic signed [31:0] selected_sample;
    logic signed [55:0] product;
    logic signed [62:0] sum_with_product;
    always_comb begin
        // The odd-phase delayed sample is captured before the circular write;
        // the MAC reads the same single asynchronous memory port afterward.
        if (ce_input && !busy)
            selected_age = HISTORY_ADDRESS_WIDTH'(ODD_PREWRITE_AGE);
        else
            selected_age = tap_index[INDEX_WIDTH-1:1];
        if (newest_index >= selected_age)
            selected_history_index = newest_index - selected_age;
        else
            selected_history_index =
                HISTORY_ADDRESS_WIDTH'(INPUT_HISTORY) - selected_age +
                newest_index;
        if (VALID_COUNT_WIDTH'(selected_age) < valid_samples)
            selected_sample = history[selected_history_index];
        else
            selected_sample = '0;
        product = coefficient[tap_index] * selected_sample;
        sum_with_product = accumulator + {{7{product[55]}}, product};
    end

    function automatic logic signed [31:0] rounded_saturated(
        input logic signed [62:0] off_center_sum
    );
        logic signed [63:0] gained;
        logic signed [63:0] rounded;
        begin
            gained = $signed({off_center_sum[62], off_center_sum}) <<< 1;
            rounded = (gained + 64'sd4194304) >>> 23;
            if (rounded > 64'sd2147483647)
                rounded_saturated = 32'sh7fffffff;
            else if (rounded < -64'sd2147483648)
                rounded_saturated = 32'sh80000000;
            else
                rounded_saturated = rounded[31:0];
        end
    endfunction

    function automatic logic output_overflows(
        input logic signed [62:0] off_center_sum
    );
        logic signed [63:0] gained;
        logic signed [63:0] rounded;
        begin
            gained = $signed({off_center_sum[62], off_center_sum}) <<< 1;
            rounded = (gained + 64'sd4194304) >>> 23;
            output_overflows = (rounded > 64'sd2147483647) ||
                               (rounded < -64'sd2147483648);
        end
    endfunction

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sample_output_q24 <= '0;
            output_valid <= 1'b0;
            busy <= 1'b0;
            saturation_count <= '0;
            overrun_count <= '0;
            even_ready <= '0;
            odd_ready <= '0;
            odd_output_latched <= '0;
            output_phase <= 1'b0;
            tap_index <= '0;
            write_index <= '0;
            newest_index <= '0;
            valid_samples <= '0;
            accumulator <= '0;
        end else begin
            output_valid <= 1'b0;
            if (ce_output) begin
                output_valid <= 1'b1;
                if (!output_phase) begin
                    sample_output_q24 <= even_ready;
                    odd_output_latched <= odd_ready;
                end else begin
                    sample_output_q24 <= odd_output_latched;
                end
                output_phase <= !output_phase;
            end

            if (ce_input) begin
                if (busy) begin
                    overrun_count <= overrun_count + 1'b1;
                end else begin
                    history[write_index] <= sample_input_q24;
                    newest_index <= write_index;
                    if (write_index == HISTORY_ADDRESS_WIDTH'(INPUT_HISTORY - 1))
                        write_index <= '0;
                    else
                        write_index <= write_index + 1'b1;
                    if (valid_samples != VALID_COUNT_WIDTH'(INPUT_HISTORY))
                        valid_samples <= valid_samples + 1'b1;
                    if (CENTER_DELAY == 0)
                        odd_ready <= sample_input_q24;
                    else
                        odd_ready <= selected_sample;
                    accumulator <= '0;
                    tap_index <= '0;
                    busy <= 1'b1;
                end
            end

            if (busy) begin
                if (tap_index == INDEX_WIDTH'(TAPS - 1)) begin
                    even_ready <= rounded_saturated(sum_with_product);
                    if (output_overflows(sum_with_product))
                        saturation_count <= saturation_count + 1'b1;
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
