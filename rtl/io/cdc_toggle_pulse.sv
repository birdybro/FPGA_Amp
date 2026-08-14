`timescale 1ns/1ps
`default_nettype none

// Transfer an idempotent command pulse between unrelated clock domains. Source
// pulses must be separated long enough for the toggle to cross two destination
// synchronizer stages and be observed; this is appropriate for host commands,
// not a high-rate event stream.
module cdc_toggle_pulse (
    input  logic source_clk,
    input  logic source_rst_n,
    input  logic source_pulse,
    input  logic destination_clk,
    input  logic destination_rst_n,
    output logic destination_pulse
);

    logic source_toggle;
    (* ASYNC_REG = "TRUE" *) logic destination_meta;
    (* ASYNC_REG = "TRUE" *) logic destination_sync;
    logic destination_seen;

    always_ff @(posedge source_clk or negedge source_rst_n) begin
        if (!source_rst_n)
            source_toggle <= 1'b0;
        else if (source_pulse)
            source_toggle <= ~source_toggle;
    end

    always_ff @(posedge destination_clk or negedge destination_rst_n) begin
        if (!destination_rst_n) begin
            destination_meta <= 1'b0;
            destination_sync <= 1'b0;
            destination_seen <= 1'b0;
            destination_pulse <= 1'b0;
        end else begin
            destination_meta <= source_toggle;
            destination_sync <= destination_meta;
            destination_seen <= destination_sync;
            destination_pulse <= destination_sync ^ destination_seen;
        end
    end

endmodule

`default_nettype wire
