`timescale 1ns/1ps
`default_nettype none

// Minimal physical-I/O wrapper for named-part timing of the complete 8x
// candidate stream. This is not a board top or a bitstream-ready clock design.
module stream_384khz_pnr_harness #(
    parameter int FABRIC_CLOCKS_PER_48K_INPUT = 2048,
    parameter bit PIPELINED_SOLVER_PROFILE = 1'b0,
    parameter bit PREFETCH_TUBE_INPUTS = 1'b0,
    parameter bit DECOUPLED_KCL_MAXIMUM_ONLY = 1'b0
) (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    logic rst_n;
    localparam int INPUT_PHASE_WIDTH =
        $clog2(FABRIC_CLOCKS_PER_48K_INPUT);

    logic [INPUT_PHASE_WIDTH-1:0] input_phase;
    logic signed [31:0] stimulus_lfsr;
    logic ce_input_48k;

    (* keep *) logic signed [31:0] sample_output_q24;
    (* keep *) logic output_valid;
    (* keep *) logic [31:0] resampler_saturation_count;
    (* keep *) logic [31:0] resampler_overrun_count;
    (* keep *) logic [31:0] input_phase_error_count;
    (* keep *) logic [31:0] output_conversion_saturation_count;
    (* keep *) logic [31:0] solver_missed_request_count;
    (* keep *) logic [31:0] solver_deadline_miss_count;
    (* keep *) logic [31:0] solver_saturation_count;
    (* keep *) logic [31:0] solver_lut_clip_count;
    (* keep *) logic [31:0] solver_nonconvergence_count;
    (* keep *) logic [31:0] solver_correction_scale_fallback_count;
    (* keep *) logic [5:0] solver_minimum_correction_fractional_bits;
    (* keep *) logic [62:0] solver_last_residual_q44;
    (* keep *) logic [7:0] solver_latency_cycles;

    assign rst_n = !reset;
    assign ce_input_48k = input_phase == '0;

    always_ff @(posedge fabric_clk) begin
        if (!rst_n) begin
            input_phase <= '0;
            stimulus_lfsr <= 32'h1ace_b00c;
            activity <= 1'b0;
        end else begin
            input_phase <= input_phase + 1'b1;
            if (ce_input_48k) begin
                stimulus_lfsr <= {
                    stimulus_lfsr[30:0],
                    stimulus_lfsr[31] ^ stimulus_lfsr[21]
                    ^ stimulus_lfsr[1] ^ stimulus_lfsr[0]
                };
            end
            if (output_valid) begin
                // Retain an observable registered signature without making
                // hundreds of diagnostic bits into package I/O.
                activity <= activity
                            ^ sample_output_q24[0]
                            ^ resampler_saturation_count[0]
                            ^ resampler_overrun_count[0]
                            ^ input_phase_error_count[0]
                            ^ output_conversion_saturation_count[0]
                            ^ solver_missed_request_count[0]
                            ^ solver_deadline_miss_count[0]
                            ^ solver_saturation_count[0]
                            ^ solver_lut_clip_count[0]
                            ^ solver_nonconvergence_count[0]
                            ^ solver_correction_scale_fallback_count[0]
                            ^ solver_minimum_correction_fractional_bits[0]
                            ^ solver_last_residual_q44[0]
                            ^ solver_latency_cycles[0];
            end
        end
    end

    (* keep *) phono_stream_mono_wide_trapezoidal_384khz_banked_terminal #(
        .FABRIC_CLOCKS_PER_48K_INPUT(FABRIC_CLOCKS_PER_48K_INPUT),
        .PIPELINED_SOLVER_PROFILE(PIPELINED_SOLVER_PROFILE),
        .PREFETCH_TUBE_INPUTS(PREFETCH_TUBE_INPUTS),
        .DECOUPLED_KCL_MAXIMUM_ONLY(DECOUPLED_KCL_MAXIMUM_ONLY)
    ) stream (
            .clk(fabric_clk),
            .rst_n,
            .ce_input_48k,
            .sample_input_q24(stimulus_lfsr),
            .sample_output_q24,
            .output_valid,
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

// Explicit half-frequency timing target. The circuit sample rate and all
// arithmetic remain identical; only the fabric enable schedule changes.
module stream_384khz_49mhz_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);
    stream_384khz_pnr_harness #(
        .FABRIC_CLOCKS_PER_48K_INPUT(1024)
    ) candidate (.*);
endmodule

// Separately named, scheduling-only candidate. It uses the previously verified
// 123-clock parallel/decoupled pipeline and leaves five clocks per 384 kHz
// update at 49.152 MHz. It is not the default circuit stream.
module stream_384khz_49mhz_pipelined_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);
    stream_384khz_pnr_harness #(
        .FABRIC_CLOCKS_PER_48K_INPUT(1024),
        .PIPELINED_SOLVER_PROFILE(1'b1)
    ) candidate (.*);
endmodule

// Route-informed candidate: preserve the selected serial 127-clock solver but
// capture exact triode pin values one cycle before each residual launch.
module stream_384khz_49mhz_prefetched_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);
    stream_384khz_pnr_harness #(
        .FABRIC_CLOCKS_PER_48K_INPUT(1024),
        .PREFETCH_TUBE_INPUTS(1'b1)
    ) candidate (.*);
endmodule

// Combine route-informed tube-pin prefetch with a final-only KCL maximum
// sideband. Both changes preserve the selected 127-clock correction schedule.
module stream_384khz_49mhz_retimed_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);
    stream_384khz_pnr_harness #(
        .FABRIC_CLOCKS_PER_48K_INPUT(1024),
        .PREFETCH_TUBE_INPUTS(1'b1),
        .DECOUPLED_KCL_MAXIMUM_ONLY(1'b1)
    ) candidate (.*);
endmodule

`default_nettype wire
