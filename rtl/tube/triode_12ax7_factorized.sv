`timescale 1ns/1ps
`default_nettype none

// Factorized fixed-point implementation of the Koren 12AX7 current law.
//
// Inputs retain the established Q8.24 Vgk and Q12.20 Vpk interfaces; outputs
// are signed Q0.31 amperes. Three physical scalar functions are represented by
// packed 1-D value/derivative-times-step ROMs and cubic Hermite interpolation.
module triode_12ax7_factorized #(
    parameter RECIPROCAL_FILE = "model/generated/12ax7_factor_reciprocal_q32.mem",
    parameter SOFTPLUS_FILE = "model/generated/12ax7_factor_softplus_q32.mem",
    parameter POWER_FILE = "model/generated/12ax7_factor_power_q31.mem",
    parameter GRID_FILE = "model/generated/12ax7_factor_grid_q31.mem"
) (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               ce,
    input  logic signed [31:0] v_gk,
    input  logic signed [31:0] v_pk,
    output logic signed [31:0] i_p,
    output logic signed [31:0] i_g,
    output logic               range_clipped,
    output logic               valid
);

    localparam int RECIPROCAL_POINTS = 512;
    localparam int SOFTPLUS_POINTS = 1024;
    localparam int POWER_POINTS = 2048;
    localparam int GRID_POINTS = 128;
    localparam logic signed [31:0] VG_MIN_Q24 = -32'sd83886080;
    localparam logic signed [31:0] VG_MAX_Q24 = 32'sd16777216;
    localparam logic signed [31:0] VP_MIN_Q20 = 32'sd0;
    localparam logic signed [31:0] VP_MAX_Q20 = 32'sd419430400;
    localparam logic signed [63:0] Z_MIN_Q30 = -64'sd322122547;
    localparam logic signed [63:0] Z_MAX_Q30 = 64'sd85899346;
    localparam logic signed [63:0] E1_MIN_Q20 = 64'sd0;
    localparam logic signed [63:0] E1_MAX_Q20 = 64'sd6291456;
    localparam logic signed [63:0] INV_MU_Q30 = 64'sd10737418;
    localparam logic signed [31:0] RECIPROCAL_SCALE_Q24 = 32'sd1339556;
    localparam logic signed [31:0] SOFTPLUS_SCALE_Q24 = 32'sd2756716;
    localparam logic signed [31:0] POWER_SCALE_Q24 = 32'sd357739179;
    localparam logic signed [31:0] GRID_SCALE_Q24 = 32'sd1387179;

    // Low word is the function value; high word is derivative times axis step.
    logic [63:0] reciprocal_lut [0:RECIPROCAL_POINTS-1];
    logic [63:0] softplus_lut [0:SOFTPLUS_POINTS-1];
    logic [63:0] power_lut [0:POWER_POINTS-1];
    logic signed [31:0] grid_lut [0:GRID_POINTS-1];

    initial begin
        $readmemh(RECIPROCAL_FILE, reciprocal_lut);
        $readmemh(SOFTPLUS_FILE, softplus_lut);
        $readmemh(POWER_FILE, power_lut);
        $readmemh(GRID_FILE, grid_lut);
    end

    function automatic logic signed [31:0] hermite_q16(
        input logic signed [31:0] y0,
        input logic signed [31:0] y1,
        input logic signed [31:0] m0,
        input logic signed [31:0] m1,
        input logic        [15:0] fraction
    );
        logic signed [31:0] delta;
        logic signed [31:0] coefficient_2;
        logic signed [31:0] coefficient_3;
        logic signed [48:0] product;
        logic signed [31:0] stage;
        logic signed [16:0] fraction_signed;
        begin
            fraction_signed = $signed({1'b0, fraction});
            delta = y1 - y0;
            coefficient_2 = 3 * delta - 2 * m0 - m1;
            coefficient_3 = -2 * delta + m0 + m1;
            product = coefficient_3 * fraction_signed;
            stage = 32'(($signed(product) + 49'sd32768) >>> 16) + coefficient_2;
            product = stage * fraction_signed;
            stage = 32'(($signed(product) + 49'sd32768) >>> 16) + m0;
            product = stage * fraction_signed;
            stage = 32'(($signed(product) + 49'sd32768) >>> 16) + y0;
            hermite_q16 = stage;
        end
    endfunction

    function automatic logic signed [31:0] linear_q16(
        input logic signed [31:0] lower,
        input logic signed [31:0] upper,
        input logic        [15:0] fraction
    );
        logic signed [63:0] delta;
        logic signed [63:0] weighted;
        logic signed [16:0] fraction_signed;
        begin
            fraction_signed = $signed({1'b0, fraction});
            delta = $signed({{32{upper[31]}}, upper}) -
                    $signed({{32{lower[31]}}, lower});
            weighted = ($signed({{32{lower[31]}}, lower}) <<< 16)
                     + delta * fraction_signed;
            linear_q16 = 32'(($signed(weighted) + 64'sd32768) >>> 16);
        end
    endfunction

    function automatic logic [31:0] map_plate_coordinate(
        input logic signed [31:0] value_q20
    );
        logic signed [63:0] product;
        begin
            if (value_q20 <= VP_MIN_Q20)
                map_plate_coordinate = 32'd0;
            else if (value_q20 >= VP_MAX_Q20)
                map_plate_coordinate = 32'd33488896;
            else begin
                product = $signed(value_q20) * $signed(RECIPROCAL_SCALE_Q24);
                map_plate_coordinate =
                    32'(($signed(product) + 64'sd8388608) >>> 24);
            end
        end
    endfunction

    function automatic logic [31:0] map_softplus_coordinate(
        input logic signed [63:0] value_q30
    );
        logic signed [63:0] offset;
        logic signed [63:0] product;
        begin
            if (value_q30 <= Z_MIN_Q30)
                map_softplus_coordinate = 32'd0;
            else if (value_q30 >= Z_MAX_Q30)
                map_softplus_coordinate = 32'd67043328;
            else begin
                offset = value_q30 - Z_MIN_Q30;
                product = offset * $signed(SOFTPLUS_SCALE_Q24);
                map_softplus_coordinate =
                    32'(($signed(product) + 64'sd8388608) >>> 24);
            end
        end
    endfunction

    function automatic logic [31:0] map_power_coordinate(
        input logic signed [63:0] value_q20
    );
        logic signed [63:0] product;
        begin
            if (value_q20 <= E1_MIN_Q20)
                map_power_coordinate = 32'd0;
            else if (value_q20 >= E1_MAX_Q20)
                map_power_coordinate = 32'd134152192;
            else begin
                product = value_q20 * $signed(POWER_SCALE_Q24);
                map_power_coordinate =
                    32'(($signed(product) + 64'sd8388608) >>> 24);
            end
        end
    endfunction

    function automatic logic [31:0] map_grid_coordinate(
        input logic signed [31:0] value_q24
    );
        logic signed [63:0] offset;
        logic signed [63:0] product;
        begin
            if (value_q24 <= VG_MIN_Q24)
                map_grid_coordinate = 32'd0;
            else if (value_q24 >= VG_MAX_Q24)
                map_grid_coordinate = 32'd8323072;
            else begin
                offset = $signed({{32{value_q24[31]}}, value_q24}) -
                         $signed({{32{VG_MIN_Q24[31]}}, VG_MIN_Q24});
                product = offset * $signed(GRID_SCALE_Q24);
                map_grid_coordinate =
                    32'(($signed(product) + 64'sd8388608) >>> 24);
            end
        end
    endfunction

    typedef enum logic [3:0] {
        IDLE,
        RECIPROCAL_WAIT,
        RECIPROCAL_CALCULATE,
        SOFTPLUS_MAP,
        SOFTPLUS_WAIT,
        SOFTPLUS_CALCULATE,
        POWER_MAP,
        POWER_WAIT,
        POWER_CALCULATE
    } state_t;

    state_t state;
    logic signed [31:0] v_gk_latched;
    logic signed [31:0] v_pk_latched;
    logic clipped_pending;
    logic [15:0] reciprocal_fraction;
    logic [15:0] softplus_fraction;
    logic [15:0] power_fraction;
    logic [15:0] grid_fraction;
    logic [8:0] reciprocal_address_0;
    logic [8:0] reciprocal_address_1;
    logic [9:0] softplus_address_0;
    logic [9:0] softplus_address_1;
    logic [10:0] power_address_0;
    logic [10:0] power_address_1;
    logic [6:0] grid_address_0;
    logic [6:0] grid_address_1;
    logic [63:0] reciprocal_read_0;
    logic [63:0] reciprocal_read_1;
    logic [63:0] softplus_read_0;
    logic [63:0] softplus_read_1;
    logic [63:0] power_read_0;
    logic [63:0] power_read_1;
    logic signed [31:0] grid_read_0;
    logic signed [31:0] grid_read_1;
    logic signed [63:0] transformed_q30;
    logic signed [63:0] e1_q20;

    logic [31:0] plate_coordinate_comb;
    logic [31:0] grid_coordinate_comb;
    logic [31:0] softplus_coordinate_comb;
    logic [31:0] power_coordinate_comb;
    logic signed [31:0] hermite_y0;
    logic signed [31:0] hermite_y1;
    logic signed [31:0] hermite_m0;
    logic signed [31:0] hermite_m1;
    logic [15:0] hermite_fraction;
    logic signed [31:0] hermite_interpolated;
    logic signed [31:0] grid_interpolated;
    logic signed [63:0] reciprocal_product;
    logic signed [63:0] transformed_comb;
    logic signed [63:0] e1_product;
    logic signed [63:0] e1_comb;

    always_comb begin
        plate_coordinate_comb = map_plate_coordinate(v_pk);
        grid_coordinate_comb = map_grid_coordinate(v_gk);
        softplus_coordinate_comb = map_softplus_coordinate(transformed_q30);
        power_coordinate_comb = map_power_coordinate(e1_q20);
        hermite_y0 = $signed(power_read_0[31:0]);
        hermite_y1 = $signed(power_read_1[31:0]);
        hermite_m0 = $signed(power_read_0[63:32]);
        hermite_m1 = $signed(power_read_1[63:32]);
        hermite_fraction = power_fraction;
        if (state == RECIPROCAL_CALCULATE) begin
            hermite_y0 = $signed(reciprocal_read_0[31:0]);
            hermite_y1 = $signed(reciprocal_read_1[31:0]);
            hermite_m0 = $signed(reciprocal_read_0[63:32]);
            hermite_m1 = $signed(reciprocal_read_1[63:32]);
            hermite_fraction = reciprocal_fraction;
        end else if (state == SOFTPLUS_CALCULATE) begin
            hermite_y0 = $signed(softplus_read_0[31:0]);
            hermite_y1 = $signed(softplus_read_1[31:0]);
            hermite_m0 = $signed(softplus_read_0[63:32]);
            hermite_m1 = $signed(softplus_read_1[63:32]);
            hermite_fraction = softplus_fraction;
        end
        hermite_interpolated = hermite_q16(
            hermite_y0,
            hermite_y1,
            hermite_m0,
            hermite_m1,
            hermite_fraction
        );
        grid_interpolated = linear_q16(
            grid_read_0, grid_read_1, grid_fraction
        );
        reciprocal_product = $signed(v_gk_latched) *
                             $signed(hermite_interpolated);
        transformed_comb = INV_MU_Q30 +
                           (($signed(reciprocal_product) + 64'sd33554432) >>> 26);
        if (v_pk_latched > 0)
            e1_product = $signed(v_pk_latched) * $signed(hermite_interpolated);
        else
            e1_product = '0;
        e1_comb = ($signed(e1_product) + 64'sd2147483648) >>> 32;
    end

    // The two endpoint reads intentionally describe the two native ports of
    // each ROM. All four memories can operate concurrently.
    always_ff @(posedge clk) begin
        reciprocal_read_0 <= reciprocal_lut[reciprocal_address_0];
        reciprocal_read_1 <= reciprocal_lut[reciprocal_address_1];
        softplus_read_0 <= softplus_lut[softplus_address_0];
        softplus_read_1 <= softplus_lut[softplus_address_1];
        power_read_0 <= power_lut[power_address_0];
        power_read_1 <= power_lut[power_address_1];
        grid_read_0 <= grid_lut[grid_address_0];
        grid_read_1 <= grid_lut[grid_address_1];
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            i_p <= '0;
            i_g <= '0;
            range_clipped <= 1'b0;
            valid <= 1'b0;
            clipped_pending <= 1'b0;
            transformed_q30 <= '0;
            e1_q20 <= '0;
        end else begin
            valid <= 1'b0;
            case (state)
                IDLE: begin
                    if (ce) begin
                        v_gk_latched <= v_gk;
                        v_pk_latched <= v_pk;
                        clipped_pending <= (v_gk < VG_MIN_Q24) ||
                                           (v_gk > VG_MAX_Q24) ||
                                           (v_pk < VP_MIN_Q20) ||
                                           (v_pk > VP_MAX_Q20);
                        if (plate_coordinate_comb[31:16] >= 16'd511) begin
                            reciprocal_address_0 <= 9'd510;
                            reciprocal_address_1 <= 9'd511;
                            reciprocal_fraction <= 16'hffff;
                        end else begin
                            reciprocal_address_0 <= plate_coordinate_comb[24:16];
                            reciprocal_address_1 <= plate_coordinate_comb[24:16] + 1'b1;
                            reciprocal_fraction <= plate_coordinate_comb[15:0];
                        end
                        if (grid_coordinate_comb[31:16] >= 16'd127) begin
                            grid_address_0 <= 7'd126;
                            grid_address_1 <= 7'd127;
                            grid_fraction <= 16'hffff;
                        end else begin
                            grid_address_0 <= grid_coordinate_comb[22:16];
                            grid_address_1 <= grid_coordinate_comb[22:16] + 1'b1;
                            grid_fraction <= grid_coordinate_comb[15:0];
                        end
                        state <= RECIPROCAL_WAIT;
                    end
                end

                RECIPROCAL_WAIT: state <= RECIPROCAL_CALCULATE;

                RECIPROCAL_CALCULATE: begin
                    transformed_q30 <= transformed_comb;
                    if ((transformed_comb < Z_MIN_Q30) ||
                        (transformed_comb > Z_MAX_Q30))
                        clipped_pending <= 1'b1;
                    state <= SOFTPLUS_MAP;
                end

                SOFTPLUS_MAP: begin
                    if (softplus_coordinate_comb[31:16] >= 16'd1023) begin
                        softplus_address_0 <= 10'd1022;
                        softplus_address_1 <= 10'd1023;
                        softplus_fraction <= 16'hffff;
                    end else begin
                        softplus_address_0 <= softplus_coordinate_comb[25:16];
                        softplus_address_1 <= softplus_coordinate_comb[25:16] + 1'b1;
                        softplus_fraction <= softplus_coordinate_comb[15:0];
                    end
                    state <= SOFTPLUS_WAIT;
                end

                SOFTPLUS_WAIT: state <= SOFTPLUS_CALCULATE;

                SOFTPLUS_CALCULATE: begin
                    e1_q20 <= e1_comb;
                    state <= POWER_MAP;
                end

                POWER_MAP: begin
                    if ((e1_q20 < E1_MIN_Q20) || (e1_q20 > E1_MAX_Q20))
                        clipped_pending <= 1'b1;
                    if (power_coordinate_comb[31:16] >= 16'd2047) begin
                        power_address_0 <= 11'd2046;
                        power_address_1 <= 11'd2047;
                        power_fraction <= 16'hffff;
                    end else begin
                        power_address_0 <= power_coordinate_comb[26:16];
                        power_address_1 <= power_coordinate_comb[26:16] + 1'b1;
                        power_fraction <= power_coordinate_comb[15:0];
                    end
                    state <= POWER_WAIT;
                end

                POWER_WAIT: state <= POWER_CALCULATE;

                POWER_CALCULATE: begin
                    if (v_pk_latched <= 0)
                        i_p <= '0;
                    else if (hermite_interpolated[31])
                        i_p <= '0;
                    else
                        i_p <= hermite_interpolated;
                    i_g <= grid_interpolated;
                    range_clipped <= clipped_pending;
                    valid <= 1'b1;
                    state <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule

`default_nettype wire
