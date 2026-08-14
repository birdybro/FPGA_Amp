`timescale 1ns/1ps
`default_nettype none

module phono_i2s_mono_top_tb;
    localparam int VECTOR_COUNT = 64;
    localparam int INPUT_FULL_SCALE_PEAK_VOLTS_Q24 = 335544;
    localparam int OUTPUT_RECIPROCAL_FULL_SCALE_Q24 = 2097152;

    logic i2s_bclk;
    logic i2s_rst_n = 1'b0;
    logic fabric_clk;
    logic fabric_rst_n = 1'b0;
    logic audio_rst_n = 1'b0;

    logic [63:0] adc_frame_data = '0;
    logic adc_frame_valid = 1'b0;
    logic adc_frame_ready;
    logic adc_lrclk;
    logic adc_serial_data;
    logic adc_underflow;

    logic dac_lrclk;
    logic dac_serial_data;
    logic [63:0] dac_frame_data;
    logic dac_frame_valid;
    logic dac_frame_error;

    logic i2s_clear_diagnostics = 1'b0;
    logic fabric_clear_diagnostics = 1'b0;
    logic signed [31:0] input_full_scale_peak_volts_q24 =
        INPUT_FULL_SCALE_PEAK_VOLTS_Q24;
    logic signed [31:0] output_reciprocal_full_scale_q24 =
        OUTPUT_RECIPROCAL_FULL_SCALE_Q24;

    logic rx_frame_error_sticky;
    logic rx_fifo_overflow_sticky;
    logic rx_fifo_underflow_sticky;
    logic tx_fifo_overflow_sticky;
    logic tx_fifo_underflow_sticky;
    logic tx_serial_underflow_sticky;
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

    logic signed [23:0] left_input [0:VECTOR_COUNT-1];
    logic signed [23:0] right_input [0:VECTOR_COUNT-1];
    logic signed [31:0] expected_model_input [0:VECTOR_COUNT-1];
    logic signed [23:0] expected_output [0:VECTOR_COUNT-1];
    logic signed [31:0] expected_model_output [0:VECTOR_COUNT-1];

    integer model_input_index;
    integer model_output_index;
    integer dac_output_index;
    integer first_nonzero_output;
    integer input_error_count;
    integer launch_error_count;
    integer dac_error_count;
    integer error_count;
    integer file_handle;
    integer scan_count;
    integer index;
    string marker;
    logic dac_scoreboard_started;

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

    i2s_transmitter adc_source (
        .bclk(i2s_bclk),
        .rst_n(i2s_rst_n),
        .frame_data(adc_frame_data),
        .frame_valid(adc_frame_valid),
        .frame_ready(adc_frame_ready),
        .clear_underflow(i2s_clear_diagnostics),
        .lrclk(adc_lrclk),
        .serial_data(adc_serial_data),
        .underflow_sticky(adc_underflow)
    );

    phono_i2s_mono_top dut (
        .i2s_bclk,
        .i2s_rst_n,
        .i2s_adc_lrclk(adc_lrclk),
        .i2s_adc_serial_data(adc_serial_data),
        .i2s_dac_lrclk(dac_lrclk),
        .i2s_dac_serial_data(dac_serial_data),
        .i2s_clear_diagnostics,
        .fabric_clk,
        .fabric_rst_n,
        .audio_rst_n,
        .fabric_clear_diagnostics,
        .input_full_scale_peak_volts_q24,
        .output_reciprocal_full_scale_q24,
        .rx_frame_error_sticky,
        .rx_fifo_overflow_sticky,
        .rx_fifo_underflow_sticky,
        .tx_fifo_overflow_sticky,
        .tx_fifo_underflow_sticky,
        .tx_serial_underflow_sticky,
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

    i2s_receiver dac_sink (
        .bclk(i2s_bclk),
        .rst_n(i2s_rst_n),
        .lrclk(dac_lrclk),
        .serial_data(dac_serial_data),
        .clear_frame_error(i2s_clear_diagnostics),
        .frame_data(dac_frame_data),
        .frame_valid(dac_frame_valid),
        .frame_error_sticky(dac_frame_error)
    );

    // Exactly frequency locked: 98.304 MHz / 3.072 MHz = 32. The independent
    // phase offsets still exercise the asynchronous FIFO crossings.
    initial begin
        fabric_clk = 1'b0;
        #3;
        forever #5 fabric_clk = ~fabric_clk;
    end
    initial begin
        i2s_bclk = 1'b0;
        #37;
        forever #160 i2s_bclk = ~i2s_bclk;
    end

    task automatic enqueue_adc(input logic [63:0] value);
        begin
            @(posedge i2s_bclk);
            while (!adc_frame_ready)
                @(posedge i2s_bclk);
            adc_frame_data = value;
            adc_frame_valid = 1'b1;
            @(posedge i2s_bclk);
            adc_frame_valid = 1'b0;
        end
    endtask

    // Check the complete serial receive/CDC/calibration input path before the
    // nonlinear state can obscure an ordering or channel-selection error.
    always @(posedge fabric_clk) begin
        if (!audio_rst_n) begin
            model_input_index <= 0;
            model_output_index <= 0;
            input_error_count <= 0;
        end else if (dut.adapter.calibrated_input_valid
                     && model_input_index < VECTOR_COUNT) begin
            if (dut.adapter.calibrated_input_q24
                !== expected_model_input[model_input_index]) begin
                $error("model input %0d got=%0d expected=%0d",
                       model_input_index, dut.adapter.calibrated_input_q24,
                       expected_model_input[model_input_index]);
                input_error_count <= input_error_count + 1;
            end
            if (scheduler_phase_counter != 11'd0) begin
                $error("calibrated input %0d reached model at phase %0d",
                       model_input_index, scheduler_phase_counter);
                input_error_count <= input_error_count + 1;
            end
            model_input_index <= model_input_index + 1;
        end
        if (audio_rst_n && dut.adapter.model_output_valid
            && model_output_index < VECTOR_COUNT) begin
            if (dut.adapter.model_output_q24
                !== expected_model_output[model_output_index]) begin
                $error("model output %0d got=%0d expected=%0d",
                       model_output_index, dut.adapter.model_output_q24,
                       expected_model_output[model_output_index]);
                input_error_count <= input_error_count + 1;
            end
            model_output_index <= model_output_index + 1;
        end
    end

    always @(negedge fabric_clk) begin
        if (!audio_rst_n)
            launch_error_count <= 0;
        else if (dut.adapter.scheduled_frame_valid
                 && !scheduled_frame_present) begin
                $error("scheduler launched a missing frame in locked-rate test");
                launch_error_count <= launch_error_count + 1;
            end
    end

    // Startup DAC starvation produces zero frames before the model pipeline
    // fills. Begin the pin-level scoreboard at the first expected nonzero frame
    // and then require the complete remaining sequence and mono duplication.
    always @(posedge i2s_bclk) begin
        #1;
        if (dac_frame_valid) begin
            if (!dac_scoreboard_started && dac_frame_data != 64'd0) begin
                dac_scoreboard_started <= 1'b1;
                dac_output_index <= first_nonzero_output;
                if (dac_frame_data !== duplicate_frame(
                    expected_output[first_nonzero_output]
                )) begin
                    $error("first DAC frame got=%016x expected=%016x",
                           dac_frame_data,
                           duplicate_frame(expected_output[first_nonzero_output]));
                    dac_error_count <= dac_error_count + 1;
                end
            end else if (dac_scoreboard_started) begin
                dac_output_index <= dac_output_index + 1;
                if (dac_output_index + 1 >= VECTOR_COUNT
                    || dac_frame_data !== duplicate_frame(
                        expected_output[dac_output_index + 1]
                    )) begin
                    $error("DAC frame %0d got=%016x expected=%016x",
                           dac_output_index + 1, dac_frame_data,
                           (dac_output_index + 1 < VECTOR_COUNT)
                               ? duplicate_frame(
                                   expected_output[dac_output_index + 1]
                                 ) : 64'd0);
                    dac_error_count <= dac_error_count + 1;
                end
            end
        end
    end

    initial begin
        error_count = 0;
        input_error_count = 0;
        launch_error_count = 0;
        dac_error_count = 0;
        model_input_index = 0;
        model_output_index = 0;
        dac_output_index = 0;
        first_nonzero_output = -1;
        dac_scoreboard_started = 1'b0;
        file_handle = $fopen(
            "sim/vectors/generated/phono_fabric_mono_adapter.txt", "r"
        );
        if (file_handle == 0)
            $fatal(1, "cannot open I2S-top vectors");
        for (index = 0; index < VECTOR_COUNT; index++) begin
            scan_count = $fscanf(
                file_handle, "%d %d %d\n", left_input[index],
                right_input[index], expected_model_input[index]
            );
            if (scan_count != 3)
                $fatal(1, "malformed I2S-top input %0d", index);
        end
        scan_count = $fscanf(file_handle, "%s\n", marker);
        if (scan_count != 1 || marker != "EXPECTED")
            $fatal(1, "missing I2S-top expected marker");
        for (index = 0; index < VECTOR_COUNT; index++) begin
            scan_count = $fscanf(
                file_handle, "%d %d\n", expected_output[index],
                expected_model_output[index]
            );
            if (scan_count != 2)
                $fatal(1, "malformed I2S-top output %0d", index);
            if (first_nonzero_output < 0 && expected_output[index] != 0)
                first_nonzero_output = index;
        end
        $fclose(file_handle);
        if (first_nonzero_output < 0)
            $fatal(1, "I2S-top vectors contain no observable nonzero output");

        adc_frame_data = stereo_frame(left_input[0], right_input[0]);
        adc_frame_valid = 1'b1;
        repeat (3) @(posedge fabric_clk);
        #1;
        fabric_rst_n = 1'b1;
        repeat (3) @(posedge i2s_bclk);
        #1;
        i2s_rst_n = 1'b1;
        @(posedge i2s_bclk);
        adc_frame_valid = 1'b0;
        for (index = 1; index < VECTOR_COUNT; index++)
            enqueue_adc(stereo_frame(left_input[index], right_input[index]));
    end

    // Fill across the CDC before starting scheduler phase acquisition. This
    // explicit reset sequence is part of the top-level digital contract.
    initial begin
        wait (fabric_rst_n);
        wait (dut.bridge.fabric_rx_frame_valid);
        @(negedge fabric_clk);
        audio_rst_n = 1'b1;

        wait (dac_scoreboard_started);
        wait (dac_output_index == VECTOR_COUNT - 1);
        #1;
        if (model_input_index != VECTOR_COUNT
            || model_output_index < VECTOR_COUNT) begin
            $error("model boundaries input=%0d output=%0d expected=%0d",
                   model_input_index, model_output_index, VECTOR_COUNT);
            error_count = error_count + 1;
        end
        if (rx_frame_error_sticky || rx_fifo_overflow_sticky
            || rx_fifo_underflow_sticky || tx_fifo_overflow_sticky
            || tx_fifo_underflow_sticky || dac_frame_error
            || scheduler_underflow_count != 0
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
            $error("unexpected I2S-top diagnostic");
            error_count = error_count + 1;
        end
        if (!tx_serial_underflow_sticky) begin
            $error("expected startup serial underflow was not retained");
            error_count = error_count + 1;
        end
        if (!adc_underflow) begin
            $error("expected exhausted test-source underflow was not retained");
            error_count = error_count + 1;
        end

        error_count = error_count + input_error_count + launch_error_count
                      + dac_error_count;
        if (error_count != 0)
            $fatal(1, "FAIL: %0d pin-facing mono-top errors", error_count);
        $display("PASS: %0d serial inputs and %0d post-startup DAC frames exact",
                 model_input_index, VECTOR_COUNT - first_nonzero_output);
        $finish;
    end

    initial begin
        #4_000_000;
        $fatal(1, "pin-facing mono top timed out");
    end
endmodule

`default_nettype wire
