`timescale 1ns/1ps
`default_nettype none

module pcm5242_dac_startup_controller_tb;

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
    logic configuration_verified;
    logic unmute_permitted;
    logic error;
    logic initialization_error;
    logic verification_error;
    logic verification_nack_error;
    logic verification_mismatch_error;
    logic runtime_healthy;
    logic runtime_fault;
    logic runtime_nack_error;
    logic runtime_mismatch_error;
    logic [4:0] initialization_sequence_index;
    logic [4:0] initialization_failed_index;
    logic [4:0] verification_sequence_index;
    logic [4:0] verification_failed_index;
    logic [7:0] failed_observed;
    logic [7:0] failed_expected;
    logic [7:0] failed_mask;
    logic [7:0] clock_status;
    logic [7:0] power_status;
    logic [7:0] runtime_failed_register;
    logic [7:0] runtime_failed_observed;
    logic [7:0] runtime_failed_expected;
    logic [7:0] runtime_failed_mask;
    logic [1:0] runtime_sequence_index;
    logic [31:0] runtime_poll_count;
    logic [7:0] runtime_clock_status;
    logic [7:0] runtime_clock_error_status;
    logic [7:0] runtime_short_status;
    logic [7:0] runtime_power_status;
    tri1 scl_bus;
    tri1 sda_bus;

    integer transaction_count = 0;

    assign scl_bus = scl_drive_low ? 1'b0 : 1'bz;
    assign scl_bus = target_scl_low ? 1'b0 : 1'bz;
    assign sda_bus = sda_drive_low ? 1'b0 : 1'bz;
    assign sda_bus = target_sda_low ? 1'b0 : 1'bz;

    always #5 clk = !clk;

    pcm5242_dac_startup_controller #(
        .STARTUP_DELAY_CYCLES(3),
        .I2C_CLOCK_DIVIDER(1),
        .RUNTIME_POLL_INTERVAL_CYCLES(16)
    ) dut (
        .clk,
        .rst_n,
        .scl_in(scl_bus),
        .sda_in(sda_bus),
        .scl_drive_low,
        .sda_drive_low,
        .busy,
        .configuration_written,
        .configuration_verified,
        .unmute_permitted,
        .error,
        .initialization_error,
        .verification_error,
        .verification_nack_error,
        .verification_mismatch_error,
        .runtime_healthy,
        .runtime_fault,
        .runtime_nack_error,
        .runtime_mismatch_error,
        .initialization_sequence_index,
        .initialization_failed_index,
        .verification_sequence_index,
        .verification_failed_index,
        .failed_observed,
        .failed_expected,
        .failed_mask,
        .clock_status,
        .power_status,
        .runtime_failed_register,
        .runtime_failed_observed,
        .runtime_failed_expected,
        .runtime_failed_mask,
        .runtime_sequence_index,
        .runtime_poll_count,
        .runtime_clock_status,
        .runtime_clock_error_status,
        .runtime_short_status,
        .runtime_power_status
    );

    function automatic logic [7:0] init_register(input integer index);
        case (index)
            0: init_register = 8'h00;
            1: init_register = 8'h03;
            2: init_register = 8'h04;
            3: init_register = 8'h07;
            4: init_register = 8'h28;
            5: init_register = 8'h29;
            6: init_register = 8'h2a;
            7: init_register = 8'h2b;
            8: init_register = 8'h3c;
            9: init_register = 8'h3d;
            10: init_register = 8'h3e;
            11: init_register = 8'h41;
            12: init_register = 8'h00;
            13: init_register = 8'h01;
            14: init_register = 8'h02;
            15: init_register = 8'h06;
            16: init_register = 8'h07;
            17: init_register = 8'h00;
            18: init_register = 8'h02;
            default: init_register = 8'h03;
        endcase
    endfunction

    function automatic logic [7:0] init_data(input integer index);
        case (index)
            0: init_data = 8'h00;
            1: init_data = 8'h11;
            2, 3: init_data = 8'h00;
            4: init_data = 8'h02;
            5: init_data = 8'h00;
            6: init_data = 8'h11;
            7: init_data = 8'h01;
            8: init_data = 8'h00;
            9, 10: init_data = 8'h30;
            11: init_data = 8'h00;
            12: init_data = 8'h01;
            default: init_data = 8'h00;
        endcase
    endfunction

    function automatic logic verify_is_write(input integer index);
        verify_is_write = index == 0 || index == 13 || index == 18;
    endfunction

    function automatic logic [7:0] verify_register(input integer index);
        case (index)
            0: verify_register = 8'h00;
            1: verify_register = 8'h02;
            2: verify_register = 8'h03;
            3: verify_register = 8'h04;
            4: verify_register = 8'h07;
            5: verify_register = 8'h28;
            6: verify_register = 8'h29;
            7: verify_register = 8'h2a;
            8: verify_register = 8'h2b;
            9: verify_register = 8'h3c;
            10: verify_register = 8'h3d;
            11: verify_register = 8'h3e;
            12: verify_register = 8'h41;
            13: verify_register = 8'h00;
            14: verify_register = 8'h01;
            15: verify_register = 8'h02;
            16: verify_register = 8'h06;
            17: verify_register = 8'h07;
            18: verify_register = 8'h00;
            19: verify_register = 8'h5b;
            20: verify_register = 8'h5c;
            21: verify_register = 8'h5d;
            22: verify_register = 8'h5e;
            default: verify_register = 8'h76;
        endcase
    endfunction

    function automatic logic [7:0] verify_write_data(input integer index);
        verify_write_data = index == 13 ? 8'h01 : 8'h00;
    endfunction

    function automatic logic [7:0] verify_response(input integer index);
        case (index)
            1, 2, 4, 6, 9, 12, 14, 15, 16, 17, 20:
                verify_response = 8'h00;
            3: verify_response = 8'h10;
            5: verify_response = 8'h02;
            7: verify_response = 8'h11;
            8: verify_response = 8'h01;
            10, 11: verify_response = 8'h30;
            19: verify_response = 8'h38;
            21: verify_response = 8'h40;
            22: verify_response = 8'h20;
            default: verify_response = 8'h85;
        endcase
    endfunction

    function automatic logic [7:0] runtime_register(input integer index);
        case (index)
            0: runtime_register = 8'h5e;
            1: runtime_register = 8'h5f;
            2: runtime_register = 8'h6d;
            default: runtime_register = 8'h76;
        endcase
    endfunction

    function automatic logic [7:0] runtime_response(input integer index);
        case (index)
            0: runtime_response = 8'h20;
            1, 2: runtime_response = 8'h00;
            default: runtime_response = 8'h85;
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

    task automatic serve_write(
        input logic [7:0] expected_register,
        input logic [7:0] expected_data,
        input logic nack_address
    );
        logic [7:0] observed;
        begin
            @(negedge sda_bus);
            if (!scl_bus)
                $fatal(1, "write START invalid at transaction %0d", transaction_count);
            capture_byte(observed);
            if (observed !== 8'h98)
                $fatal(1, "write address mismatch at transaction %0d", transaction_count);
            if (nack_address) begin
                acknowledge(1'b0);
                wait_for_stop();
            end else begin
                acknowledge(1'b1);
                capture_byte(observed);
                if (observed !== expected_register)
                    $fatal(1, "register mismatch at transaction %0d", transaction_count);
                acknowledge(1'b1);
                capture_byte(observed);
                if (observed !== expected_data)
                    $fatal(1, "write data mismatch at transaction %0d", transaction_count);
                acknowledge(1'b1);
                wait_for_stop();
            end
            transaction_count = transaction_count + 1;
        end
    endtask

    task automatic serve_read(
        input logic [7:0] expected_register,
        input logic [7:0] response
    );
        logic [7:0] observed;
        integer bit_number;
        begin
            @(negedge sda_bus);
            if (!scl_bus)
                $fatal(1, "read START invalid at transaction %0d", transaction_count);
            capture_byte(observed);
            if (observed !== 8'h98)
                $fatal(1, "read write-address mismatch at transaction %0d", transaction_count);
            acknowledge(1'b1);
            capture_byte(observed);
            if (observed !== expected_register)
                $fatal(1, "read register mismatch at transaction %0d", transaction_count);
            acknowledge(1'b1);
            @(negedge sda_bus);
            if (!scl_bus)
                $fatal(1, "repeated START invalid at transaction %0d", transaction_count);
            capture_byte(observed);
            if (observed !== 8'h99)
                $fatal(1, "read address mismatch at transaction %0d", transaction_count);
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
                $fatal(1, "master ACKed final read at transaction %0d", transaction_count);
            wait_for_stop();
            transaction_count = transaction_count + 1;
        end
    endtask

    task automatic serve_initialization(
        input integer final_index,
        input integer nack_index
    );
        integer index;
        begin
            for (index = 0; index <= final_index; index = index + 1)
                serve_write(init_register(index), init_data(index), index == nack_index);
        end
    endtask

    task automatic serve_verification(
        input integer final_index,
        input integer corrupt_index
    );
        integer index;
        logic [7:0] response;
        begin
            for (index = 0; index <= final_index; index = index + 1) begin
                if (verify_is_write(index)) begin
                    serve_write(verify_register(index), verify_write_data(index), 1'b0);
                end else begin
                    response = verify_response(index);
                    if (index == corrupt_index)
                        response = response ^ 8'h01;
                    serve_read(verify_register(index), response);
                end
            end
        end
    endtask

    task automatic serve_runtime_poll(input integer corrupt_index);
        integer index;
        logic [7:0] response;
        begin
            for (index = 0; index < 4; index = index + 1) begin
                response = runtime_response(index);
                if (index == corrupt_index)
                    response = response ^ 8'h01;
                serve_read(runtime_register(index), response);
            end
        end
    endtask

    task automatic reset_test;
        begin
            @(negedge clk);
            rst_n = 1'b0;
            repeat (2) @(posedge clk);
            target_sda_low = 1'b0;
            target_scl_low = 1'b0;
            transaction_count = 0;
            @(negedge clk);
            rst_n = 1'b1;
        end
    endtask

    always @(posedge clk) begin
        if (unmute_permitted && !configuration_verified)
            $fatal(1, "unmute permission rose without verified configuration");
    end

    initial begin
        repeat (3) @(posedge clk);
        rst_n = 1'b1;

        serve_initialization(19, -1);
        wait (configuration_written || error);
        #1;
        if (!configuration_written || unmute_permitted)
            $fatal(1, "ACK-only completion incorrectly allowed unmute");
        serve_verification(23, -1);
        wait (configuration_verified || error);
        #1;
        if (!configuration_verified || unmute_permitted)
            $fatal(1, "startup snapshot bypassed first runtime-health poll");
        serve_runtime_poll(-1);
        wait (unmute_permitted || error);
        @(posedge clk);
        if (!configuration_written || !configuration_verified ||
            !unmute_permitted || error || busy || transaction_count != 48 ||
            clock_status !== 8'h20 || power_status !== 8'h85 ||
            !runtime_healthy || runtime_fault || runtime_poll_count != 1 ||
            runtime_clock_status !== 8'h20 ||
            runtime_clock_error_status !== 8'h00 ||
            runtime_short_status !== 8'h00 || runtime_power_status !== 8'h85 ||
            initialization_sequence_index != 19 ||
            verification_sequence_index != 23 || scl_drive_low || sda_drive_low)
            $fatal(1, "successful integrated startup status mismatch");

        serve_read(runtime_register(0), runtime_response(0));
        serve_read(runtime_register(1), runtime_response(1));
        serve_read(runtime_register(2), 8'h01);
        wait (runtime_fault);
        @(posedge clk);
        if (unmute_permitted || !error || !runtime_fault || runtime_healthy ||
            runtime_nack_error || !runtime_mismatch_error ||
            transaction_count != 51 || runtime_sequence_index != 2 ||
            runtime_failed_register !== 8'h6d ||
            runtime_failed_observed !== 8'h01 ||
            runtime_failed_expected !== 8'h00 || runtime_failed_mask !== 8'h11)
            $fatal(1, "post-unmute output-short status did not revoke permission");

        reset_test();
        serve_initialization(19, -1);
        serve_verification(22, 22);
        wait (configuration_verified || error);
        @(posedge clk);
        if (!configuration_written || configuration_verified ||
            unmute_permitted || !error || initialization_error ||
            !verification_error || verification_nack_error ||
            !verification_mismatch_error || transaction_count != 43 ||
            verification_failed_index != 22 || failed_observed !== 8'h21 ||
            failed_expected !== 8'h20 || failed_mask !== 8'h7f)
            $fatal(1, "clock-status mismatch did not keep integrated startup muted");

        reset_test();
        serve_initialization(6, 6);
        wait (configuration_written || error);
        @(posedge clk);
        if (configuration_written || configuration_verified ||
            unmute_permitted || !error || !initialization_error ||
            verification_error || transaction_count != 7 ||
            initialization_failed_index != 6)
            $fatal(1, "initialization NACK did not prevent verification/unmute");
        repeat (200) @(posedge clk);
        if (transaction_count != 7 || busy || scl_drive_low || sda_drive_low)
            $fatal(1, "controller continued or held bus after initialization failure");

        $display("PASS PCM5242 controller: 48-operation release, runtime revoke, and both startup phases fail muted");
        $finish;
    end

    /* verilator lint_on PROCASSINIT */
    /* verilator lint_on BLKSEQ */

endmodule

`default_nettype wire
