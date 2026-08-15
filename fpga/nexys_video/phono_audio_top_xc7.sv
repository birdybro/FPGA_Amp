`timescale 1ns/1ps
`default_nettype none

// Nexys Video Rev. A board top for the timing-closed 384 kHz V1 candidate.
// All device-specific clock and pin behavior stops at this wrapper. The codec
// is subordinate to FPGA-generated MCLK/BCLK/LRCLK; SPI is the host control
// plane, and audio remains reset/muted until the complete codec table ACKs.
module phono_audio_top_xc7 (
    input  logic clk_100mhz,
    input  logic cpu_resetn,
    input  logic force_mute_switch,

    output logic codec_mclk,
    output logic codec_bclk,
    output logic codec_lrclk,
    input  logic codec_adc_serial_data,
    output logic codec_dac_serial_data,
    inout  wire  codec_i2c_scl,
    inout  wire  codec_i2c_sda,

    input  logic spi_cs_n,
    input  logic spi_sclk,
    input  logic spi_mosi,
    output logic spi_miso,

    output logic led_clocks_locked,
    output logic led_codec_configured,
    output logic led_codec_error,
    output logic led_output_muted
);

    logic board_reset;
    logic fabric_clk;
    logic clocks_locked;
    logic fabric_rst_n;
    logic i2s_rst_n;
    logic audio_rst_n;
    logic codec_scl_drive_low;
    logic codec_sda_drive_low;
    logic codec_init_busy;
    logic codec_configured;
    logic codec_init_error;
    logic [4:0] codec_sequence_index;
    logic [4:0] codec_failed_index;
    logic digital_adc_lrclk;
    logic digital_adc_serial_data;
    logic digital_dac_lrclk;
    logic digital_dac_serial_data;
    logic codec_ready_bclk;
    logic output_muted;
    logic output_ramping;
    logic audio_clock_rate_locked;
    logic audio_clock_rate_error_sticky;
    logic rate_fault_mute_active;
    logic spi_frame_error_sticky;
    logic spi_response_underflow_sticky;
    logic [31:0] spi_completed_frame_count;
    logic control_bus_error_sticky;
    logic calibration_rejected_sticky;
    logic snapshot_capture_timeout_sticky;

    always_comb begin
        board_reset = !cpu_resetn;
        audio_rst_n = fabric_rst_n && codec_configured;
        led_clocks_locked = clocks_locked;
        led_codec_configured = codec_configured;
        led_codec_error = codec_init_error;
        led_output_muted = output_muted || !codec_ready_bclk;
    end

    assign codec_i2c_scl = codec_scl_drive_low ? 1'b0 : 1'bz;
    assign codec_i2c_sda = codec_sda_drive_low ? 1'b0 : 1'bz;

    audio_clock_synth_xc7 clock_synth (
        .clk_100mhz,
        .reset(board_reset),
        .codec_mclk_12m288(codec_mclk),
        .fabric_clk_49m152(fabric_clk),
        .locked(clocks_locked)
    );

    audio_serial_clock_master_xc7 serial_clocks (
        .fabric_clk_49m152(fabric_clk),
        .async_reset(board_reset || !clocks_locked),
        .codec_bclk_3m072(codec_bclk),
        .fabric_rst_n,
        .i2s_rst_n
    );

    adau1761_codec_init codec_initializer (
        .clk(fabric_clk),
        .rst_n(fabric_rst_n),
        .scl_in(codec_i2c_scl),
        .sda_in(codec_i2c_sda),
        .scl_drive_low(codec_scl_drive_low),
        .sda_drive_low(codec_sda_drive_low),
        .busy(codec_init_busy),
        .configured(codec_configured),
        .error(codec_init_error),
        .sequence_index(codec_sequence_index),
        .failed_index(codec_failed_index)
    );

    codec_shared_i2s_guard shared_serial_guard (
        .bclk(codec_bclk),
        .rst_n(i2s_rst_n),
        .codec_configured,
        .digital_dac_lrclk,
        .digital_dac_serial_data,
        .digital_adc_lrclk,
        .digital_adc_serial_data,
        .codec_lrclk,
        .codec_dac_serial_data,
        .codec_adc_serial_data,
        .codec_ready_bclk
    );

    phono_i2s_spi_top #(
        .MODEL_SAMPLE_RATE_HZ(384000),
        .FABRIC_CLOCKS_PER_48K_INPUT(1024),
        .CLOCK_MONITOR_WINDOW_FABRIC_CLOCKS(16384)
    ) audio_and_control (
        .i2s_bclk(codec_bclk),
        .i2s_rst_n,
        .i2s_adc_lrclk(digital_adc_lrclk),
        .i2s_adc_serial_data(digital_adc_serial_data),
        .i2s_dac_lrclk(digital_dac_lrclk),
        .i2s_dac_serial_data(digital_dac_serial_data),
        .fabric_clk,
        .fabric_rst_n,
        .audio_rst_n,
        .force_mute(force_mute_switch || !codec_configured),
        .spi_cs_n,
        .spi_sclk,
        .spi_mosi,
        .spi_miso,
        .output_muted,
        .output_ramping,
        .audio_clock_rate_locked,
        .audio_clock_rate_error_sticky,
        .rate_fault_mute_active,
        .spi_frame_error_sticky,
        .spi_response_underflow_sticky,
        .spi_completed_frame_count,
        .control_bus_error_sticky,
        .calibration_rejected_sticky,
        .snapshot_capture_timeout_sticky
    );

endmodule

`default_nettype wire
