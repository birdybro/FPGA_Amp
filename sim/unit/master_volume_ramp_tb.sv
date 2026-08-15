`timescale 1ns/1ps
`default_nettype none

module master_volume_ramp_tb;
    localparam int SLEW_SHIFT = 3;
    localparam longint signed UNITY_GAIN = 64'sh000000007fffffff;

    logic clk;
    logic rst_n = 1'b0;
    logic sample_valid = 1'b0;
    logic signed [31:0] sample_left_q24 = '0;
    logic signed [31:0] sample_right_q24 = '0;
    logic output_valid;
    logic signed [31:0] output_left_q24;
    logic signed [31:0] output_right_q24;
    logic target_valid = 1'b0;
    logic [31:0] target_gain_q31 = '0;
    logic target_accepted;
    logic diagnostic_clear = 1'b0;
    logic [30:0] active_gain_q31;
    logic [30:0] active_target_q31;
    logic ramping;
    logic invalid_target_sticky;

    master_volume_ramp #(.SLEW_SHIFT(SLEW_SHIFT)) dut (.*);
    always #5 clk = ~clk;

    integer errors = 0;
    integer sample_index;
    integer seed = 32'h4d4f544f;
    longint signed expected_gain = 0;
    longint signed expected_target = 0;
    longint signed expected_step = 0;
    longint signed product;
    longint signed rounded;
    longint signed expected_left;
    longint signed expected_right;
    longint signed delta;

    function automatic longint signed scaled_sample(
        input integer signed sample,
        input longint signed gain
    );
        begin
            if (gain == 0)
                scaled_sample = 0;
            else if (gain == UNITY_GAIN)
                scaled_sample = longint'(sample);
            else begin
                product = sample * gain;
                rounded = product + ((product < 0) ? 1073741823 : 1073741824);
                scaled_sample = rounded >>> 31;
            end
        end
    endfunction

    task automatic commit_target(input logic [31:0] target, input bit accepted);
        begin
            target_gain_q31 = target;
            target_valid = 1'b1;
            @(posedge clk);
            #1;
            target_valid = 1'b0;
            if (target_accepted !== accepted) begin
                $error("target accepted got=%0b expected=%0b target=%08x",
                       target_accepted, accepted, target);
                errors = errors + 1;
            end
            if (accepted) begin
                expected_target = {33'd0, target[30:0]};
                delta = (expected_target >= expected_gain)
                    ? expected_target - expected_gain
                    : expected_gain - expected_target;
                expected_step = (delta + ((64'sd1 << SLEW_SHIFT) - 1))
                    >>> SLEW_SHIFT;
            end
            @(negedge clk);
        end
    endtask

    task automatic send_sample(
        input integer signed left_value,
        input integer signed right_value
    );
        begin
            sample_left_q24 = left_value;
            sample_right_q24 = right_value;
            sample_valid = 1'b1;
            @(posedge clk);
            #1;
            sample_valid = 1'b0;
            expected_left = scaled_sample(left_value, expected_gain);
            expected_right = scaled_sample(right_value, expected_gain);
            if (!output_valid) begin
                $error("missing output valid");
                errors = errors + 1;
            end
            if ($signed(output_left_q24) !== expected_left[31:0]) begin
                $error("left output got=%0d expected=%0d gain=%0d",
                       $signed(output_left_q24), expected_left, expected_gain);
                errors = errors + 1;
            end
            if ($signed(output_right_q24) !== expected_right[31:0]) begin
                $error("right output got=%0d expected=%0d gain=%0d",
                       $signed(output_right_q24), expected_right, expected_gain);
                errors = errors + 1;
            end

            if (expected_gain < expected_target) begin
                delta = expected_target - expected_gain;
                expected_gain = (delta <= expected_step)
                    ? expected_target : expected_gain + expected_step;
            end else if (expected_gain > expected_target) begin
                delta = expected_gain - expected_target;
                expected_gain = (delta <= expected_step)
                    ? expected_target : expected_gain - expected_step;
            end
            if (active_gain_q31 !== expected_gain[30:0]) begin
                $error("active gain got=%0d expected=%0d",
                       active_gain_q31, expected_gain);
                errors = errors + 1;
            end
            if (active_target_q31 !== expected_target[30:0]) begin
                $error("active target got=%0d expected=%0d",
                       active_target_q31, expected_target);
                errors = errors + 1;
            end
            @(posedge clk);
            #1;
            if (output_valid) begin
                $error("output valid did not pulse");
                errors = errors + 1;
            end
            @(negedge clk);
        end
    endtask

    initial begin
        clk = 1'b0;
        repeat (3) @(posedge clk);
        #1;
        if (active_gain_q31 != 0 || active_target_q31 != 0 || output_valid) begin
            $error("reset did not begin silent");
            errors = errors + 1;
        end
        rst_n = 1'b1;
        @(negedge clk);

        // Values above unsigned Q0.31 unity are invalid and must not commit.
        commit_target(32'h80000000, 1'b0);
        if (!invalid_target_sticky || active_target_q31 != 0) begin
            $error("invalid target was not retained and rejected");
            errors = errors + 1;
        end
        diagnostic_clear = 1'b1;
        @(posedge clk);
        #1;
        diagnostic_clear = 1'b0;
        if (invalid_target_sticky) begin
            $error("diagnostic clear failed");
            errors = errors + 1;
        end
        @(negedge clk);

        // Eight accepted samples reach unity; the ninth proves exact bypass.
        commit_target(32'h7fffffff, 1'b1);
        for (sample_index = 0; sample_index < 8; sample_index++)
            send_sample(32'sh7fffffff - sample_index, -32'sh40000000 + sample_index);
        if (expected_gain != UNITY_GAIN || ramping) begin
            $error("unity ramp did not finish");
            errors = errors + 1;
        end
        send_sample(32'sh7fffffff, -32'sh80000000);

        // Reverse toward half gain and retarget while moving.
        commit_target(32'h40000000, 1'b1);
        send_sample(32'sd16777217, -32'sd16777217);
        send_sample(-32'sd33554431, 32'sd33554431);
        commit_target(32'h70000000, 1'b1);
        for (sample_index = 0; sample_index < 10; sample_index++)
            send_sample($urandom(seed), $urandom(seed));

        // Exercise randomized signed scaling and repeated mid-ramp commits.
        for (sample_index = 0; sample_index < 512; sample_index++) begin
            if ((sample_index % 17) == 0)
                commit_target($urandom(seed) & 32'h7fffffff, 1'b1);
            send_sample($urandom(seed), $urandom(seed));
        end

        commit_target(32'd0, 1'b1);
        for (sample_index = 0; sample_index < 8; sample_index++)
            send_sample(-32'sd1, 32'sd1);
        if (active_gain_q31 != 0 || ramping) begin
            $error("zero ramp did not finish");
            errors = errors + 1;
        end

        if (errors != 0)
            $fatal(1, "FAIL: %0d master-volume errors", errors);
        $display("PASS: stereo Q0.31 volume, retarget, rounding, unity, and diagnostics");
        $finish;
    end
endmodule

`default_nettype wire
