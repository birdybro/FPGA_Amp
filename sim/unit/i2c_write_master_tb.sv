`timescale 1ns/1ps
`default_nettype none

module i2c_write_master_tb;

    /* verilator lint_off BLKSEQ */
    /* verilator lint_off PROCASSINIT */
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic start = 1'b0;
    logic [6:0] device_address = 7'h3b;
    logic [15:0] register_address = 16'h4015;
    logic [7:0] write_data = 8'h00;
    logic scl_drive_low;
    logic sda_drive_low;
    logic target_sda_low = 1'b0;
    logic target_scl_low = 1'b0;
    logic busy;
    logic done;
    logic nack;
    tri1 scl_bus;
    tri1 sda_bus;

    logic target_active = 1'b0;
    logic ack_pending = 1'b0;
    logic ack_active = 1'b0;
    integer active_bit_count = 0;
    integer active_byte_count = 0;
    integer transaction_count = 0;
    integer nack_byte_index = -1;
    logic [7:0] shift_byte = '0;
    logic [7:0] captured [0:11][0:3];

    assign scl_bus = scl_drive_low ? 1'b0 : 1'bz;
    assign scl_bus = target_scl_low ? 1'b0 : 1'bz;
    assign sda_bus = sda_drive_low ? 1'b0 : 1'bz;
    assign sda_bus = target_sda_low ? 1'b0 : 1'bz;

    always #5 clk = !clk;

    i2c_write_master #(
        .CLOCK_DIVIDER(2)
    ) dut (
        .clk,
        .rst_n,
        .start,
        .device_address,
        .register_address,
        .write_data,
        .scl_in(scl_bus),
        .sda_in(sda_bus),
        .scl_drive_low,
        .sda_drive_low,
        .busy,
        .done,
        .nack
    );

    always @(negedge sda_bus) begin
        if (scl_bus && !target_active) begin
            target_active = 1'b1;
            active_bit_count = 0;
            active_byte_count = 0;
            shift_byte = '0;
            ack_pending = 1'b0;
            ack_active = 1'b0;
        end
    end

    always @(posedge scl_bus) begin
        if (target_active && !ack_active) begin
            shift_byte = {shift_byte[6:0], sda_bus};
            if (active_bit_count == 7) begin
                captured[transaction_count][active_byte_count] = shift_byte;
                active_bit_count = 0;
                ack_pending = 1'b1;
            end else begin
                active_bit_count = active_bit_count + 1;
            end
        end
    end

    always @(negedge scl_bus) begin
        if (target_active) begin
            if (ack_active) begin
                target_sda_low = 1'b0;
                ack_active = 1'b0;
                active_byte_count = active_byte_count + 1;
            end else if (ack_pending) begin
                target_sda_low = active_byte_count != nack_byte_index;
                ack_pending = 1'b0;
                ack_active = 1'b1;
            end
        end
    end

    always @(posedge sda_bus) begin
        if (scl_bus && target_active && !sda_drive_low) begin
            target_active = 1'b0;
            target_sda_low = 1'b0;
            transaction_count = transaction_count + 1;
        end
    end

    task automatic launch_write(
        input logic [15:0] requested_register,
        input logic [7:0] requested_data
    );
        begin
            @(negedge clk);
            register_address = requested_register;
            write_data = requested_data;
            start = 1'b1;
            @(negedge clk);
            start = 1'b0;
            wait (done);
            @(posedge clk);
        end
    endtask

    task automatic check_transaction(
        input integer index,
        input logic [15:0] expected_register,
        input logic [7:0] expected_data
    );
        begin
            if (captured[index][0] !== 8'h76 ||
                captured[index][1] !== expected_register[15:8] ||
                captured[index][2] !== expected_register[7:0] ||
                captured[index][3] !== expected_data)
                $fatal(1, "transaction %0d mismatch: %02x %02x %02x %02x",
                       index, captured[index][0], captured[index][1],
                       captured[index][2], captured[index][3]);
        end
    endtask

    initial begin
        repeat (3) @(posedge clk);
        rst_n = 1'b1;

        launch_write(16'h4015, 8'h00);
        if (busy || nack || transaction_count != 1)
            $fatal(1, "acknowledged transaction status mismatch");
        check_transaction(0, 16'h4015, 8'h00);

        nack_byte_index = 2;
        launch_write(16'h40f9, 8'h7f);
        if (!nack || transaction_count != 2)
            $fatal(1, "NACK was not retained through stop");
        check_transaction(1, 16'h40f9, 8'h7f);

        nack_byte_index = -1;
        launch_write(16'h4025, 8'he4);
        if (nack || transaction_count != 3)
            $fatal(1, "NACK did not clear on a new transaction");
        check_transaction(2, 16'h4025, 8'he4);

        $display("PASS I2C writer: exact bytes, ACK, NACK, and recovery");
        $finish;
    end

    /* verilator lint_on PROCASSINIT */
    /* verilator lint_on BLKSEQ */

endmodule

`default_nettype wire
