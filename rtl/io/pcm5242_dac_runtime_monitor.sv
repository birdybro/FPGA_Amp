`timescale 1ns/1ps
`default_nettype none

// Periodic fail-latched PCM5242 runtime health monitor.
//
// Page 0 must be selected before enable is asserted. Each poll reads live clock
// validity, latched clock faults, active/sticky output-short status, and DSP
// boot/run state. A NACK or masked mismatch permanently removes healthy until
// reset. Reading registers 0x5f and 0x6d clears their device-side sticky bits;
// this block captures the first failing value before that information is lost.
module pcm5242_dac_runtime_monitor #(
    parameter int unsigned I2C_CLOCK_DIVIDER = 32,
    parameter int unsigned POLL_INTERVAL_CYCLES = 9_830_400
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        enable,

    input  logic        scl_in,
    input  logic        sda_in,
    output logic        scl_drive_low,
    output logic        sda_drive_low,

    output logic        busy,
    output logic        healthy,
    output logic        fault,
    output logic        nack_error,
    output logic        mismatch_error,
    output logic [1:0]  sequence_index,
    output logic [7:0]  failed_register,
    output logic [7:0]  failed_observed,
    output logic [7:0]  failed_expected,
    output logic [7:0]  failed_mask,
    output logic [31:0] poll_count,
    output logic [7:0]  clock_status,
    output logic [7:0]  clock_error_status,
    output logic [7:0]  short_status,
    output logic [7:0]  power_status
);

    localparam logic [6:0] DEVICE_ADDRESS = 7'h4c;
    localparam int unsigned INTERVAL_WIDTH =
        POLL_INTERVAL_CYCLES <= 1 ? 1 : $clog2(POLL_INTERVAL_CYCLES);

    typedef enum logic [2:0] {
        STATE_DISABLED,
        STATE_LAUNCH_READ,
        STATE_WAIT_READ,
        STATE_WAIT_INTERVAL,
        STATE_FAULT
    } state_t;

    state_t state;
    logic [INTERVAL_WIDTH-1:0] interval_count;
    logic reader_start;
    logic reader_busy;
    logic reader_done;
    logic reader_nack;
    logic [7:0] reader_data;
    logic [7:0] selected_register;
    logic [7:0] selected_expected;
    logic [7:0] selected_mask;
    logic selected_mismatch;

    initial begin
        if (POLL_INTERVAL_CYCLES < 1)
            $error("POLL_INTERVAL_CYCLES must be positive");
    end

    function automatic logic [7:0] register_for_index(input logic [1:0] index);
        case (index)
            2'd0: register_for_index = 8'h5e; // Live clock validity
            2'd1: register_for_index = 8'h5f; // Latched/live clock error
            2'd2: register_for_index = 8'h6d; // Active/sticky output short
            default: register_for_index = 8'h76; // DSP boot/power state
        endcase
    endfunction

    function automatic logic [7:0] expected_for_index(input logic [1:0] index);
        case (index)
            2'd0: expected_for_index = 8'h20; // PLL disabled; clocks valid
            2'd1: expected_for_index = 8'h00; // No halt/resync/error
            2'd2: expected_for_index = 8'h00; // No active/sticky short
            default: expected_for_index = 8'h85; // DSP booted, run state
        endcase
    endfunction

    function automatic logic [7:0] mask_for_index(input logic [1:0] index);
        case (index)
            2'd0: mask_for_index = 8'h7f;
            2'd1: mask_for_index = 8'h17;
            2'd2: mask_for_index = 8'h11;
            default: mask_for_index = 8'h8f;
        endcase
    endfunction

    always_comb begin
        selected_register = register_for_index(sequence_index);
        selected_expected = expected_for_index(sequence_index);
        selected_mask = mask_for_index(sequence_index);
        selected_mismatch = |((reader_data ^ selected_expected) & selected_mask);
        busy = state == STATE_LAUNCH_READ || state == STATE_WAIT_READ;
        healthy = state == STATE_WAIT_INTERVAL && !fault;
    end

    i2c_read_register_master #(
        .CLOCK_DIVIDER(I2C_CLOCK_DIVIDER)
    ) reader (
        .clk,
        .rst_n,
        .start(reader_start),
        .device_address(DEVICE_ADDRESS),
        .register_address(selected_register),
        .scl_in,
        .sda_in,
        .scl_drive_low,
        .sda_drive_low,
        .busy(reader_busy),
        .done(reader_done),
        .nack(reader_nack),
        .read_data(reader_data)
    );

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= STATE_DISABLED;
            interval_count <= '0;
            reader_start <= 1'b0;
            fault <= 1'b0;
            nack_error <= 1'b0;
            mismatch_error <= 1'b0;
            sequence_index <= '0;
            failed_register <= '0;
            failed_observed <= '0;
            failed_expected <= '0;
            failed_mask <= '0;
            poll_count <= '0;
            clock_status <= '0;
            clock_error_status <= '0;
            short_status <= '0;
            power_status <= '0;
        end else begin
            reader_start <= 1'b0;
            case (state)
                STATE_DISABLED: begin
                    interval_count <= '0;
                    sequence_index <= '0;
                    if (enable) begin
                        if (fault)
                            state <= STATE_FAULT;
                        else
                            state <= STATE_LAUNCH_READ;
                    end
                end
                STATE_LAUNCH_READ: begin
                    if (!enable) begin
                        state <= STATE_DISABLED;
                    end else if (!reader_busy) begin
                        reader_start <= 1'b1;
                        state <= STATE_WAIT_READ;
                    end
                end
                STATE_WAIT_READ: begin
                    if (reader_done) begin
                        case (sequence_index)
                            2'd0: clock_status <= reader_data;
                            2'd1: clock_error_status <= reader_data;
                            2'd2: short_status <= reader_data;
                            default: power_status <= reader_data;
                        endcase
                        if (reader_nack || selected_mismatch) begin
                            fault <= 1'b1;
                            nack_error <= reader_nack;
                            mismatch_error <= !reader_nack && selected_mismatch;
                            failed_register <= selected_register;
                            failed_observed <= reader_data;
                            failed_expected <= selected_expected;
                            failed_mask <= selected_mask;
                            state <= STATE_FAULT;
                        end else if (sequence_index == 2'd3) begin
                            poll_count <= poll_count + 1'b1;
                            interval_count <= '0;
                            state <= STATE_WAIT_INTERVAL;
                        end else begin
                            sequence_index <= sequence_index + 1'b1;
                            state <= STATE_LAUNCH_READ;
                        end
                    end
                end
                STATE_WAIT_INTERVAL: begin
                    if (!enable) begin
                        state <= STATE_DISABLED;
                    end else if (interval_count ==
                                 INTERVAL_WIDTH'(POLL_INTERVAL_CYCLES - 1)) begin
                        interval_count <= '0;
                        sequence_index <= '0;
                        state <= STATE_LAUNCH_READ;
                    end else begin
                        interval_count <= interval_count + 1'b1;
                    end
                end
                default: state <= STATE_FAULT;
            endcase
        end
    end

endmodule

`default_nettype wire
