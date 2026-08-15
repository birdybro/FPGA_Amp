`timescale 1ns/1ps
`default_nettype none

module pcm5242_dac_verify_tb;

    /* verilator lint_off BLKSEQ */
    /* verilator lint_off PROCASSINIT */
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic start = 1'b0;
    logic target_sda_low = 1'b0;
    logic target_scl_low = 1'b0;
    logic scl_drive_low;
    logic sda_drive_low;
    logic busy;
    logic configuration_verified;
    logic error;
    logic nack_error;
    logic mismatch_error;
    logic [4:0] sequence_index;
    logic [4:0] failed_index;
    logic [7:0] failed_observed;
    logic [7:0] failed_expected;
    logic [7:0] failed_mask;
    logic [7:0] clock_status;
    logic [7:0] power_status;
    tri1 scl_bus;
    tri1 sda_bus;

    logic [7:0] captured [0:31][0:2];
    integer transaction_count = 0;

    assign scl_bus = scl_drive_low ? 1'b0 : 1'bz;
    assign scl_bus = target_scl_low ? 1'b0 : 1'bz;
    assign sda_bus = sda_drive_low ? 1'b0 : 1'bz;
    assign sda_bus = target_sda_low ? 1'b0 : 1'bz;

    always #5 clk = !clk;

    pcm5242_dac_verify #(
        .I2C_CLOCK_DIVIDER(1)
    ) dut (
        .clk,
        .rst_n,
        .start,
        .scl_in(scl_bus),
        .sda_in(sda_bus),
        .scl_drive_low,
        .sda_drive_low,
        .busy,
        .configuration_verified,
        .error,
        .nack_error,
        .mismatch_error,
        .sequence_index,
        .failed_index,
        .failed_observed,
        .failed_expected,
        .failed_mask,
        .clock_status,
        .power_status
    );

    function automatic logic is_write(input integer index);
        is_write = index == 0 || index == 13 || index == 18;
    endfunction

    function automatic logic [7:0] expected_register(input integer index);
        case (index)
            0: expected_register = 8'h00;
            1: expected_register = 8'h02;
            2: expected_register = 8'h03;
            3: expected_register = 8'h04;
            4: expected_register = 8'h07;
            5: expected_register = 8'h28;
            6: expected_register = 8'h29;
            7: expected_register = 8'h2a;
            8: expected_register = 8'h2b;
            9: expected_register = 8'h3c;
            10: expected_register = 8'h3d;
            11: expected_register = 8'h3e;
            12: expected_register = 8'h41;
            13: expected_register = 8'h00;
            14: expected_register = 8'h01;
            15: expected_register = 8'h02;
            16: expected_register = 8'h06;
            17: expected_register = 8'h07;
            18: expected_register = 8'h00;
            19: expected_register = 8'h5b;
            20: expected_register = 8'h5c;
            21: expected_register = 8'h5d;
            22: expected_register = 8'h5e;
            default: expected_register = 8'h76;
        endcase
    endfunction

    function automatic logic [7:0] expected_write_data(input integer index);
        expected_write_data = index == 13 ? 8'h01 : 8'h00;
    endfunction

    function automatic logic [7:0] expected_response(input integer index);
        case (index)
            1, 2, 4, 6, 9, 12, 14, 15, 16, 17, 20:
                expected_response = 8'h00;
            3: expected_response = 8'h10;
            5: expected_response = 8'h02;
            7: expected_response = 8'h11;
            8: expected_response = 8'h01;
            10, 11: expected_response = 8'h30;
            19: expected_response = 8'h38;
            21: expected_response = 8'h40;
            22: expected_response = 8'h20;
            default: expected_response = 8'h85;
        endcase
    endfunction

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

    task automatic wait_for_stop;
        begin
            do begin
                @(posedge sda_bus);
            end while (!scl_bus);
        end
    endtask

    task automatic serve_operation(
        input integer index,
        input integer corrupt_index,
        input integer nack_index
    );
        logic [7:0] response;
        integer bit_number;
        begin
            @(negedge sda_bus);
            if (!scl_bus)
                $fatal(1, "operation %0d START was not asserted while SCL high", index);
            capture_byte(captured[index][0]);
            if (captured[index][0] !== 8'h98)
                $fatal(1, "operation %0d write address mismatch", index);

            if (index == nack_index) begin
                acknowledge(1'b0);
                wait_for_stop();
            end else begin
                acknowledge(1'b1);
                capture_byte(captured[index][1]);
                if (captured[index][1] !== expected_register(index))
                    $fatal(1, "operation %0d register mismatch: %02x", index,
                           captured[index][1]);
                acknowledge(1'b1);

                if (is_write(index)) begin
                    capture_byte(captured[index][2]);
                    if (captured[index][2] !== expected_write_data(index))
                        $fatal(1, "operation %0d page write mismatch", index);
                    acknowledge(1'b1);
                    wait_for_stop();
                end else begin
                    @(negedge sda_bus);
                    if (!scl_bus)
                        $fatal(1, "operation %0d repeated START invalid", index);
                    capture_byte(captured[index][2]);
                    if (captured[index][2] !== 8'h99)
                        $fatal(1, "operation %0d read address mismatch", index);
                    acknowledge(1'b1);

                    response = expected_response(index);
                    if (index == corrupt_index)
                        response = response ^ 8'h01;
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
                        $fatal(1, "operation %0d master did not NACK final byte", index);
                    wait_for_stop();
                end
            end
            transaction_count = transaction_count + 1;
        end
    endtask

    task automatic serve_sequence(
        input integer final_index,
        input integer corrupt_index,
        input integer nack_index
    );
        integer index;
        begin
            for (index = 0; index <= final_index; index = index + 1)
                serve_operation(index, corrupt_index, nack_index);
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

    task automatic reset_test;
        integer row;
        integer column;
        begin
            @(negedge clk);
            rst_n = 1'b0;
            repeat (2) @(posedge clk);
            target_sda_low = 1'b0;
            target_scl_low = 1'b0;
            transaction_count = 0;
            for (row = 0; row < 32; row = row + 1)
                for (column = 0; column < 3; column = column + 1)
                    captured[row][column] = '0;
            @(negedge clk);
            rst_n = 1'b1;
        end
    endtask

    initial begin
        repeat (3) @(posedge clk);
        rst_n = 1'b1;

        fork
            serve_sequence(23, -1, -1);
            launch();
        join
        wait (configuration_verified || error);
        @(posedge clk);
        if (!configuration_verified || error || busy || nack_error ||
            mismatch_error || transaction_count != 24 || sequence_index != 23 ||
            clock_status !== 8'h20 || power_status !== 8'h85 ||
            scl_drive_low || sda_drive_low)
            $fatal(1, "successful PCM5242 verification status mismatch");

        reset_test();
        fork
            serve_sequence(8, 8, -1);
            launch();
        join
        wait (configuration_verified || error);
        @(posedge clk);
        if (configuration_verified || !error || nack_error || !mismatch_error ||
            transaction_count != 9 || failed_index != 8 ||
            failed_observed !== 8'h00 || failed_expected !== 8'h01 ||
            failed_mask !== 8'h1f)
            $fatal(1, "masked mismatch did not fail closed at operation 8");

        reset_test();
        fork
            serve_sequence(15, -1, 15);
            launch();
        join
        wait (configuration_verified || error);
        @(posedge clk);
        if (configuration_verified || !error || !nack_error || mismatch_error ||
            transaction_count != 16 || failed_index != 15)
            $fatal(1, "NACK did not fail closed at operation 15");
        repeat (100) @(posedge clk);
        if (busy || scl_drive_low || sda_drive_low)
            $fatal(1, "verification continued or held bus after failure");

        $display("PASS PCM5242 verify: 24 exact page/read/status operations, masked mismatch and NACK fail closed");
        $finish;
    end

    /* verilator lint_on PROCASSINIT */
    /* verilator lint_on BLKSEQ */

endmodule

`default_nettype wire
