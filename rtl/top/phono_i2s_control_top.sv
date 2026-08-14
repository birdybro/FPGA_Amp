`timescale 1ns/1ps
`default_nettype none

// Pin-facing mono V1 hierarchy with a concrete fabric register boundary. The
// register request bus is synchronous to fabric_clk; a later SPI/UART/CPU
// transport can drive it without entering the audio solver.
module phono_i2s_control_top #(
    parameter int unsigned OUTPUT_RAMP_SAMPLES = 2048
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

    input  logic                 control_request_valid,
    input  logic                 control_request_write,
    input  logic [7:0]           control_request_address,
    input  logic [31:0]          control_request_write_data,
    output logic                 control_response_valid,
    output logic [31:0]          control_response_read_data,
    output logic                 control_response_error,

    output logic                 output_muted,
    output logic                 output_ramping,
    output logic                 audio_clock_rate_locked,
    output logic                 audio_clock_rate_error_sticky,
    output logic [31:0]          control_snapshot_sequence,
    output logic [31:0]          calibration_commit_sequence,
    output logic [31:0]          calibration_accepted_sequence,
    output logic                 control_bus_error_sticky,
    output logic                 calibration_rejected_sticky
);

    localparam int unsigned DIAGNOSTIC_WORD_COUNT = 20;

    logic i2s_clear_diagnostics;
    logic fabric_clear_diagnostics;
    logic mute_request;
    logic signed [31:0] calibration_candidate_input_peak_q24;
    logic signed [31:0] calibration_candidate_output_reciprocal_q24;
    logic calibration_update_valid;
    logic calibration_update_ack;
    logic calibration_invalid_update_sticky;
    logic calibration_unsafe_update_sticky;
    logic signed [31:0] calibration_active_input_peak_q24;
    logic signed [31:0] calibration_active_output_reciprocal_q24;
    logic [DIAGNOSTIC_WORD_COUNT*32-1:0] diagnostic_words_flat;

    logic [15:0] output_gain_q16;
    logic rx_frame_error_sticky;
    logic rx_fifo_overflow_sticky;
    logic rx_fifo_underflow_sticky;
    logic tx_fifo_overflow_sticky;
    logic tx_fifo_underflow_sticky;
    logic tx_serial_underflow_sticky;
    // Raw I2S-domain multibit levels are deliberately not sampled by the
    // fabric register bank. Keep the connections visible so that omission
    // cannot be mistaken for a forgotten top-level port.
    /* verilator lint_off UNUSEDSIGNAL */
    logic [3:0] rx_fifo_i2s_level;
    logic [3:0] rx_fifo_i2s_high_water;
    logic [3:0] tx_fifo_i2s_level;
    logic [3:0] tx_fifo_i2s_high_water;
    /* verilator lint_on UNUSEDSIGNAL */
    logic [3:0] rx_fifo_fabric_level;
    logic [3:0] rx_fifo_fabric_high_water;
    logic [3:0] tx_fifo_fabric_level;
    logic [3:0] tx_fifo_fabric_high_water;
    logic audio_clock_measurement_valid;
    logic [15:0] audio_clock_measured_bclk_edges;
    logic [7:0] audio_clock_good_windows;
    logic scheduled_frame_present;
    logic [10:0] scheduler_phase_counter;
    logic [31:0] scheduler_underflow_count;
    logic [31:0] input_pcm_endpoint_count;
    logic input_configuration_error_sticky;
    logic [31:0] output_pcm_saturation_count;
    logic output_configuration_error_sticky;
    logic [31:0] output_frame_overrun_count;
    logic [31:0] resampler_saturation_count;
    logic [31:0] resampler_overrun_count;
    logic [31:0] input_phase_error_count;
    logic [31:0] output_conversion_saturation_count;
    logic [31:0] solver_missed_request_count;
    logic [31:0] solver_deadline_miss_count;
    logic [31:0] solver_saturation_count;
    logic [31:0] solver_lut_clip_count;
    logic [31:0] solver_nonconvergence_count;
    logic [31:0] solver_correction_scale_fallback_count;
    logic [5:0] solver_minimum_correction_fractional_bits;
    logic [62:0] solver_last_residual_q44;
    logic [7:0] solver_latency_cycles;

    logic [3:0] i2s_sticky_async;
    (* ASYNC_REG = "TRUE" *) logic [3:0] i2s_sticky_meta;
    (* ASYNC_REG = "TRUE" *) logic [3:0] i2s_sticky_sync;

    assign i2s_sticky_async = {
        tx_serial_underflow_sticky,
        tx_fifo_underflow_sticky,
        rx_fifo_overflow_sticky,
        rx_frame_error_sticky
    };

    always_ff @(posedge fabric_clk or negedge fabric_rst_n) begin
        if (!fabric_rst_n) begin
            i2s_sticky_meta <= '0;
            i2s_sticky_sync <= '0;
        end else begin
            i2s_sticky_meta <= i2s_sticky_async;
            i2s_sticky_sync <= i2s_sticky_meta;
        end
    end

    cdc_toggle_pulse clear_to_i2s (
        .source_clk(fabric_clk),
        .source_rst_n(fabric_rst_n),
        .source_pulse(fabric_clear_diagnostics),
        .destination_clk(i2s_bclk),
        .destination_rst_n(i2s_rst_n),
        .destination_pulse(i2s_clear_diagnostics)
    );

    always_comb begin
        diagnostic_words_flat = '0;
        diagnostic_words_flat[0*32 + 0] = audio_clock_rate_locked;
        diagnostic_words_flat[0*32 + 1] =
            audio_clock_rate_error_sticky;
        diagnostic_words_flat[0*32 + 2] = scheduled_frame_present;
        diagnostic_words_flat[0*32 + 3] = output_muted;
        diagnostic_words_flat[0*32 + 4] = output_ramping;
        diagnostic_words_flat[0*32 + 5] =
            calibration_invalid_update_sticky;
        diagnostic_words_flat[0*32 + 6] =
            calibration_unsafe_update_sticky;
        diagnostic_words_flat[0*32 + 7] =
            input_configuration_error_sticky;
        diagnostic_words_flat[0*32 + 8] =
            output_configuration_error_sticky;
        diagnostic_words_flat[0*32 + 12 +: 4] = i2s_sticky_sync;
        diagnostic_words_flat[0*32 + 16] = rx_fifo_underflow_sticky;
        diagnostic_words_flat[0*32 + 17] = tx_fifo_overflow_sticky;
        diagnostic_words_flat[0*32 + 18] = force_mute;

        diagnostic_words_flat[1*32 + 0] =
            audio_clock_measurement_valid;
        diagnostic_words_flat[1*32 + 1] = audio_clock_rate_locked;
        diagnostic_words_flat[1*32 + 2] =
            audio_clock_rate_error_sticky;
        diagnostic_words_flat[1*32 + 8 +: 8] = audio_clock_good_windows;
        diagnostic_words_flat[1*32 + 16 +: 16] =
            audio_clock_measured_bclk_edges;

        diagnostic_words_flat[2*32 + 0 +: 4] =
            rx_fifo_fabric_level;
        diagnostic_words_flat[2*32 + 4 +: 4] =
            rx_fifo_fabric_high_water;
        diagnostic_words_flat[2*32 + 8 +: 4] =
            tx_fifo_fabric_level;
        diagnostic_words_flat[2*32 + 12 +: 4] =
            tx_fifo_fabric_high_water;
        diagnostic_words_flat[2*32 + 16 +: 11] =
            scheduler_phase_counter;

        diagnostic_words_flat[3*32 + 0 +: 16] = output_gain_q16;
        diagnostic_words_flat[3*32 + 16 +: 8] = solver_latency_cycles;
        diagnostic_words_flat[3*32 + 24 +: 6] =
            solver_minimum_correction_fractional_bits;
        diagnostic_words_flat[3*32 + 30] = output_muted;
        diagnostic_words_flat[3*32 + 31] = output_ramping;

        diagnostic_words_flat[4*32 +: 32] = scheduler_underflow_count;
        diagnostic_words_flat[5*32 +: 32] = input_pcm_endpoint_count;
        diagnostic_words_flat[6*32 +: 32] = output_pcm_saturation_count;
        diagnostic_words_flat[7*32 +: 32] = output_frame_overrun_count;
        diagnostic_words_flat[8*32 +: 32] = resampler_saturation_count;
        diagnostic_words_flat[9*32 +: 32] = resampler_overrun_count;
        diagnostic_words_flat[10*32 +: 32] = input_phase_error_count;
        diagnostic_words_flat[11*32 +: 32] =
            output_conversion_saturation_count;
        diagnostic_words_flat[12*32 +: 32] = solver_missed_request_count;
        diagnostic_words_flat[13*32 +: 32] = solver_deadline_miss_count;
        diagnostic_words_flat[14*32 +: 32] = solver_saturation_count;
        diagnostic_words_flat[15*32 +: 32] = solver_lut_clip_count;
        diagnostic_words_flat[16*32 +: 32] = solver_nonconvergence_count;
        diagnostic_words_flat[17*32 +: 32] =
            solver_correction_scale_fallback_count;
        diagnostic_words_flat[18*32 +: 32] =
            solver_last_residual_q44[31:0];
        diagnostic_words_flat[19*32 +: 31] =
            solver_last_residual_q44[62:32];
    end

    phono_control_registers #(
        .DIAGNOSTIC_WORD_COUNT(DIAGNOSTIC_WORD_COUNT)
    ) control_registers (
        .clk(fabric_clk),
        .rst_n(fabric_rst_n),
        .request_valid(control_request_valid),
        .request_write(control_request_write),
        .request_address(control_request_address),
        .request_write_data(control_request_write_data),
        .response_valid(control_response_valid),
        .response_read_data(control_response_read_data),
        .response_error(control_response_error),
        .diagnostic_words_flat,
        .output_muted,
        .output_ramping,
        .mute_request,
        .fabric_clear_diagnostics,
        .calibration_candidate_input_peak_q24,
        .calibration_candidate_output_reciprocal_q24,
        .calibration_update_valid,
        .calibration_update_ack,
        .calibration_invalid_update_sticky,
        .calibration_unsafe_update_sticky,
        .calibration_active_input_peak_q24,
        .calibration_active_output_reciprocal_q24,
        .snapshot_sequence(control_snapshot_sequence),
        .calibration_commit_sequence,
        .calibration_accepted_sequence,
        .bus_error_sticky(control_bus_error_sticky),
        .calibration_rejected_sticky
    );

    phono_i2s_mono_top #(
        .OUTPUT_RAMP_SAMPLES(OUTPUT_RAMP_SAMPLES)
    ) digital_top (
        .i2s_bclk,
        .i2s_rst_n,
        .i2s_adc_lrclk,
        .i2s_adc_serial_data,
        .i2s_dac_lrclk,
        .i2s_dac_serial_data,
        .i2s_clear_diagnostics,
        .fabric_clk,
        .fabric_rst_n,
        .audio_rst_n,
        .fabric_clear_diagnostics,
        .input_full_scale_peak_volts_q24(
            calibration_candidate_input_peak_q24
        ),
        .output_reciprocal_full_scale_q24(
            calibration_candidate_output_reciprocal_q24
        ),
        .calibration_update_valid,
        .calibration_update_ack,
        .calibration_invalid_update_sticky,
        .calibration_unsafe_update_sticky,
        .active_input_full_scale_peak_volts_q24(
            calibration_active_input_peak_q24
        ),
        .active_output_reciprocal_full_scale_q24(
            calibration_active_output_reciprocal_q24
        ),
        .mute_request,
        .force_mute,
        .output_gain_q16,
        .output_muted,
        .output_ramping,
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
        .tx_fifo_i2s_high_water,
        .audio_clock_measurement_valid,
        .audio_clock_measured_bclk_edges,
        .audio_clock_good_windows,
        .audio_clock_rate_locked,
        .audio_clock_rate_error_sticky,
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
