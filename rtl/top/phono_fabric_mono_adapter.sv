`timescale 1ns/1ps
`default_nettype none

// Fabric-domain bring-up adapter for the accuracy-first V1 mono phono model.
//
// The input and output use the bridge's stereo frame convention: left is
// [63:32], right is [31:0], and each slot contains sign-extended PCM24. Only
// the left input is modeled. The mono result is intentionally duplicated into
// both output slots; this is not a stereo reference implementation.
//
// Calibration coefficients are physical boundary data and must remain stable
// while unmuted. This block detects invalid coefficients but does not provide
// the future atomic control-plane update or startup mute sequence.
module phono_fabric_mono_adapter (
    input  logic                 clk,
    input  logic                 rst_n,

    input  logic [63:0]          rx_frame_data,
    input  logic                 rx_frame_valid,
    output logic                 rx_frame_ready,

    output logic [63:0]          tx_frame_data,
    output logic                 tx_frame_valid,
    input  logic                 tx_frame_ready,

    input  logic signed [31:0]   input_full_scale_peak_volts_q24,
    input  logic signed [31:0]   output_reciprocal_full_scale_q24,
    input  logic                 clear_diagnostics,

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

    // The right slot and the left sign-extension byte are intentionally
    // discarded by this explicitly mono PCM24 boundary.
    /* verilator lint_off UNUSEDSIGNAL */
    logic [63:0] scheduled_frame_data;
    /* verilator lint_on UNUSEDSIGNAL */
    logic scheduled_frame_valid;
    audio_frame_scheduler scheduler (
        .clk,
        .rst_n,
        .frame_input_data(rx_frame_data),
        .frame_input_valid(rx_frame_valid),
        .frame_input_ready(rx_frame_ready),
        .frame_output_data(scheduled_frame_data),
        .frame_output_valid(scheduled_frame_valid),
        .frame_was_present(scheduled_frame_present),
        .clear_diagnostics,
        .underflow_count(scheduler_underflow_count),
        .phase_counter(scheduler_phase_counter)
    );

    logic signed [31:0] calibrated_input_q24;
    logic calibrated_input_valid;
    pcm24_to_q8_24 input_calibration (
        .clk,
        .rst_n,
        .input_valid(scheduled_frame_valid),
        .sample_input_pcm24($signed(scheduled_frame_data[55:32])),
        .full_scale_peak_volts_q24(input_full_scale_peak_volts_q24),
        .clear_diagnostics,
        .sample_output_q24(calibrated_input_q24),
        .output_valid(calibrated_input_valid),
        .pcm_endpoint_count(input_pcm_endpoint_count),
        .configuration_error_sticky(input_configuration_error_sticky)
    );

    // Keep the stream core in reset during the scheduler's initial phase
    // acquisition. Its interpolator emits scheduled internal zeros even
    // before the first external ce_input; allowing those hidden samples would
    // advance the physical capacitor state before the first accepted frame.
    // The first scheduler launch registers calibration while the core remains
    // reset, then releases it for that calibrated sample at core phase zero.
    logic model_started;
    logic model_rst_n;
    always_ff @(posedge clk) begin
        if (!rst_n)
            model_started <= 1'b0;
        else if (scheduled_frame_valid)
            model_started <= 1'b1;
    end
    always_comb model_rst_n = rst_n && model_started;

    logic signed [31:0] model_output_q24;
    logic model_output_valid;
    phono_stream_mono_wide_trapezoidal_banked_terminal model (
        .clk,
        .rst_n(model_rst_n),
        .ce_input_48k(calibrated_input_valid),
        .sample_input_q24(calibrated_input_q24),
        .sample_output_q24(model_output_q24),
        .output_valid(model_output_valid),
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

    logic signed [23:0] calibrated_output_pcm24;
    logic calibrated_output_valid;
    q8_24_to_pcm24 output_calibration (
        .clk,
        .rst_n,
        .input_valid(model_output_valid),
        .sample_input_q24(model_output_q24),
        .reciprocal_full_scale_per_volt_q24(
            output_reciprocal_full_scale_q24
        ),
        .clear_diagnostics,
        .sample_output_pcm24(calibrated_output_pcm24),
        .output_valid(calibrated_output_valid),
        .saturation_count(output_pcm_saturation_count),
        .configuration_error_sticky(output_configuration_error_sticky)
    );

    logic [31:0] duplicated_pcm_slot;
    always_comb begin
        duplicated_pcm_slot = {
            {8{calibrated_output_pcm24[23]}}, calibrated_output_pcm24
        };
    end

    // One held frame decouples the registered converter boundary from a
    // downstream ready pulse. A newly completed model sample is never allowed
    // to overwrite a stalled older sample silently.
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            tx_frame_data <= '0;
            tx_frame_valid <= 1'b0;
            output_frame_overrun_count <= '0;
        end else begin
            if (clear_diagnostics)
                output_frame_overrun_count <= '0;

            if (calibrated_output_valid) begin
                if (!tx_frame_valid || tx_frame_ready) begin
                    tx_frame_data <= {
                        duplicated_pcm_slot, duplicated_pcm_slot
                    };
                    tx_frame_valid <= 1'b1;
                end else if (!clear_diagnostics
                             && output_frame_overrun_count != 32'hffffffff) begin
                    output_frame_overrun_count <=
                        output_frame_overrun_count + 1'b1;
                end
            end else if (tx_frame_valid && tx_frame_ready) begin
                tx_frame_valid <= 1'b0;
            end
        end
    end

endmodule

`default_nettype wire
