`timescale 1ns/1ps
`default_nettype none

// SPI mode-0 transport for the protocol-neutral control bus. The asynchronous
// pins are oversampled in fabric_clk; no SPI-derived fabric clock is created.
// Each CS-low frame is exactly 80 bits, MSB first:
//   request:  [write, address[6:0]], write_data[31:0]
//   response: status[7:0] (bit 0 = bus error), read_data[31:0]
// The SPI clock must be slow enough for synchronized edge detection and for the
// one-clock register response to arrive before the response half of the frame.
module spi_control_transport (
    input  logic                 fabric_clk,
    input  logic                 fabric_rst_n,
    input  logic                 spi_cs_n,
    input  logic                 spi_sclk,
    input  logic                 spi_mosi,
    output logic                 spi_miso,

    output logic                 control_request_valid,
    output logic                 control_request_write,
    output logic [7:0]           control_request_address,
    output logic [31:0]          control_request_write_data,
    input  logic                 control_response_valid,
    input  logic [31:0]          control_response_read_data,
    input  logic                 control_response_error,

    input  logic                 clear_diagnostics,
    output logic                 frame_error_sticky,
    output logic                 response_underflow_sticky,
    output logic [31:0]          completed_frame_count
);

    (* ASYNC_REG = "TRUE" *) logic cs_meta;
    (* ASYNC_REG = "TRUE" *) logic cs_sync;
    (* ASYNC_REG = "TRUE" *) logic sclk_meta;
    (* ASYNC_REG = "TRUE" *) logic sclk_sync;
    (* ASYNC_REG = "TRUE" *) logic mosi_meta;
    (* ASYNC_REG = "TRUE" *) logic mosi_sync;
    logic cs_previous;
    logic sclk_previous;
    logic [6:0] bit_count;
    logic [38:0] request_shift;
    logic [39:0] response_shift;
    logic awaiting_response;
    logic response_ready;

    function automatic logic [31:0] increment_saturating(
        input logic [31:0] value
    );
        begin
            increment_saturating = (&value) ? value : value + 32'd1;
        end
    endfunction

    always_ff @(posedge fabric_clk or negedge fabric_rst_n) begin
        if (!fabric_rst_n) begin
            cs_meta <= 1'b1;
            cs_sync <= 1'b1;
            sclk_meta <= 1'b0;
            sclk_sync <= 1'b0;
            mosi_meta <= 1'b0;
            mosi_sync <= 1'b0;
            cs_previous <= 1'b1;
            sclk_previous <= 1'b0;
            bit_count <= '0;
            request_shift <= '0;
            response_shift <= '0;
            awaiting_response <= 1'b0;
            response_ready <= 1'b0;
            spi_miso <= 1'b0;
            control_request_valid <= 1'b0;
            control_request_write <= 1'b0;
            control_request_address <= '0;
            control_request_write_data <= '0;
            frame_error_sticky <= 1'b0;
            response_underflow_sticky <= 1'b0;
            completed_frame_count <= '0;
        end else begin
            cs_meta <= spi_cs_n;
            cs_sync <= cs_meta;
            sclk_meta <= spi_sclk;
            sclk_sync <= sclk_meta;
            mosi_meta <= spi_mosi;
            mosi_sync <= mosi_meta;
            cs_previous <= cs_sync;
            sclk_previous <= sclk_sync;
            control_request_valid <= 1'b0;

            if (clear_diagnostics) begin
                frame_error_sticky <= 1'b0;
                response_underflow_sticky <= 1'b0;
            end

            if (control_response_valid && awaiting_response) begin
                response_shift <= {
                    7'd0,
                    control_response_error,
                    control_response_read_data
                };
                awaiting_response <= 1'b0;
                response_ready <= 1'b1;
            end

            if (cs_sync) begin
                spi_miso <= 1'b0;
                if (!cs_previous && bit_count != 0 && bit_count != 7'd80)
                    frame_error_sticky <= 1'b1;
                bit_count <= '0;
                request_shift <= '0;
                response_shift <= '0;
                awaiting_response <= 1'b0;
                response_ready <= 1'b0;
            end else if (cs_previous) begin
                // Synchronized falling CS starts a fresh frame. SCLK must be
                // at its mode-0 idle level before CS assertion.
                bit_count <= '0;
                request_shift <= '0;
                response_shift <= '0;
                awaiting_response <= 1'b0;
                response_ready <= 1'b0;
                spi_miso <= 1'b0;
            end else begin
                if (!sclk_previous && sclk_sync) begin
                    if (bit_count < 7'd40) begin
                        request_shift <= {request_shift[37:0], mosi_sync};
                        bit_count <= bit_count + 7'd1;
                        if (bit_count == 7'd39) begin
                            control_request_write <= request_shift[38];
                            control_request_address <= {
                                1'b0, request_shift[37:31]
                            };
                            control_request_write_data <= {
                                request_shift[30:0], mosi_sync
                            };
                            control_request_valid <= 1'b1;
                            awaiting_response <= 1'b1;
                        end
                    end else if (bit_count < 7'd80) begin
                        bit_count <= bit_count + 7'd1;
                        if (bit_count == 7'd79)
                            completed_frame_count <= increment_saturating(
                                completed_frame_count
                            );
                    end
                end

                if (sclk_previous && !sclk_sync
                    && bit_count >= 7'd40 && bit_count < 7'd80) begin
                    if (response_ready) begin
                        spi_miso <= response_shift[39];
                        response_shift <= {response_shift[38:0], 1'b0};
                    end else if (control_response_valid
                                 && awaiting_response) begin
                        // A response arriving on this exact fabric edge still
                        // meets the first response bit without a false miss.
                        spi_miso <= 1'b0;
                        response_shift <= {
                            6'd0,
                            control_response_error,
                            control_response_read_data,
                            1'b0
                        };
                        awaiting_response <= 1'b0;
                        response_ready <= 1'b1;
                    end else begin
                        spi_miso <= 1'b0;
                        if (!clear_diagnostics)
                            response_underflow_sticky <= 1'b1;
                    end
                end
            end
        end
    end

endmodule

`default_nettype wire
