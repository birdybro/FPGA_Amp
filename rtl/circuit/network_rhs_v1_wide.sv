`timescale 1ns/1ps
`default_nettype none

// Wide-state branch stamping moves capacitor history into the KCL engine, so
// the per-sample RHS contains only fixed B+ sources and the sampled input.
module network_rhs_v1_wide #(
    parameter FIXED_RHS_FILE = "model/generated/v1_fixed_rhs_q4_44.mem"
) (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 start,
    input  logic signed [31:0]   input_q24,
    output logic [494:0]         rhs_q44,
    output logic                 busy,
    output logic                 valid
);

    localparam logic signed [40:0] INPUT_G_Q47 = 41'sd636821214278;

    logic signed [47:0] fixed_rhs [0:8];
    logic signed [31:0] input_latched;
    logic signed [72:0] input_product;
    logic signed [72:0] input_biased;
    logic signed [54:0] input_current_q44;

    typedef enum logic [1:0] {IDLE, APPLY_INPUT, FINISH} state_t;
    state_t state;

    initial $readmemh(FIXED_RHS_FILE, fixed_rhs);

    always_comb begin
        input_product = INPUT_G_Q47 * input_latched;
        input_biased = input_product + (73'sd1 <<< 26);
        input_current_q44 = 55'($signed(input_biased) >>> 27);
    end

    integer lane;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            busy <= 1'b0;
            valid <= 1'b0;
            input_latched <= '0;
            rhs_q44 <= '0;
        end else begin
            valid <= 1'b0;
            case (state)
                IDLE: begin
                    busy <= 1'b0;
                    if (start) begin
                        input_latched <= input_q24;
                        busy <= 1'b1;
                        state <= APPLY_INPUT;
                    end
                end
                APPLY_INPUT: begin
                    for (lane = 0; lane < 9; lane = lane + 1)
                        rhs_q44[lane * 55 +: 55] <= {{7{fixed_rhs[lane][47]}},
                                                     fixed_rhs[lane]};
                    rhs_q44[0 +: 55] <= {{7{fixed_rhs[0][47]}}, fixed_rhs[0]}
                                         + input_current_q44;
                    state <= FINISH;
                end
                FINISH: begin
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
