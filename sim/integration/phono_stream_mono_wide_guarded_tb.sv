`timescale 1ns/1ps
`default_nettype none

module phono_stream_mono_wide_guarded_tb;
    logic clk;
    logic rst_n = 1'b0;
    logic ce_input_48k = 1'b0;
    logic signed [31:0] sample_input_q24 = '0;
    logic model_change_request = 1'b0;
    logic mute_request = 1'b0;
    logic force_mute = 1'b0;
    logic signed [31:0] sample_output_q24;
    logic output_valid;
    logic model_change_ack;
    logic change_busy;
    logic output_ready;
    logic core_reset_active;
    logic [15:0] output_gain_q16;
    logic output_muted;
    logic output_ramping;
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

    phono_stream_mono_wide_guarded #(
        .WARMUP_SAMPLES(4),
        .RAMP_SAMPLES(4)
    ) dut (.*);
    always #5 clk = ~clk;

    integer errors = 0;
    integer clock_count = 0;
    integer input_index = 0;
    integer acknowledge_count = 0;
    logic change_issued = 1'b0;
    logic reset_seen_after_request = 1'b0;
    logic acknowledge_seen = 1'b0;
    logic completed = 1'b0;

    function automatic logic signed [31:0] tone_sample(input integer index);
        begin
            case (index & 7)
                0: tone_sample = 32'sd0;
                1: tone_sample = 32'sd59316;
                2: tone_sample = 32'sd83886;
                3: tone_sample = 32'sd59316;
                4: tone_sample = 32'sd0;
                5: tone_sample = -32'sd59316;
                6: tone_sample = -32'sd83886;
                default: tone_sample = -32'sd59316;
            endcase
        end
    endfunction

    initial begin
        clk = 1'b0;
        repeat (3) @(posedge clk);
        @(negedge clk);
        rst_n = 1'b1;
        sample_input_q24 = tone_sample(input_index);
        ce_input_48k = 1'b1;

        while (!completed) begin
            @(posedge clk);
            #1;
            ce_input_48k = 1'b0;
            clock_count = clock_count + 1;

            if (core_reset_active && !output_muted) begin
                $error("core reset escaped before output mute completed");
                errors = errors + 1;
            end
            if (change_issued && core_reset_active)
                reset_seen_after_request = 1'b1;
            if (reset_seen_after_request && !acknowledge_seen
                && output_valid && sample_output_q24 != 0) begin
                $error("nonzero held output escaped during model reset/warmup");
                errors = errors + 1;
            end
            if (model_change_ack) begin
                acknowledge_count = acknowledge_count + 1;
                if (!reset_seen_after_request || !output_muted
                    || output_gain_q16 != 0) begin
                    $error("model change acknowledged before safe warmup completion");
                    errors = errors + 1;
                end
                acknowledge_seen = 1'b1;
                model_change_request = 1'b0;
            end
            if (output_ready && !change_issued) begin
                if (output_gain_q16 != 16'hffff || output_ramping
                    || output_muted || change_busy) begin
                    $error("startup ready asserted before unity output");
                    errors = errors + 1;
                end
                change_issued = 1'b1;
                model_change_request = 1'b1;
            end else if (output_ready && acknowledge_seen) begin
                completed = 1'b1;
            end

            if ((clock_count % 2048) == 0) begin
                input_index = input_index + 1;
                sample_input_q24 = tone_sample(input_index);
                ce_input_48k = 1'b1;
            end
            if (clock_count > 200000)
                $fatal(1, "guarded stream timeout");
        end

        if (acknowledge_count != 1) begin
            $error("acknowledge count got=%0d expected=1", acknowledge_count);
            errors = errors + 1;
        end
        if (resampler_saturation_count != 0 || resampler_overrun_count != 0
            || input_phase_error_count != 0
            || output_conversion_saturation_count != 0
            || solver_missed_request_count != 0
            || solver_deadline_miss_count != 0
            || solver_saturation_count != 0 || solver_lut_clip_count != 0
            || solver_nonconvergence_count != 0
            || solver_correction_scale_fallback_count != 0
            || solver_minimum_correction_fractional_bits != 0
            || solver_latency_cycles != 8'd116
            || solver_last_residual_q44 > 63'd35184372) begin
            $error("guarded stream diagnostics are nonzero or invalid");
            errors = errors + 1;
        end
        if (errors != 0)
            $fatal(1, "FAIL: %0d guarded stream errors", errors);
        $display("PASS: ramp-down, aligned reset, warmup, ack, and ramp-up");
        $finish;
    end

endmodule

`default_nettype wire
