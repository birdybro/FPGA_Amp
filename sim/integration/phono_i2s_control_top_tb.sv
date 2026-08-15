`timescale 1ns/1ps
`default_nettype none

module phono_i2s_control_top_tb #(
    parameter int MODEL_SAMPLE_RATE_HZ = 768000,
    parameter int FABRIC_CLOCKS_PER_48K_INPUT = 2048
);
    logic i2s_bclk;
    logic bclk_running = 1'b1;
    logic i2s_rst_n = 1'b0;
    logic i2s_adc_lrclk = 1'b0;
    logic i2s_adc_serial_data = 1'b0;
    logic i2s_dac_lrclk;
    logic i2s_dac_serial_data;
    logic fabric_clk;
    logic fabric_rst_n = 1'b0;
    logic audio_rst_n = 1'b0;
    logic force_mute = 1'b0;
    logic transport_frame_error_sticky = 1'b0;
    logic transport_response_underflow_sticky = 1'b0;
    logic [31:0] transport_completed_frame_count = '0;
    logic transport_clear_diagnostics;
    logic control_request_valid = 1'b0;
    logic control_request_write = 1'b0;
    logic [7:0] control_request_address = '0;
    logic [31:0] control_request_write_data = '0;
    logic control_response_valid;
    logic [31:0] control_response_read_data;
    logic control_response_error;
    logic output_muted;
    logic output_ramping;
    logic audio_clock_rate_locked;
    logic audio_clock_rate_error_sticky;
    logic rate_fault_mute_active;
    logic [31:0] control_snapshot_sequence;
    logic [31:0] calibration_commit_sequence;
    logic [31:0] calibration_accepted_sequence;
    logic control_bus_error_sticky;
    logic calibration_rejected_sticky;
    logic snapshot_capture_timeout_sticky;
    logic [31:0] captured_read_data;
    integer i2s_clear_pulse_count;
    integer transport_clear_pulse_count;
    integer errors = 0;

    initial begin
        fabric_clk = 1'b0;
        forever #5 fabric_clk = ~fabric_clk;
    end
    initial begin
        i2s_bclk = 1'b0;
        forever begin
            #160;
            if (bclk_running)
                i2s_bclk = ~i2s_bclk;
            else
                i2s_bclk = 1'b0;
        end
    end

    phono_i2s_control_top #(
        .OUTPUT_RAMP_SAMPLES(8),
        .CLOCK_MONITOR_WINDOW_FABRIC_CLOCKS(320),
        .CLOCK_MONITOR_EXPECTED_BCLK_EDGES(10),
        .CLOCK_MONITOR_EDGE_TOLERANCE(0),
        .CLOCK_MONITOR_LOCK_WINDOWS(3),
        .DIAGNOSTIC_SNAPSHOT_TIMEOUT_CLOCKS(512),
        .MODEL_SAMPLE_RATE_HZ(MODEL_SAMPLE_RATE_HZ),
        .FABRIC_CLOCKS_PER_48K_INPUT(FABRIC_CLOCKS_PER_48K_INPUT)
    ) dut (.*);

    always_ff @(posedge i2s_bclk or negedge i2s_rst_n) begin
        if (!i2s_rst_n)
            i2s_clear_pulse_count <= 0;
        else if (dut.i2s_clear_diagnostics)
            i2s_clear_pulse_count <= i2s_clear_pulse_count + 1;
    end

    always_ff @(posedge fabric_clk or negedge fabric_rst_n) begin
        if (!fabric_rst_n)
            transport_clear_pulse_count <= 0;
        else if (transport_clear_diagnostics)
            transport_clear_pulse_count <= transport_clear_pulse_count + 1;
    end

    task automatic bus_write(
        input logic [7:0] address,
        input logic [31:0] data
    );
        begin
            @(negedge fabric_clk);
            control_request_valid = 1'b1;
            control_request_write = 1'b1;
            control_request_address = address;
            control_request_write_data = data;
            @(posedge fabric_clk);
            #1;
            if (!control_response_valid || control_response_error) begin
                $error("control write failed address=%02x", address);
                errors = errors + 1;
            end
            @(negedge fabric_clk);
            control_request_valid = 1'b0;
            control_request_write = 1'b0;
        end
    endtask

    task automatic bus_read(input logic [7:0] address);
        begin
            @(negedge fabric_clk);
            control_request_valid = 1'b1;
            control_request_write = 1'b0;
            control_request_address = address;
            control_request_write_data = '0;
            @(posedge fabric_clk);
            #1;
            captured_read_data = control_response_read_data;
            if (!control_response_valid || control_response_error) begin
                $error("control read failed address=%02x", address);
                errors = errors + 1;
            end
            @(negedge fabric_clk);
            control_request_valid = 1'b0;
        end
    endtask

    initial begin
        repeat (4) @(posedge fabric_clk);
        fabric_rst_n = 1'b1;
        repeat (2) @(posedge i2s_bclk);
        i2s_rst_n = 1'b1;

        bus_read(8'h00);
        if (captured_read_data != 32'h4650_4741) begin
            $error("controlled top identity mismatch");
            errors = errors + 1;
        end
        if (!output_muted) begin
            $error("controlled top did not reset muted");
            errors = errors + 1;
        end

        bus_write(8'h08, 32'd335544);
        bus_write(8'h09, 32'd2097152);
        bus_write(8'h0a, 32'd1);
        repeat (4) @(posedge fabric_clk);
        bus_read(8'h06);
        if (captured_read_data != 1) begin
            $error("controlled top commit sequence mismatch");
            errors = errors + 1;
        end
        bus_read(8'h07);
        if (captured_read_data != 1) begin
            $error("controlled top accepted sequence mismatch");
            errors = errors + 1;
        end
        bus_read(8'h0b);
        if (captured_read_data != 32'd335544) begin
            $error("controlled top active input calibration mismatch");
            errors = errors + 1;
        end

        // Snapshot the reset-muted state, then change a live input and prove
        // the retained word does not change until the second command.
        wait (dut.diagnostic_capture_available);
        bus_write(8'h04, 32'h0000_0003);
        wait (control_snapshot_sequence == 1);
        bus_read(8'h23);
        if (!captured_read_data[30]) begin
            $error("snapshot did not capture muted status");
            errors = errors + 1;
        end
        bus_read(8'h20);
        if (captured_read_data[18]) begin
            $error("first snapshot unexpectedly captured force mute");
            errors = errors + 1;
        end
        force_mute = 1'b1;
        bus_read(8'h20);
        if (captured_read_data[18]) begin
            $error("live force mute tore retained snapshot");
            errors = errors + 1;
        end
        wait (dut.diagnostic_capture_available);
        bus_write(8'h04, 32'h0000_0003);
        wait (control_snapshot_sequence == 2);
        bus_read(8'h20);
        if (!captured_read_data[18] || control_snapshot_sequence != 2) begin
            $error("second snapshot did not capture force mute");
            errors = errors + 1;
        end

        // One fabric clear command must become one I2S-domain pulse despite
        // the unrelated 100 MHz / approximately 3.07 MHz clocks.
        bus_write(8'h04, 32'h0000_0005);
        repeat (8) @(posedge i2s_bclk);
        #1;
        if (i2s_clear_pulse_count != 1) begin
            $error("I2S clear crossing count=%0d", i2s_clear_pulse_count);
            errors = errors + 1;
        end

        if (control_bus_error_sticky || calibration_rejected_sticky
            || calibration_commit_sequence != 1
            || calibration_accepted_sequence != 1
            || output_ramping || audio_clock_rate_locked
            || audio_clock_rate_error_sticky
            || !rate_fault_mute_active
            || transport_clear_pulse_count != 1
            || ((^{i2s_dac_lrclk, i2s_dac_serial_data}) === 1'bx)) begin
            $error("unexpected controlled-top diagnostic");
            errors = errors + 1;
        end

        // The wrapper fails closed until three exact-rate windows qualify.
        // A stopped BCLK drops lock, latches evidence, and remains force-muted
        // even after rate recovery until the host snapshots and clears it.
        force_mute = 1'b0;
        wait (audio_clock_rate_locked);
        @(negedge fabric_clk);
        #1;
        if (rate_fault_mute_active || dut.effective_force_mute
            || audio_clock_rate_error_sticky) begin
            $error("qualified BCLK did not release rate-fault mute");
            errors = errors + 1;
        end
        bclk_running = 1'b0;
        wait (audio_clock_rate_error_sticky);
        #1;
        if (audio_clock_rate_locked || !rate_fault_mute_active
            || !dut.effective_force_mute) begin
            $error("stopped BCLK did not assert retained force mute");
            errors = errors + 1;
        end
        wait (dut.diagnostic_capture_available);
        bus_write(8'h04, 32'h0000_0002);
        wait (snapshot_capture_timeout_sticky);
        #1;
        if (control_snapshot_sequence != 2) begin
            $error("stopped-BCLK snapshot advanced without a coherent image");
            errors = errors + 1;
        end
        bclk_running = 1'b1;
        wait (audio_clock_rate_locked);
        wait (dut.diagnostic_capture_available);
        #1;
        if (!audio_clock_rate_error_sticky || !rate_fault_mute_active
            || !dut.effective_force_mute) begin
            $error("rate recovery improperly bypassed retained fault");
            errors = errors + 1;
        end
        wait (dut.diagnostic_capture_available);
        bus_write(8'h04, 32'h0000_0002);
        wait (control_snapshot_sequence == 3);
        bus_read(8'h20);
        if (!captured_read_data[1] || !captured_read_data[9]
            || !captured_read_data[10]) begin
            $error("rate-fault snapshot evidence missing");
            errors = errors + 1;
        end
        bus_write(8'h04, 32'h0000_000c);
        repeat (8) @(posedge i2s_bclk);
        #1;
        if (audio_clock_rate_error_sticky || rate_fault_mute_active
            || dut.effective_force_mute || !audio_clock_rate_locked
            || i2s_clear_pulse_count != 2
            || transport_clear_pulse_count != 2) begin
            $error("qualified rate-fault clear did not release output");
            errors = errors + 1;
        end
        bus_read(8'h35);
        if (captured_read_data[15:0] != dut.i2s_diagnostic_snapshot
            || snapshot_capture_timeout_sticky) begin
            $error("I2S snapshot register=%04x CDC=%04x timeout=%0b",
                   captured_read_data[15:0], dut.i2s_diagnostic_snapshot,
                   snapshot_capture_timeout_sticky);
            errors = errors + 1;
        end
        if (errors != 0)
            $fatal(1, "FAIL: %0d controlled-top errors", errors);
        $display("PASS: control, snapshot, clear CDC, and fail-closed BCLK guard");
        $finish;
    end

    initial begin
        #1_000_000;
        $fatal(1, "controlled top timed out");
    end

endmodule

`default_nettype wire
