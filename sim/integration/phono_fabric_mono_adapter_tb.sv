`timescale 1ns/1ps
`default_nettype none

module phono_fabric_mono_adapter_tb;
    localparam int VECTOR_COUNT = 64;
    localparam int INPUT_FULL_SCALE_PEAK_VOLTS_Q24 = 335544;
    localparam int OUTPUT_RECIPROCAL_FULL_SCALE_Q24 = 2097152;

    logic clk;
    logic rst_n = 1'b0;
    logic [63:0] rx_frame_data = '0;
    logic rx_frame_valid = 1'b0;
    logic rx_frame_ready;
    logic [63:0] tx_frame_data;
    logic tx_frame_valid;
    logic tx_frame_ready = 1'b0;
    logic clear_diagnostics = 1'b0;
    logic mute_request = 1'b0;
    logic force_mute = 1'b0;
    logic [15:0] output_gain_q16;
    logic output_muted;
    logic output_ramping;

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

    logic signed [31:0] input_full_scale_peak_volts_q24 =
        INPUT_FULL_SCALE_PEAK_VOLTS_Q24;
    logic signed [31:0] output_reciprocal_full_scale_q24 =
        OUTPUT_RECIPROCAL_FULL_SCALE_Q24;

    logic signed [23:0] left_input [0:VECTOR_COUNT-1];
    logic signed [23:0] right_input [0:VECTOR_COUNT-1];
    logic signed [31:0] expected_model_input [0:VECTOR_COUNT-1];
    logic signed [23:0] expected_output [0:VECTOR_COUNT-1];
    logic signed [31:0] expected_model_output [0:VECTOR_COUNT-1];

    integer output_index;
    integer model_input_index;
    integer model_output_index;
    integer scoreboard_error_count;
    integer held_output_error_count;
    integer error_count;
    integer input_index;
    integer file_handle;
    integer scan_count;
    integer clock_count;
    string marker;
    logic [63:0] held_overrun_frame;

    function automatic logic [63:0] stereo_frame(
        input logic signed [23:0] left,
        input logic signed [23:0] right
    );
        logic [31:0] left_slot;
        logic [31:0] right_slot;
        begin
            left_slot = {{8{left[23]}}, left};
            right_slot = {{8{right[23]}}, right};
            stereo_frame = {left_slot, right_slot};
        end
    endfunction

    function automatic logic [63:0] duplicate_frame(
        input logic signed [23:0] sample
    );
        logic [31:0] slot;
        begin
            slot = {{8{sample[23]}}, sample};
            duplicate_frame = {slot, slot};
        end
    endfunction

    phono_fabric_mono_adapter #(
        .OUTPUT_RAMP_SAMPLES(8)
    ) dut (.*);

    always #5 clk = ~clk;

    // Score only real ready/valid transfers. The sink begins stalled so the
    // separate hold check can prove stable output data before the first frame
    // is accepted.
    always @(posedge clk) begin
        if (!rst_n) begin
            output_index <= 0;
            model_input_index <= 0;
            model_output_index <= 0;
            scoreboard_error_count <= 0;
        end else begin
            if (dut.calibrated_input_valid
                && model_input_index < VECTOR_COUNT) begin
                if (dut.calibrated_input_q24
                    !== expected_model_input[model_input_index]) begin
                    $error("model input %0d got=%0d expected=%0d",
                           model_input_index, dut.calibrated_input_q24,
                           expected_model_input[model_input_index]);
                    scoreboard_error_count <= scoreboard_error_count + 1;
                end
                model_input_index <= model_input_index + 1;
            end
            if (dut.model_output_valid
                && model_output_index < VECTOR_COUNT) begin
                if (dut.model_output_q24
                    !== expected_model_output[model_output_index]) begin
                    $error("model output %0d got=%0d expected=%0d",
                           model_output_index, dut.model_output_q24,
                           expected_model_output[model_output_index]);
                    scoreboard_error_count <= scoreboard_error_count + 1;
                end
                model_output_index <= model_output_index + 1;
            end
            if (tx_frame_valid && tx_frame_ready) begin
                if (output_index >= VECTOR_COUNT
                    || tx_frame_data !== duplicate_frame(
                        expected_output[output_index]
                    )) begin
                    $error("output %0d got=%016x expected=%016x",
                           output_index, tx_frame_data,
                           (output_index < VECTOR_COUNT)
                               ? duplicate_frame(expected_output[output_index])
                               : 64'd0);
                    scoreboard_error_count <= scoreboard_error_count + 1;
                end
                output_index <= output_index + 1;
            end
        end
    end

    // Stall the first completed frame for five clocks. This is much shorter
    // than one audio period, so it must exercise holding without an overrun.
    initial begin
        logic [63:0] held_frame;
        held_output_error_count = 0;
        wait (rst_n);
        wait (tx_frame_valid);
        held_frame = tx_frame_data;
        repeat (5) begin
            @(negedge clk);
            if (!tx_frame_valid || tx_frame_data !== held_frame) begin
                $error("output frame changed while sink was stalled");
                held_output_error_count = held_output_error_count + 1;
            end
        end
        tx_frame_ready = 1'b1;
    end

    initial begin
        clk = 1'b0;
        error_count = 0;
        clock_count = 0;
        file_handle = $fopen(
            "sim/vectors/generated/phono_fabric_mono_adapter.txt", "r"
        );
        if (file_handle == 0)
            $fatal(1, "cannot open mono-adapter vectors");
        for (input_index = 0; input_index < VECTOR_COUNT; input_index++) begin
            scan_count = $fscanf(
                file_handle, "%d %d %d\n", left_input[input_index],
                right_input[input_index], expected_model_input[input_index]
            );
            if (scan_count != 3)
                $fatal(1, "malformed adapter input %0d", input_index);
        end
        scan_count = $fscanf(file_handle, "%s\n", marker);
        if (scan_count != 1 || marker != "EXPECTED")
            $fatal(1, "missing adapter expected marker");
        for (input_index = 0; input_index < VECTOR_COUNT; input_index++) begin
            scan_count = $fscanf(
                file_handle, "%d %d\n", expected_output[input_index],
                expected_model_output[input_index]
            );
            if (scan_count != 2)
                $fatal(1, "malformed adapter output %0d", input_index);
        end
        $fclose(file_handle);

        repeat (3) @(posedge clk);
        #1;
        rst_n = 1'b1;

        // Supply every source frame under the held ready/valid contract.
        for (input_index = 0; input_index < VECTOR_COUNT; input_index++) begin
            @(negedge clk);
            rx_frame_data = stereo_frame(
                left_input[input_index], right_input[input_index]
            );
            rx_frame_valid = 1'b1;
            while (!rx_frame_ready)
                @(negedge clk);
            if (!scheduled_frame_present
                || scheduler_phase_counter != 11'd2047) begin
                $error("input %0d accepted outside present launch phase",
                       input_index);
                error_count = error_count + 1;
            end
            @(posedge clk);
        end

        // Continue supplying deterministic zero padding while the final model
        // output drains. This preserves the required sample cadence without
        // introducing a scheduler-underflow event into the regression.
        @(negedge clk);
        rx_frame_data = '0;
        rx_frame_valid = 1'b1;

        while (output_index < VECTOR_COUNT) begin
            @(posedge clk);
            clock_count = clock_count + 1;
            if (clock_count > VECTOR_COUNT * 2300)
                $fatal(1, "adapter timeout output=%0d", output_index);
        end
        #1;

        if (model_input_index < VECTOR_COUNT
            || model_output_index < VECTOR_COUNT) begin
            $error("boundary scores input=%0d output=%0d expected=%0d",
                   model_input_index, model_output_index, VECTOR_COUNT);
            error_count = error_count + 1;
        end

        // Keep one later padding result stalled across the following model
        // output. The held frame must survive and the otherwise-lost new frame
        // must be made visible by the saturating overrun counter.
        @(negedge clk);
        tx_frame_ready = 1'b0;
        wait (tx_frame_valid);
        held_overrun_frame = tx_frame_data;
        wait (output_frame_overrun_count == 1);
        #1;
        if (!tx_frame_valid || tx_frame_data !== held_overrun_frame) begin
            $error("stalled frame was overwritten on output overrun");
            error_count = error_count + 1;
        end
        @(negedge clk);
        clear_diagnostics = 1'b1;
        @(posedge clk);
        #1;
        clear_diagnostics = 1'b0;
        if (output_frame_overrun_count != 0) begin
            $error("output overrun diagnostic did not clear");
            error_count = error_count + 1;
        end
        if (output_gain_q16 != 16'hffff || output_muted
            || output_ramping) begin
            $error("startup output ramp did not reach exact unity");
            error_count = error_count + 1;
        end
        @(negedge clk);
        force_mute = 1'b1;
        @(posedge clk);
        #1;
        if (output_gain_q16 != 0 || !output_muted) begin
            $error("force mute did not clear adapter output gain");
            error_count = error_count + 1;
        end

        if (scheduler_underflow_count != 0
            || input_pcm_endpoint_count != 0
            || input_configuration_error_sticky
            || output_pcm_saturation_count != 0
            || output_configuration_error_sticky
            || output_frame_overrun_count != 0
            || resampler_saturation_count != 0
            || resampler_overrun_count != 0
            || input_phase_error_count != 0
            || output_conversion_saturation_count != 0
            || solver_missed_request_count != 0
            || solver_deadline_miss_count != 0
            || solver_saturation_count != 0
            || solver_lut_clip_count != 0
            || solver_nonconvergence_count != 0
            || solver_correction_scale_fallback_count != 0
            || solver_minimum_correction_fractional_bits != 0
            || solver_latency_cycles != 8'd127
            || solver_last_residual_q44 > 63'd35184372) begin
            $error("adapter diagnostics sched=%0d endpoint=%0d iconfig=%0d osat=%0d oconfig=%0d overrun=%0d rsat=%0d rover=%0d phase=%0d convsat=%0d smissed=%0d sdeadline=%0d ssat=%0d sclip=%0d snonconv=%0d fallback=%0d min=%0d latency=%0d residual=%0d",
                   scheduler_underflow_count, input_pcm_endpoint_count,
                   input_configuration_error_sticky,
                   output_pcm_saturation_count,
                   output_configuration_error_sticky,
                   output_frame_overrun_count, resampler_saturation_count,
                   resampler_overrun_count, input_phase_error_count,
                   output_conversion_saturation_count,
                   solver_missed_request_count, solver_deadline_miss_count,
                   solver_saturation_count, solver_lut_clip_count,
                   solver_nonconvergence_count,
                   solver_correction_scale_fallback_count,
                   solver_minimum_correction_fractional_bits,
                   solver_latency_cycles, solver_last_residual_q44);
            error_count = error_count + 1;
        end
        error_count = error_count + scoreboard_error_count
                      + held_output_error_count;
        if (error_count != 0)
            $fatal(1, "FAIL: %0d fabric mono-adapter errors", error_count);
        $display("PASS: %0d exact calibrated mono frames, held and duplicated",
                 output_index);
        $finish;
    end
endmodule

`default_nettype wire
