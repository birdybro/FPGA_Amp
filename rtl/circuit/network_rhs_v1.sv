`timescale 1ns/1ps
`default_nettype none

// Build the per-sample right-hand side for the frozen V1 backward-Euler network.
// Input is Q8.24 volts; all ten capacitor histories are Q12.20 volts. Output is
// nine signed Q4.44 currents carried in 55-bit lanes for downstream headroom.
module network_rhs_v1 #(
    parameter FIXED_RHS_FILE = "model/generated/v1_fixed_rhs_q4_44.mem",
    parameter CAP_G_FILE = "model/generated/v1_cap_conductance_q0_47.mem"
) (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 start,
    input  logic signed [31:0]   input_q24,
    input  logic [319:0]         capacitor_state_q20,
    output logic [494:0]         rhs_q44,
    output logic                 busy,
    output logic                 valid
);

    localparam logic signed [47:0] INPUT_G_Q47 = 48'sd636821214278;

    logic signed [47:0] fixed_rhs [0:8];
    logic signed [47:0] capacitor_g [0:9];
    logic signed [54:0] accumulator [0:8];
    logic signed [31:0] input_latched;
    logic signed [31:0] capacitor_latched [0:9];
    logic [3:0] capacitor_index;

    typedef enum logic [1:0] {IDLE, APPLY_INPUT, APPLY_CAPACITOR, FINISH} state_t;
    state_t state;

    initial begin
        $readmemh(FIXED_RHS_FILE, fixed_rhs);
        $readmemh(CAP_G_FILE, capacitor_g);
    end

    function automatic int cap_node_a(input logic [3:0] index);
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

    function automatic int cap_node_b(input logic [3:0] index);
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

    logic signed [79:0] input_product;
    logic signed [79:0] capacitor_product;
    logic signed [54:0] input_current_q44;
    logic signed [54:0] capacitor_current_q44;
    integer current_node_a;
    integer current_node_b;

    always_comb begin
        input_product = INPUT_G_Q47 * input_latched;
        capacitor_product = capacitor_g[capacitor_index] *
                            capacitor_latched[capacitor_index];
        input_current_q44 = rounded_q44(input_product, 27);
        capacitor_current_q44 = rounded_q44(capacitor_product, 23);
        current_node_a = cap_node_a(capacitor_index);
        current_node_b = cap_node_b(capacitor_index);
    end

    integer lane;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            busy <= 1'b0;
            valid <= 1'b0;
            capacitor_index <= '0;
            rhs_q44 <= '0;
            input_latched <= '0;
            for (lane = 0; lane < 10; lane = lane + 1)
                capacitor_latched[lane] <= '0;
            for (lane = 0; lane < 9; lane = lane + 1)
                accumulator[lane] <= '0;
        end else begin
            valid <= 1'b0;
            case (state)
                IDLE: begin
                    busy <= 1'b0;
                    if (start) begin
                        busy <= 1'b1;
                        input_latched <= input_q24;
                        capacitor_index <= 4'd0;
                        for (lane = 0; lane < 10; lane = lane + 1)
                            capacitor_latched[lane] <= $signed(
                                capacitor_state_q20[lane * 32 +: 32]
                            );
                        for (lane = 0; lane < 9; lane = lane + 1)
                            accumulator[lane] <= {{7{fixed_rhs[lane][47]}},
                                                  fixed_rhs[lane]};
                        state <= APPLY_INPUT;
                    end
                end
                APPLY_INPUT: begin
                    accumulator[0] <= accumulator[0] + input_current_q44;
                    state <= APPLY_CAPACITOR;
                end
                APPLY_CAPACITOR: begin
                    if (current_node_a >= 0)
                        accumulator[current_node_a] <= accumulator[current_node_a] +
                                               capacitor_current_q44;
                    if (current_node_b >= 0)
                        accumulator[current_node_b] <= accumulator[current_node_b] -
                                               capacitor_current_q44;
                    if (capacitor_index == 4'd9)
                        state <= FINISH;
                    else
                        capacitor_index <= capacitor_index + 1'b1;
                end
                FINISH: begin
                    for (lane = 0; lane < 9; lane = lane + 1)
                        rhs_q44[lane * 55 +: 55] <= accumulator[lane];
                    valid <= 1'b1;
                    busy <= 1'b0;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule

`default_nettype wire
