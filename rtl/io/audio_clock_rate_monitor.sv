`timescale 1ns/1ps
`default_nettype none

// Measures BCLK edges over a fixed fabric-clock window. The BCLK-domain binary
// counter crosses only as Gray code; the fabric domain converts the synchronized
// value and subtracts successive snapshots. This diagnoses frequency lock but
// does not establish phase alignment, constrain CDC paths, or perform rate
// matching.
module audio_clock_rate_monitor #(
    parameter int unsigned BCLK_COUNTER_WIDTH = 16,
    parameter int unsigned WINDOW_FABRIC_CLOCKS = 32768,
    parameter int unsigned EXPECTED_BCLK_EDGES = 1024,
    parameter int unsigned EDGE_TOLERANCE = 1,
    parameter int unsigned LOCK_WINDOWS = 3
) (
    input  logic                          i2s_bclk,
    input  logic                          i2s_rst_n,
    input  logic                          fabric_clk,
    input  logic                          fabric_rst_n,
    input  logic                          clear_diagnostics,
    output logic                          measurement_valid,
    output logic [BCLK_COUNTER_WIDTH-1:0] measured_bclk_edges,
    output logic [7:0]                    consecutive_good_windows,
    output logic                          rate_locked,
    output logic                          rate_error_sticky
);

    localparam int unsigned WINDOW_COUNTER_WIDTH =
        $clog2(WINDOW_FABRIC_CLOCKS);
    localparam int unsigned MINIMUM_BCLK_EDGES =
        EXPECTED_BCLK_EDGES - EDGE_TOLERANCE;
    localparam int unsigned MAXIMUM_BCLK_EDGES =
        EXPECTED_BCLK_EDGES + EDGE_TOLERANCE;

    initial begin
        if (BCLK_COUNTER_WIDTH < 2)
            $error("BCLK_COUNTER_WIDTH must be at least two");
        if (WINDOW_FABRIC_CLOCKS < 2)
            $error("WINDOW_FABRIC_CLOCKS must be at least two");
        if (EXPECTED_BCLK_EDGES < EDGE_TOLERANCE)
            $error("EDGE_TOLERANCE exceeds expected edge count");
        if (MAXIMUM_BCLK_EDGES >= (1 << BCLK_COUNTER_WIDTH))
            $error("BCLK counter is too narrow for the measurement window");
        if (LOCK_WINDOWS == 0 || LOCK_WINDOWS > 255)
            $error("LOCK_WINDOWS must be within 1..255");
    end

    function automatic logic [BCLK_COUNTER_WIDTH-1:0] binary_to_gray(
        input logic [BCLK_COUNTER_WIDTH-1:0] binary_value
    );
        binary_to_gray = (binary_value >> 1) ^ binary_value;
    endfunction

    function automatic logic [BCLK_COUNTER_WIDTH-1:0] gray_to_binary(
        input logic [BCLK_COUNTER_WIDTH-1:0] gray_value
    );
        integer bit_index;
        begin
            gray_to_binary[BCLK_COUNTER_WIDTH-1] =
                gray_value[BCLK_COUNTER_WIDTH-1];
            for (bit_index = BCLK_COUNTER_WIDTH - 2;
                 bit_index >= 0; bit_index--)
                gray_to_binary[bit_index] =
                    gray_to_binary[bit_index + 1] ^ gray_value[bit_index];
        end
    endfunction

    logic [BCLK_COUNTER_WIDTH-1:0] bclk_binary;
    logic [BCLK_COUNTER_WIDTH-1:0] bclk_gray;
    logic bclk_active;
    always_ff @(posedge i2s_bclk or negedge i2s_rst_n) begin
        if (!i2s_rst_n) begin
            bclk_binary <= '0;
            bclk_gray <= '0;
            bclk_active <= 1'b0;
        end else begin
            bclk_binary <= bclk_binary + 1'b1;
            bclk_gray <= binary_to_gray(bclk_binary + 1'b1);
            bclk_active <= 1'b1;
        end
    end

    (* async_reg = "true" *) logic [BCLK_COUNTER_WIDTH-1:0] bclk_gray_sync1;
    (* async_reg = "true" *) logic [BCLK_COUNTER_WIDTH-1:0] bclk_gray_sync2;
    (* async_reg = "true" *) logic bclk_active_sync1;
    (* async_reg = "true" *) logic bclk_active_sync2;
    always_ff @(posedge fabric_clk or negedge fabric_rst_n) begin
        if (!fabric_rst_n) begin
            bclk_gray_sync1 <= '0;
            bclk_gray_sync2 <= '0;
            bclk_active_sync1 <= 1'b0;
            bclk_active_sync2 <= 1'b0;
        end else begin
            bclk_gray_sync1 <= bclk_gray;
            bclk_gray_sync2 <= bclk_gray_sync1;
            bclk_active_sync1 <= bclk_active;
            bclk_active_sync2 <= bclk_active_sync1;
        end
    end

    logic [BCLK_COUNTER_WIDTH-1:0] synchronized_bclk_binary;
    logic [BCLK_COUNTER_WIDTH-1:0] measurement_baseline;
    logic [BCLK_COUNTER_WIDTH-1:0] edge_delta;
    logic measurement_good;
    always_comb begin
        synchronized_bclk_binary = gray_to_binary(bclk_gray_sync2);
        edge_delta = synchronized_bclk_binary - measurement_baseline;
        measurement_good =
            edge_delta >= BCLK_COUNTER_WIDTH'(MINIMUM_BCLK_EDGES)
            && edge_delta <= BCLK_COUNTER_WIDTH'(MAXIMUM_BCLK_EDGES);
    end

    logic [WINDOW_COUNTER_WIDTH-1:0] window_counter;
    logic monitor_active;
    always_ff @(posedge fabric_clk or negedge fabric_rst_n) begin
        if (!fabric_rst_n) begin
            window_counter <= '0;
            measurement_baseline <= '0;
            monitor_active <= 1'b0;
            measurement_valid <= 1'b0;
            measured_bclk_edges <= '0;
            consecutive_good_windows <= '0;
            rate_locked <= 1'b0;
            rate_error_sticky <= 1'b0;
        end else begin
            measurement_valid <= 1'b0;
            if (clear_diagnostics)
                rate_error_sticky <= 1'b0;

            if (!bclk_active_sync2) begin
                window_counter <= '0;
                measurement_baseline <= synchronized_bclk_binary;
                monitor_active <= 1'b0;
                measured_bclk_edges <= '0;
                consecutive_good_windows <= '0;
                rate_locked <= 1'b0;
            end else if (!monitor_active) begin
                window_counter <= '0;
                measurement_baseline <= synchronized_bclk_binary;
                monitor_active <= 1'b1;
                measured_bclk_edges <= '0;
                consecutive_good_windows <= '0;
                rate_locked <= 1'b0;
            end else if (window_counter
                         == WINDOW_COUNTER_WIDTH'(WINDOW_FABRIC_CLOCKS - 1)) begin
                window_counter <= '0;
                measurement_baseline <= synchronized_bclk_binary;
                measurement_valid <= 1'b1;
                measured_bclk_edges <= edge_delta;
                if (measurement_good) begin
                    if (consecutive_good_windows < 8'(LOCK_WINDOWS))
                        consecutive_good_windows <=
                            consecutive_good_windows + 1'b1;
                    if (consecutive_good_windows >= 8'(LOCK_WINDOWS - 1))
                        rate_locked <= 1'b1;
                end else begin
                    consecutive_good_windows <= '0;
                    rate_locked <= 1'b0;
                    if (!clear_diagnostics)
                        rate_error_sticky <= 1'b1;
                end
            end else begin
                window_counter <= window_counter + 1'b1;
            end
        end
    end

`ifdef FORMAL
    logic formal_bclk_past_valid;
    logic formal_fabric_past_valid;

    always_ff @(posedge i2s_bclk) begin
        if (!i2s_rst_n) begin
            formal_bclk_past_valid <= 1'b0;
        end else begin
            formal_bclk_past_valid <= 1'b1;
            if (formal_bclk_past_valid) begin
                assert ({bclk_binary, bclk_active}
                    == {$past(bclk_binary) + 1'b1, 1'b1});
                assert (bclk_gray == binary_to_gray(bclk_binary));
            end
        end
    end

    always_ff @(posedge fabric_clk) begin
        if (!fabric_rst_n) begin
            formal_fabric_past_valid <= 1'b0;
        end else begin
            formal_fabric_past_valid <= 1'b1;
            if (formal_fabric_past_valid) begin
                assert ({bclk_gray_sync1, bclk_gray_sync2,
                         bclk_active_sync1, bclk_active_sync2}
                    == {$past(bclk_gray), $past(bclk_gray_sync1),
                        $past(bclk_active), $past(bclk_active_sync1)});
                assert (measurement_valid
                    == ($past(bclk_active_sync2)
                        && $past(monitor_active)
                        && $past(window_counter)
                            == WINDOW_COUNTER_WIDTH'(
                                WINDOW_FABRIC_CLOCKS - 1)));

                if (!$past(bclk_active_sync2)) begin
                    assert ({window_counter, measurement_baseline,
                             monitor_active, measured_bclk_edges,
                             consecutive_good_windows, rate_locked}
                        == {WINDOW_COUNTER_WIDTH'(0),
                            $past(synchronized_bclk_binary), 1'b0,
                            BCLK_COUNTER_WIDTH'(0), 8'(0), 1'b0});
                end else if (!$past(monitor_active)) begin
                    assert ({window_counter, measurement_baseline,
                             monitor_active, measured_bclk_edges,
                             consecutive_good_windows, rate_locked}
                        == {WINDOW_COUNTER_WIDTH'(0),
                            $past(synchronized_bclk_binary), 1'b1,
                            BCLK_COUNTER_WIDTH'(0), 8'(0), 1'b0});
                end else if ($past(window_counter)
                             == WINDOW_COUNTER_WIDTH'(
                                 WINDOW_FABRIC_CLOCKS - 1)) begin
                    assert ({window_counter, measurement_baseline,
                             monitor_active, measured_bclk_edges}
                        == {WINDOW_COUNTER_WIDTH'(0),
                            $past(synchronized_bclk_binary), 1'b1,
                            $past(edge_delta)});
                    if ($past(measurement_good)) begin
                        assert ({consecutive_good_windows, rate_locked}
                            == {($past(consecutive_good_windows)
                                    < 8'(LOCK_WINDOWS)
                                ? $past(consecutive_good_windows) + 1'b1
                                : $past(consecutive_good_windows)),
                                ($past(rate_locked)
                                    || $past(consecutive_good_windows)
                                        >= 8'(LOCK_WINDOWS - 1))});
                    end else begin
                        assert ({consecutive_good_windows, rate_locked}
                            == {8'(0), 1'b0});
                    end
                end else begin
                    assert ({window_counter, measurement_baseline,
                             monitor_active, measured_bclk_edges,
                             consecutive_good_windows, rate_locked}
                        == {$past(window_counter) + 1'b1,
                            $past(measurement_baseline), 1'b1,
                            $past(measured_bclk_edges),
                            $past(consecutive_good_windows),
                            $past(rate_locked)});
                end

                assert (rate_error_sticky
                    == ($past(clear_diagnostics)
                        ? 1'b0
                        : ($past(bclk_active_sync2)
                            && $past(monitor_active)
                            && $past(window_counter)
                                == WINDOW_COUNTER_WIDTH'(
                                    WINDOW_FABRIC_CLOCKS - 1)
                            && !$past(measurement_good))
                            ? 1'b1
                            : $past(rate_error_sticky)));
                assert (!measurement_valid || monitor_active);
                assert (monitor_active
                    || (!rate_locked && consecutive_good_windows == 0));
            end
        end
    end
`endif

endmodule

`default_nettype wire
