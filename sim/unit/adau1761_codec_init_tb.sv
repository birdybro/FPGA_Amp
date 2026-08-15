`timescale 1ns/1ps
`default_nettype none

module adau1761_codec_init_tb;

    /* verilator lint_off BLKSEQ */
    /* verilator lint_off PROCASSINIT */
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic target_sda_low = 1'b0;
    logic target_scl_low = 1'b0;
    logic scl_drive_low;
    logic sda_drive_low;
    logic busy;
    logic configured;
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
    logic [7:0] captured [0:31][0:3];

    assign scl_bus = scl_drive_low ? 1'b0 : 1'bz;
    assign scl_bus = target_scl_low ? 1'b0 : 1'bz;
    assign sda_bus = sda_drive_low ? 1'b0 : 1'bz;
    assign sda_bus = target_sda_low ? 1'b0 : 1'bz;

    always #5 clk = !clk;

    adau1761_codec_init #(
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
        .configured,
        .error,
        .sequence_index,
        .failed_index
    );

    function automatic logic [15:0] expected_register(input integer index);
        case (index)
            0: expected_register = 16'h4000;
            1: expected_register = 16'h4025;
            2: expected_register = 16'h4026;
            3: expected_register = 16'h4015;
            4: expected_register = 16'h4016;
            5: expected_register = 16'h4017;
            6: expected_register = 16'h40f8;
            7: expected_register = 16'h400a;
            8: expected_register = 16'h400b;
            9: expected_register = 16'h400c;
            10: expected_register = 16'h400d;
            11: expected_register = 16'h4019;
            12: expected_register = 16'h402a;
            13: expected_register = 16'h4029;
            14: expected_register = 16'h40f2;
            15: expected_register = 16'h40f3;
            16: expected_register = 16'h401c;
            17: expected_register = 16'h401d;
            18: expected_register = 16'h401e;
            19: expected_register = 16'h401f;
            20: expected_register = 16'h4020;
            21: expected_register = 16'h4021;
            22: expected_register = 16'h40f4;
            23: expected_register = 16'h40f9;
            24: expected_register = 16'h40fa;
            25: expected_register = 16'h4025;
            default: expected_register = 16'h4026;
        endcase
    endfunction

    function automatic logic [7:0] expected_data(input integer index);
        case (index)
            0: expected_data = 8'h01;
            1, 2: expected_data = 8'he4;
            3, 4, 5, 6: expected_data = 8'h00;
            7: expected_data = 8'h01;
            8: expected_data = 8'h05;
            9: expected_data = 8'h01;
            10: expected_data = 8'h05;
            11: expected_data = 8'h13;
            12, 13: expected_data = 8'h03;
            14, 15: expected_data = 8'h01;
            16: expected_data = 8'h21;
            17: expected_data = 8'h00;
            18: expected_data = 8'h41;
            19: expected_data = 8'h00;
            20: expected_data = 8'h03;
            21: expected_data = 8'h09;
            22: expected_data = 8'h00;
            23: expected_data = 8'h7f;
            24: expected_data = 8'h01;
            default: expected_data = 8'he6;
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
            for (row = 0; row < 32; row = row + 1)
                for (column = 0; column < 4; column = column + 1)
                    captured[row][column] = '0;
        end
    endtask

    task automatic verify_transaction(input integer index);
        logic [15:0] register_address;
        begin
            register_address = expected_register(index);
            if (captured[index][0] !== 8'h76 ||
                captured[index][1] !== register_address[15:8] ||
                captured[index][2] !== register_address[7:0] ||
                captured[index][3] !== expected_data(index))
                $fatal(1, "sequence %0d mismatch: %02x %02x %02x %02x",
                       index, captured[index][0], captured[index][1],
                       captured[index][2], captured[index][3]);
        end
    endtask

    integer index;
    initial begin
        clear_target();
        repeat (3) @(posedge clk);
        rst_n = 1'b1;

        wait (configured || error);
        @(posedge clk);
        if (!configured || error || busy || transaction_count != 27 ||
            sequence_index != 26)
            $fatal(1, "successful startup status mismatch");
        for (index = 0; index < 27; index = index + 1)
            verify_transaction(index);

        @(negedge clk);
        rst_n = 1'b0;
        repeat (2) @(posedge clk);
        clear_target();
        nack_transaction = 5;
        @(negedge clk);
        rst_n = 1'b1;

        wait (configured || error);
        @(posedge clk);
        if (configured || !error || busy || transaction_count != 6 ||
            failed_index != 5 || sequence_index != 5)
            $fatal(1, "NACK abort status mismatch");
        for (index = 0; index < 6; index = index + 1)
            verify_transaction(index);
        repeat (200) @(posedge clk);
        if (transaction_count != 6)
            $fatal(1, "writes continued after NACK");

        $display("PASS ADAU1761 init: exact 27 writes and fail-closed NACK abort");
        $finish;
    end

    /* verilator lint_on PROCASSINIT */
    /* verilator lint_on BLKSEQ */

endmodule

`default_nettype wire
