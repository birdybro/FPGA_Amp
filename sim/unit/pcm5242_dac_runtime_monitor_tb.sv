`timescale 1ns/1ps
`default_nettype none

module pcm5242_dac_runtime_monitor_tb;

    /* verilator lint_off BLKSEQ */
    /* verilator lint_off PROCASSINIT */
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic enable = 1'b0;
    logic target_sda_low = 1'b0;
    logic target_scl_low = 1'b0;
    logic scl_drive_low;
    logic sda_drive_low;
    logic busy;
    logic healthy;
    logic fault;
    logic nack_error;
    logic mismatch_error;
    logic [1:0] sequence_index;
    logic [7:0] failed_register;
    logic [7:0] failed_observed;
    logic [7:0] failed_expected;
    logic [7:0] failed_mask;
    logic [31:0] poll_count;
    logic [7:0] clock_status;
    logic [7:0] clock_error_status;
    logic [7:0] short_status;
    logic [7:0] power_status;
    tri1 scl_bus;
    tri1 sda_bus;

    integer transaction_count = 0;

    assign scl_bus = scl_drive_low ? 1'b0 : 1'bz;
    assign scl_bus = target_scl_low ? 1'b0 : 1'bz;
    assign sda_bus = sda_drive_low ? 1'b0 : 1'bz;
    assign sda_bus = target_sda_low ? 1'b0 : 1'bz;

    always #5 clk = !clk;

    pcm5242_dac_runtime_monitor #(
        .I2C_CLOCK_DIVIDER(1),
        .POLL_INTERVAL_CYCLES(16)
    ) dut (
        .clk,
        .rst_n,
        .enable,
        .scl_in(scl_bus),
        .sda_in(sda_bus),
        .scl_drive_low,
        .sda_drive_low,
        .busy,
        .healthy,
        .fault,
        .nack_error,
        .mismatch_error,
        .sequence_index,
        .failed_register,
        .failed_observed,
        .failed_expected,
        .failed_mask,
        .poll_count,
        .clock_status,
        .clock_error_status,
        .short_status,
        .power_status
    );

    function automatic logic [7:0] register_for_index(input integer index);
        case (index)
            0: register_for_index = 8'h5e;
            1: register_for_index = 8'h5f;
            2: register_for_index = 8'h6d;
            default: register_for_index = 8'h76;
        endcase
    endfunction

    function automatic logic [7:0] response_for_index(input integer index);
        case (index)
            0: response_for_index = 8'h20;
            1, 2: response_for_index = 8'h00;
            default: response_for_index = 8'h85;
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

    task automatic serve_read(
        input integer index,
        input logic [7:0] response,
        input logic nack_address
    );
        logic [7:0] observed;
        integer bit_number;
        begin
            @(negedge sda_bus);
            capture_byte(observed);
            if (observed !== 8'h98)
                $fatal(1, "poll %0d write address mismatch", transaction_count);
            if (nack_address) begin
                acknowledge(1'b0);
                wait_for_stop();
            end else begin
                acknowledge(1'b1);
                capture_byte(observed);
                if (observed !== register_for_index(index))
                    $fatal(1, "poll register mismatch at index %0d", index);
                acknowledge(1'b1);
                @(negedge sda_bus);
                if (!scl_bus)
                    $fatal(1, "repeated START invalid at poll index %0d", index);
                capture_byte(observed);
                if (observed !== 8'h99)
                    $fatal(1, "poll read address mismatch at index %0d", index);
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
                    $fatal(1, "master ACKed final runtime status byte");
                wait_for_stop();
            end
            transaction_count = transaction_count + 1;
        end
    endtask

    task automatic serve_poll(input integer corrupt_index);
        integer index;
        logic [7:0] response;
        begin
            for (index = 0; index < 4; index = index + 1) begin
                response = response_for_index(index);
                if (index == corrupt_index)
                    response = response ^ 8'h01;
                serve_read(index, response, 1'b0);
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

    initial begin
        repeat (3) @(posedge clk);
        rst_n = 1'b1;
        enable = 1'b1;

        serve_poll(-1);
        wait (healthy || fault);
        @(posedge clk);
        if (!healthy || fault || poll_count != 1 || transaction_count != 4 ||
            clock_status !== 8'h20 || clock_error_status !== 8'h00 ||
            short_status !== 8'h00 || power_status !== 8'h85)
            $fatal(1, "first healthy runtime poll status mismatch");

        serve_read(0, 8'h20, 1'b0);
        serve_read(1, 8'h00, 1'b0);
        serve_read(2, 8'h01, 1'b0);
        wait (fault);
        @(posedge clk);
        if (healthy || !fault || nack_error || !mismatch_error ||
            poll_count != 1 || transaction_count != 7 ||
            sequence_index != 2 ||
            failed_register !== 8'h6d || failed_observed !== 8'h01 ||
            failed_expected !== 8'h00 || failed_mask !== 8'h11)
            $fatal(1, "sticky short indication did not latch runtime fault");
        repeat (100) @(posedge clk);
        if (transaction_count != 7 || busy || scl_drive_low || sda_drive_low)
            $fatal(1, "runtime reads continued after latched mismatch");

        enable = 1'b0;
        reset_test();
        enable = 1'b1;
        serve_read(0, 8'h00, 1'b1);
        wait (fault);
        @(posedge clk);
        if (healthy || !fault || !nack_error || mismatch_error ||
            transaction_count != 1 || sequence_index != 0 ||
            failed_register !== 8'h5e)
            $fatal(1, "runtime address NACK did not latch fault");

        $display("PASS PCM5242 runtime monitor: healthy poll, sticky-short fault, and NACK latch");
        $finish;
    end

    /* verilator lint_on PROCASSINIT */
    /* verilator lint_on BLKSEQ */

endmodule

`default_nettype wire
