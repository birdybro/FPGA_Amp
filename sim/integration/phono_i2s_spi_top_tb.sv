`timescale 1ns/1ps
`default_nettype none

module phono_i2s_spi_top_tb;
    localparam time SPI_HALF_PERIOD = 100ns;

    logic i2s_bclk;
    logic i2s_rst_n = 1'b0;
    logic i2s_adc_lrclk = 1'b0;
    logic i2s_adc_serial_data = 1'b0;
    logic i2s_dac_lrclk;
    logic i2s_dac_serial_data;
    logic fabric_clk;
    logic fabric_rst_n = 1'b0;
    logic audio_rst_n = 1'b0;
    logic force_mute = 1'b0;
    logic spi_cs_n = 1'b1;
    logic spi_sclk = 1'b0;
    logic spi_mosi = 1'b0;
    logic spi_miso;
    logic output_muted;
    logic output_ramping;
    logic audio_clock_rate_locked;
    logic audio_clock_rate_error_sticky;
    logic rate_fault_mute_active;
    logic spi_frame_error_sticky;
    logic spi_response_underflow_sticky;
    logic [31:0] spi_completed_frame_count;
    logic control_bus_error_sticky;
    logic calibration_rejected_sticky;
    logic [39:0] response_frame;
    integer i2s_clear_pulse_count;
    integer errors = 0;
    integer bit_index;

    initial begin
        fabric_clk = 1'b0;
        forever #5ns fabric_clk = ~fabric_clk;
    end
    initial begin
        i2s_bclk = 1'b0;
        forever #163ns i2s_bclk = ~i2s_bclk;
    end

    phono_i2s_spi_top #(
        .OUTPUT_RAMP_SAMPLES(8)
    ) dut (.*);

    always_ff @(posedge i2s_bclk or negedge i2s_rst_n) begin
        if (!i2s_rst_n)
            i2s_clear_pulse_count <= 0;
        else if (dut.controlled_audio.i2s_clear_diagnostics)
            i2s_clear_pulse_count <= i2s_clear_pulse_count + 1;
    end

    task automatic spi_transaction(
        input logic write_request,
        input logic [6:0] word_address,
        input logic [31:0] write_data,
        output logic [39:0] received_response
    );
        logic [39:0] request_frame;
        begin
            request_frame = {write_request, word_address, write_data};
            received_response = '0;
            spi_cs_n = 1'b0;
            #(SPI_HALF_PERIOD);
            for (bit_index = 39; bit_index >= 0; bit_index = bit_index - 1) begin
                spi_mosi = request_frame[bit_index];
                spi_sclk = 1'b1;
                #(SPI_HALF_PERIOD);
                spi_sclk = 1'b0;
                #(SPI_HALF_PERIOD);
            end
            spi_mosi = 1'b0;
            for (bit_index = 39; bit_index >= 0; bit_index = bit_index - 1) begin
                spi_sclk = 1'b1;
                #(SPI_HALF_PERIOD/2);
                received_response[bit_index] = spi_miso;
                #(SPI_HALF_PERIOD/2);
                spi_sclk = 1'b0;
                #(SPI_HALF_PERIOD);
            end
            spi_cs_n = 1'b1;
            #(4*SPI_HALF_PERIOD);
        end
    endtask

    task automatic expect_response(
        input logic [7:0] expected_status,
        input logic [31:0] expected_data,
        input string label_text
    );
        begin
            if (response_frame != {expected_status, expected_data}) begin
                $error("%s response=%010x expected=%02x%08x",
                       label_text, response_frame,
                       expected_status, expected_data);
                errors = errors + 1;
            end
        end
    endtask

    initial begin
        repeat (4) @(posedge fabric_clk);
        fabric_rst_n = 1'b1;
        repeat (2) @(posedge i2s_bclk);
        i2s_rst_n = 1'b1;

        spi_transaction(1'b0, 7'h00, 32'd0, response_frame);
        expect_response(8'h00, 32'h4650_4741, "identity");
        if (!output_muted) begin
            $error("SPI top did not reset muted");
            errors = errors + 1;
        end

        spi_transaction(1'b1, 7'h08, 32'd335544, response_frame);
        expect_response(8'h00, 32'd0, "input shadow");
        spi_transaction(1'b1, 7'h09, 32'd2097152, response_frame);
        expect_response(8'h00, 32'd0, "output shadow");
        spi_transaction(1'b1, 7'h0a, 32'd1, response_frame);
        expect_response(8'h00, 32'd0, "calibration commit");
        repeat (5) @(posedge fabric_clk);
        spi_transaction(1'b0, 7'h06, 32'd0, response_frame);
        expect_response(8'h00, 32'd1, "attempted sequence");
        spi_transaction(1'b0, 7'h07, 32'd0, response_frame);
        expect_response(8'h00, 32'd1, "accepted sequence");
        spi_transaction(1'b0, 7'h0b, 32'd0, response_frame);
        expect_response(8'h00, 32'd335544, "active input");

        // An incomplete frame must be retained by the transport and appear in
        // the next coherent diagnostic image without advancing frame count.
        spi_cs_n = 1'b0;
        #(SPI_HALF_PERIOD);
        for (bit_index = 0; bit_index < 10; bit_index = bit_index + 1) begin
            spi_sclk = 1'b1;
            #(SPI_HALF_PERIOD);
            spi_sclk = 1'b0;
            #(SPI_HALF_PERIOD);
        end
        spi_cs_n = 1'b1;
        #(4*SPI_HALF_PERIOD);
        if (!spi_frame_error_sticky) begin
            $error("complete SPI top did not retain short frame");
            errors = errors + 1;
        end

        spi_transaction(1'b1, 7'h04, 32'h0000_0003, response_frame);
        expect_response(8'h00, 32'd0, "first snapshot");
        spi_transaction(1'b0, 7'h23, 32'd0, response_frame);
        if (response_frame[39:32] != 0 || !response_frame[30]) begin
            $error("SPI snapshot did not contain muted status");
            errors = errors + 1;
        end
        spi_transaction(1'b0, 7'h20, 32'd0, response_frame);
        if (response_frame[39:32] != 0 || response_frame[18]
            || !response_frame[19]) begin
            $error("first SPI snapshot force-mute/transport flags mismatch");
            errors = errors + 1;
        end
        force_mute = 1'b1;
        spi_transaction(1'b0, 7'h20, 32'd0, response_frame);
        if (response_frame[18]) begin
            $error("force mute tore SPI snapshot");
            errors = errors + 1;
        end
        spi_transaction(1'b1, 7'h04, 32'h0000_0003, response_frame);
        expect_response(8'h00, 32'd0, "second snapshot");
        spi_transaction(1'b0, 7'h20, 32'd0, response_frame);
        if (!response_frame[18]) begin
            $error("second SPI snapshot missed force mute");
            errors = errors + 1;
        end
        spi_transaction(1'b0, 7'h34, 32'd0, response_frame);
        expect_response(8'h00, 32'd11, "transport count snapshot");

        spi_transaction(1'b1, 7'h04, 32'h0000_0005, response_frame);
        expect_response(8'h00, 32'd0, "cross-domain clear");
        repeat (8) @(posedge i2s_bclk);
        #1;
        if (i2s_clear_pulse_count != 1
            || spi_completed_frame_count != 15
            || spi_frame_error_sticky
            || spi_response_underflow_sticky
            || control_bus_error_sticky
            || calibration_rejected_sticky
            || output_ramping || audio_clock_rate_locked
            || audio_clock_rate_error_sticky
            || !rate_fault_mute_active
            || ((^{i2s_dac_lrclk, i2s_dac_serial_data}) === 1'bx)) begin
            $error("unexpected full SPI-top diagnostic frames=%0d clear=%0d",
                   spi_completed_frame_count, i2s_clear_pulse_count);
            errors = errors + 1;
        end

        if (errors != 0)
            $fatal(1, "FAIL: %0d full SPI-top errors", errors);
        $display("PASS: 15 SPI frames plus abort own calibration, snapshots, and I2S clear");
        $finish;
    end

    initial begin
        #400_000ns;
        $fatal(1, "full SPI top timed out");
    end

endmodule

`default_nettype wire
