`timescale 1ns/1fs
`default_nettype none

module phono_i2s_mono_top_tb #(
    parameter int MODEL_SAMPLE_RATE_HZ = 768000,
    parameter int FABRIC_CLOCKS_PER_48K_INPUT = 2048
);
    localparam int VECTOR_COUNT = 64;
    localparam int INPUT_FULL_SCALE_PEAK_VOLTS_Q24 = 335544;
    localparam int OUTPUT_RECIPROCAL_FULL_SCALE_Q24 = 2097152;
    localparam realtime FABRIC_HALF_PERIOD_NS =
        (FABRIC_CLOCKS_PER_48K_INPUT == 1024)
            ? 10.172526041667 : 5.086263020833;
    localparam realtime I2S_BCLK_HALF_PERIOD_NS = 162.760416666667;
    localparam int CLOCK_MONITOR_WINDOW_FABRIC_CLOCKS =
        (FABRIC_CLOCKS_PER_48K_INPUT == 1024) ? 16384 : 32768;
    localparam string VECTOR_FILE = (MODEL_SAMPLE_RATE_HZ == 384000)
        ? "sim/vectors/generated/phono_fabric_mono_adapter_384khz.txt"
        : "sim/vectors/generated/phono_fabric_mono_adapter.txt";

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
    logic calibration_update_valid = 1'b0;
    logic calibration_update_ack;
    logic calibration_invalid_update_sticky;
    logic calibration_unsafe_update_sticky;
    logic signed [31:0] active_input_full_scale_peak_volts_q24;
    logic signed [31:0] active_output_reciprocal_full_scale_q24;
    logic calibration_committed = 1'b0;
    logic mute_request = 1'b0;
    logic force_mute = 1'b0;
    logic [15:0] output_gain_q16;
    logic output_muted;
    logic output_ramping;

    logic rx_frame_error_sticky;
    logic rx_fifo_overflow_sticky;
    logic rx_fifo_underflow_sticky;
    logic tx_fifo_overflow_sticky;
    logic tx_fifo_underflow_sticky;
    logic tx_serial_underflow_sticky;
    logic [3:0] rx_fifo_i2s_level;
    logic [3:0] rx_fifo_i2s_high_water;
    logic [3:0] rx_fifo_fabric_level;
    logic [3:0] rx_fifo_fabric_high_water;
    logic [3:0] tx_fifo_fabric_level;
    logic [3:0] tx_fifo_fabric_high_water;
    logic [3:0] tx_fifo_i2s_level;
    logic [3:0] tx_fifo_i2s_high_water;
    logic audio_clock_measurement_valid;
    logic [15:0] audio_clock_measured_bclk_edges;
    logic [7:0] audio_clock_good_windows;
    logic audio_clock_rate_locked;
    logic audio_clock_rate_error_sticky;
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
    integer audio_clock_measurement_count;
    logic [3:0] observed_rx_fifo_i2s_high_water;
    logic [3:0] observed_rx_fifo_fabric_high_water;
    logic [3:0] observed_tx_fifo_fabric_high_water;
    logic [3:0] observed_tx_fifo_i2s_high_water;
    string marker;
    logic dac_scoreboard_started;

    longint unsigned fabric_cycle_count;
    longint unsigned bclk_rising_edge_count;
    longint signed first_fabric_rx_accept_cycle;
    longint signed first_model_input_cycle;
    longint signed first_model_output_cycle;
    longint signed first_calibrated_output_cycle;
    longint signed first_fabric_tx_accept_cycle;
    longint signed first_adc_frame_complete_bclk;
    longint signed first_tx_fifo_read_bclk;
    longint signed first_tx_serial_frame_start_bclk;
    longint signed first_dac_model_frame_bclk;
    longint signed first_nonzero_dac_frame_bclk;
    realtime first_adc_frame_complete_ns;
    realtime first_fabric_rx_accept_ns;
    realtime first_model_input_ns;
    realtime first_model_output_ns;
    realtime first_calibrated_output_ns;
    realtime first_fabric_tx_accept_ns;
    realtime first_tx_fifo_read_ns;
    realtime first_tx_serial_frame_start_ns;
    realtime first_dac_model_frame_ns;
    realtime first_nonzero_dac_frame_ns;
    logic first_tx_fifo_word_seen;
    logic first_tx_serial_frame_started;

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

    phono_i2s_mono_top #(
        .OUTPUT_RAMP_SAMPLES(8),
        .CLOCK_MONITOR_WINDOW_FABRIC_CLOCKS(
            CLOCK_MONITOR_WINDOW_FABRIC_CLOCKS
        ),
        .MODEL_SAMPLE_RATE_HZ(MODEL_SAMPLE_RATE_HZ),
        .FABRIC_CLOCKS_PER_48K_INPUT(FABRIC_CLOCKS_PER_48K_INPUT)
    ) dut (
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
        .calibration_update_valid,
        .calibration_update_ack,
        .calibration_invalid_update_sticky,
        .calibration_unsafe_update_sticky,
        .active_input_full_scale_peak_volts_q24,
        .active_output_reciprocal_full_scale_q24,
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

    // Exactly frequency locked at either supported fabric rate. Independent
    // phase offsets still exercise the asynchronous FIFO crossings.
    initial begin
        fabric_clk = 1'b0;
        #3;
        forever #(FABRIC_HALF_PERIOD_NS) fabric_clk = ~fabric_clk;
    end
    initial begin
        i2s_bclk = 1'b0;
        #37;
        forever #(I2S_BCLK_HALF_PERIOD_NS) i2s_bclk = ~i2s_bclk;
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

    // Absolute event markers make transport latency reproducible without
    // treating the first nonzero PCM code as the resampler's group delay.
    always @(posedge fabric_clk) begin
        fabric_cycle_count <= fabric_cycle_count + 1'b1;
        if (audio_clock_measurement_valid)
            audio_clock_measurement_count <=
                audio_clock_measurement_count + 1;
        if (dut.fabric_rx_frame_valid && dut.fabric_rx_frame_ready
            && first_fabric_rx_accept_cycle < 0) begin
            first_fabric_rx_accept_cycle <= fabric_cycle_count;
            first_fabric_rx_accept_ns <= $realtime;
        end
        if (audio_rst_n && dut.adapter.calibrated_input_valid
            && first_model_input_cycle < 0) begin
            first_model_input_cycle <= fabric_cycle_count;
            first_model_input_ns <= $realtime;
        end
        if (audio_rst_n && dut.adapter.model_output_valid
            && first_model_output_cycle < 0) begin
            first_model_output_cycle <= fabric_cycle_count;
            first_model_output_ns <= $realtime;
        end
        if (audio_rst_n && dut.adapter.calibrated_output_valid
            && first_calibrated_output_cycle < 0) begin
            first_calibrated_output_cycle <= fabric_cycle_count;
            first_calibrated_output_ns <= $realtime;
        end
        if (dut.fabric_tx_frame_valid && dut.fabric_tx_frame_ready
            && first_fabric_tx_accept_cycle < 0) begin
            first_fabric_tx_accept_cycle <= fabric_cycle_count;
            first_fabric_tx_accept_ns <= $realtime;
        end
    end

    always @(posedge i2s_bclk) begin
        bclk_rising_edge_count <= bclk_rising_edge_count + 1'b1;
        #1;
        if (dut.bridge.rx_serial_frame_valid
            && first_adc_frame_complete_bclk < 0) begin
            first_adc_frame_complete_bclk <= bclk_rising_edge_count;
            first_adc_frame_complete_ns <= $realtime;
        end
        if (dut.bridge.tx_fifo_read_valid
            && first_tx_fifo_read_bclk < 0) begin
            first_tx_fifo_read_bclk <= bclk_rising_edge_count;
            first_tx_fifo_read_ns <= $realtime;
            first_tx_fifo_word_seen <= 1'b1;
        end
        if (dac_frame_valid && first_tx_serial_frame_started
            && first_dac_model_frame_bclk < 0) begin
            first_dac_model_frame_bclk <= bclk_rising_edge_count;
            first_dac_model_frame_ns <= $realtime;
        end
    end

    always @(negedge i2s_bclk) begin
        if (first_tx_fifo_word_seen && !first_tx_serial_frame_started
            && dut.bridge.transmitter.entering_left_slot
            && dut.bridge.transmitter.pending_valid) begin
            first_tx_serial_frame_started <= 1'b1;
            first_tx_serial_frame_start_bclk <= bclk_rising_edge_count;
            first_tx_serial_frame_start_ns <= $realtime;
        end
    end

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
                first_nonzero_dac_frame_ns <= $realtime;
                first_nonzero_dac_frame_bclk <= bclk_rising_edge_count;
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
        fabric_cycle_count = 0;
        bclk_rising_edge_count = 0;
        first_fabric_rx_accept_cycle = -1;
        first_model_input_cycle = -1;
        first_model_output_cycle = -1;
        first_calibrated_output_cycle = -1;
        first_fabric_tx_accept_cycle = -1;
        first_adc_frame_complete_bclk = -1;
        first_tx_fifo_read_bclk = -1;
        first_tx_serial_frame_start_bclk = -1;
        first_dac_model_frame_bclk = -1;
        first_nonzero_dac_frame_bclk = -1;
        first_adc_frame_complete_ns = -1.0;
        first_fabric_rx_accept_ns = -1.0;
        first_model_input_ns = -1.0;
        first_model_output_ns = -1.0;
        first_calibrated_output_ns = -1.0;
        first_fabric_tx_accept_ns = -1.0;
        first_tx_fifo_read_ns = -1.0;
        first_tx_serial_frame_start_ns = -1.0;
        first_dac_model_frame_ns = -1.0;
        first_nonzero_dac_frame_ns = -1.0;
        first_tx_fifo_word_seen = 1'b0;
        first_tx_serial_frame_started = 1'b0;
        audio_clock_measurement_count = 0;
        observed_rx_fifo_i2s_high_water = '0;
        observed_rx_fifo_fabric_high_water = '0;
        observed_tx_fifo_fabric_high_water = '0;
        observed_tx_fifo_i2s_high_water = '0;
        file_handle = $fopen(
            VECTOR_FILE, "r"
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
        @(negedge fabric_clk);
        calibration_update_valid = 1'b1;
        @(posedge fabric_clk);
        #1;
        if (!calibration_update_ack
            || active_input_full_scale_peak_volts_q24
                != INPUT_FULL_SCALE_PEAK_VOLTS_Q24
            || active_output_reciprocal_full_scale_q24
                != OUTPUT_RECIPROCAL_FULL_SCALE_Q24) begin
            $error("startup calibration did not commit atomically");
            error_count = error_count + 1;
        end
        calibration_committed = 1'b1;
        @(negedge fabric_clk);
        calibration_update_valid = 1'b0;
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
        wait (calibration_committed);
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
            || calibration_invalid_update_sticky
            || calibration_unsafe_update_sticky
            || audio_clock_rate_error_sticky
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
        if (rx_fifo_i2s_high_water == 0 || rx_fifo_i2s_high_water > 8
            || rx_fifo_fabric_high_water == 0
            || rx_fifo_fabric_high_water > 8
            || tx_fifo_fabric_high_water == 0
            || tx_fifo_fabric_high_water > 8
            || tx_fifo_i2s_high_water == 0
            || tx_fifo_i2s_high_water > 8
            || rx_fifo_i2s_level > 8 || rx_fifo_fabric_level > 8
            || tx_fifo_fabric_level > 8 || tx_fifo_i2s_level > 8) begin
            $error("invalid pin-top FIFO occupancy level/watermark");
            error_count = error_count + 1;
        end
        observed_rx_fifo_i2s_high_water = rx_fifo_i2s_high_water;
        observed_rx_fifo_fabric_high_water = rx_fifo_fabric_high_water;
        observed_tx_fifo_fabric_high_water = tx_fifo_fabric_high_water;
        observed_tx_fifo_i2s_high_water = tx_fifo_i2s_high_water;
        if (!audio_clock_rate_locked || audio_clock_good_windows != 8'd3
            || audio_clock_measured_bclk_edges < 16'd1023
            || audio_clock_measured_bclk_edges > 16'd1025
            || audio_clock_measurement_count < 3) begin
            $error("audio clock did not establish expected locked rate");
            error_count = error_count + 1;
        end
        if (output_gain_q16 != 16'hffff || output_muted
            || output_ramping) begin
            $error("pin-top startup ramp did not reach exact unity");
            error_count = error_count + 1;
        end

        // Once audio is live, a positive but unmuted coefficient pair must be
        // rejected without changing either active value.
        @(negedge fabric_clk);
        input_full_scale_peak_volts_q24 =
            INPUT_FULL_SCALE_PEAK_VOLTS_Q24 + 1;
        calibration_update_valid = 1'b1;
        @(posedge fabric_clk);
        #1;
        if (calibration_update_ack || !calibration_unsafe_update_sticky
            || active_input_full_scale_peak_volts_q24
                != INPUT_FULL_SCALE_PEAK_VOLTS_Q24
            || active_output_reciprocal_full_scale_q24
                != OUTPUT_RECIPROCAL_FULL_SCALE_Q24) begin
            $error("live calibration update was not rejected atomically");
            error_count = error_count + 1;
        end
        @(negedge fabric_clk);
        calibration_update_valid = 1'b0;
        fabric_clear_diagnostics = 1'b1;
        @(posedge fabric_clk);
        #1;
        fabric_clear_diagnostics = 1'b0;
        if (calibration_invalid_update_sticky
            || calibration_unsafe_update_sticky) begin
            $error("calibration control diagnostic did not clear");
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
        if (first_adc_frame_complete_bclk < 0
            || first_fabric_rx_accept_cycle < 0
            || first_model_input_cycle < 0
            || first_model_output_cycle < 0
            || first_calibrated_output_cycle < 0
            || first_fabric_tx_accept_cycle < 0
            || first_tx_fifo_read_bclk < 0
            || first_tx_serial_frame_start_bclk < 0
            || first_tx_serial_frame_start_ns < 0.0
            || first_dac_model_frame_bclk < 0
            || first_nonzero_dac_frame_bclk < 0
            || first_nonzero_dac_frame_ns < 0.0) begin
            $error("one or more latency markers were not observed");
            error_count = error_count + 1;
        end

        error_count = error_count + input_error_count + launch_error_count
                      + dac_error_count;
        if (error_count != 0)
            $fatal(1, "FAIL: %0d pin-facing mono-top errors", error_count);
        $write("LATENCY_REPORT {");
        $write("\"first_nonzero_output_index\":%0d,",
               first_nonzero_output);
        $write("\"first_adc_frame_complete_bclk\":%0d,",
               first_adc_frame_complete_bclk);
        $write("\"first_fabric_rx_accept_cycle\":%0d,",
               first_fabric_rx_accept_cycle);
        $write("\"first_model_input_cycle\":%0d,", first_model_input_cycle);
        $write("\"first_model_output_cycle\":%0d,", first_model_output_cycle);
        $write("\"first_calibrated_output_cycle\":%0d,",
               first_calibrated_output_cycle);
        $write("\"first_fabric_tx_accept_cycle\":%0d,",
               first_fabric_tx_accept_cycle);
        $write("\"first_tx_fifo_read_bclk\":%0d,", first_tx_fifo_read_bclk);
        $write("\"first_tx_serial_frame_start_bclk\":%0d,",
               first_tx_serial_frame_start_bclk);
        $write("\"first_dac_model_frame_bclk\":%0d,",
               first_dac_model_frame_bclk);
        $write("\"first_nonzero_dac_frame_bclk\":%0d,",
               first_nonzero_dac_frame_bclk);
        $write("\"rx_fifo_i2s_high_water\":%0d,",
               observed_rx_fifo_i2s_high_water);
        $write("\"rx_fifo_fabric_high_water\":%0d,",
               observed_rx_fifo_fabric_high_water);
        $write("\"tx_fifo_fabric_high_water\":%0d,",
               observed_tx_fifo_fabric_high_water);
        $write("\"tx_fifo_i2s_high_water\":%0d,",
               observed_tx_fifo_i2s_high_water);
        $write("\"audio_clock_measured_bclk_edges\":%0d,",
               audio_clock_measured_bclk_edges);
        $write("\"audio_clock_good_windows\":%0d,",
               audio_clock_good_windows);
        $write("\"audio_clock_measurement_count\":%0d,",
               audio_clock_measurement_count);
        $write("\"first_adc_frame_complete_ns\":%.6f,",
               first_adc_frame_complete_ns);
        $write("\"first_fabric_rx_accept_ns\":%.6f,",
               first_fabric_rx_accept_ns);
        $write("\"first_model_input_ns\":%.6f,", first_model_input_ns);
        $write("\"first_model_output_ns\":%.6f,", first_model_output_ns);
        $write("\"first_calibrated_output_ns\":%.6f,",
               first_calibrated_output_ns);
        $write("\"first_fabric_tx_accept_ns\":%.6f,",
               first_fabric_tx_accept_ns);
        $write("\"first_tx_fifo_read_ns\":%.6f,", first_tx_fifo_read_ns);
        $write("\"first_tx_serial_frame_start_ns\":%.6f,",
               first_tx_serial_frame_start_ns);
        $write("\"first_dac_model_frame_ns\":%.6f,",
               first_dac_model_frame_ns);
        $display("\"first_nonzero_dac_frame_ns\":%.6f}",
                 first_nonzero_dac_frame_ns);
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
