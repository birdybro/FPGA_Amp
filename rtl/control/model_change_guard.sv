`timescale 1ns/1ps
`default_nettype none

// Downstream safety/control wrapper for state-reset transactions. This block is
// outside the historical circuit model. It assumes ce_input_48k is periodic at
// INPUT_PERIOD_CLOCKS and aligns core reset release to the following frame.
module model_change_guard #(
    parameter int unsigned INPUT_PERIOD_CLOCKS = 2048,
    parameter int unsigned WARMUP_SAMPLES = 64,
    parameter int unsigned RAMP_SAMPLES = 2048
) (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 ce_input_48k,
    input  logic signed [31:0]   core_sample_q24,
    input  logic                 core_sample_valid,
    input  logic                 model_change_request,
    input  logic                 mute_request,
    input  logic                 force_mute,
    output logic                 core_rst_n,
    output logic                 core_ce_input_48k,
    output logic signed [31:0]   sample_output_q24,
    output logic                 output_valid,
    output logic                 model_change_ack,
    output logic                 change_busy,
    output logic                 output_ready,
    output logic                 core_reset_active,
    output logic [15:0]          output_gain_q16,
    output logic                 output_muted,
    output logic                 output_ramping
);

    initial begin
        if (INPUT_PERIOD_CLOCKS < 2)
            $error("INPUT_PERIOD_CLOCKS must be at least two");
        if (WARMUP_SAMPLES == 0)
            $error("WARMUP_SAMPLES must be nonzero");
    end

    typedef enum logic [2:0] {
        ALIGN_RESET,
        HOLD_RESET,
        WARMUP,
        RUNNING,
        RAMP_DOWN
    } state_t;
    state_t state;

    localparam int unsigned RESET_COUNTER_WIDTH = $clog2(INPUT_PERIOD_CLOCKS);
    localparam int unsigned WARMUP_COUNTER_WIDTH = $clog2(WARMUP_SAMPLES + 1);
    localparam logic [RESET_COUNTER_WIDTH-1:0] RESET_LAST =
        RESET_COUNTER_WIDTH'(INPUT_PERIOD_CLOCKS - 2);
    localparam logic [WARMUP_COUNTER_WIDTH-1:0] WARMUP_LAST =
        WARMUP_COUNTER_WIDTH'(WARMUP_SAMPLES - 1);
    logic [RESET_COUNTER_WIDTH-1:0] reset_clock_count;
    logic [WARMUP_COUNTER_WIDTH-1:0] warmup_sample_count;
    logic request_seen;
    logic change_pending;
    logic ramp_mute_request;

    always_comb begin
        core_reset_active = (state == ALIGN_RESET) || (state == HOLD_RESET);
        core_rst_n = rst_n && !core_reset_active;
        core_ce_input_48k = ce_input_48k && core_rst_n;
        ramp_mute_request = mute_request || (state != RUNNING);
        change_busy = (state != RUNNING) || output_ramping;
        output_ready = (state == RUNNING) && !output_ramping && !output_muted;
    end

    output_mute_ramp #(
        .RAMP_SAMPLES(RAMP_SAMPLES)
    ) output_guard (
        .clk,
        .rst_n,
        .sample_valid(core_sample_valid),
        .sample_input_q24(core_sample_q24),
        .mute_request(ramp_mute_request),
        .force_mute,
        .sample_output_q24,
        .output_valid,
        .gain_q16(output_gain_q16),
        .muted(output_muted),
        .ramping(output_ramping)
    );

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= ALIGN_RESET;
            reset_clock_count <= '0;
            warmup_sample_count <= '0;
            request_seen <= 1'b0;
            change_pending <= 1'b0;
            model_change_ack <= 1'b0;
        end else begin
            model_change_ack <= 1'b0;
            if (!model_change_request)
                request_seen <= 1'b0;
            case (state)
                ALIGN_RESET: begin
                    if (ce_input_48k) begin
                        reset_clock_count <= '0;
                        state <= HOLD_RESET;
                    end
                end
                HOLD_RESET: begin
                    if (reset_clock_count == RESET_LAST) begin
                        warmup_sample_count <= '0;
                        state <= WARMUP;
                    end else begin
                        reset_clock_count <= reset_clock_count + 1'b1;
                    end
                end
                WARMUP: begin
                    if (core_sample_valid) begin
                        if (warmup_sample_count == WARMUP_LAST) begin
                            warmup_sample_count <= '0;
                            state <= RUNNING;
                            if (change_pending) begin
                                model_change_ack <= 1'b1;
                                change_pending <= 1'b0;
                            end
                        end else begin
                            warmup_sample_count <= warmup_sample_count + 1'b1;
                        end
                    end
                end
                RUNNING: begin
                    if (model_change_request && !request_seen) begin
                        request_seen <= 1'b1;
                        change_pending <= 1'b1;
                        state <= RAMP_DOWN;
                    end
                end
                RAMP_DOWN: begin
                    if (output_muted)
                        state <= ALIGN_RESET;
                end
                default: state <= ALIGN_RESET;
            endcase
        end
    end

endmodule

`default_nettype wire
