`timescale 1ns/1ps
`default_nettype none

module terminal_current_update_v1_half_parallel_tb;

    logic clk;
    logic rst_n;
    logic start;
    logic [399:0] terminal_voltage_q30;
    logic [399:0] previous_voltage_q30;
    logic [479:0] previous_current_q44;
    logic [479:0] reference_current_q44;
    logic [3:0] reference_saturation_count;
    logic [479:0] candidate_current_q44;
    logic [3:0] candidate_saturation_count;
    logic candidate_ready;

    terminal_current_update_v1 reference_model (
        .terminal_voltage_q30,
        .previous_voltage_q30,
        .previous_current_q44,
        .next_current_q44(reference_current_q44),
        .saturation_count(reference_saturation_count)
    );

    terminal_current_update_v1_half_parallel dut (
        .clk,
        .rst_n,
        .start,
        .terminal_voltage_q30,
        .previous_voltage_q30,
        .previous_current_q44,
        .next_current_q44(candidate_current_q44),
        .saturation_count(candidate_saturation_count),
        .ready(candidate_ready)
    );

    always #5 clk = ~clk;

    function automatic logic [31:0] xorshift32(input logic [31:0] value);
        logic [31:0] next_value;
        begin
            next_value = value ^ (value << 13);
            next_value = next_value ^ (next_value >> 17);
            xorshift32 = next_value ^ (next_value << 5);
        end
    endfunction

    logic [31:0] random_state = 32'h6d2b_79f5;
    task automatic randomize_inputs;
        begin
            for (int word = 0; word < 12; word = word + 1) begin
                random_state = xorshift32(random_state);
                terminal_voltage_q30[word * 32 +: 32] = random_state;
            end
            random_state = xorshift32(random_state);
            terminal_voltage_q30[384 +: 16] = random_state[15:0];
            for (int word = 0; word < 12; word = word + 1) begin
                random_state = xorshift32(random_state);
                previous_voltage_q30[word * 32 +: 32] = random_state;
            end
            random_state = xorshift32(random_state);
            previous_voltage_q30[384 +: 16] = random_state[15:0];
            for (int word = 0; word < 15; word = word + 1) begin
                random_state = xorshift32(random_state);
                previous_current_q44[word * 32 +: 32] = random_state;
            end
        end
    endtask

    task automatic run_vector(input int vector_index);
        begin
            start = 1'b1;
            @(posedge clk);
            #1;
            start = 1'b0;
            if (candidate_ready)
                $fatal(1, "vector %0d became ready early", vector_index);
            @(posedge clk);
            #1;
            if (!candidate_ready)
                $fatal(1, "vector %0d did not become ready", vector_index);
            if (candidate_current_q44 !== reference_current_q44
                || candidate_saturation_count
                   !== reference_saturation_count) begin
                $error("vector %0d mismatch candidate_sat=%0d reference_sat=%0d",
                       vector_index, candidate_saturation_count,
                       reference_saturation_count);
                $fatal(1, "half-parallel terminal-current mismatch");
            end
            @(posedge clk);
            #1;
            if (candidate_ready)
                $fatal(1, "vector %0d ready did not clear", vector_index);
        end
    endtask

    initial begin
        clk = 1'b0;
        rst_n = 1'b0;
        start = 1'b0;
        terminal_voltage_q30 = '0;
        previous_voltage_q30 = '0;
        previous_current_q44 = '0;
        repeat (3) @(posedge clk);
        rst_n = 1'b1;
        @(posedge clk);
        #1;

        run_vector(0);
        terminal_voltage_q30 = {10{40'h7fffffffff}};
        previous_voltage_q30 = {10{40'h8000000000}};
        previous_current_q44 = {10{48'h800000000000}};
        run_vector(1);
        terminal_voltage_q30 = {10{40'h8000000000}};
        previous_voltage_q30 = {10{40'h7fffffffff}};
        previous_current_q44 = {10{48'h7fffffffffff}};
        run_vector(2);

        for (int vector_index = 3; vector_index < 1027;
             vector_index = vector_index + 1) begin
            randomize_inputs();
            run_vector(vector_index);
        end

        $display("terminal_current_update_v1_half_parallel: 1027 exact vectors passed");
        $finish;
    end

endmodule

`default_nettype wire
