`timescale 1ns/1ps
`default_nettype none

// Timing-only wrappers for the three wide-network blocks surrounding the tube
// primitive.  Wide internal LFSRs keep package I/O to the same three Arty pins
// as the complete solver harness while exercising every datapath bit.  These
// modules are diagnostic tops, not deployable audio designs.
module terminal_current_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    logic [399:0] terminal_voltage_q30;
    logic [399:0] previous_voltage_q30;
    logic [479:0] previous_current_q44;
    (* keep *) logic [479:0] next_current_q44;
    (* keep *) logic [3:0] saturation_count;

    always_ff @(posedge fabric_clk) begin
        if (reset) begin
            terminal_voltage_q30 <= {{12{32'h1ace_b00c}}, 16'h5a39};
            previous_voltage_q30 <= {{12{32'h91e1_0da5}}, 16'hc36f};
            previous_current_q44 <= {15{32'h6d2b_79f5}};
            activity <= 1'b0;
        end else begin
            terminal_voltage_q30 <= {
                terminal_voltage_q30[398:0],
                terminal_voltage_q30[399] ^ terminal_voltage_q30[264]
                ^ terminal_voltage_q30[17] ^ terminal_voltage_q30[0]
            };
            previous_voltage_q30 <= {
                previous_voltage_q30[398:0],
                previous_voltage_q30[399] ^ previous_voltage_q30[356]
                ^ previous_voltage_q30[121] ^ previous_voltage_q30[0]
            };
            previous_current_q44 <= {
                previous_current_q44[478:0],
                previous_current_q44[479] ^ previous_current_q44[370]
                ^ previous_current_q44[47] ^ previous_current_q44[0]
            };
            // The keep-marked buses preserve the full engine.  Feed only one
            // bit to the package pin so this harness does not append a wide
            // reduction tree to the datapath being measured.
            activity <= activity ^ next_current_q44[0]
                        ^ saturation_count[0];
        end
    end

    (* keep *) terminal_current_update_v1 engine (
        .terminal_voltage_q30,
        .previous_voltage_q30,
        .previous_current_q44,
        .next_current_q44,
        .saturation_count
    );

endmodule

module kcl_pnr_harness #(
    parameter bit PIPELINED_FINISH = 1'b0,
    parameter bit PIPELINED_COLUMNS = 1'b0,
    parameter bit PIPELINED_ACCUMULATOR = 1'b0,
    parameter bit PIPELINED_CAPACITOR_CURRENT = 1'b0,
    parameter bit PIPELINED_MAXIMUM = 1'b0
) (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    logic rst_n;
    logic [359:0] voltage;
    logic [399:0] capacitor_state_q30;
    logic [479:0] capacitor_current_state_q44;
    logic [494:0] rhs_q44;
    logic [127:0] tube_current_q31;
    logic start;
    (* keep *) logic [224:0] residual;
    (* keep *) logic [5:0] residual_fractional_bits;
    (* keep *) logic [62:0] max_abs_residual_q44;
    (* keep *) logic correction_scale_fallback;
    (* keep *) logic saturation_any;
    (* keep *) logic [3:0] saturation_count;
    (* keep *) logic [479:0] capacitor_current_next_q44;
    (* keep *) logic [3:0] capacitor_current_saturation_count;
    (* keep *) logic busy;
    (* keep *) logic valid;

    assign rst_n = !reset;
    assign start = !busy;

    always_ff @(posedge fabric_clk) begin
        if (!rst_n) begin
            voltage <= {{11{32'h1ace_b00c}}, 8'h5a};
            capacitor_state_q30 <= {{12{32'h91e1_0da5}}, 16'hc36f};
            capacitor_current_state_q44 <= {15{32'h6d2b_79f5}};
            rhs_q44 <= {{15{32'hcafe_4a11}}, 15'h2c39};
            tube_current_q31 <= {4{32'h1234_5678}};
            activity <= 1'b0;
        end else begin
            voltage <= {voltage[358:0], voltage[359] ^ voltage[23] ^ voltage[0]};
            capacitor_state_q30 <= {
                capacitor_state_q30[398:0],
                capacitor_state_q30[399] ^ capacitor_state_q30[121]
                ^ capacitor_state_q30[0]
            };
            capacitor_current_state_q44 <= {
                capacitor_current_state_q44[478:0],
                capacitor_current_state_q44[479]
                ^ capacitor_current_state_q44[47]
                ^ capacitor_current_state_q44[0]
            };
            rhs_q44 <= {rhs_q44[493:0], rhs_q44[494] ^ rhs_q44[313] ^ rhs_q44[0]};
            tube_current_q31 <= {
                tube_current_q31[126:0],
                tube_current_q31[127] ^ tube_current_q31[95]
                ^ tube_current_q31[0]
            };
            if (valid)
                activity <= activity
                            ^ residual[0]
                            ^ residual_fractional_bits[0]
                            ^ max_abs_residual_q44[0]
                            ^ correction_scale_fallback
                            ^ saturation_any
                            ^ saturation_count[0]
                            ^ capacitor_current_next_q44[0]
                            ^ capacitor_current_saturation_count[0];
        end
    end

    (* keep *) network_kcl_v1_wide #(
        .CAP_G_FILE(
            "model/generated/v1_cap_conductance_q0_47_trapezoidal.mem"
        ),
        .TRAPEZOIDAL(1'b1),
        .PIPELINED_FINISH(PIPELINED_FINISH),
        .PIPELINED_COLUMNS(PIPELINED_COLUMNS),
        .PIPELINED_ACCUMULATOR(PIPELINED_ACCUMULATOR),
        .PIPELINED_CAPACITOR_CURRENT(PIPELINED_CAPACITOR_CURRENT),
        .PIPELINED_MAXIMUM(PIPELINED_MAXIMUM)
    ) engine (
        .clk(fabric_clk),
        .rst_n,
        .start,
        .voltage,
        .capacitor_state_q30,
        .capacitor_current_state_q44,
        .rhs_q44,
        .requested_residual_fractional_bits(6'd40),
        .diagnostic_max_enable(1'b1),
        .tube_current_valid(1'b1),
        .tube_current_q31,
        .residual,
        .residual_fractional_bits,
        .max_abs_residual_q44,
        .correction_scale_fallback,
        .saturation_any,
        .saturation_count,
        .capacitor_current_next_q44,
        .capacitor_current_saturation_count,
        .busy,
        .valid
    );

endmodule

module deep_pipelined_kcl_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    kcl_pnr_harness #(
        .PIPELINED_FINISH(1'b1),
        .PIPELINED_COLUMNS(1'b1),
        .PIPELINED_ACCUMULATOR(1'b1)
    ) harness (.*);

endmodule

module max_pipelined_kcl_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    kcl_pnr_harness #(
        .PIPELINED_FINISH(1'b1),
        .PIPELINED_COLUMNS(1'b1),
        .PIPELINED_ACCUMULATOR(1'b1),
        .PIPELINED_CAPACITOR_CURRENT(1'b1)
    ) harness (.*);

endmodule

module diagnostic_pipelined_kcl_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    kcl_pnr_harness #(
        .PIPELINED_FINISH(1'b1),
        .PIPELINED_COLUMNS(1'b1),
        .PIPELINED_ACCUMULATOR(1'b1),
        .PIPELINED_MAXIMUM(1'b1)
    ) harness (.*);

endmodule

module pipelined_kcl_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    kcl_pnr_harness #(
        .PIPELINED_FINISH(1'b1),
        .PIPELINED_COLUMNS(1'b1)
    ) harness (.*);

endmodule

module chord_pnr_harness #(
    parameter bit PIPELINED_APPLY = 1'b0
) (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    logic rst_n;
    logic [359:0] voltage;
    logic [224:0] residual;
    logic [2:0] coefficient_set;
    logic start;
    (* keep *) logic [359:0] corrected_voltage;
    (* keep *) logic saturation_any;
    (* keep *) logic [3:0] saturation_count;
    (* keep *) logic busy;
    (* keep *) logic valid;

    assign rst_n = !reset;
    assign start = !busy;

    always_ff @(posedge fabric_clk) begin
        if (!rst_n) begin
            voltage <= {{11{32'h1ace_b00c}}, 8'h5a};
            residual <= {{7{32'h91e1_0da5}}, 1'b1};
            coefficient_set <= '0;
            activity <= 1'b0;
        end else begin
            voltage <= {voltage[358:0], voltage[359] ^ voltage[23] ^ voltage[0]};
            residual <= {
                residual[223:0],
                residual[224] ^ residual[159] ^ residual[0]
            };
            if (start)
                coefficient_set <= coefficient_set == 3'd4
                                   ? 3'd0 : coefficient_set + 1'b1;
            if (valid)
                activity <= activity
                            ^ corrected_voltage[0]
                            ^ saturation_any
                            ^ saturation_count[0];
        end
    end

    (* keep *) chord_corrector_v1_wide #(
        .COEFFICIENT_FILE(
            "model/generated/v1_chord_inverse_banked_q17_1_trapezoidal.mem"
        ),
        .COEFFICIENT_SETS(5),
        .PIPELINED_APPLY(PIPELINED_APPLY)
    ) engine (
        .clk(fabric_clk),
        .rst_n,
        .start,
        .voltage,
        .residual,
        .residual_fractional_bits(6'd40),
        .coefficient_set,
        .corrected_voltage,
        .saturation_any,
        .saturation_count,
        .busy,
        .valid
    );

endmodule

module pipelined_chord_pnr_harness (
    input  logic fabric_clk,
    input  logic reset,
    output logic activity
);

    chord_pnr_harness #(
        .PIPELINED_APPLY(1'b1)
    ) harness (.*);

endmodule

`default_nettype wire
