`timescale 1ns/1ps
`default_nettype none

module spi_control_transport_tb;
    localparam time SPI_HALF_PERIOD = 100ns;

    logic fabric_clk;
    logic fabric_rst_n = 1'b0;
    logic spi_cs_n = 1'b1;
    logic spi_sclk = 1'b0;
    logic spi_mosi = 1'b0;
    logic spi_miso;
    logic control_request_valid;
    logic control_request_write;
    logic [7:0] control_request_address;
    logic [31:0] control_request_write_data;
    logic register_response_valid;
    logic [31:0] register_response_read_data;
    logic register_response_error;
    logic control_response_valid;
    logic [31:0] control_response_read_data;
    logic control_response_error;
    logic clear_diagnostics;
    logic frame_error_sticky;
    logic response_underflow_sticky;
    logic [31:0] completed_frame_count;
    logic [31:0] diagnostic_words_flat = '0;
    logic diagnostic_capture_available = 1'b1;
    logic diagnostic_capture_request;
    logic diagnostic_capture_valid;
    logic output_muted = 1'b1;
    logic output_ramping = 1'b0;
    logic mute_request;
    logic fabric_clear_diagnostics;
    logic signed [31:0] calibration_candidate_input_peak_q24;
    logic signed [31:0] calibration_candidate_output_reciprocal_q24;
    logic calibration_update_valid;
    logic calibration_update_ack;
    logic calibration_invalid_update_sticky;
    logic calibration_unsafe_update_sticky;
    logic signed [31:0] calibration_active_input_peak_q24;
    logic signed [31:0] calibration_active_output_reciprocal_q24;
    logic [31:0] snapshot_sequence;
    logic [31:0] calibration_commit_sequence;
    logic [31:0] calibration_accepted_sequence;
    logic bus_error_sticky;
    logic calibration_rejected_sticky;
    logic snapshot_capture_timeout_sticky;
    logic hold_response = 1'b0;
    logic [39:0] response_frame;
    integer errors = 0;
    integer bit_index;

    initial begin
        fabric_clk = 1'b0;
        forever #5ns fabric_clk = ~fabric_clk;
    end

    assign control_response_valid = register_response_valid && !hold_response;
    assign control_response_read_data = register_response_read_data;
    assign control_response_error = register_response_error;
    assign clear_diagnostics = fabric_clear_diagnostics;

    spi_control_transport transport (.*);

    phono_control_registers #(
        .DIAGNOSTIC_WORD_COUNT(1)
    ) registers (
        .clk(fabric_clk),
        .rst_n(fabric_rst_n),
        .request_valid(control_request_valid),
        .request_write(control_request_write),
        .request_address(control_request_address),
        .request_write_data(control_request_write_data),
        .response_valid(register_response_valid),
        .response_read_data(register_response_read_data),
        .response_error(register_response_error),
        .diagnostic_words_flat,
        .diagnostic_capture_available,
        .diagnostic_capture_request,
        .diagnostic_capture_valid,
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
        .snapshot_sequence,
        .calibration_commit_sequence,
        .calibration_accepted_sequence,
        .bus_error_sticky,
        .calibration_rejected_sticky,
        .snapshot_capture_timeout_sticky
    );

    always_ff @(posedge fabric_clk or negedge fabric_rst_n) begin
        if (!fabric_rst_n)
            diagnostic_capture_valid <= 1'b0;
        else
            diagnostic_capture_valid <= diagnostic_capture_request;
    end

    calibration_commit_guard calibration_guard (
        .clk(fabric_clk),
        .rst_n(fabric_rst_n),
        .candidate_input_peak_q24(calibration_candidate_input_peak_q24),
        .candidate_output_reciprocal_q24(
            calibration_candidate_output_reciprocal_q24
        ),
        .update_valid(calibration_update_valid),
        .output_muted,
        .clear_diagnostics(fabric_clear_diagnostics),
        .active_input_peak_q24(calibration_active_input_peak_q24),
        .active_output_reciprocal_q24(
            calibration_active_output_reciprocal_q24
        ),
        .update_ack(calibration_update_ack),
        .invalid_update_sticky(calibration_invalid_update_sticky),
        .unsafe_update_sticky(calibration_unsafe_update_sticky)
    );

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
        repeat (4) @(posedge fabric_clk);

        spi_transaction(1'b0, 7'h00, 32'd0, response_frame);
        expect_response(8'h00, 32'h4650_4741, "identity");

        spi_transaction(1'b1, 7'h08, 32'd335544, response_frame);
        expect_response(8'h00, 32'd0, "input shadow");
        spi_transaction(1'b1, 7'h09, 32'd2097152, response_frame);
        expect_response(8'h00, 32'd0, "output shadow");
        spi_transaction(1'b1, 7'h0a, 32'd1, response_frame);
        expect_response(8'h00, 32'd0, "calibration commit");
        repeat (6) @(posedge fabric_clk);
        spi_transaction(1'b0, 7'h0b, 32'd0, response_frame);
        expect_response(8'h00, 32'd335544, "active calibration");

        spi_transaction(1'b0, 7'h7f, 32'd0, response_frame);
        expect_response(8'h01, 32'd0, "bad address");

        // Abort after ten clocks and prove the incomplete frame is retained.
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
        if (!frame_error_sticky) begin
            $error("short SPI frame was not retained");
            errors = errors + 1;
        end

        // Withhold the bus reply across the first response edge.
        hold_response = 1'b1;
        spi_transaction(1'b0, 7'h00, 32'd0, response_frame);
        hold_response = 1'b0;
        if (!response_underflow_sticky) begin
            $error("withheld register response did not flag underflow");
            errors = errors + 1;
        end

        // Register control bit 2 clears both transport diagnostics through the
        // same fabric pulse used by the rest of the hierarchy.
        spi_transaction(1'b1, 7'h04, 32'h0000_0005, response_frame);
        expect_response(8'h00, 32'd0, "diagnostic clear");
        repeat (3) @(posedge fabric_clk);
        if (frame_error_sticky || response_underflow_sticky
            || completed_frame_count != 8 || !mute_request
            || snapshot_sequence != 0
            || calibration_commit_sequence != 1
            || calibration_accepted_sequence != 1
            || !bus_error_sticky || calibration_rejected_sticky
            || snapshot_capture_timeout_sticky) begin
            $error("transport diagnostics/count mismatch frames=%0d",
                   completed_frame_count);
            errors = errors + 1;
        end

        if (errors != 0)
            $fatal(1, "FAIL: %0d SPI transport errors", errors);
        $display("PASS: read/write/error/short/underflow over 8 complete frames");
        $finish;
    end

    initial begin
        #300_000ns;
        $fatal(1, "SPI control transport timed out");
    end

endmodule

`default_nettype wire
