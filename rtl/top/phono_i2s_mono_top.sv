`timescale 1ns/1ps
`default_nettype none

// Pin-facing digital integration of the asynchronous I2S bridge and the
// accuracy-first fabric mono adapter. This block defines no converter voltage,
// clock-master, board-I/O, mute, or analog-safety policy.
module phono_i2s_mono_top (
    input  logic                 i2s_bclk,
    input  logic                 i2s_rst_n,
    input  logic                 i2s_adc_lrclk,
    input  logic                 i2s_adc_serial_data,
    output logic                 i2s_dac_lrclk,
    output logic                 i2s_dac_serial_data,
    input  logic                 i2s_clear_diagnostics,

    input  logic                 fabric_clk,
    input  logic                 fabric_rst_n,
    // Synchronous to fabric_clk. It may be held low while the bridge fills so
    // the model starts only after an input frame is available.
    input  logic                 audio_rst_n,
    input  logic                 fabric_clear_diagnostics,
    input  logic signed [31:0]   input_full_scale_peak_volts_q24,
    input  logic signed [31:0]   output_reciprocal_full_scale_q24,

    output logic                 rx_frame_error_sticky,
    output logic                 rx_fifo_overflow_sticky,
    output logic                 rx_fifo_underflow_sticky,
    output logic                 tx_fifo_overflow_sticky,
    output logic                 tx_fifo_underflow_sticky,
    output logic                 tx_serial_underflow_sticky,

    output logic                 scheduled_frame_present,
    output logic [10:0]          scheduler_phase_counter,
    output logic [31:0]          scheduler_underflow_count,
    output logic [31:0]          input_pcm_endpoint_count,
    output logic                 input_configuration_error_sticky,
    output logic [31:0]          output_pcm_saturation_count,
    output logic                 output_configuration_error_sticky,
    output logic [31:0]          output_frame_overrun_count,
    output logic [31:0]          resampler_saturation_count,
    output logic [31:0]          resampler_overrun_count,
    output logic [31:0]          input_phase_error_count,
    output logic [31:0]          output_conversion_saturation_count,
    output logic [31:0]          solver_missed_request_count,
    output logic [31:0]          solver_deadline_miss_count,
    output logic [31:0]          solver_saturation_count,
    output logic [31:0]          solver_lut_clip_count,
    output logic [31:0]          solver_nonconvergence_count,
    output logic [31:0]          solver_correction_scale_fallback_count,
    output logic [5:0]           solver_minimum_correction_fractional_bits,
    output logic [62:0]          solver_last_residual_q44,
    output logic [7:0]           solver_latency_cycles
);

    logic [63:0] fabric_rx_frame_data;
    logic fabric_rx_frame_valid;
    logic fabric_rx_frame_ready;
    logic [63:0] fabric_tx_frame_data;
    logic fabric_tx_frame_valid;
    logic fabric_tx_frame_ready;

    i2s_async_bridge bridge (
        .i2s_bclk,
        .i2s_rst_n,
        .i2s_adc_lrclk,
        .i2s_adc_serial_data,
        .i2s_dac_lrclk,
        .i2s_dac_serial_data,
        .i2s_clear_diagnostics,
        .fabric_clk,
        .fabric_rst_n,
        .fabric_rx_frame_data,
        .fabric_rx_frame_valid,
        .fabric_rx_frame_ready,
        .fabric_tx_frame_data,
        .fabric_tx_frame_valid,
        .fabric_tx_frame_ready,
        .fabric_clear_diagnostics,
        .rx_frame_error_sticky,
        .rx_fifo_overflow_sticky,
        .rx_fifo_underflow_sticky,
        .tx_fifo_overflow_sticky,
        .tx_fifo_underflow_sticky,
        .tx_serial_underflow_sticky
    );

    phono_fabric_mono_adapter adapter (
        .clk(fabric_clk),
        .rst_n(audio_rst_n),
        .rx_frame_data(fabric_rx_frame_data),
        .rx_frame_valid(fabric_rx_frame_valid),
        .rx_frame_ready(fabric_rx_frame_ready),
        .tx_frame_data(fabric_tx_frame_data),
        .tx_frame_valid(fabric_tx_frame_valid),
        .tx_frame_ready(fabric_tx_frame_ready),
        .input_full_scale_peak_volts_q24,
        .output_reciprocal_full_scale_q24,
        .clear_diagnostics(fabric_clear_diagnostics),
        .scheduled_frame_present,
        .scheduler_phase_counter,
        .scheduler_underflow_count,
        .input_pcm_endpoint_count,
        .input_configuration_error_sticky,
        .output_pcm_saturation_count,
        .output_configuration_error_sticky,
        .output_frame_overrun_count,
        .resampler_saturation_count,
        .resampler_overrun_count,
        .input_phase_error_count,
        .output_conversion_saturation_count,
        .solver_missed_request_count,
        .solver_deadline_miss_count,
        .solver_saturation_count,
        .solver_lut_clip_count,
        .solver_nonconvergence_count,
        .solver_correction_scale_fallback_count,
        .solver_minimum_correction_fractional_bits,
        .solver_last_residual_q44,
        .solver_latency_cycles
    );

endmodule

`default_nettype wire
