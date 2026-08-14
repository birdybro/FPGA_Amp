`timescale 1ns/1ps
`default_nettype none

// Align held ready/valid stereo frames to a deterministic fabric-clock phase.
// The output is combinational during exactly one launch clock. A registered
// preprocessing block of PREPROCESS_LATENCY_CLOCKS then presents its valid at
// phase zero to a consumer reset from the same rst_n.
module audio_frame_scheduler #(
    parameter int unsigned PERIOD_CLOCKS = 2048,
    parameter int unsigned PREPROCESS_LATENCY_CLOCKS = 1
) (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic [63:0]          frame_input_data,
    input  logic                 frame_input_valid,
    output logic                 frame_input_ready,
    output logic [63:0]          frame_output_data,
    output logic                 frame_output_valid,
    output logic                 frame_was_present,
    input  logic                 clear_diagnostics,
    output logic [31:0]          underflow_count,
    output logic [$clog2(PERIOD_CLOCKS)-1:0] phase_counter
);

    localparam int unsigned PHASE_WIDTH = $clog2(PERIOD_CLOCKS);
    localparam logic [PHASE_WIDTH-1:0] LAST_PHASE =
        PHASE_WIDTH'(PERIOD_CLOCKS - 1);
    localparam logic [PHASE_WIDTH-1:0] LAUNCH_PHASE =
        PHASE_WIDTH'(PERIOD_CLOCKS - PREPROCESS_LATENCY_CLOCKS);

    initial begin
        if (PERIOD_CLOCKS < 2)
            $error("PERIOD_CLOCKS must be at least two");
        if ((1 << PHASE_WIDTH) < PERIOD_CLOCKS)
            $error("phase counter width is insufficient");
        if (PREPROCESS_LATENCY_CLOCKS == 0
            || PREPROCESS_LATENCY_CLOCKS >= PERIOD_CLOCKS)
            $error("PREPROCESS_LATENCY_CLOCKS must be within 1..period-1");
    end

    logic launch_boundary;
    always_comb begin
        launch_boundary = phase_counter == LAUNCH_PHASE;
        frame_input_ready = launch_boundary;
        frame_output_valid = launch_boundary;
        frame_was_present = launch_boundary && frame_input_valid;
        frame_output_data = frame_input_valid ? frame_input_data : 64'd0;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            phase_counter <= '0;
            underflow_count <= '0;
        end else begin
            if (phase_counter == LAST_PHASE)
                phase_counter <= '0;
            else
                phase_counter <= phase_counter + 1'b1;

            if (clear_diagnostics) begin
                underflow_count <= '0;
            end else if (launch_boundary && !frame_input_valid
                         && underflow_count != 32'hffffffff) begin
                underflow_count <= underflow_count + 1'b1;
            end
        end
    end

endmodule

`default_nettype wire
