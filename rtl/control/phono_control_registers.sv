`timescale 1ns/1ps
`default_nettype none

// Protocol-neutral, fabric-clocked host boundary. The bus accepts one request
// per clock and returns a registered response one clock later. Diagnostic words
// are copied together only on an explicit snapshot command; reads never sample
// a moving counter directly.
module phono_control_registers #(
    parameter int unsigned DIAGNOSTIC_WORD_COUNT = 16,
    parameter int unsigned SNAPSHOT_TIMEOUT_CLOCKS = 131072
) (
    input  logic                 clk,
    input  logic                 rst_n,

    input  logic                 request_valid,
    input  logic                 request_write,
    input  logic [7:0]           request_address,
    input  logic [31:0]          request_write_data,
    output logic                 response_valid,
    output logic [31:0]          response_read_data,
    output logic                 response_error,

    input  logic [DIAGNOSTIC_WORD_COUNT*32-1:0] diagnostic_words_flat,
    input  logic                 diagnostic_capture_available,
    output logic                 diagnostic_capture_request,
    input  logic                 diagnostic_capture_valid,
    input  logic                 output_muted,
    input  logic                 output_ramping,

    output logic                 mute_request,
    output logic                 fabric_clear_diagnostics,
    output logic signed [31:0]   calibration_candidate_input_peak_q24,
    output logic signed [31:0]   calibration_candidate_output_reciprocal_q24,
    output logic                 calibration_update_valid,
    input  logic                 calibration_update_ack,
    input  logic                 calibration_invalid_update_sticky,
    input  logic                 calibration_unsafe_update_sticky,
    input  logic signed [31:0]   calibration_active_input_peak_q24,
    input  logic signed [31:0]   calibration_active_output_reciprocal_q24,

    output logic [31:0]          snapshot_sequence,
    output logic [31:0]          calibration_commit_sequence,
    output logic [31:0]          calibration_accepted_sequence,
    output logic                 bus_error_sticky,
    output logic                 calibration_rejected_sticky,
    output logic                 snapshot_capture_timeout_sticky
);

    localparam logic [7:0] ADDRESS_IDENTITY = 8'h00;
    localparam logic [7:0] ADDRESS_ABI_VERSION = 8'h01;
    localparam logic [7:0] ADDRESS_CAPABILITIES = 8'h02;
    localparam logic [7:0] ADDRESS_STATUS = 8'h03;
    localparam logic [7:0] ADDRESS_CONTROL = 8'h04;
    localparam logic [7:0] ADDRESS_SNAPSHOT_SEQUENCE = 8'h05;
    localparam logic [7:0] ADDRESS_CALIBRATION_COMMIT_SEQUENCE = 8'h06;
    localparam logic [7:0] ADDRESS_CALIBRATION_ACCEPTED_SEQUENCE = 8'h07;
    localparam logic [7:0] ADDRESS_CALIBRATION_SHADOW_INPUT = 8'h08;
    localparam logic [7:0] ADDRESS_CALIBRATION_SHADOW_OUTPUT = 8'h09;
    localparam logic [7:0] ADDRESS_CALIBRATION_COMMAND = 8'h0a;
    localparam logic [7:0] ADDRESS_CALIBRATION_ACTIVE_INPUT = 8'h0b;
    localparam logic [7:0] ADDRESS_CALIBRATION_ACTIVE_OUTPUT = 8'h0c;
    localparam logic [7:0] ADDRESS_STICKY_STATUS = 8'h0d;
    localparam logic [7:0] ADDRESS_DIAGNOSTIC_BASE = 8'h20;
    localparam int unsigned DIAGNOSTIC_INDEX_WIDTH =
        (DIAGNOSTIC_WORD_COUNT <= 2) ? 1 : $clog2(DIAGNOSTIC_WORD_COUNT);
    localparam logic [5:0] DIAGNOSTIC_WORD_COUNT_6 =
        DIAGNOSTIC_WORD_COUNT[5:0];
    localparam int unsigned SNAPSHOT_TIMEOUT_COUNTER_WIDTH =
        (SNAPSHOT_TIMEOUT_CLOCKS <= 2)
            ? 1 : $clog2(SNAPSHOT_TIMEOUT_CLOCKS);

    initial begin
        if (SNAPSHOT_TIMEOUT_CLOCKS < 2)
            $error("SNAPSHOT_TIMEOUT_CLOCKS must be at least two");
    end

    logic [31:0] diagnostic_snapshot [0:DIAGNOSTIC_WORD_COUNT-1];
    logic [DIAGNOSTIC_INDEX_WIDTH-1:0] diagnostic_read_index;
    logic [1:0] calibration_result_delay;
    logic [31:0] pending_calibration_sequence;
    logic calibration_busy;
    logic snapshot_valid;
    logic snapshot_busy;
    logic [SNAPSHOT_TIMEOUT_COUNTER_WIDTH-1:0] snapshot_timeout_counter;
    integer diagnostic_index;

    always_comb begin
        // The diagnostic aperture is the aligned 0x20--0x3f word page.
        diagnostic_read_index =
            request_address[DIAGNOSTIC_INDEX_WIDTH-1:0];
    end

    function automatic logic [31:0] increment_saturating(
        input logic [31:0] value
    );
        begin
            increment_saturating = (&value) ? value : value + 32'd1;
        end
    endfunction

    function automatic logic [31:0] status_word;
        begin
            status_word = '0;
            status_word[0] = mute_request;
            status_word[1] = output_muted;
            status_word[2] = output_ramping;
            status_word[3] = calibration_busy;
            status_word[4] = snapshot_valid;
            status_word[5] = snapshot_busy;
            status_word[6] = diagnostic_capture_available;
        end
    endfunction

    function automatic logic [31:0] sticky_status_word;
        begin
            sticky_status_word = '0;
            sticky_status_word[0] = bus_error_sticky;
            sticky_status_word[1] = calibration_rejected_sticky;
            sticky_status_word[2] = calibration_invalid_update_sticky;
            sticky_status_word[3] = calibration_unsafe_update_sticky;
            sticky_status_word[4] = snapshot_capture_timeout_sticky;
        end
    endfunction

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            response_valid <= 1'b0;
            response_read_data <= '0;
            response_error <= 1'b0;
            mute_request <= 1'b1;
            fabric_clear_diagnostics <= 1'b0;
            diagnostic_capture_request <= 1'b0;
            calibration_candidate_input_peak_q24 <= '0;
            calibration_candidate_output_reciprocal_q24 <= '0;
            calibration_update_valid <= 1'b0;
            snapshot_sequence <= '0;
            calibration_commit_sequence <= '0;
            calibration_accepted_sequence <= '0;
            pending_calibration_sequence <= '0;
            calibration_result_delay <= '0;
            calibration_busy <= 1'b0;
            snapshot_valid <= 1'b0;
            snapshot_busy <= 1'b0;
            snapshot_timeout_counter <= '0;
            bus_error_sticky <= 1'b0;
            calibration_rejected_sticky <= 1'b0;
            snapshot_capture_timeout_sticky <= 1'b0;
            for (diagnostic_index = 0;
                 diagnostic_index < DIAGNOSTIC_WORD_COUNT;
                 diagnostic_index = diagnostic_index + 1) begin
                diagnostic_snapshot[diagnostic_index] <= '0;
            end
        end else begin
            response_valid <= request_valid;
            response_read_data <= '0;
            response_error <= 1'b0;
            fabric_clear_diagnostics <= 1'b0;
            diagnostic_capture_request <= 1'b0;
            calibration_update_valid <= 1'b0;

            if (diagnostic_capture_valid && snapshot_busy) begin
                for (diagnostic_index = 0;
                     diagnostic_index < DIAGNOSTIC_WORD_COUNT;
                     diagnostic_index = diagnostic_index + 1) begin
                    diagnostic_snapshot[diagnostic_index] <=
                        diagnostic_words_flat[diagnostic_index*32 +: 32];
                end
                snapshot_sequence <= increment_saturating(snapshot_sequence);
                snapshot_valid <= 1'b1;
                snapshot_busy <= 1'b0;
                snapshot_timeout_counter <= '0;
            end else if (snapshot_busy) begin
                if (snapshot_timeout_counter
                    == SNAPSHOT_TIMEOUT_COUNTER_WIDTH'(
                        SNAPSHOT_TIMEOUT_CLOCKS - 1
                    )) begin
                    snapshot_busy <= 1'b0;
                    snapshot_timeout_counter <= '0;
                    snapshot_capture_timeout_sticky <= 1'b1;
                end else begin
                    snapshot_timeout_counter <= snapshot_timeout_counter + 1'b1;
                end
            end

            // The guard samples update_valid on the first following edge and
            // produces update_ack on that edge. Waiting two control clocks lets
            // this block distinguish accepted and rejected attempts exactly.
            if (calibration_result_delay != 0) begin
                calibration_result_delay <= calibration_result_delay - 2'd1;
                if (calibration_result_delay == 2'd1) begin
                    calibration_busy <= 1'b0;
                    if (calibration_update_ack)
                        calibration_accepted_sequence <=
                            pending_calibration_sequence;
                    else
                        calibration_rejected_sticky <= 1'b1;
                end
            end

            if (request_valid) begin
                if (request_write) begin
                    case (request_address)
                        ADDRESS_CONTROL: begin
                            mute_request <= request_write_data[0];
                            if (request_write_data[1]) begin
                                if (snapshot_busy
                                    || !diagnostic_capture_available) begin
                                    response_error <= 1'b1;
                                    bus_error_sticky <= 1'b1;
                                end else begin
                                    diagnostic_capture_request <= 1'b1;
                                    snapshot_busy <= 1'b1;
                                    snapshot_timeout_counter <= '0;
                                end
                            end
                            if (request_write_data[2])
                                fabric_clear_diagnostics <= 1'b1;
                            if (request_write_data[3]) begin
                                bus_error_sticky <= 1'b0;
                                calibration_rejected_sticky <= 1'b0;
                                snapshot_capture_timeout_sticky <= 1'b0;
                            end
                        end
                        ADDRESS_CALIBRATION_SHADOW_INPUT: begin
                            if (calibration_busy) begin
                                response_error <= 1'b1;
                                bus_error_sticky <= 1'b1;
                            end else begin
                                calibration_candidate_input_peak_q24 <=
                                    request_write_data;
                            end
                        end
                        ADDRESS_CALIBRATION_SHADOW_OUTPUT: begin
                            if (calibration_busy) begin
                                response_error <= 1'b1;
                                bus_error_sticky <= 1'b1;
                            end else begin
                                calibration_candidate_output_reciprocal_q24 <=
                                    request_write_data;
                            end
                        end
                        ADDRESS_CALIBRATION_COMMAND: begin
                            if (!request_write_data[0] || calibration_busy) begin
                                response_error <= 1'b1;
                                bus_error_sticky <= 1'b1;
                            end else begin
                                calibration_update_valid <= 1'b1;
                                calibration_busy <= 1'b1;
                                calibration_result_delay <= 2'd2;
                                calibration_commit_sequence <=
                                    increment_saturating(
                                        calibration_commit_sequence
                                    );
                                pending_calibration_sequence <=
                                    increment_saturating(
                                        calibration_commit_sequence
                                    );
                            end
                        end
                        default: begin
                            response_error <= 1'b1;
                            bus_error_sticky <= 1'b1;
                        end
                    endcase
                end else if (
                    request_address[7:5] == ADDRESS_DIAGNOSTIC_BASE[7:5]
                    && {1'b0, request_address[4:0]}
                       < DIAGNOSTIC_WORD_COUNT_6
                ) begin
                    response_read_data <=
                        diagnostic_snapshot[diagnostic_read_index];
                end else begin
                    case (request_address)
                        ADDRESS_IDENTITY:
                            response_read_data <= 32'h4650_4741;
                        ADDRESS_ABI_VERSION:
                            response_read_data <= 32'h0001_0001;
                        ADDRESS_CAPABILITIES:
                            response_read_data <= 32'h0000_000f;
                        ADDRESS_STATUS:
                            response_read_data <= status_word();
                        ADDRESS_CONTROL:
                            response_read_data <= {31'd0, mute_request};
                        ADDRESS_SNAPSHOT_SEQUENCE:
                            response_read_data <= snapshot_sequence;
                        ADDRESS_CALIBRATION_COMMIT_SEQUENCE:
                            response_read_data <= calibration_commit_sequence;
                        ADDRESS_CALIBRATION_ACCEPTED_SEQUENCE:
                            response_read_data <= calibration_accepted_sequence;
                        ADDRESS_CALIBRATION_SHADOW_INPUT:
                            response_read_data <=
                                calibration_candidate_input_peak_q24;
                        ADDRESS_CALIBRATION_SHADOW_OUTPUT:
                            response_read_data <=
                                calibration_candidate_output_reciprocal_q24;
                        ADDRESS_CALIBRATION_ACTIVE_INPUT:
                            response_read_data <=
                                calibration_active_input_peak_q24;
                        ADDRESS_CALIBRATION_ACTIVE_OUTPUT:
                            response_read_data <=
                                calibration_active_output_reciprocal_q24;
                        ADDRESS_STICKY_STATUS:
                            response_read_data <= sticky_status_word();
                        default: begin
                            response_error <= 1'b1;
                            bus_error_sticky <= 1'b1;
                        end
                    endcase
                end
            end
        end
    end

endmodule

`default_nettype wire
