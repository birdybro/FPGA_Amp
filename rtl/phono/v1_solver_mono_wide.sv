`timescale 1ns/1ps
`default_nettype none

// Persistent 40-bit V1 solver using the factorized Koren tube, direct Q30
// capacitor branches, and three adaptive Q30/Q34/Q40 chord corrections.
module v1_solver_mono_wide #(
    parameter NODE_INITIAL_FILE = "model/generated/v1_node_initial_wide.mem",
    parameter CAP_INITIAL_FILE = "model/generated/v1_cap_initial_q30_wide.mem",
    parameter CAP_CURRENT_INITIAL_FILE =
        "model/generated/v1_cap_current_initial_q4_44_trapezoidal.mem",
    parameter CAP_G_FILE = "model/generated/v1_cap_conductance_q0_47.mem",
    parameter CHORD_COEFFICIENT_FILE =
        "model/generated/v1_chord_inverse_q17_1.mem",
    parameter integer CHORD_COEFFICIENT_SETS = 1,
    parameter bit TRAPEZOIDAL = 1'b0,
    // Reuse the final diagnostic residual for a fourth chord update.  The
    // reported residual remains the explicitly documented pre-update value.
    parameter bit TERMINAL_CORRECTION = 1'b0,
    // Approximation architecture only: both options evaluate the same Koren
    // physical law and retain the same eight-clock request/valid contract.
    parameter bit USE_LINEAR_FACTORIZED_TUBE = 1'b0,
    // Scheduling architecture only: evaluate the two physical triodes at the
    // same time instead of reusing one engine sequentially.  This duplicates
    // the primitive but does not change its arithmetic or the circuit law.
    parameter bit PARALLEL_TUBES = 1'b0,
    // Split KCL finish conversion, global selection, and saturation across
    // registers. Intended to consume part of the parallel-tube cycle margin.
    parameter bit PIPELINED_KCL_FINISH = 1'b0,
    // Register and overlap KCL matrix/capacitor column issue and accumulation.
    parameter bit PIPELINED_KCL_COLUMNS = 1'b0,
    // Register each KCL column contribution before accumulator feedback.
    parameter bit PIPELINED_KCL_ACCUMULATOR = 1'b0,
    // Separate KCL capacitor-product rounding from current-history subtraction.
    parameter bit PIPELINED_KCL_CAPACITOR_CURRENT = 1'b0,
    // Pipeline the final-pass-only KCL maximum-residual diagnostic.
    parameter bit PIPELINED_KCL_MAXIMUM = 1'b0,
    // Split chord scaling, node update, and saturation across registers.
    parameter bit PIPELINED_CHORD_APPLY = 1'b0,
    // Reuse five terminal-current multipliers across two batches. The first
    // batch overlaps the final chord preview cycle; a registered second batch
    // consumes the last available solver clock. Requires pipelined chord apply
    // and terminal correction.
    parameter bit HALF_PARALLEL_TERMINAL_CURRENT = 1'b0
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  ce_sample,
    input  logic signed [31:0]    input_q24,
    output logic signed [39:0]    output_q32,
    output logic                  output_valid,
    output logic                  busy,
    output logic [7:0]            sample_latency_cycles,
    output logic [31:0]           missed_request_count,
    output logic [31:0]           deadline_miss_count,
    output logic [31:0]           saturation_count,
    output logic [31:0]           lut_clip_count,
    output logic [31:0]           nonconvergence_count,
    output logic [31:0]           correction_scale_fallback_count,
    output logic [5:0]            minimum_correction_fractional_bits,
    output logic [62:0]           last_residual_q44,
    output logic [359:0]          node_voltage_debug,
    output logic [399:0]          capacitor_state_debug,
    output logic [479:0]          capacitor_current_state_debug
);

    localparam logic [62:0] RESIDUAL_LIMIT_Q44 = 63'd35184372; // 2 uA

    typedef enum logic [3:0] {
        IDLE,
        WAIT_RHS,
        WAIT_TUBE_1,
        WAIT_TUBE_2,
        WAIT_KCL,
        WAIT_CHORD,
        WAIT_TERMINAL
    } state_t;

    state_t state;
    logic [1:0] correction_index;
    logic final_pass;
    logic [7:0] cycle_count;
    logic deadline_reported;

    logic signed [39:0] node_initial [0:8];
    logic signed [39:0] capacitor_initial [0:9];
    logic signed [47:0] capacitor_current_initial [0:9];
    logic signed [39:0] node_voltage [0:8];
    logic signed [39:0] capacitor_state [0:9];
    logic signed [39:0] capacitor_next [0:9];
    logic signed [47:0] capacitor_current_state [0:9];

    initial begin
        $readmemh(NODE_INITIAL_FILE, node_initial);
        $readmemh(CAP_INITIAL_FILE, capacitor_initial);
        if (TRAPEZOIDAL)
            $readmemh(CAP_CURRENT_INITIAL_FILE, capacitor_current_initial);
        else
            for (int initial_lane = 0; initial_lane < 10;
                 initial_lane = initial_lane + 1)
                capacitor_current_initial[initial_lane] = '0;
    end

    function automatic int cap_node_a(input int index);
        begin
            case (index)
                0, 1: cap_node_a = 0;
                2, 6: cap_node_a = 1;
                3, 4, 8: cap_node_a = 4;
                5, 9: cap_node_a = 6;
                7: cap_node_a = 5;
                default: cap_node_a = -1;
            endcase
        end
    endfunction

    function automatic int cap_node_b(input int index);
        begin
            case (index)
                0: cap_node_b = 2;
                1: cap_node_b = 1;
                2: cap_node_b = 2;
                3: cap_node_b = 7;
                4: cap_node_b = 6;
                5: cap_node_b = 7;
                6: cap_node_b = 3;
                9: cap_node_b = 8;
                default: cap_node_b = -1;
            endcase
        end
    endfunction

    function automatic logic node_is_q28(input int index);
        begin
            case (index)
                1, 3, 6: node_is_q28 = 1'b1;
                default: node_is_q28 = 1'b0;
            endcase
        end
    endfunction

    function automatic logic [2:0] select_chord_coefficient_set(
        input logic signed [40:0] previous_v_gk2_q32,
        input logic signed [40:0] prior_v_gk2_q32
    );
        logic signed [41:0] slew_delta_q32;
        logic [41:0] slew_magnitude_q32;
        begin
            slew_delta_q32 =
                $signed({previous_v_gk2_q32[40], previous_v_gk2_q32})
                - $signed({prior_v_gk2_q32[40], prior_v_gk2_q32});
            if (slew_delta_q32 < 0)
                slew_magnitude_q32 = -slew_delta_q32;
            else
                slew_magnitude_q32 = slew_delta_q32;
            select_chord_coefficient_set = 3'd0;
            if (CHORD_COEFFICIENT_SETS == 4) begin
                if (previous_v_gk2_q32 < -41'sd13958643712) // -3.25 V
                    select_chord_coefficient_set = 3'd0;
                else if (previous_v_gk2_q32 < -41'sd11811160064) // -2.75 V
                    select_chord_coefficient_set = 3'd1;
                else if ((previous_v_gk2_q32 < -41'sd10737418240) &&
                         (slew_magnitude_q32 > 42'd85899346)) // -2.5 V, 20 mV
                    select_chord_coefficient_set = 3'd2;
                else
                    select_chord_coefficient_set = 3'd3;
            end else if (CHORD_COEFFICIENT_SETS == 5) begin
                if (previous_v_gk2_q32 < -41'sd17179869184) // -4.0 V
                    select_chord_coefficient_set = 3'd0;
                else if (previous_v_gk2_q32 < -41'sd15032385536) // -3.5 V
                    select_chord_coefficient_set = 3'd1;
                else if (previous_v_gk2_q32 < -41'sd12884901888) // -3.0 V
                    select_chord_coefficient_set = 3'd2;
                else if (previous_v_gk2_q32 < -41'sd11811160064) // -2.75 V
                    select_chord_coefficient_set = 3'd3;
                else if ((previous_v_gk2_q32 < -41'sd10737418240) &&
                         (slew_magnitude_q32 > 42'd85899346)) // -2.5 V, 20 mV
                    select_chord_coefficient_set = 3'd3;
                else
                    select_chord_coefficient_set = 3'd4;
            end
        end
    endfunction

    function automatic logic signed [39:0] node_to_q24_wide(
        input logic signed [39:0] value,
        input int index
    );
        logic signed [40:0] biased;
        begin
            biased = $signed({value[39], value});
            if (node_is_q28(index)) begin
                biased = biased + 41'sd8;
                node_to_q24_wide = 40'($signed(biased) >>> 4);
            end else begin
                biased = biased + 41'sd128;
                node_to_q24_wide = 40'($signed(biased) >>> 8);
            end
        end
    endfunction

    function automatic logic signed [39:0] node_to_q20_wide(
        input logic signed [39:0] value,
        input int index
    );
        logic signed [40:0] biased;
        begin
            biased = $signed({value[39], value});
            if (node_is_q28(index)) begin
                biased = biased + 41'sd128;
                node_to_q20_wide = 40'($signed(biased) >>> 8);
            end else begin
                biased = biased + 41'sd2048;
                node_to_q20_wide = 40'($signed(biased) >>> 12);
            end
        end
    endfunction

    function automatic logic signed [31:0] saturate_32(
        input logic signed [40:0] value
    );
        begin
            if (value > 41'sd2147483647)
                saturate_32 = 32'sh7fffffff;
            else if (value < -41'sd2147483648)
                saturate_32 = 32'sh80000000;
            else
                saturate_32 = value[31:0];
        end
    endfunction

    function automatic logic signed [31:0] node_difference_q24(
        input logic signed [39:0] left_value,
        input int left_index,
        input logic signed [39:0] right_value,
        input int right_index
    );
        logic signed [39:0] left_converted;
        logic signed [39:0] right_converted;
        logic signed [40:0] difference;
        begin
            left_converted = node_to_q24_wide(left_value, left_index);
            right_converted = node_to_q24_wide(right_value, right_index);
            difference = $signed({left_converted[39], left_converted})
                         - $signed({right_converted[39], right_converted});
            node_difference_q24 = saturate_32(difference);
        end
    endfunction

    function automatic logic signed [31:0] node_difference_q20(
        input logic signed [39:0] left_value,
        input int left_index,
        input logic signed [39:0] right_value,
        input int right_index
    );
        logic signed [39:0] left_converted;
        logic signed [39:0] right_converted;
        logic signed [40:0] difference;
        begin
            left_converted = node_to_q20_wide(left_value, left_index);
            right_converted = node_to_q20_wide(right_value, right_index);
            difference = $signed({left_converted[39], left_converted})
                         - $signed({right_converted[39], right_converted});
            node_difference_q20 = saturate_32(difference);
        end
    endfunction

    function automatic logic signed [41:0] node_to_q30(
        input logic signed [39:0] value,
        input int index
    );
        logic signed [41:0] extended;
        begin
            extended = {{2{value[39]}}, value};
            if (node_is_q28(index))
                node_to_q30 = extended <<< 2;
            else
                node_to_q30 = (extended + 42'sd2) >>> 2;
        end
    endfunction

    function automatic logic signed [39:0] saturate_40(
        input logic signed [42:0] value
    );
        begin
            if (value > 43'sd549755813887)
                saturate_40 = 40'sh7fffffffff;
            else if (value < -43'sd549755813888)
                saturate_40 = 40'sh8000000000;
            else
                saturate_40 = value[39:0];
        end
    endfunction

    function automatic logic exceeds_40(input logic signed [42:0] value);
        begin
            exceeds_40 = (value > 43'sd549755813887)
                         || (value < -43'sd549755813888);
        end
    endfunction

    logic [359:0] voltage_flat;
    logic [399:0] capacitor_flat;
    logic [479:0] capacitor_current_flat;
    logic [399:0] terminal_preview_capacitor_flat;
    logic [479:0] terminal_current_flat;
    logic [479:0] capacitor_current_next_unused;
    logic [3:0] capacitor_current_saturation_unused;
    logic signed [41:0] capacitor_voltage_a [0:9];
    logic signed [41:0] capacitor_voltage_b [0:9];
    logic signed [42:0] capacitor_difference [0:9];
    logic [3:0] capacitor_saturation_count;
    logic [359:0] corrected_voltage;
    logic signed [39:0] corrected_node_voltage [0:8];
    logic signed [39:0] preview_node_voltage [0:8];
    logic signed [39:0] terminal_capacitor_next [0:9];
    logic signed [41:0] terminal_capacitor_voltage_a [0:9];
    logic signed [41:0] terminal_capacitor_voltage_b [0:9];
    logic signed [42:0] terminal_capacitor_difference [0:9];
    logic signed [41:0] terminal_preview_capacitor_voltage_a [0:9];
    logic signed [41:0] terminal_preview_capacitor_voltage_b [0:9];
    logic signed [42:0] terminal_preview_capacitor_difference [0:9];
    logic [3:0] terminal_capacitor_saturation_count;
    logic [3:0] terminal_current_saturation_count;
    logic [9:0] capacitor_saturation_by_lane;
    logic [9:0] terminal_capacitor_saturation_by_lane;

    function automatic logic [3:0] popcount10(input logic [9:0] bits);
        logic [1:0] pair_0;
        logic [1:0] pair_1;
        logic [1:0] pair_2;
        logic [1:0] pair_3;
        logic [1:0] pair_4;
        logic [2:0] group_0;
        logic [2:0] group_1;
        begin
            pair_0 = {1'b0, bits[0]} + {1'b0, bits[1]};
            pair_1 = {1'b0, bits[2]} + {1'b0, bits[3]};
            pair_2 = {1'b0, bits[4]} + {1'b0, bits[5]};
            pair_3 = {1'b0, bits[6]} + {1'b0, bits[7]};
            pair_4 = {1'b0, bits[8]} + {1'b0, bits[9]};
            group_0 = {1'b0, pair_0} + {1'b0, pair_1};
            group_1 = {1'b0, pair_2} + {1'b0, pair_3};
            popcount10 = {1'b0, group_0} + {1'b0, group_1}
                         + {2'b00, pair_4};
        end
    endfunction

    always_comb begin
        for (int lane = 0; lane < 9; lane = lane + 1) begin
            voltage_flat[lane * 40 +: 40] = node_voltage[lane];
            node_voltage_debug[lane * 40 +: 40] = node_voltage[lane];
            corrected_node_voltage[lane] = $signed(
                corrected_voltage[lane * 40 +: 40]
            );
            preview_node_voltage[lane] = $signed(
                chord_preview_voltage[lane * 40 +: 40]
            );
        end
        for (int lane = 0; lane < 10; lane = lane + 1) begin
            capacitor_flat[lane * 40 +: 40] = capacitor_state[lane];
            capacitor_state_debug[lane * 40 +: 40] = capacitor_state[lane];
            capacitor_current_flat[lane * 48 +: 48] =
                capacitor_current_state[lane];
            capacitor_current_state_debug[lane * 48 +: 48] =
                capacitor_current_state[lane];
            capacitor_voltage_a[lane] = '0;
            capacitor_voltage_b[lane] = '0;
            if (cap_node_a(lane) >= 0)
                capacitor_voltage_a[lane] = node_to_q30(
                    node_voltage[cap_node_a(lane)], cap_node_a(lane)
                );
            if (cap_node_b(lane) >= 0)
                capacitor_voltage_b[lane] = node_to_q30(
                    node_voltage[cap_node_b(lane)], cap_node_b(lane)
                );
            capacitor_difference[lane] =
                $signed({capacitor_voltage_a[lane][41], capacitor_voltage_a[lane]})
                - $signed({capacitor_voltage_b[lane][41], capacitor_voltage_b[lane]});
            capacitor_next[lane] = saturate_40(capacitor_difference[lane]);
            capacitor_saturation_by_lane[lane] = exceeds_40(
                capacitor_difference[lane]
            );

            terminal_capacitor_voltage_a[lane] = '0;
            terminal_capacitor_voltage_b[lane] = '0;
            if (cap_node_a(lane) >= 0)
                terminal_capacitor_voltage_a[lane] = node_to_q30(
                    corrected_node_voltage[cap_node_a(lane)], cap_node_a(lane)
                );
            if (cap_node_b(lane) >= 0)
                terminal_capacitor_voltage_b[lane] = node_to_q30(
                    corrected_node_voltage[cap_node_b(lane)], cap_node_b(lane)
                );
            terminal_capacitor_difference[lane] =
                $signed({terminal_capacitor_voltage_a[lane][41],
                         terminal_capacitor_voltage_a[lane]})
                - $signed({terminal_capacitor_voltage_b[lane][41],
                           terminal_capacitor_voltage_b[lane]});
            terminal_capacitor_next[lane] = saturate_40(
                terminal_capacitor_difference[lane]
            );
            terminal_capacitor_saturation_by_lane[lane] = exceeds_40(
                terminal_capacitor_difference[lane]
            );

            terminal_preview_capacitor_voltage_a[lane] = '0;
            terminal_preview_capacitor_voltage_b[lane] = '0;
            if (cap_node_a(lane) >= 0)
                terminal_preview_capacitor_voltage_a[lane] = node_to_q30(
                    preview_node_voltage[cap_node_a(lane)], cap_node_a(lane)
                );
            if (cap_node_b(lane) >= 0)
                terminal_preview_capacitor_voltage_b[lane] = node_to_q30(
                    preview_node_voltage[cap_node_b(lane)], cap_node_b(lane)
                );
            terminal_preview_capacitor_difference[lane] =
                $signed({terminal_preview_capacitor_voltage_a[lane][41],
                         terminal_preview_capacitor_voltage_a[lane]})
                - $signed({terminal_preview_capacitor_voltage_b[lane][41],
                           terminal_preview_capacitor_voltage_b[lane]});
            terminal_preview_capacitor_flat[lane * 40 +: 40] = saturate_40(
                terminal_preview_capacitor_difference[lane]
            );
        end
        capacitor_saturation_count = popcount10(
            capacitor_saturation_by_lane
        );
        terminal_capacitor_saturation_count = popcount10(
            terminal_capacitor_saturation_by_lane
        );
    end

    logic terminal_current_ready;
    logic terminal_current_preview_start;
    assign terminal_current_preview_start = HALF_PARALLEL_TERMINAL_CURRENT
        && chord_preview_valid
        && (state == WAIT_CHORD) && final_pass && TERMINAL_CORRECTION;

    generate
        if (HALF_PARALLEL_TERMINAL_CURRENT) begin : generate_half_terminal_current
            terminal_current_update_v1_half_parallel terminal_current_engine (
                .clk,
                .rst_n,
                .start(terminal_current_preview_start),
                .terminal_voltage_q30(terminal_preview_capacitor_flat),
                .previous_voltage_q30(capacitor_flat),
                .previous_current_q44(capacitor_current_flat),
                .next_current_q44(terminal_current_flat),
                .saturation_count(terminal_current_saturation_count),
                .ready(terminal_current_ready)
            );
        end else begin : generate_full_terminal_current
            logic [399:0] terminal_capacitor_flat;
            always_comb begin
                for (int terminal_lane = 0; terminal_lane < 10;
                     terminal_lane = terminal_lane + 1)
                    terminal_capacitor_flat[terminal_lane * 40 +: 40] =
                        terminal_capacitor_next[terminal_lane];
            end
            terminal_current_update_v1 terminal_current_engine (
                .terminal_voltage_q30(terminal_capacitor_flat),
                .previous_voltage_q30(capacitor_flat),
                .previous_current_q44(capacitor_current_flat),
                .next_current_q44(terminal_current_flat),
                .saturation_count(terminal_current_saturation_count)
            );
            always_comb terminal_current_ready = 1'b1;
        end
    endgenerate

    logic rhs_start;
    logic [494:0] rhs_result;
    logic [494:0] rhs_latched;
    logic rhs_busy;
    logic rhs_valid;
    assign rhs_start = (state == IDLE) && ce_sample;

    network_rhs_v1_wide rhs_engine (
        .clk,
        .rst_n,
        .start(rhs_start),
        .input_q24,
        .rhs_q44(rhs_result),
        .busy(rhs_busy),
        .valid(rhs_valid)
    );

    logic kcl_start;
    logic residual_launch;
    logic [359:0] residual_voltage_flat;
    logic [494:0] residual_rhs_q44;
    logic [5:0] requested_residual_fractional_bits;
    logic kcl_diagnostic_max_enable;
    logic kcl_tube_current_valid;
    logic [127:0] tube_current_flat;
    logic [224:0] residual;
    logic [5:0] residual_fractional_bits;
    logic [62:0] kcl_max_abs_q44;
    logic kcl_scale_fallback;
    logic kcl_saturation_any;
    logic [3:0] kcl_saturation_count;
    logic kcl_busy;
    logic kcl_valid;
    always_comb begin
        residual_launch = ((state == WAIT_RHS) && rhs_valid)
                          || ((state == WAIT_CHORD) && chord_valid
                              && !final_pass);
        if ((state == WAIT_CHORD) && chord_valid)
            residual_voltage_flat = corrected_voltage;
        else
            residual_voltage_flat = voltage_flat;
        if ((state == WAIT_RHS) && rhs_valid)
            residual_rhs_q44 = rhs_result;
        else
            residual_rhs_q44 = rhs_latched;
        // On a chord-valid launch, correction_index still names the correction
        // that just finished until this edge commits. Select the following
        // pass explicitly so the KCL engine latches the intended format.
        requested_residual_fractional_bits = 6'd30;
        kcl_diagnostic_max_enable = (state == WAIT_CHORD) && chord_valid
                                    && (correction_index == 2'd2);
        if ((state == WAIT_CHORD) && chord_valid) begin
            if (correction_index == 2'd0)
                requested_residual_fractional_bits = 6'd34;
            else if ((correction_index == 2'd1)
                     || ((correction_index == 2'd2) && TERMINAL_CORRECTION))
                requested_residual_fractional_bits = 6'd40;
        end
        kcl_start = residual_launch;
    end

    network_kcl_v1_wide #(
        .CAP_G_FILE(CAP_G_FILE),
        .TRAPEZOIDAL(TRAPEZOIDAL),
        .PIPELINED_FINISH(PIPELINED_KCL_FINISH),
        .PIPELINED_COLUMNS(PIPELINED_KCL_COLUMNS),
        .PIPELINED_ACCUMULATOR(PIPELINED_KCL_ACCUMULATOR),
        .PIPELINED_CAPACITOR_CURRENT(PIPELINED_KCL_CAPACITOR_CURRENT),
        .PIPELINED_MAXIMUM(PIPELINED_KCL_MAXIMUM)
    ) kcl_engine (
        .clk,
        .rst_n,
        .start(kcl_start),
        .voltage(residual_voltage_flat),
        .capacitor_state_q30(capacitor_flat),
        .capacitor_current_state_q44(capacitor_current_flat),
        .rhs_q44(residual_rhs_q44),
        .requested_residual_fractional_bits,
        .diagnostic_max_enable(kcl_diagnostic_max_enable),
        .tube_current_valid(kcl_tube_current_valid),
        .tube_current_q31(tube_current_flat),
        .residual,
        .residual_fractional_bits,
        .max_abs_residual_q44(kcl_max_abs_q44),
        .correction_scale_fallback(kcl_scale_fallback),
        .saturation_any(kcl_saturation_any),
        .saturation_count(kcl_saturation_count),
        .capacitor_current_next_q44(capacitor_current_next_unused),
        .capacitor_current_saturation_count(capacitor_current_saturation_unused),
        .busy(kcl_busy),
        .valid(kcl_valid)
    );

    logic triode_ce;
    logic signed [31:0] triode_v_gk;
    logic signed [31:0] triode_v_pk;
    logic signed [31:0] triode_i_p;
    logic signed [31:0] triode_i_g;
    logic triode_range_clipped;
    logic triode_valid;
    logic signed [31:0] triode2_i_p;
    logic signed [31:0] triode2_i_g;
    logic triode2_range_clipped;
    logic triode2_valid;
    logic signed [31:0] tube1_i_p;
    logic signed [31:0] tube1_i_g;
    logic tube1_range_clipped;

    always_comb begin
        triode_ce = residual_launch;
        triode_v_gk = node_difference_q24(
            $signed(residual_voltage_flat[0 * 40 +: 40]), 0,
            $signed(residual_voltage_flat[2 * 40 +: 40]), 2
        );
        triode_v_pk = node_difference_q20(
            $signed(residual_voltage_flat[1 * 40 +: 40]), 1,
            $signed(residual_voltage_flat[2 * 40 +: 40]), 2
        );
        if (!PARALLEL_TUBES && state == WAIT_TUBE_1) begin
            triode_ce = triode_valid;
            triode_v_gk = node_difference_q24(
                node_voltage[4], 4,
                node_voltage[7], 7
            );
            triode_v_pk = node_difference_q20(
                node_voltage[6], 6,
                node_voltage[7], 7
            );
        end
        if (PARALLEL_TUBES) begin
            kcl_tube_current_valid = (state == WAIT_TUBE_1)
                                     && triode_valid && triode2_valid;
            tube_current_flat[31:0] = triode_i_p;
            tube_current_flat[63:32] = triode_i_g;
            tube_current_flat[95:64] = triode2_i_p;
            tube_current_flat[127:96] = triode2_i_g;
        end else begin
            kcl_tube_current_valid = (state == WAIT_TUBE_2) && triode_valid;
            tube_current_flat[31:0] = tube1_i_p;
            tube_current_flat[63:32] = tube1_i_g;
            tube_current_flat[95:64] = triode_i_p;
            tube_current_flat[127:96] = triode_i_g;
        end
    end

    generate
        if (USE_LINEAR_FACTORIZED_TUBE) begin : generate_linear_tube
            triode_12ax7_factorized_linear tube_engine (
                .clk,
                .rst_n,
                .ce(triode_ce),
                .v_gk(triode_v_gk),
                .v_pk(triode_v_pk),
                .i_p(triode_i_p),
                .i_g(triode_i_g),
                .range_clipped(triode_range_clipped),
                .valid(triode_valid)
            );
        end else begin : generate_hermite_tube
            triode_12ax7_factorized tube_engine (
                .clk,
                .rst_n,
                .ce(triode_ce),
                .v_gk(triode_v_gk),
                .v_pk(triode_v_pk),
                .i_p(triode_i_p),
                .i_g(triode_i_g),
                .range_clipped(triode_range_clipped),
                .valid(triode_valid)
            );
        end
    endgenerate

    generate
        if (PARALLEL_TUBES) begin : generate_parallel_tube
            logic signed [31:0] v_gk;
            logic signed [31:0] v_pk;

            always_comb begin
                v_gk = node_difference_q24(
                    $signed(residual_voltage_flat[4 * 40 +: 40]), 4,
                    $signed(residual_voltage_flat[7 * 40 +: 40]), 7
                );
                v_pk = node_difference_q20(
                    $signed(residual_voltage_flat[6 * 40 +: 40]), 6,
                    $signed(residual_voltage_flat[7 * 40 +: 40]), 7
                );
            end

            if (USE_LINEAR_FACTORIZED_TUBE) begin : generate_linear_tube
                triode_12ax7_factorized_linear tube_engine (
                    .clk,
                    .rst_n,
                    .ce(residual_launch),
                    .v_gk(v_gk),
                    .v_pk(v_pk),
                    .i_p(triode2_i_p),
                    .i_g(triode2_i_g),
                    .range_clipped(triode2_range_clipped),
                    .valid(triode2_valid)
                );
            end else begin : generate_hermite_tube
                triode_12ax7_factorized tube_engine (
                    .clk,
                    .rst_n,
                    .ce(residual_launch),
                    .v_gk(v_gk),
                    .v_pk(v_pk),
                    .i_p(triode2_i_p),
                    .i_g(triode2_i_g),
                    .range_clipped(triode2_range_clipped),
                    .valid(triode2_valid)
                );
            end
        end else begin : generate_no_parallel_tube
            always_comb begin
                triode2_i_p = '0;
                triode2_i_g = '0;
                triode2_range_clipped = 1'b0;
                triode2_valid = 1'b0;
            end
        end
    endgenerate

    logic chord_start;
    logic chord_saturation_any;
    logic [3:0] chord_saturation_count;
    logic chord_busy;
    logic chord_valid;
    logic [359:0] chord_preview_voltage;
    logic chord_preview_valid;
    logic signed [40:0] previous_v_gk2_q32;
    logic signed [40:0] selector_prior_v_gk2_q32;
    logic [2:0] chord_coefficient_set;
    assign chord_start = (state == WAIT_KCL) && kcl_valid
                         && (!final_pass || TERMINAL_CORRECTION);
    assign previous_v_gk2_q32 =
        $signed({node_voltage[4][39], node_voltage[4]})
        - $signed({node_voltage[7][39], node_voltage[7]});

    chord_corrector_v1_wide #(
        .COEFFICIENT_FILE(CHORD_COEFFICIENT_FILE),
        .COEFFICIENT_SETS(CHORD_COEFFICIENT_SETS),
        .PIPELINED_APPLY(PIPELINED_CHORD_APPLY)
    ) chord_engine (
        .clk,
        .rst_n,
        .start(chord_start),
        .voltage(voltage_flat),
        .residual,
        .residual_fractional_bits,
        .coefficient_set(chord_coefficient_set),
        .corrected_voltage,
        .preview_voltage(chord_preview_voltage),
        .preview_valid(chord_preview_valid),
        .saturation_any(chord_saturation_any),
        .saturation_count(chord_saturation_count),
        .busy(chord_busy),
        .valid(chord_valid)
    );

    integer lane;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            correction_index <= '0;
            final_pass <= 1'b0;
            cycle_count <= '0;
            deadline_reported <= 1'b0;
            rhs_latched <= '0;
            tube1_i_p <= '0;
            tube1_i_g <= '0;
            tube1_range_clipped <= 1'b0;
            output_q32 <= '0;
            output_valid <= 1'b0;
            busy <= 1'b0;
            sample_latency_cycles <= '0;
            missed_request_count <= '0;
            deadline_miss_count <= '0;
            saturation_count <= '0;
            lut_clip_count <= '0;
            nonconvergence_count <= '0;
            correction_scale_fallback_count <= '0;
            minimum_correction_fractional_bits <= '0;
            last_residual_q44 <= '0;
            chord_coefficient_set <= '0;
            selector_prior_v_gk2_q32 <=
                $signed({node_initial[4][39], node_initial[4]})
                - $signed({node_initial[7][39], node_initial[7]});
            for (lane = 0; lane < 9; lane = lane + 1)
                node_voltage[lane] <= node_initial[lane];
            for (lane = 0; lane < 10; lane = lane + 1)
                capacitor_state[lane] <= capacitor_initial[lane];
            for (lane = 0; lane < 10; lane = lane + 1)
                capacitor_current_state[lane] <= capacitor_current_initial[lane];
        end else begin
            output_valid <= 1'b0;
            if (ce_sample && busy)
                missed_request_count <= missed_request_count + 1'b1;
            if (busy) begin
                cycle_count <= cycle_count + 1'b1;
                if ((cycle_count == 8'd127) && !deadline_reported) begin
                    deadline_miss_count <= deadline_miss_count + 1'b1;
                    deadline_reported <= 1'b1;
                end
            end

            case (state)
                IDLE: begin
                    busy <= 1'b0;
                    if (ce_sample) begin
                        busy <= 1'b1;
                        cycle_count <= '0;
                        deadline_reported <= 1'b0;
                        correction_index <= '0;
                        final_pass <= 1'b0;
                        chord_coefficient_set <= select_chord_coefficient_set(
                            previous_v_gk2_q32,
                            selector_prior_v_gk2_q32
                        );
                        selector_prior_v_gk2_q32 <= previous_v_gk2_q32;
                        state <= WAIT_RHS;
                    end
                end

                WAIT_RHS: begin
                    if (rhs_valid) begin
                        rhs_latched <= rhs_result;
                        tube1_range_clipped <= 1'b0;
                        state <= WAIT_TUBE_1;
                    end
                end

                WAIT_TUBE_1: begin
                    if (PARALLEL_TUBES && triode_valid && triode2_valid) begin
                        if (triode_range_clipped || triode2_range_clipped)
                            lut_clip_count <= lut_clip_count + 1'b1;
                        state <= WAIT_KCL;
                    end else if (!PARALLEL_TUBES && triode_valid) begin
                        tube1_i_p <= triode_i_p;
                        tube1_i_g <= triode_i_g;
                        tube1_range_clipped <= triode_range_clipped;
                        state <= WAIT_TUBE_2;
                    end
                end

                WAIT_TUBE_2: begin
                    if (triode_valid) begin
                        if (tube1_range_clipped || triode_range_clipped)
                            lut_clip_count <= lut_clip_count + 1'b1;
                        state <= WAIT_KCL;
                    end
                end

                WAIT_KCL: begin
                    if (kcl_valid) begin
                        if (final_pass) begin
                            last_residual_q44 <= kcl_max_abs_q44;
                            if (kcl_max_abs_q44 > RESIDUAL_LIMIT_Q44)
                                nonconvergence_count <= nonconvergence_count + 1'b1;
                            if (TERMINAL_CORRECTION) begin
                                saturation_count <= saturation_count
                                    + {28'd0, kcl_saturation_count};
                                if (kcl_scale_fallback) begin
                                    correction_scale_fallback_count <=
                                        correction_scale_fallback_count + 1'b1;
                                    if (minimum_correction_fractional_bits == 0
                                        || residual_fractional_bits
                                           < minimum_correction_fractional_bits)
                                        minimum_correction_fractional_bits <=
                                            residual_fractional_bits;
                                end
                                state <= WAIT_CHORD;
                            end else begin
                                saturation_count <= saturation_count
                                    + {28'd0, capacitor_saturation_count}
                                    + {28'd0, capacitor_current_saturation_unused};
                                for (lane = 0; lane < 10; lane = lane + 1) begin
                                    capacitor_state[lane] <= capacitor_next[lane];
                                    if (TRAPEZOIDAL)
                                        capacitor_current_state[lane] <= $signed(
                                            capacitor_current_next_unused[
                                                lane * 48 +: 48
                                            ]
                                        );
                                end
                                output_q32 <= node_voltage[8];
                                sample_latency_cycles <= cycle_count + 1'b1;
                                output_valid <= 1'b1;
                                busy <= 1'b0;
                                state <= IDLE;
                            end
                        end else begin
                            saturation_count <= saturation_count
                                + {28'd0, kcl_saturation_count};
                            if (kcl_scale_fallback) begin
                                correction_scale_fallback_count <=
                                    correction_scale_fallback_count + 1'b1;
                                if (minimum_correction_fractional_bits == 0
                                    || residual_fractional_bits
                                       < minimum_correction_fractional_bits)
                                    minimum_correction_fractional_bits <=
                                        residual_fractional_bits;
                            end
                            state <= WAIT_CHORD;
                        end
                    end
                end

                WAIT_CHORD: begin
                    if (chord_valid) begin
                        if (final_pass) begin
                            if (HALF_PARALLEL_TERMINAL_CURRENT) begin
                                state <= WAIT_TERMINAL;
                            end else begin
                                saturation_count <= saturation_count
                                    + {28'd0, chord_saturation_count}
                                    + {28'd0,
                                       terminal_capacitor_saturation_count}
                                    + (TRAPEZOIDAL
                                       ? {28'd0,
                                          terminal_current_saturation_count}
                                       : 32'd0);
                                for (lane = 0; lane < 9; lane = lane + 1)
                                    node_voltage[lane] <=
                                        corrected_node_voltage[lane];
                                for (lane = 0; lane < 10;
                                     lane = lane + 1) begin
                                    capacitor_state[lane] <=
                                        terminal_capacitor_next[lane];
                                    if (TRAPEZOIDAL)
                                        capacitor_current_state[lane] <=
                                            $signed(terminal_current_flat[
                                                lane * 48 +: 48
                                            ]);
                                end
                                output_q32 <= corrected_node_voltage[8];
                                sample_latency_cycles <= cycle_count + 1'b1;
                                output_valid <= 1'b1;
                                busy <= 1'b0;
                                state <= IDLE;
                            end
                        end else begin
                            saturation_count <= saturation_count
                                + {28'd0, chord_saturation_count};
                            for (lane = 0; lane < 9; lane = lane + 1)
                                node_voltage[lane] <= corrected_node_voltage[lane];
                            if (correction_index == 2'd2)
                                final_pass <= 1'b1;
                            else
                                correction_index <= correction_index + 1'b1;
                            tube1_range_clipped <= 1'b0;
                            state <= WAIT_TUBE_1;
                        end
                    end
                end

                WAIT_TERMINAL: begin
                    if (terminal_current_ready) begin
                        saturation_count <= saturation_count
                            + {28'd0, chord_saturation_count}
                            + {28'd0, terminal_capacitor_saturation_count}
                            + {28'd0, terminal_current_saturation_count};
                        for (lane = 0; lane < 9; lane = lane + 1)
                            node_voltage[lane] <= corrected_node_voltage[lane];
                        for (lane = 0; lane < 10; lane = lane + 1) begin
                            capacitor_state[lane] <=
                                terminal_capacitor_next[lane];
                            capacitor_current_state[lane] <=
                                $signed(terminal_current_flat[
                                    lane * 48 +: 48
                                ]);
                        end
                        output_q32 <= corrected_node_voltage[8];
                        sample_latency_cycles <= cycle_count + 1'b1;
                        output_valid <= 1'b1;
                        busy <= 1'b0;
                        state <= IDLE;
                    end
                end

                default: state <= IDLE;
            endcase
        end
    end

    logic unused_status;
    always_comb unused_status = rhs_busy || kcl_busy || kcl_saturation_any
                                || chord_busy || chord_saturation_any
                                || (HALF_PARALLEL_TERMINAL_CURRENT
                                    && (state == WAIT_TERMINAL)
                                    && !terminal_current_ready)
                                || ((!HALF_PARALLEL_TERMINAL_CURRENT)
                                    && ((|terminal_preview_capacitor_flat)
                                        || terminal_current_preview_start))
                                || ((!TRAPEZOIDAL)
                                    && ((|capacitor_current_next_unused)
                                        || (|capacitor_current_saturation_unused)));

endmodule

`default_nettype wire
