`timescale 1ns/1ps
`default_nettype none

module pcm5242_dac_init_tb;

    /* verilator lint_off BLKSEQ */
    /* verilator lint_off PROCASSINIT */
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic target_sda_low = 1'b0;
    logic target_scl_low = 1'b0;
    logic scl_drive_low;
    logic sda_drive_low;
    logic busy;
    logic configuration_written;
    logic error;
    logic [4:0] sequence_index;
    logic [4:0] failed_index;
    tri1 scl_bus;
    tri1 sda_bus;

    logic target_active = 1'b0;
    logic ack_pending = 1'b0;
    logic ack_active = 1'b0;
    integer active_bit_count = 0;
    integer active_byte_count = 0;
    integer transaction_count = 0;
    integer nack_transaction = -1;
    logic [7:0] shift_byte = '0;
    logic [7:0] captured [0:23][0:2];

    assign scl_bus = scl_drive_low ? 1'b0 : 1'bz;
    assign scl_bus = target_scl_low ? 1'b0 : 1'bz;
    assign sda_bus = sda_drive_low ? 1'b0 : 1'bz;
    assign sda_bus = target_sda_low ? 1'b0 : 1'bz;

    always #5 clk = !clk;

    pcm5242_dac_init #(
        .STARTUP_DELAY_CYCLES(3),
        .I2C_CLOCK_DIVIDER(1)
    ) dut (
        .clk,
        .rst_n,
        .scl_in(scl_bus),
        .sda_in(sda_bus),
        .scl_drive_low,
        .sda_drive_low,
        .busy,
        .configuration_written,
        .error,
        .sequence_index,
        .failed_index
    );

    function automatic logic [7:0] expected_register(input integer index);
        case (index)
            0: expected_register = 8'h00;
            1: expected_register = 8'h03;
            2: expected_register = 8'h04;
            3: expected_register = 8'h07;
            4: expected_register = 8'h28;
            5: expected_register = 8'h29;
            6: expected_register = 8'h2a;
            7: expected_register = 8'h2b;
            8: expected_register = 8'h3c;
            9: expected_register = 8'h3d;
            10: expected_register = 8'h3e;
            11: expected_register = 8'h41;
            12: expected_register = 8'h00;
            13: expected_register = 8'h01;
            14: expected_register = 8'h02;
            15: expected_register = 8'h06;
            16: expected_register = 8'h07;
            17: expected_register = 8'h00;
            18: expected_register = 8'h02;
            default: expected_register = 8'h03;
        endcase
    endfunction

    function automatic logic [7:0] expected_data(input integer index);
        case (index)
            0: expected_data = 8'h00;
            1: expected_data = 8'h11;
            2: expected_data = 8'h00;
            3: expected_data = 8'h00;
            4: expected_data = 8'h02;
            5: expected_data = 8'h00;
            6: expected_data = 8'h11;
            7: expected_data = 8'h01;
            8: expected_data = 8'h00;
            9, 10: expected_data = 8'h30;
            11: expected_data = 8'h00;
            12: expected_data = 8'h01;
            default: expected_data = 8'h00;
        endcase
    endfunction

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
                target_sda_low = transaction_count != nack_transaction;
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

    task automatic clear_target;
        integer row;
        integer column;
        begin
            target_sda_low = 1'b0;
            target_scl_low = 1'b0;
            target_active = 1'b0;
            ack_pending = 1'b0;
            ack_active = 1'b0;
            active_bit_count = 0;
            active_byte_count = 0;
            transaction_count = 0;
            shift_byte = '0;
            for (row = 0; row < 24; row = row + 1)
                for (column = 0; column < 3; column = column + 1)
                    captured[row][column] = '0;
        end
    endtask

    task automatic verify_transaction(input integer index);
        begin
            if (captured[index][0] !== 8'h98 ||
                captured[index][1] !== expected_register(index) ||
                captured[index][2] !== expected_data(index))
                $fatal(1, "sequence %0d mismatch: %02x %02x %02x",
                       index, captured[index][0], captured[index][1], captured[index][2]);
        end
    endtask

    integer index;
    initial begin
        clear_target();
        repeat (3) @(posedge clk);
        rst_n = 1'b1;

        wait (configuration_written || error);
        @(posedge clk);
        if (!configuration_written || error || busy || transaction_count != 20 ||
            sequence_index != 19 || scl_drive_low || sda_drive_low)
            $fatal(1, "successful startup status mismatch");
        for (index = 0; index < 20; index = index + 1)
            verify_transaction(index);

        @(negedge clk);
        rst_n = 1'b0;
        repeat (2) @(posedge clk);
        clear_target();
        nack_transaction = 6;
        @(negedge clk);
        rst_n = 1'b1;

        wait (configuration_written || error);
        @(posedge clk);
        if (configuration_written || !error || busy || transaction_count != 7 ||
            failed_index != 6 || sequence_index != 6)
            $fatal(1, "NACK abort status mismatch");
        for (index = 0; index < 7; index = index + 1)
            verify_transaction(index);
        repeat (150) @(posedge clk);
        if (transaction_count != 7 || scl_drive_low || sda_drive_low)
            $fatal(1, "writes continued or bus held after NACK");

        $display("PASS PCM5242 init: exact 20 one-byte-register writes and fail-closed NACK abort");
        $finish;
    end

    /* verilator lint_on PROCASSINIT */
    /* verilator lint_on BLKSEQ */

endmodule

`default_nettype wire
