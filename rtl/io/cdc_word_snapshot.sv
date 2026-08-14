`timescale 1ns/1ps
`default_nettype none

// Coherent held-bus snapshot across unrelated clock domains. A four-phase
// request/acknowledge handshake guarantees that destination_snapshot_hold does
// not change while its bits traverse the source-domain synchronizers. The
// source emits valid only one extra clock after observing acknowledge, giving
// the data synchronizers a complete settling edge.
module cdc_word_snapshot #(
    parameter int unsigned WIDTH = 16
) (
    input  logic                 source_clk,
    input  logic                 source_rst_n,
    input  logic                 source_request,
    output logic                 source_available,
    output logic                 source_snapshot_valid,
    output logic [WIDTH-1:0]     source_snapshot_data,

    input  logic                 destination_clk,
    input  logic                 destination_rst_n,
    input  logic [WIDTH-1:0]     destination_live_data
);

    initial begin
        if (WIDTH == 0)
            $error("WIDTH must be positive");
    end

    logic source_request_level;
    logic source_transaction_active;
    logic source_capture_pending;

    (* ASYNC_REG = "TRUE" *) logic destination_acknowledge_meta;
    (* ASYNC_REG = "TRUE" *) logic destination_acknowledge_sync;
    (* ASYNC_REG = "TRUE" *) logic destination_idle_meta;
    (* ASYNC_REG = "TRUE" *) logic destination_idle_sync;
    (* ASYNC_REG = "TRUE" *) logic [WIDTH-1:0] destination_data_meta;
    (* ASYNC_REG = "TRUE" *) logic [WIDTH-1:0] destination_data_sync;

    logic destination_acknowledge_level;
    logic destination_idle;
    logic [WIDTH-1:0] destination_snapshot_hold;
    (* ASYNC_REG = "TRUE" *) logic source_request_meta;
    (* ASYNC_REG = "TRUE" *) logic source_request_sync;

    assign source_available = destination_idle_sync
        && !destination_acknowledge_sync
        && !source_request_level
        && !source_transaction_active
        && !source_capture_pending;

    always_ff @(posedge source_clk or negedge source_rst_n) begin
        if (!source_rst_n) begin
            source_request_level <= 1'b0;
            source_transaction_active <= 1'b0;
            source_capture_pending <= 1'b0;
            source_snapshot_valid <= 1'b0;
            source_snapshot_data <= '0;
            destination_acknowledge_meta <= 1'b0;
            destination_acknowledge_sync <= 1'b0;
            destination_idle_meta <= 1'b0;
            destination_idle_sync <= 1'b0;
            destination_data_meta <= '0;
            destination_data_sync <= '0;
        end else begin
            destination_acknowledge_meta <=
                destination_acknowledge_level;
            destination_acknowledge_sync <=
                destination_acknowledge_meta;
            destination_idle_meta <= destination_idle;
            destination_idle_sync <= destination_idle_meta;
            destination_data_meta <= destination_snapshot_hold;
            destination_data_sync <= destination_data_meta;
            source_snapshot_valid <= 1'b0;

            if (source_request && source_available) begin
                source_request_level <= 1'b1;
                source_transaction_active <= 1'b1;
            end

            if (source_transaction_active
                && destination_acknowledge_sync) begin
                source_request_level <= 1'b0;
                source_transaction_active <= 1'b0;
                source_capture_pending <= 1'b1;
            end else if (source_capture_pending) begin
                source_snapshot_data <= destination_data_sync;
                source_snapshot_valid <= 1'b1;
                source_capture_pending <= 1'b0;
            end
        end
    end

    always_ff @(posedge destination_clk or negedge destination_rst_n) begin
        if (!destination_rst_n) begin
            source_request_meta <= 1'b0;
            source_request_sync <= 1'b0;
            destination_acknowledge_level <= 1'b0;
            destination_idle <= 1'b1;
            destination_snapshot_hold <= '0;
        end else begin
            source_request_meta <= source_request_level;
            source_request_sync <= source_request_meta;

            if (source_request_sync
                && !destination_acknowledge_level) begin
                destination_snapshot_hold <= destination_live_data;
                destination_acknowledge_level <= 1'b1;
            end else if (!source_request_sync
                         && destination_acknowledge_level) begin
                destination_acknowledge_level <= 1'b0;
            end
            destination_idle <= !source_request_sync
                && !destination_acknowledge_level;
        end
    end

endmodule

`default_nettype wire
