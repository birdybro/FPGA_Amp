`default_nettype none

// Bounded arbitrary-clock safety contract for low-rate toggle commands.
module cdc_toggle_pulse_formal;
    (* anyseq *) logic source_clk;
    (* anyseq *) logic source_pulse;
    (* anyseq *) logic destination_clk;

    logic [2:0] startup_phase = 3'd0;
    logic shared_rst_n;
    logic destination_pulse;
    logic [3:0] accepted_count;
    logic [3:0] delivered_count;
    logic destination_past_valid;

    assign shared_rst_n = startup_phase >= 3'd3;

    always @($global_clock) begin
        if (startup_phase < 3'd4)
            startup_phase <= startup_phase + 1'b1;
        case (startup_phase)
            3'd0: begin
                assume (!source_clk);
                assume (!destination_clk);
            end
            3'd1: begin
                assume (source_clk);
                assume (destination_clk);
            end
            3'd2, 3'd3: begin
                assume (!source_clk);
                assume (!destination_clk);
            end
            default: begin
            end
        endcase
    end

    cdc_toggle_pulse dut (
        .source_clk,
        .source_rst_n(shared_rst_n),
        .source_pulse,
        .destination_clk,
        .destination_rst_n(shared_rst_n),
        .destination_pulse
    );

    always_ff @(posedge source_clk) begin
        if (!shared_rst_n) begin
            accepted_count <= '0;
        end else begin
            // This primitive has no return-path ready signal. Its low-rate
            // protocol requires each event to be observed before another is
            // launched; a FIFO is required for arbitrary-rate traffic.
            assume (!source_pulse || accepted_count == delivered_count);
            if (source_pulse)
                accepted_count <= accepted_count + 1'b1;

            assert (accepted_count <= delivered_count + 1'b1);
        end
    end

    always_ff @(posedge destination_clk) begin
        if (!shared_rst_n) begin
            delivered_count <= '0;
            destination_past_valid <= 1'b0;
        end else begin
            destination_past_valid <= 1'b1;
            if (destination_pulse)
                delivered_count <= delivered_count + 1'b1;

            assert (delivered_count <= accepted_count);
            if (destination_pulse)
                assert (accepted_count == delivered_count + 1'b1);
            if (destination_past_valid && destination_pulse)
                assert (!$past(destination_pulse));
            if (delivered_count == accepted_count)
                assert (!destination_pulse);
        end
    end

endmodule

`default_nettype wire
