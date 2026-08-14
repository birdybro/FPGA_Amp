`default_nettype none

module spi_control_transport_formal (
    input logic fabric_clk,
    output logic frame_error_sticky,
    output logic response_underflow_sticky,
    output logic ever_request
);
    (* anyseq *) logic fabric_rst_n;
    (* anyseq *) logic spi_cs_n;
    (* anyseq *) logic spi_sclk;
    (* anyseq *) logic spi_mosi;
    (* anyseq *) logic control_response_valid;
    (* anyseq *) logic [31:0] control_response_read_data;
    (* anyseq *) logic control_response_error;
    (* anyseq *) logic clear_diagnostics;

    logic spi_miso;
    logic control_request_valid;
    logic control_request_write;
    logic [7:0] control_request_address;
    logic [31:0] control_request_write_data;
    logic [31:0] completed_frame_count;
    logic past_valid = 1'b0;

    always_ff @(posedge fabric_clk) begin
        if (!past_valid)
            assume (!fabric_rst_n);
        else
            assume (fabric_rst_n);
        past_valid <= 1'b1;

        if (!fabric_rst_n)
            ever_request <= 1'b0;
        else if (control_request_valid)
            ever_request <= 1'b1;
    end

    spi_control_transport dut (.*);

endmodule

`default_nettype wire
