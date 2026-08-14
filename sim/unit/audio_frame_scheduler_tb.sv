`timescale 1ns/1ps
`default_nettype none

module audio_frame_scheduler_tb;
    localparam int PERIOD_CLOCKS = 8;
    localparam int FRAME_COUNT = 3;

    logic clk;
    logic rst_n = 1'b0;
    logic [63:0] frame_input_data = '0;
    logic frame_input_valid = 1'b0;
    logic frame_input_ready;
    logic [63:0] frame_output_data;
    logic frame_output_valid;
    logic frame_was_present;
    logic clear_diagnostics = 1'b0;
    logic [31:0] underflow_count;
    logic [2:0] phase_counter;

    logic [63:0] preprocessed_data;
    logic preprocessed_valid;
    logic [2:0] consumer_phase;
    logic [63:0] expected [0:FRAME_COUNT-1];
    integer output_index;
    integer consumer_errors;
    integer errors;

    audio_frame_scheduler #(
        .PERIOD_CLOCKS(PERIOD_CLOCKS),
        .PREPROCESS_LATENCY_CLOCKS(1)
    ) dut (.*);

    always #5 clk = ~clk;

    // Model the one-clock registered calibration boundary and independently
    // prove its output reaches the consumer only at phase zero.
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            preprocessed_data <= '0;
            preprocessed_valid <= 1'b0;
            consumer_phase <= '0;
            output_index <= 0;
            consumer_errors <= 0;
        end else begin
            preprocessed_data <= frame_output_data;
            preprocessed_valid <= frame_output_valid;
            if (consumer_phase == 3'(PERIOD_CLOCKS - 1))
                consumer_phase <= '0;
            else
                consumer_phase <= consumer_phase + 1'b1;
            if (phase_counter !== consumer_phase) begin
                $error("scheduler/consumer phase mismatch");
                consumer_errors <= consumer_errors + 1;
            end

            if (preprocessed_valid) begin
                if (consumer_phase != 0) begin
                    $error("consumer valid at phase %0d", consumer_phase);
                    consumer_errors <= consumer_errors + 1;
                end
                if (output_index >= FRAME_COUNT
                    || preprocessed_data !== expected[output_index]) begin
                    $error("frame %0d got=%016x", output_index, preprocessed_data);
                    consumer_errors <= consumer_errors + 1;
                end
                output_index <= output_index + 1;
            end
        end
    end

    task automatic hold_until_accepted(input logic [63:0] value);
        begin
            @(negedge clk);
            frame_input_data = value;
            frame_input_valid = 1'b1;
            while (!frame_input_ready)
                @(negedge clk);
            if (!frame_was_present) begin
                $error("accepted frame was not marked present");
                errors = errors + 1;
            end
            @(posedge clk);
            @(negedge clk);
            frame_input_valid = 1'b0;
        end
    endtask

    initial begin
        clk = 1'b0;
        errors = 0;
        expected[0] = 64'h00123456_fffedcba;
        expected[1] = 64'd0;
        expected[2] = 64'hff800000_007fffff;
        repeat (3) @(posedge clk);
        #1;
        rst_n = 1'b1;

        hold_until_accepted(expected[0]);

        // Deliberately leave the next launch boundary empty. The scheduler
        // must preserve cadence with a zero frame and retain one underflow.
        @(negedge clk);
        while (!frame_input_ready)
            @(negedge clk);
        if (frame_was_present || frame_output_data != 0) begin
            $error("starved boundary did not inject an absent zero frame");
            errors = errors + 1;
        end
        @(posedge clk);
        @(negedge clk);

        hold_until_accepted(expected[2]);
        wait (output_index == FRAME_COUNT);
        #1;
        if (underflow_count != 1) begin
            $error("underflow count got=%0d expected=1", underflow_count);
            errors = errors + 1;
        end

        clear_diagnostics = 1'b1;
        @(posedge clk);
        #1;
        clear_diagnostics = 1'b0;
        if (underflow_count != 0) begin
            $error("underflow diagnostic did not clear");
            errors = errors + 1;
        end

        errors = errors + consumer_errors;
        if (errors != 0)
            $fatal(1, "FAIL: %0d frame scheduler errors", errors);
        $display("PASS: held frames, phase-zero launch, zero fill, and underflow");
        $finish;
    end
endmodule

`default_nettype wire
