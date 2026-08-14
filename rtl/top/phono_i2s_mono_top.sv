`timescale 1ns/1ps
`default_nettype none

// Pin-facing digital integration of the asynchronous I2S bridge and the
// accuracy-first fabric mono adapter. This block accepts measured converter
// scaling coefficients, but defines no clock-master, board-I/O, or physical
// analog-safety policy.
module phono_i2s_mono_top #(
    parameter int unsigned OUTPUT_RAMP_SAMPLES = 2048
) (
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
    input  logic                 calibration_update_valid,
    output logic                 calibration_update_ack,
    output logic                 calibration_invalid_update_sticky,
    output logic                 calibration_unsafe_update_sticky,
    output logic signed [31:0]   active_input_full_scale_peak_volts_q24,
    output logic signed [31:0]   active_output_reciprocal_full_scale_q24,
    input  logic                 mute_request,
    input  logic                 force_mute,
    output logic [15:0]          output_gain_q16,
    output logic                 output_muted,
    output logic                 output_ramping,

    output logic                 rx_frame_error_sticky,
    output logic                 rx_fifo_overflow_sticky,
    output logic                 rx_fifo_underflow_sticky,
    output logic                 tx_fifo_overflow_sticky,
    output logic                 tx_fifo_underflow_sticky,
    output logic                 tx_serial_underflow_sticky,
    output logic [3:0]           rx_fifo_i2s_level,
    output logic [3:0]           rx_fifo_i2s_high_water,
    output logic [3:0]           rx_fifo_fabric_level,
    output logic [3:0]           rx_fifo_fabric_high_water,
    output logic [3:0]           tx_fifo_fabric_level,
    output logic [3:0]           tx_fifo_fabric_high_water,
    output logic [3:0]           tx_fifo_i2s_level,
    output logic [3:0]           tx_fifo_i2s_high_water,

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

    calibration_commit_guard calibration_control (
        .clk(fabric_clk),
        .rst_n(fabric_rst_n),
        .candidate_input_peak_q24(input_full_scale_peak_volts_q24),
        .candidate_output_reciprocal_q24(
            output_reciprocal_full_scale_q24
        ),
        .update_valid(calibration_update_valid),
        .output_muted,
        .clear_diagnostics(fabric_clear_diagnostics),
        .active_input_peak_q24(
            active_input_full_scale_peak_volts_q24
        ),
        .active_output_reciprocal_q24(
            active_output_reciprocal_full_scale_q24
        ),
        .update_ack(calibration_update_ack),
        .invalid_update_sticky(calibration_invalid_update_sticky),
        .unsafe_update_sticky(calibration_unsafe_update_sticky)
    );

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
        .tx_serial_underflow_sticky,
        .rx_fifo_i2s_level,
        .rx_fifo_i2s_high_water,
        .rx_fifo_fabric_level,
        .rx_fifo_fabric_high_water,
        .tx_fifo_fabric_level,
        .tx_fifo_fabric_high_water,
        .tx_fifo_i2s_level,
        .tx_fifo_i2s_high_water
    );

    phono_fabric_mono_adapter #(
        .OUTPUT_RAMP_SAMPLES(OUTPUT_RAMP_SAMPLES)
    ) adapter (
        .clk(fabric_clk),
        .rst_n(audio_rst_n),
        .rx_frame_data(fabric_rx_frame_data),
        .rx_frame_valid(fabric_rx_frame_valid),
        .rx_frame_ready(fabric_rx_frame_ready),
        .tx_frame_data(fabric_tx_frame_data),
        .tx_frame_valid(fabric_tx_frame_valid),
        .tx_frame_ready(fabric_tx_frame_ready),
        .input_full_scale_peak_volts_q24(
            active_input_full_scale_peak_volts_q24
        ),
        .output_reciprocal_full_scale_q24(
            active_output_reciprocal_full_scale_q24
        ),
        .clear_diagnostics(fabric_clear_diagnostics),
        .mute_request,
        .force_mute,
        .output_gain_q16,
        .output_muted,
        .output_ramping,
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
