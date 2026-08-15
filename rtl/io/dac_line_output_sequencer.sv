`timescale 1ns/1ps
`default_nettype none

// Controller-side sequence for the Rev-A DAC board's two hardware interlocks.
//
// Normal release closes the normally-open line relays first and waits for
// contact settling before releasing PCM5242 XSMT. Normal mute drops XSMT first,
// waits for its soft ramp, then opens the relays. emergency_mute drops both
// controller permissions on the next fabric edge. HARD_MUTE_N remains a wholly
// independent hardware veto on the PCB; this logic is not a safety substitute.
module dac_line_output_sequencer #(
    parameter int unsigned RELAY_SETTLE_CYCLES = 491_520,
    parameter int unsigned DAC_MUTE_SETTLE_CYCLES = 491_520
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       release_request,
    input  logic       emergency_mute,

    output logic       line_relay_enable_ctl,
    output logic       dac_soft_unmute_ctl,
    output logic       output_released,
    output logic [2:0] sequence_state
);

    localparam int unsigned MAX_DELAY_CYCLES =
        RELAY_SETTLE_CYCLES > DAC_MUTE_SETTLE_CYCLES ?
        RELAY_SETTLE_CYCLES : DAC_MUTE_SETTLE_CYCLES;
    localparam int unsigned COUNTER_WIDTH =
        MAX_DELAY_CYCLES <= 1 ? 1 : $clog2(MAX_DELAY_CYCLES);

    typedef enum logic [2:0] {
        STATE_OFF,
        STATE_RELAY_SETTLE,
        STATE_RELEASED,
        STATE_DAC_MUTE_SETTLE,
        STATE_EMERGENCY
    } state_t;

    state_t state;
    logic [COUNTER_WIDTH-1:0] delay_counter;

    initial begin
        if (RELAY_SETTLE_CYCLES < 1)
            $error("RELAY_SETTLE_CYCLES must be positive");
        if (DAC_MUTE_SETTLE_CYCLES < 1)
            $error("DAC_MUTE_SETTLE_CYCLES must be positive");
    end

    always_comb begin
        sequence_state = state;
        line_relay_enable_ctl = 1'b0;
        dac_soft_unmute_ctl = 1'b0;
        output_released = 1'b0;
        case (state)
            STATE_RELAY_SETTLE: line_relay_enable_ctl = 1'b1;
            STATE_RELEASED: begin
                line_relay_enable_ctl = 1'b1;
                dac_soft_unmute_ctl = 1'b1;
                output_released = 1'b1;
            end
            STATE_DAC_MUTE_SETTLE: line_relay_enable_ctl = 1'b1;
            default: begin
                line_relay_enable_ctl = 1'b0;
                dac_soft_unmute_ctl = 1'b0;
                output_released = 1'b0;
            end
        endcase
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= STATE_OFF;
            delay_counter <= '0;
        end else if (emergency_mute) begin
            state <= STATE_EMERGENCY;
            delay_counter <= '0;
        end else begin
            case (state)
                STATE_OFF: begin
                    delay_counter <= '0;
                    if (release_request)
                        state <= STATE_RELAY_SETTLE;
                end
                STATE_RELAY_SETTLE: begin
                    if (!release_request) begin
                        state <= STATE_OFF;
                        delay_counter <= '0;
                    end else if (delay_counter ==
                                 COUNTER_WIDTH'(RELAY_SETTLE_CYCLES - 1)) begin
                        state <= STATE_RELEASED;
                        delay_counter <= '0;
                    end else begin
                        delay_counter <= delay_counter + 1'b1;
                    end
                end
                STATE_RELEASED: begin
                    delay_counter <= '0;
                    if (!release_request)
                        state <= STATE_DAC_MUTE_SETTLE;
                end
                STATE_DAC_MUTE_SETTLE: begin
                    if (release_request) begin
                        state <= STATE_RELEASED;
                        delay_counter <= '0;
                    end else if (delay_counter ==
                                 COUNTER_WIDTH'(DAC_MUTE_SETTLE_CYCLES - 1)) begin
                        state <= STATE_OFF;
                        delay_counter <= '0;
                    end else begin
                        delay_counter <= delay_counter + 1'b1;
                    end
                end
                STATE_EMERGENCY: begin
                    delay_counter <= '0;
                    if (!release_request)
                        state <= STATE_OFF;
                end
                default: begin
                    state <= STATE_EMERGENCY;
                    delay_counter <= '0;
                end
            endcase
        end
    end

endmodule

`default_nettype wire
