`timescale 1ns/1ps
`default_nettype none

module i2c_read_register_master_tb;

    /* verilator lint_off BLKSEQ */
    /* verilator lint_off PROCASSINIT */
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic start = 1'b0;
    logic [6:0] device_address = 7'h4c;
    logic [7:0] register_address = 8'h2b;
    logic target_sda_low = 1'b0;
    logic target_scl_low = 1'b0;
    logic scl_drive_low;
    logic sda_drive_low;
    logic busy;
    logic done;
    logic nack;
    logic [7:0] read_data;
    tri1 scl_bus;
    tri1 sda_bus;

    logic [7:0] observed [0:2];

    assign scl_bus = scl_drive_low ? 1'b0 : 1'bz;
    assign scl_bus = target_scl_low ? 1'b0 : 1'bz;
    assign sda_bus = sda_drive_low ? 1'b0 : 1'bz;
    assign sda_bus = target_sda_low ? 1'b0 : 1'bz;

    always #5 clk = !clk;

    i2c_read_register_master #(
        .CLOCK_DIVIDER(1)
    ) dut (
        .clk,
        .rst_n,
        .start,
        .device_address,
        .register_address,
        .scl_in(scl_bus),
        .sda_in(sda_bus),
        .scl_drive_low,
        .sda_drive_low,
        .busy,
        .done,
        .nack,
        .read_data
    );

    task automatic capture_byte(output logic [7:0] value);
        integer bit_number;
        begin
            value = '0;
            for (bit_number = 7; bit_number >= 0; bit_number = bit_number - 1) begin
                @(posedge scl_bus);
                value[bit_number] = sda_bus;
            end
        end
    endtask

    task automatic acknowledge(input logic ack);
        begin
            @(negedge scl_bus);
            target_sda_low = ack;
            @(posedge scl_bus);
            @(negedge scl_bus);
            target_sda_low = 1'b0;
        end
    endtask

    task automatic serve_success(input logic [7:0] response);
        integer bit_number;
        begin
            @(negedge sda_bus);
            if (!scl_bus)
                $fatal(1, "initial START was not asserted while SCL high");
            capture_byte(observed[0]);
            acknowledge(1'b1);
            capture_byte(observed[1]);
            acknowledge(1'b1);

            @(negedge sda_bus);
            if (!scl_bus)
                $fatal(1, "repeated START was not asserted while SCL high");
            capture_byte(observed[2]);
            acknowledge(1'b1);

            target_sda_low = !response[7];
            for (bit_number = 7; bit_number >= 0; bit_number = bit_number - 1) begin
                @(posedge scl_bus);
                if (bit_number > 0) begin
                    @(negedge scl_bus);
                    target_sda_low = !response[bit_number - 1];
                end
            end
            @(negedge scl_bus);
            target_sda_low = 1'b0;
            @(posedge scl_bus);
            if (!sda_bus)
                $fatal(1, "master ACKed final read byte instead of NACKing");
            @(posedge sda_bus);
            if (!scl_bus)
                $fatal(1, "STOP was not released while SCL high");
        end
    endtask

    task automatic serve_address_nack;
        begin
            @(negedge sda_bus);
            capture_byte(observed[0]);
            acknowledge(1'b0);
            @(posedge sda_bus);
        end
    endtask

    task automatic launch;
        begin
            @(negedge clk);
            start = 1'b1;
            @(negedge clk);
            start = 1'b0;
        end
    endtask

    initial begin
        repeat (3) @(posedge clk);
        rst_n = 1'b1;

        fork
            serve_success(8'ha5);
            launch();
        join
        wait (done);
        @(posedge clk);
        if (busy || nack || read_data !== 8'ha5 ||
            observed[0] !== 8'h98 || observed[1] !== 8'h2b || observed[2] !== 8'h99)
            $fatal(1, "successful read protocol/data mismatch");
        if (scl_drive_low || sda_drive_low)
            $fatal(1, "bus not released after successful read");

        register_address = 8'h5e;
        fork
            serve_address_nack();
            launch();
        join
        wait (done);
        @(posedge clk);
        if (busy || !nack || read_data !== 8'h00 || observed[0] !== 8'h98)
            $fatal(1, "address-NACK handling mismatch");
        repeat (100) @(posedge clk);
        if (busy || scl_drive_low || sda_drive_low)
            $fatal(1, "bus held after failed read");

        $display("PASS I2C read: exact repeated-start byte read, final NACK, STOP, and address-NACK abort");
        $finish;
    end

    /* verilator lint_on PROCASSINIT */
    /* verilator lint_on BLKSEQ */

endmodule

`default_nettype wire
