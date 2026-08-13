`timescale 1ns/1ps
`default_nettype none

module output_mute_ramp_tb;
    localparam int RAMP_SAMPLES = 8;
    localparam int GAIN_STEP = (65535 + RAMP_SAMPLES - 1) / RAMP_SAMPLES;

    logic clk;
    logic rst_n = 1'b0;
    logic sample_valid = 1'b0;
    logic signed [31:0] sample_input_q24 = '0;
    logic mute_request = 1'b1;
    logic force_mute = 1'b0;
    logic signed [31:0] sample_output_q24;
    logic output_valid;
    logic [15:0] gain_q16;
    logic muted;
    logic ramping;

    output_mute_ramp #(.RAMP_SAMPLES(RAMP_SAMPLES)) dut (.*);
    always #5 clk = ~clk;

    integer errors = 0;
    integer expected_gain = 0;
    integer expected_output;
    integer sample_index;
    longint signed product;

    task automatic send_sample(input integer value);
        begin
            sample_input_q24 = value;
            sample_valid = 1'b1;
            @(posedge clk);
            #1;
            sample_valid = 1'b0;
            if (!output_valid) begin
                $error("missing output valid");
                errors = errors + 1;
            end
            if (force_mute || expected_gain == 0)
                expected_output = 0;
            else if (expected_gain == 65535)
                expected_output = value;
            else begin
                product = $signed(value) * expected_gain;
                expected_output = 32'((product
                    + ((product < 0) ? 32767 : 32768)) >>> 16);
            end
            if ($signed(sample_output_q24) !== expected_output) begin
                $error("output got=%0d expected=%0d gain=%0d",
                       $signed(sample_output_q24), expected_output, expected_gain);
                errors = errors + 1;
            end
            if (force_mute)
                expected_gain = 0;
            else if (mute_request)
                expected_gain = (expected_gain <= GAIN_STEP)
                    ? 0 : expected_gain - GAIN_STEP;
            else
                expected_gain = (expected_gain + GAIN_STEP >= 65535)
                    ? 65535 : expected_gain + GAIN_STEP;
            if (gain_q16 !== expected_gain[15:0]) begin
                $error("gain got=%0d expected=%0d", gain_q16, expected_gain);
                errors = errors + 1;
            end
            @(posedge clk);
            #1;
            if (output_valid) begin
                $error("valid did not pulse");
                errors = errors + 1;
            end
            @(negedge clk);
        end
    endtask

    initial begin
        clk = 1'b0;
        repeat (3) @(posedge clk);
        #1;
        if (!muted || gain_q16 != 0 || output_valid) begin
            $error("reset did not begin muted");
            errors = errors + 1;
        end
        rst_n = 1'b1;
        mute_request = 1'b0;
        @(negedge clk);

        // Power-up ramp covers positive and negative signed rounding.
        for (sample_index = 0; sample_index < RAMP_SAMPLES; sample_index++) begin
            if (sample_index[0])
                send_sample(-32'sd16777216);
            else
                send_sample(32'sd16777216);
        end
        if (gain_q16 != 16'hffff || ramping || muted) begin
            $error("unmute ramp did not finish");
            errors = errors + 1;
        end
        send_sample(32'sd123456789); // unity must be bit exact

        // A fault clamps the held output even when no new sample is presented.
        force_mute = 1'b1;
        @(posedge clk);
        #1;
        if (sample_output_q24 != 0 || gain_q16 != 0 || output_valid) begin
            $error("force mute did not synchronously clamp held output");
            errors = errors + 1;
        end
        expected_gain = 0;
        force_mute = 1'b0;
        mute_request = 1'b0;
        @(negedge clk);
        for (sample_index = 0; sample_index < RAMP_SAMPLES; sample_index++)
            send_sample(32'sd1234567);

        mute_request = 1'b1;
        for (sample_index = 0; sample_index < 3; sample_index++)
            send_sample(32'sd33554432);
        force_mute = 1'b1;
        send_sample(32'sd33554432);
        if (!muted || gain_q16 != 0) begin
            $error("force mute did not clear gain immediately");
            errors = errors + 1;
        end
        force_mute = 1'b0;
        send_sample(-32'sd33554432);

        if (errors != 0)
            $fatal(1, "FAIL: %0d output mute/ramp errors", errors);
        $display("PASS: reset, signed ramp, unity, ramp-down, and force mute");
        $finish;
    end
endmodule

`default_nettype wire
