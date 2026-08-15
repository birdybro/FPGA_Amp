`timescale 1ns/1ps
`default_nettype none

// Complete one-shot startup controller for the Rev-A PCM5242 line-output PCB.
//
// The ACK-only initialization runs first. Only after it completes does the
// page-aware readback/status verifier start. unmute_permitted remains low until
// both phases succeed, and any error is latched by its owning sub-block until
// reset. The board must still AND this permission with its independent external
// supervisor, and continuous runtime clock/fault monitoring remains separate.
module pcm5242_dac_startup_controller #(
    parameter int unsigned STARTUP_DELAY_CYCLES = 491_520,
    parameter int unsigned I2C_CLOCK_DIVIDER = 32
) (
    input  logic       clk,
    input  logic       rst_n,

    input  logic       scl_in,
    input  logic       sda_in,
    output logic       scl_drive_low,
    output logic       sda_drive_low,

    output logic       busy,
    output logic       configuration_written,
    output logic       configuration_verified,
    output logic       unmute_permitted,
    output logic       error,
    output logic       initialization_error,
    output logic       verification_error,
    output logic       verification_nack_error,
    output logic       verification_mismatch_error,
    output logic [4:0] initialization_sequence_index,
    output logic [4:0] initialization_failed_index,
    output logic [4:0] verification_sequence_index,
    output logic [4:0] verification_failed_index,
    output logic [7:0] failed_observed,
    output logic [7:0] failed_expected,
    output logic [7:0] failed_mask,
    output logic [7:0] clock_status,
    output logic [7:0] power_status
);

    logic init_busy;
    logic init_scl_drive_low;
    logic init_sda_drive_low;
    logic verify_start;
    logic verification_started;
    logic verify_busy;
    logic verify_scl_drive_low;
    logic verify_sda_drive_low;

    always_comb begin
        scl_drive_low = init_scl_drive_low | verify_scl_drive_low;
        sda_drive_low = init_sda_drive_low | verify_sda_drive_low;
        error = initialization_error | verification_error;
        busy = init_busy || verify_busy ||
               (!configuration_verified && !error);
        unmute_permitted = configuration_verified && !error;
    end

    pcm5242_dac_init #(
        .STARTUP_DELAY_CYCLES(STARTUP_DELAY_CYCLES),
        .I2C_CLOCK_DIVIDER(I2C_CLOCK_DIVIDER)
    ) initializer (
        .clk,
        .rst_n,
        .scl_in,
        .sda_in,
        .scl_drive_low(init_scl_drive_low),
        .sda_drive_low(init_sda_drive_low),
        .busy(init_busy),
        .configuration_written,
        .error(initialization_error),
        .sequence_index(initialization_sequence_index),
        .failed_index(initialization_failed_index)
    );

    pcm5242_dac_verify #(
        .I2C_CLOCK_DIVIDER(I2C_CLOCK_DIVIDER)
    ) verifier (
        .clk,
        .rst_n,
        .start(verify_start),
        .scl_in,
        .sda_in,
        .scl_drive_low(verify_scl_drive_low),
        .sda_drive_low(verify_sda_drive_low),
        .busy(verify_busy),
        .configuration_verified,
        .error(verification_error),
        .nack_error(verification_nack_error),
        .mismatch_error(verification_mismatch_error),
        .sequence_index(verification_sequence_index),
        .failed_index(verification_failed_index),
        .failed_observed,
        .failed_expected,
        .failed_mask,
        .clock_status,
        .power_status
    );

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            verify_start <= 1'b0;
            verification_started <= 1'b0;
        end else begin
            verify_start <= 1'b0;
            if (configuration_written && !verification_started) begin
                verify_start <= 1'b1;
                verification_started <= 1'b1;
            end
        end
    end

endmodule

`default_nettype wire
