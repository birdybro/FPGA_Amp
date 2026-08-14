`timescale 1ns/1ps
`default_nettype none

// Complete digital pin hierarchy: I2S ADC/DAC, accuracy-first mono model, and
// mode-0 SPI host control. Physical clock generation, I/O constraints, analog
// mute, converters, and speaker protection remain board responsibilities.
module phono_i2s_spi_top #(
    parameter int unsigned OUTPUT_RAMP_SAMPLES = 2048,
    parameter int unsigned CLOCK_MONITOR_WINDOW_FABRIC_CLOCKS = 32768,
    parameter int unsigned CLOCK_MONITOR_EXPECTED_BCLK_EDGES = 1024,
    parameter int unsigned CLOCK_MONITOR_EDGE_TOLERANCE = 1,
    parameter int unsigned CLOCK_MONITOR_LOCK_WINDOWS = 3,
    parameter int unsigned DIAGNOSTIC_SNAPSHOT_TIMEOUT_CLOCKS = 131072
) (
    input  logic                 i2s_bclk,
    input  logic                 i2s_rst_n,
    input  logic                 i2s_adc_lrclk,
    input  logic                 i2s_adc_serial_data,
    output logic                 i2s_dac_lrclk,
    output logic                 i2s_dac_serial_data,

    input  logic                 fabric_clk,
    input  logic                 fabric_rst_n,
    input  logic                 audio_rst_n,
    input  logic                 force_mute,

    input  logic                 spi_cs_n,
    input  logic                 spi_sclk,
    input  logic                 spi_mosi,
    output logic                 spi_miso,

    output logic                 output_muted,
    output logic                 output_ramping,
    output logic                 audio_clock_rate_locked,
    output logic                 audio_clock_rate_error_sticky,
    output logic                 rate_fault_mute_active,
    output logic                 spi_frame_error_sticky,
    output logic                 spi_response_underflow_sticky,
    output logic [31:0]          spi_completed_frame_count,
    output logic                 control_bus_error_sticky,
    output logic                 calibration_rejected_sticky,
    output logic                 snapshot_capture_timeout_sticky
);

    logic control_request_valid;
    logic control_request_write;
    logic [7:0] control_request_address;
    logic [31:0] control_request_write_data;
    logic control_response_valid;
    logic [31:0] control_response_read_data;
    logic control_response_error;
    logic transport_clear_diagnostics;
    // These counters remain host-readable through the register bank.  Keep a
    // named sink here because this pin-level wrapper does not duplicate them
    // onto package pins.
    logic [95:0] unused_register_sequences;

    spi_control_transport control_transport (
        .fabric_clk,
        .fabric_rst_n,
        .spi_cs_n,
        .spi_sclk,
        .spi_mosi,
        .spi_miso,
        .control_request_valid,
        .control_request_write,
        .control_request_address,
        .control_request_write_data,
        .control_response_valid,
        .control_response_read_data,
        .control_response_error,
        .clear_diagnostics(transport_clear_diagnostics),
        .frame_error_sticky(spi_frame_error_sticky),
        .response_underflow_sticky(spi_response_underflow_sticky),
        .completed_frame_count(spi_completed_frame_count)
    );

    phono_i2s_control_top #(
        .OUTPUT_RAMP_SAMPLES(OUTPUT_RAMP_SAMPLES),
        .CLOCK_MONITOR_WINDOW_FABRIC_CLOCKS(
            CLOCK_MONITOR_WINDOW_FABRIC_CLOCKS
        ),
        .CLOCK_MONITOR_EXPECTED_BCLK_EDGES(
            CLOCK_MONITOR_EXPECTED_BCLK_EDGES
        ),
        .CLOCK_MONITOR_EDGE_TOLERANCE(
            CLOCK_MONITOR_EDGE_TOLERANCE
        ),
        .CLOCK_MONITOR_LOCK_WINDOWS(CLOCK_MONITOR_LOCK_WINDOWS),
        .DIAGNOSTIC_SNAPSHOT_TIMEOUT_CLOCKS(
            DIAGNOSTIC_SNAPSHOT_TIMEOUT_CLOCKS
        )
    ) controlled_audio (
        .i2s_bclk,
        .i2s_rst_n,
        .i2s_adc_lrclk,
        .i2s_adc_serial_data,
        .i2s_dac_lrclk,
        .i2s_dac_serial_data,
        .fabric_clk,
        .fabric_rst_n,
        .audio_rst_n,
        .force_mute,
        .transport_frame_error_sticky(spi_frame_error_sticky),
        .transport_response_underflow_sticky(
            spi_response_underflow_sticky
        ),
        .transport_completed_frame_count(spi_completed_frame_count),
        .transport_clear_diagnostics,
        .control_request_valid,
        .control_request_write,
        .control_request_address,
        .control_request_write_data,
        .control_response_valid,
        .control_response_read_data,
        .control_response_error,
        .output_muted,
        .output_ramping,
        .audio_clock_rate_locked,
        .audio_clock_rate_error_sticky,
        .rate_fault_mute_active,
        .control_snapshot_sequence(unused_register_sequences[31:0]),
        .calibration_commit_sequence(unused_register_sequences[63:32]),
        .calibration_accepted_sequence(unused_register_sequences[95:64]),
        .control_bus_error_sticky,
        .calibration_rejected_sticky,
        .snapshot_capture_timeout_sticky
    );

endmodule

`default_nettype wire
