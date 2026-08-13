`timescale 1ns/1ps
`default_nettype none

// Complete wide reference stream with an explicitly non-reference output guard
// and state-change sequencer. The core remains independently usable/verified.
module phono_stream_mono_wide_guarded #(
    parameter int unsigned WARMUP_SAMPLES = 64,
    parameter int unsigned RAMP_SAMPLES = 2048
) (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 ce_input_48k,
    input  logic signed [31:0]   sample_input_q24,
    input  logic                 model_change_request,
    input  logic                 mute_request,
    input  logic                 force_mute,
    output logic signed [31:0]   sample_output_q24,
    output logic                 output_valid,
    output logic                 model_change_ack,
    output logic                 change_busy,
    output logic                 output_ready,
    output logic                 core_reset_active,
    output logic [15:0]          output_gain_q16,
    output logic                 output_muted,
    output logic                 output_ramping,
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

    logic core_rst_n;
    logic core_ce_input_48k;
    logic signed [31:0] core_sample_q24;
    logic core_sample_valid;

    phono_stream_mono_wide reference_core (
        .clk,
        .rst_n(core_rst_n),
        .ce_input_48k(core_ce_input_48k),
        .sample_input_q24,
        .sample_output_q24(core_sample_q24),
        .output_valid(core_sample_valid),
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

    model_change_guard #(
        .INPUT_PERIOD_CLOCKS(2048),
        .WARMUP_SAMPLES(WARMUP_SAMPLES),
        .RAMP_SAMPLES(RAMP_SAMPLES)
    ) safety_control (
        .clk,
        .rst_n,
        .ce_input_48k,
        .core_sample_q24,
        .core_sample_valid,
        .model_change_request,
        .mute_request,
        .force_mute,
        .core_rst_n,
        .core_ce_input_48k,
        .sample_output_q24,
        .output_valid,
        .model_change_ack,
        .change_busy,
        .output_ready,
        .core_reset_active,
        .output_gain_q16,
        .output_muted,
        .output_ramping
    );

endmodule

`default_nettype wire
