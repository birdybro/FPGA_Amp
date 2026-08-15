`timescale 1ns/1ps
`default_nettype none

// One-shot, fail-closed verification of the PCM5242 reference-path startup.
//
// The caller starts this block only after pcm5242_dac_init reports that all
// writes were ACKed. The verifier explicitly selects each register page, reads
// back every critical writable field with a reserved-bit-safe mask, and then
// validates the detected 48 kHz / 512-fS SCK / 64-fS BCK clock state plus DSP
// boot/run state. configuration_verified is therefore stronger than an ACKed
// write sequence, but it remains a startup snapshot rather than a continuous
// runtime clock/fault monitor.
module pcm5242_dac_verify #(
    parameter int unsigned I2C_CLOCK_DIVIDER = 32
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       start,

    input  logic       scl_in,
    input  logic       sda_in,
    output logic       scl_drive_low,
    output logic       sda_drive_low,

    output logic       busy,
    output logic       configuration_verified,
    output logic       error,
    output logic       nack_error,
    output logic       mismatch_error,
    output logic [4:0] sequence_index,
    output logic [4:0] failed_index,
    output logic [7:0] failed_observed,
    output logic [7:0] failed_expected,
    output logic [7:0] failed_mask,
    output logic [7:0] clock_status,
    output logic [7:0] power_status
);

    localparam logic [6:0] DEVICE_ADDRESS = 7'h4c;
    localparam int unsigned OPERATION_COUNT = 24;

    typedef enum logic [3:0] {
        STATE_IDLE,
        STATE_LAUNCH_WRITE,
        STATE_WAIT_WRITE,
        STATE_LAUNCH_READ,
        STATE_WAIT_READ,
        STATE_VERIFIED,
        STATE_FAILED
    } state_t;

    state_t state;
    logic writer_start;
    logic writer_busy;
    logic writer_done;
    logic writer_nack;
    logic writer_scl_drive_low;
    logic writer_sda_drive_low;
    logic reader_start;
    logic reader_busy;
    logic reader_done;
    logic reader_nack;
    logic reader_scl_drive_low;
    logic reader_sda_drive_low;
    logic [7:0] reader_data;
    logic [7:0] selected_register;
    logic [7:0] selected_write_data;
    logic [7:0] selected_expected;
    logic [7:0] selected_mask;
    logic selected_mismatch;

    function automatic logic is_write_for_index(input logic [4:0] index);
        is_write_for_index = index == 5'd0 || index == 5'd13 || index == 5'd18;
    endfunction

    function automatic logic [7:0] register_for_index(input logic [4:0] index);
        case (index)
            5'd0:  register_for_index = 8'h00; // Select page 0
            5'd1:  register_for_index = 8'h02; // Normal operation request
            5'd2:  register_for_index = 8'h03; // Register soft mute released
            5'd3:  register_for_index = 8'h04; // PLL disabled / lock monitor
            5'd4:  register_for_index = 8'h07; // De-emphasis / SDOUT
            5'd5:  register_for_index = 8'h28; // 24-bit I2S
            5'd6:  register_for_index = 8'h29; // I2S shift
            5'd7:  register_for_index = 8'h2a; // Direct L/R data paths
            5'd8:  register_for_index = 8'h2b; // DSP program 1
            5'd9:  register_for_index = 8'h3c; // Independent volume
            5'd10: register_for_index = 8'h3d; // Left digital 0 dB
            5'd11: register_for_index = 8'h3e; // Right digital 0 dB
            5'd12: register_for_index = 8'h41; // Auto mute disabled
            5'd13: register_for_index = 8'h00; // Select page 1
            5'd14: register_for_index = 8'h01; // VREF output
            5'd15: register_for_index = 8'h02; // Analog gains 0 dB
            5'd16: register_for_index = 8'h06; // Analog mute follows digital
            5'd17: register_for_index = 8'h07; // No +10% boost
            5'd18: register_for_index = 8'h00; // Return to page 0
            5'd19: register_for_index = 8'h5b; // Detected fS/SCK ratio
            5'd20: register_for_index = 8'h5c; // Detected BCK ratio bit 8
            5'd21: register_for_index = 8'h5d; // Detected BCK ratio bits 7:0
            5'd22: register_for_index = 8'h5e; // Clock validity status
            default: register_for_index = 8'h76; // DSP boot/power state
        endcase
    endfunction

    function automatic logic [7:0] write_data_for_index(input logic [4:0] index);
        write_data_for_index = index == 5'd13 ? 8'h01 : 8'h00;
    endfunction

    function automatic logic [7:0] expected_for_index(input logic [4:0] index);
        case (index)
            5'd1:  expected_for_index = 8'h00;
            5'd2:  expected_for_index = 8'h00;
            5'd3:  expected_for_index = 8'h10;
            5'd4:  expected_for_index = 8'h00;
            5'd5:  expected_for_index = 8'h02;
            5'd6:  expected_for_index = 8'h00;
            5'd7:  expected_for_index = 8'h11;
            5'd8:  expected_for_index = 8'h01;
            5'd9:  expected_for_index = 8'h00;
            5'd10: expected_for_index = 8'h30;
            5'd11: expected_for_index = 8'h30;
            5'd12: expected_for_index = 8'h00;
            5'd14: expected_for_index = 8'h00;
            5'd15: expected_for_index = 8'h00;
            5'd16: expected_for_index = 8'h00;
            5'd17: expected_for_index = 8'h00;
            5'd19: expected_for_index = 8'h38; // 48 kHz, SCK = 512 fS
            5'd20: expected_for_index = 8'h00;
            5'd21: expected_for_index = 8'h40; // BCK = 64 fS
            5'd22: expected_for_index = 8'h20; // PLL disabled; clocks valid
            default: expected_for_index = 8'h85; // DSP booted, run state
        endcase
    endfunction

    function automatic logic [7:0] mask_for_index(input logic [4:0] index);
        case (index)
            5'd1:  mask_for_index = 8'h11;
            5'd2:  mask_for_index = 8'h11;
            5'd3:  mask_for_index = 8'h11;
            5'd4:  mask_for_index = 8'h11;
            5'd5:  mask_for_index = 8'h33;
            5'd6:  mask_for_index = 8'hff;
            5'd7:  mask_for_index = 8'h33;
            5'd8:  mask_for_index = 8'h1f;
            5'd9:  mask_for_index = 8'h03;
            5'd10: mask_for_index = 8'hff;
            5'd11: mask_for_index = 8'hff;
            5'd12: mask_for_index = 8'h07;
            5'd14: mask_for_index = 8'h01;
            5'd15: mask_for_index = 8'h11;
            5'd16: mask_for_index = 8'h01;
            5'd17: mask_for_index = 8'h11;
            5'd19: mask_for_index = 8'h7f;
            5'd20: mask_for_index = 8'h01;
            5'd21: mask_for_index = 8'hff;
            5'd22: mask_for_index = 8'h7f;
            default: mask_for_index = 8'h8f;
        endcase
    endfunction

    always_comb begin
        selected_register = register_for_index(sequence_index);
        selected_write_data = write_data_for_index(sequence_index);
        selected_expected = expected_for_index(sequence_index);
        selected_mask = mask_for_index(sequence_index);
        selected_mismatch = |((reader_data ^ selected_expected) & selected_mask);

        scl_drive_low = writer_scl_drive_low | reader_scl_drive_low;
        sda_drive_low = writer_sda_drive_low | reader_sda_drive_low;
        busy = state == STATE_LAUNCH_WRITE || state == STATE_WAIT_WRITE ||
               state == STATE_LAUNCH_READ || state == STATE_WAIT_READ;
        configuration_verified = state == STATE_VERIFIED;
        error = state == STATE_FAILED;
    end

    i2c_write_master #(
        .CLOCK_DIVIDER(I2C_CLOCK_DIVIDER),
        .REGISTER_ADDRESS_BYTES(1)
    ) writer (
        .clk,
        .rst_n,
        .start(writer_start),
        .device_address(DEVICE_ADDRESS),
        .register_address({8'h00, selected_register}),
        .write_data(selected_write_data),
        .scl_in,
        .sda_in,
        .scl_drive_low(writer_scl_drive_low),
        .sda_drive_low(writer_sda_drive_low),
        .busy(writer_busy),
        .done(writer_done),
        .nack(writer_nack)
    );

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
        .scl_drive_low(reader_scl_drive_low),
        .sda_drive_low(reader_sda_drive_low),
        .busy(reader_busy),
        .done(reader_done),
        .nack(reader_nack),
        .read_data(reader_data)
    );

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= STATE_IDLE;
            writer_start <= 1'b0;
            reader_start <= 1'b0;
            nack_error <= 1'b0;
            mismatch_error <= 1'b0;
            sequence_index <= '0;
            failed_index <= '0;
            failed_observed <= '0;
            failed_expected <= '0;
            failed_mask <= '0;
            clock_status <= '0;
            power_status <= '0;
        end else begin
            writer_start <= 1'b0;
            reader_start <= 1'b0;
            case (state)
                STATE_IDLE: begin
                    if (start) begin
                        sequence_index <= '0;
                        nack_error <= 1'b0;
                        mismatch_error <= 1'b0;
                        failed_index <= '0;
                        failed_observed <= '0;
                        failed_expected <= '0;
                        failed_mask <= '0;
                        clock_status <= '0;
                        power_status <= '0;
                        state <= STATE_LAUNCH_WRITE;
                    end
                end
                STATE_LAUNCH_WRITE: begin
                    if (!writer_busy) begin
                        writer_start <= 1'b1;
                        state <= STATE_WAIT_WRITE;
                    end
                end
                STATE_WAIT_WRITE: begin
                    if (writer_done) begin
                        if (writer_nack) begin
                            nack_error <= 1'b1;
                            failed_index <= sequence_index;
                            state <= STATE_FAILED;
                        end else begin
                            sequence_index <= sequence_index + 1'b1;
                            state <= STATE_LAUNCH_READ;
                        end
                    end
                end
                STATE_LAUNCH_READ: begin
                    if (!reader_busy) begin
                        reader_start <= 1'b1;
                        state <= STATE_WAIT_READ;
                    end
                end
                STATE_WAIT_READ: begin
                    if (reader_done) begin
                        if (sequence_index == 5'd22)
                            clock_status <= reader_data;
                        if (sequence_index == 5'd23)
                            power_status <= reader_data;
                        if (reader_nack) begin
                            nack_error <= 1'b1;
                            failed_index <= sequence_index;
                            state <= STATE_FAILED;
                        end else if (selected_mismatch) begin
                            mismatch_error <= 1'b1;
                            failed_index <= sequence_index;
                            failed_observed <= reader_data;
                            failed_expected <= selected_expected;
                            failed_mask <= selected_mask;
                            state <= STATE_FAILED;
                        end else if (sequence_index == 5'(OPERATION_COUNT - 1)) begin
                            state <= STATE_VERIFIED;
                        end else begin
                            sequence_index <= sequence_index + 1'b1;
                            if (is_write_for_index(sequence_index + 1'b1))
                                state <= STATE_LAUNCH_WRITE;
                            else
                                state <= STATE_LAUNCH_READ;
                        end
                    end
                end
                STATE_VERIFIED: state <= STATE_VERIFIED;
                default: state <= STATE_FAILED;
            endcase
        end
    end

endmodule

`default_nettype wire
