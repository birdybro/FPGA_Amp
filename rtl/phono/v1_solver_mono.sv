`timescale 1ns/1ps
`default_nettype none

// Bit-accurate mono scheduler for the frozen two-triode passive-RIAA V1 model.
//
// One sample request launches a backward-Euler RHS evaluation followed by
// three constant-Jacobian corrections and a fourth residual-only diagnostic
// pass. The nine linear KCL products overlap the two serialized tube lookups.
// All state is retained in the same heterogeneous node formats used by the
// Python fixed-point reference.
module v1_solver_mono #(
    parameter NODE_INITIAL_FILE = "model/generated/v1_node_initial.mem",
    parameter CAP_INITIAL_FILE = "model/generated/v1_cap_initial_q12_20.mem",
    parameter bit USE_FACTORIZED_TUBE = 1'b0
) (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  ce_sample,
    input  logic signed [31:0]    input_q24,
    output logic signed [31:0]    output_q20,
    output logic                  output_valid,
    output logic                  busy,
    output logic [7:0]            sample_latency_cycles,
    output logic [31:0]           missed_request_count,
    output logic [31:0]           deadline_miss_count,
    output logic [31:0]           saturation_count,
    output logic [31:0]           lut_clip_count,
    output logic [31:0]           nonconvergence_count,
    output logic [54:0]           last_residual_q44,
    output logic [287:0]          node_voltage_debug,
    output logic [319:0]          capacitor_state_debug
);

    localparam logic [54:0] RESIDUAL_LIMIT_Q44 = 55'd35184372; // 2 uA

    typedef enum logic [3:0] {
        IDLE,
        WAIT_RHS,
        WAIT_TUBE_1,
        WAIT_TUBE_2,
        WAIT_KCL,
        WAIT_CHORD
    } state_t;

    state_t state;
    logic [1:0] correction_index;
    logic final_pass;
    logic [7:0] cycle_count;
    logic deadline_reported;

    logic signed [31:0] node_initial [0:8];
    logic signed [31:0] capacitor_initial [0:9];
    logic signed [31:0] node_voltage [0:8];
    logic signed [31:0] capacitor_state [0:9];
    logic signed [31:0] capacitor_next [0:9];

    initial begin
        $readmemh(NODE_INITIAL_FILE, node_initial);
        $readmemh(CAP_INITIAL_FILE, capacitor_initial);
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

    function automatic logic node_is_q24(input int index);
        begin
            case (index)
                0, 2, 4, 5, 7: node_is_q24 = 1'b1;
                default:       node_is_q24 = 1'b0;
            endcase
        end
    endfunction

    function automatic logic signed [31:0] to_q20(
        input logic signed [31:0] value,
        input int index
    );
        logic signed [32:0] biased;
        begin
            if (node_is_q24(index)) begin
                biased = $signed({value[31], value}) + 33'sd8;
                to_q20 = 32'($signed(biased) >>> 4);
            end else begin
                to_q20 = value;
            end
        end
    endfunction

    function automatic logic signed [31:0] subtract_32(
        input logic signed [31:0] left,
        input logic signed [31:0] right
    );
        begin
            subtract_32 = left - right;
        end
    endfunction

    logic [287:0] voltage_flat;
    logic [319:0] capacitor_flat;
    always_comb begin
        for (int lane = 0; lane < 9; lane = lane + 1) begin
            voltage_flat[lane * 32 +: 32] = node_voltage[lane];
            node_voltage_debug[lane * 32 +: 32] = node_voltage[lane];
        end
        for (int lane = 0; lane < 10; lane = lane + 1) begin
            capacitor_flat[lane * 32 +: 32] = capacitor_state[lane];
            capacitor_state_debug[lane * 32 +: 32] = capacitor_state[lane];
            if (cap_node_a(lane) >= 0)
                capacitor_next[lane] = to_q20(
                    node_voltage[cap_node_a(lane)], cap_node_a(lane)
                );
            else
                capacitor_next[lane] = '0;
            if (cap_node_b(lane) >= 0)
                capacitor_next[lane] = subtract_32(
                    capacitor_next[lane],
                    to_q20(node_voltage[cap_node_b(lane)], cap_node_b(lane))
                );
        end
    end

    logic rhs_start;
    logic [494:0] rhs_result;
    logic [494:0] rhs_latched;
    logic rhs_busy;
    logic rhs_valid;
    assign rhs_start = (state == IDLE) && ce_sample;

    network_rhs_v1 rhs_engine (
        .clk,
        .rst_n,
        .start(rhs_start),
        .input_q24,
        .capacitor_state_q20(capacitor_flat),
        .rhs_q44(rhs_result),
        .busy(rhs_busy),
        .valid(rhs_valid)
    );

    logic kcl_start;
    logic residual_launch;
    logic [287:0] residual_voltage_flat;
    logic [494:0] residual_rhs_q44;
    logic kcl_tube_current_valid;
    logic [127:0] tube_current_flat;
    logic [224:0] residual_q30;
    logic [54:0] kcl_max_abs_q44;
    logic kcl_saturation_any;
    logic [3:0] kcl_saturation_count;
    logic kcl_busy;
    logic kcl_valid;
    always_comb begin
        residual_launch = ((state == WAIT_RHS) && rhs_valid) ||
                          ((state == WAIT_CHORD) && chord_valid);
        if ((state == WAIT_CHORD) && chord_valid)
            residual_voltage_flat = corrected_voltage;
        else
            residual_voltage_flat = voltage_flat;
        if ((state == WAIT_RHS) && rhs_valid)
            residual_rhs_q44 = rhs_result;
        else
            residual_rhs_q44 = rhs_latched;
        kcl_start = residual_launch;
    end

    network_kcl_v1 kcl_engine (
        .clk,
        .rst_n,
        .start(kcl_start),
        .voltage(residual_voltage_flat),
        .rhs_q44(residual_rhs_q44),
        .tube_current_valid(kcl_tube_current_valid),
        .tube_current_q31(tube_current_flat),
        .residual_q30,
        .max_abs_residual_q44(kcl_max_abs_q44),
        .saturation_any(kcl_saturation_any),
        .saturation_count(kcl_saturation_count),
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
    logic signed [31:0] tube1_i_p;
    logic signed [31:0] tube1_i_g;
    logic tube1_range_clipped;

    always_comb begin
        triode_ce = residual_launch ||
                    ((state == WAIT_TUBE_1) && triode_valid);
        if (state == WAIT_TUBE_1) begin
            triode_v_gk = subtract_32(node_voltage[4], node_voltage[7]);
            triode_v_pk = subtract_32(node_voltage[6], to_q20(node_voltage[7], 7));
        end else begin
            triode_v_gk = subtract_32(
                $signed(residual_voltage_flat[0 * 32 +: 32]),
                $signed(residual_voltage_flat[2 * 32 +: 32])
            );
            triode_v_pk = subtract_32(
                $signed(residual_voltage_flat[1 * 32 +: 32]),
                to_q20($signed(residual_voltage_flat[2 * 32 +: 32]), 2)
            );
        end
        kcl_tube_current_valid = (state == WAIT_TUBE_2) && triode_valid;
        tube_current_flat[31:0] = tube1_i_p;
        tube_current_flat[63:32] = tube1_i_g;
        tube_current_flat[95:64] = triode_i_p;
        tube_current_flat[127:96] = triode_i_g;
    end

    generate
        if (USE_FACTORIZED_TUBE) begin : generate_factorized_tube
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
        end else begin : generate_surface_tube
            triode_12ax7 tube_engine (
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

    logic chord_start;
    logic [287:0] corrected_voltage;
    logic chord_saturation_any;
    logic [3:0] chord_saturation_count;
    logic chord_busy;
    logic chord_valid;
    assign chord_start = (state == WAIT_KCL) && kcl_valid && !final_pass;

    chord_corrector_v1 chord_engine (
        .clk,
        .rst_n,
        .start(chord_start),
        .voltage(voltage_flat),
        .residual_q30,
        .corrected_voltage,
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
            output_q20 <= '0;
            output_valid <= 1'b0;
            busy <= 1'b0;
            sample_latency_cycles <= '0;
            missed_request_count <= '0;
            deadline_miss_count <= '0;
            saturation_count <= '0;
            lut_clip_count <= '0;
            nonconvergence_count <= '0;
            last_residual_q44 <= '0;
            for (lane = 0; lane < 9; lane = lane + 1)
                node_voltage[lane] <= node_initial[lane];
            for (lane = 0; lane < 10; lane = lane + 1)
                capacitor_state[lane] <= capacitor_initial[lane];
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
                    if (triode_valid) begin
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
                        saturation_count <= saturation_count +
                                            {28'd0, kcl_saturation_count};
                        if (final_pass) begin
                            last_residual_q44 <= kcl_max_abs_q44;
                            if (kcl_max_abs_q44 > RESIDUAL_LIMIT_Q44)
                                nonconvergence_count <= nonconvergence_count + 1'b1;
                            for (lane = 0; lane < 10; lane = lane + 1)
                                capacitor_state[lane] <= capacitor_next[lane];
                            output_q20 <= node_voltage[8];
                            sample_latency_cycles <= cycle_count + 1'b1;
                            output_valid <= 1'b1;
                            busy <= 1'b0;
                            state <= IDLE;
                        end else begin
                            state <= WAIT_CHORD;
                        end
                    end
                end

                WAIT_CHORD: begin
                    if (chord_valid) begin
                        saturation_count <= saturation_count +
                                            {28'd0, chord_saturation_count};
                        for (lane = 0; lane < 9; lane = lane + 1)
                            node_voltage[lane] <= $signed(
                                corrected_voltage[lane * 32 +: 32]
                            );
                        if (correction_index == 2'd2) begin
                            final_pass <= 1'b1;
                        end else begin
                            correction_index <= correction_index + 1'b1;
                        end
                        tube1_range_clipped <= 1'b0;
                        state <= WAIT_TUBE_1;
                    end
                end

                default: state <= IDLE;
            endcase
        end
    end

    // These signals are intentionally retained as integration probes even
    // though the scheduler currently relies on submodule valid pulses.
    logic unused_status;
    always_comb unused_status = rhs_busy || kcl_busy || kcl_saturation_any ||
                                chord_busy || chord_saturation_any;

endmodule

`default_nettype wire
