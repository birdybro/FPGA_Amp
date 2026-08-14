`timescale 1ns/1ps
`default_nettype none

module phono_control_registers_tb;
    localparam int unsigned DIAGNOSTIC_WORD_COUNT = 4;

    logic clk;
    logic rst_n = 1'b0;
    logic request_valid = 1'b0;
    logic request_write = 1'b0;
    logic [7:0] request_address = '0;
    logic [31:0] request_write_data = '0;
    logic response_valid;
    logic [31:0] response_read_data;
    logic response_error;
    logic [DIAGNOSTIC_WORD_COUNT*32-1:0] diagnostic_words_flat;
    logic [31:0] diagnostic_words [0:DIAGNOSTIC_WORD_COUNT-1];
    logic output_muted = 1'b1;
    logic output_ramping = 1'b0;
    logic mute_request;
    logic fabric_clear_diagnostics;
    logic signed [31:0] calibration_candidate_input_peak_q24;
    logic signed [31:0] calibration_candidate_output_reciprocal_q24;
    logic calibration_update_valid;
    logic calibration_update_ack;
    logic calibration_invalid_update_sticky;
    logic calibration_unsafe_update_sticky;
    logic signed [31:0] calibration_active_input_peak_q24;
    logic signed [31:0] calibration_active_output_reciprocal_q24;
    logic [31:0] snapshot_sequence;
    logic [31:0] calibration_commit_sequence;
    logic [31:0] calibration_accepted_sequence;
    logic bus_error_sticky;
    logic calibration_rejected_sticky;
    integer clear_pulse_count;
    integer errors = 0;
    integer index;

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    generate
        for (genvar word_index = 0;
             word_index < DIAGNOSTIC_WORD_COUNT;
             word_index = word_index + 1) begin : pack_diagnostics
            always_comb begin
                diagnostic_words_flat[word_index*32 +: 32] =
                    diagnostic_words[word_index];
            end
        end
    endgenerate

    calibration_commit_guard calibration_guard (
        .clk,
        .rst_n,
        .candidate_input_peak_q24(calibration_candidate_input_peak_q24),
        .candidate_output_reciprocal_q24(
            calibration_candidate_output_reciprocal_q24
        ),
        .update_valid(calibration_update_valid),
        .output_muted,
        .clear_diagnostics(fabric_clear_diagnostics),
        .active_input_peak_q24(calibration_active_input_peak_q24),
        .active_output_reciprocal_q24(
            calibration_active_output_reciprocal_q24
        ),
        .update_ack(calibration_update_ack),
        .invalid_update_sticky(calibration_invalid_update_sticky),
        .unsafe_update_sticky(calibration_unsafe_update_sticky)
    );

    phono_control_registers #(
        .DIAGNOSTIC_WORD_COUNT(DIAGNOSTIC_WORD_COUNT)
    ) dut (.*);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            clear_pulse_count <= 0;
        else if (fabric_clear_diagnostics)
            clear_pulse_count <= clear_pulse_count + 1;
    end

    task automatic bus_write(
        input logic [7:0] address,
        input logic [31:0] data,
        input logic expected_error
    );
        begin
            @(negedge clk);
            request_valid = 1'b1;
            request_write = 1'b1;
            request_address = address;
            request_write_data = data;
            @(posedge clk);
            #1;
            if (!response_valid || response_error != expected_error) begin
                $error("write response mismatch address=%02x valid=%0b error=%0b",
                       address, response_valid, response_error);
                errors = errors + 1;
            end
            @(negedge clk);
            request_valid = 1'b0;
            request_write = 1'b0;
        end
    endtask

    task automatic bus_read(
        input logic [7:0] address,
        input logic [31:0] expected_data,
        input logic expected_error
    );
        begin
            @(negedge clk);
            request_valid = 1'b1;
            request_write = 1'b0;
            request_address = address;
            request_write_data = '0;
            @(posedge clk);
            #1;
            if (!response_valid || response_error != expected_error
                || (!expected_error && response_read_data != expected_data)) begin
                $error("read mismatch address=%02x data=%08x error=%0b",
                       address, response_read_data, response_error);
                errors = errors + 1;
            end
            @(negedge clk);
            request_valid = 1'b0;
        end
    endtask

    initial begin
        for (index = 0; index < DIAGNOSTIC_WORD_COUNT; index = index + 1)
            diagnostic_words[index] = 32'h1000_0000 + index;

        repeat (3) @(posedge clk);
        rst_n = 1'b1;
        @(posedge clk);
        #1;
        if (!mute_request || snapshot_sequence != 0
            || calibration_commit_sequence != 0) begin
            $error("reset did not leave a muted, empty control plane");
            errors = errors + 1;
        end

        bus_read(8'h00, 32'h4650_4741, 1'b0);
        bus_read(8'h01, 32'h0001_0000, 1'b0);
        bus_read(8'h02, 32'h0000_000f, 1'b0);

        // Take one coherent diagnostic image, then prove later live changes do
        // not tear reads until another explicit snapshot.
        bus_write(8'h04, 32'h0000_0003, 1'b0);
        for (index = 0; index < DIAGNOSTIC_WORD_COUNT; index = index + 1)
            diagnostic_words[index] = 32'h2000_0000 + index;
        bus_read(8'h20, 32'h1000_0000, 1'b0);
        bus_read(8'h23, 32'h1000_0003, 1'b0);
        bus_read(8'h05, 32'd1, 1'b0);
        bus_write(8'h04, 32'h0000_0003, 1'b0);
        bus_read(8'h20, 32'h2000_0000, 1'b0);
        bus_read(8'h05, 32'd2, 1'b0);

        // Explicitly retain mute and commit a positive pair. The register bank
        // holds the pair coherent and records guard ack by transaction sequence
        // rather than trusting a level request.
        bus_write(8'h04, 32'h0000_0001, 1'b0);
        bus_write(8'h08, 32'd335544, 1'b0);
        bus_write(8'h09, 32'd2097152, 1'b0);
        bus_write(8'h0a, 32'd1, 1'b0);
        // A write while that pair is pending must not mutate the transaction.
        bus_write(8'h08, 32'd123, 1'b1);
        repeat (3) @(posedge clk);
        #1;
        if (calibration_active_input_peak_q24 != 335544
            || calibration_active_output_reciprocal_q24 != 2097152
            || calibration_commit_sequence != 1
            || calibration_accepted_sequence != 1
            || calibration_rejected_sticky) begin
            $error("accepted calibration transaction mismatch");
            errors = errors + 1;
        end

        // Zero is rejected by the real atomic guard and advances only the
        // attempted sequence. The control bank resolves the missing ack.
        bus_write(8'h08, 32'd0, 1'b0);
        bus_write(8'h09, 32'd2097152, 1'b0);
        bus_write(8'h0a, 32'd1, 1'b0);
        repeat (3) @(posedge clk);
        #1;
        if (calibration_commit_sequence != 2
            || calibration_accepted_sequence != 1
            || !calibration_rejected_sticky
            || !calibration_invalid_update_sticky) begin
            $error("invalid calibration rejection mismatch");
            errors = errors + 1;
        end

        // Clear both local and downstream sticky evidence with one command;
        // its downstream output is a one-clock pulse.
        bus_write(8'h04, 32'h0000_000d, 1'b0);
        @(posedge clk);
        #1;
        if (clear_pulse_count != 1 || bus_error_sticky
            || calibration_rejected_sticky
            || calibration_invalid_update_sticky) begin
            $error("diagnostic clear transaction mismatch");
            errors = errors + 1;
        end

        // A valid pair is still rejected while the downstream ramp reports
        // live. This is distinct from an invalid numerical pair.
        output_muted = 1'b0;
        bus_write(8'h08, 32'd335544, 1'b0);
        bus_write(8'h09, 32'd2097152, 1'b0);
        bus_write(8'h0a, 32'd1, 1'b0);
        repeat (3) @(posedge clk);
        #1;
        if (calibration_commit_sequence != 3
            || calibration_accepted_sequence != 1
            || !calibration_rejected_sticky
            || !calibration_unsafe_update_sticky) begin
            $error("unsafe calibration rejection mismatch");
            errors = errors + 1;
        end
        output_muted = 1'b1;
        bus_write(8'h04, 32'h0000_000d, 1'b0);
        @(posedge clk);
        #1;
        if (clear_pulse_count != 2 || calibration_rejected_sticky
            || calibration_unsafe_update_sticky) begin
            $error("unsafe diagnostic clear mismatch");
            errors = errors + 1;
        end

        bus_read(8'h7f, 32'd0, 1'b1);
        if (!bus_error_sticky) begin
            $error("invalid-address error was not retained");
            errors = errors + 1;
        end
        bus_write(8'h04, 32'h0000_0009, 1'b0);
        if (bus_error_sticky) begin
            $error("local sticky clear failed");
            errors = errors + 1;
        end

        if (errors != 0)
            $fatal(1, "FAIL: %0d control-register errors", errors);
        $display("PASS: snapshot, mute, calibration sequencing, clear, errors");
        $finish;
    end

endmodule

`default_nettype wire
