`timescale 1ns/1ps
`default_nettype none

// Latency-oriented factorization of the Koren 12AX7 current law.
//
// Inputs retain Q8.24 Vgk and Q12.20 Vpk; outputs are signed Q0.31 amperes.
// The physical reciprocal-sqrt, softplus, and power factorization is unchanged.
// Larger value-only 1-D tables replace cubic Hermite interpolation with one
// rounded linear interpolation per function.  This is a separately measured
// FPGA approximation candidate, not a silent change to reference mode.
module triode_12ax7_factorized_linear #(
    parameter RECIPROCAL_FILE = "model/generated/12ax7_factor_linear_reciprocal_q32.mem",
    parameter SOFTPLUS_FILE = "model/generated/12ax7_factor_linear_softplus_q32.mem",
    parameter POWER_FILE = "model/generated/12ax7_factor_linear_power_q31.mem",
    parameter GRID_FILE = "model/generated/12ax7_factor_linear_grid_q31.mem"
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

    localparam int RECIPROCAL_POINTS = 1024;
    localparam int SOFTPLUS_POINTS = 8192;
    localparam int POWER_POINTS = 4096;
    localparam int GRID_POINTS = 1024;
    localparam logic signed [31:0] VG_MIN_Q24 = -32'sd134217728;
    localparam logic signed [31:0] VG_MAX_Q24 = 32'sd16777216;
    localparam logic signed [31:0] GRID_MIN_Q24 = -32'sd83886080;
    localparam logic signed [31:0] VP_MIN_Q20 = 32'sd0;
    localparam logic signed [31:0] VP_MAX_Q20 = 32'sd419430400;
    localparam logic signed [63:0] Z_MIN_Q30 = -64'sd322122547;
    localparam logic signed [63:0] Z_MAX_Q30 = 64'sd85899346;
    localparam logic signed [63:0] E1_MIN_Q20 = 64'sd0;
    localparam logic signed [63:0] E1_MAX_Q20 = 64'sd6291456;
    localparam logic signed [63:0] INV_MU_Q30 = 64'sd10737418;
    localparam logic signed [31:0] RECIPROCAL_SCALE_Q24 = 32'sd2681733;
    localparam logic signed [31:0] SOFTPLUS_SCALE_Q24 = 32'sd22072589;
    localparam logic signed [31:0] POWER_SCALE_Q24 = 32'sd715653120;
    localparam logic signed [31:0] GRID_SCALE_Q24 = 32'sd11173888;

    logic signed [31:0] reciprocal_lut [0:RECIPROCAL_POINTS-1];
    logic signed [31:0] softplus_lut [0:SOFTPLUS_POINTS-1];
    logic signed [31:0] power_lut [0:POWER_POINTS-1];
    logic signed [31:0] grid_lut [0:GRID_POINTS-1];

    initial begin
        $readmemh(RECIPROCAL_FILE, reciprocal_lut);
        $readmemh(SOFTPLUS_FILE, softplus_lut);
        $readmemh(POWER_FILE, power_lut);
        $readmemh(GRID_FILE, grid_lut);
    end

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
            delta = $signed({{32{upper[31]}}, upper})
                  - $signed({{32{lower[31]}}, lower});
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
                map_plate_coordinate = 32'd67043328;
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
                map_softplus_coordinate = 32'd536805376;
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
                map_power_coordinate = 32'd268369920;
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
            if (value_q24 <= GRID_MIN_Q24)
                map_grid_coordinate = 32'd0;
            else if (value_q24 >= VG_MAX_Q24)
                map_grid_coordinate = 32'd67043328;
            else begin
                offset = $signed({{32{value_q24[31]}}, value_q24})
                       - $signed({{32{GRID_MIN_Q24[31]}}, GRID_MIN_Q24});
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
    logic [9:0] reciprocal_address_0;
    logic [9:0] reciprocal_address_1;
    logic [12:0] softplus_address_0;
    logic [12:0] softplus_address_1;
    logic [11:0] power_address_0;
    logic [11:0] power_address_1;
    logic [9:0] grid_address_0;
    logic [9:0] grid_address_1;
    logic signed [31:0] reciprocal_read_0;
    logic signed [31:0] reciprocal_read_1;
    logic signed [31:0] softplus_read_0;
    logic signed [31:0] softplus_read_1;
    logic signed [31:0] power_read_0;
    logic signed [31:0] power_read_1;
    logic signed [31:0] grid_read_0;
    logic signed [31:0] grid_read_1;
    logic signed [63:0] transformed_q30;
    logic signed [63:0] e1_q20;

    logic [31:0] plate_coordinate_comb;
    logic [31:0] grid_coordinate_comb;
    logic [31:0] softplus_coordinate_comb;
    logic [31:0] power_coordinate_comb;
    logic signed [31:0] lookup_lower;
    logic signed [31:0] lookup_upper;
    logic [15:0] lookup_fraction;
    logic signed [31:0] interpolated;
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

        lookup_lower = power_read_0;
        lookup_upper = power_read_1;
        lookup_fraction = power_fraction;
        if (state == RECIPROCAL_CALCULATE) begin
            lookup_lower = reciprocal_read_0;
            lookup_upper = reciprocal_read_1;
            lookup_fraction = reciprocal_fraction;
        end else if (state == SOFTPLUS_CALCULATE) begin
            lookup_lower = softplus_read_0;
            lookup_upper = softplus_read_1;
            lookup_fraction = softplus_fraction;
        end
        interpolated = linear_q16(
            lookup_lower, lookup_upper, lookup_fraction
        );
        grid_interpolated = linear_q16(
            grid_read_0, grid_read_1, grid_fraction
        );
        reciprocal_product = $signed(v_gk_latched) * $signed(interpolated);
        transformed_comb = INV_MU_Q30
                         + (($signed(reciprocal_product) + 64'sd33554432) >>> 26);
        if (v_pk_latched > 0)
            e1_product = $signed(v_pk_latched) * $signed(interpolated);
        else
            e1_product = '0;
        e1_comb = ($signed(e1_product) + 64'sd2147483648) >>> 32;
    end

    // Each physical table has two concurrent endpoint reads.  The memories
    // are independent and may all fetch while the state selects one result.
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
            unique case (state)
                IDLE: begin
                    if (ce) begin
                        v_gk_latched <= v_gk;
                        v_pk_latched <= v_pk;
                        clipped_pending <= (v_gk < VG_MIN_Q24)
                                           || (v_gk > VG_MAX_Q24)
                                           || (v_pk < VP_MIN_Q20)
                                           || (v_pk > VP_MAX_Q20);
                        if (plate_coordinate_comb[31:16] >= 16'd1023) begin
                            reciprocal_address_0 <= 10'd1022;
                            reciprocal_address_1 <= 10'd1023;
                            reciprocal_fraction <= 16'hffff;
                        end else begin
                            reciprocal_address_0 <= plate_coordinate_comb[25:16];
                            reciprocal_address_1 <= plate_coordinate_comb[25:16] + 1'b1;
                            reciprocal_fraction <= plate_coordinate_comb[15:0];
                        end
                        if (grid_coordinate_comb[31:16] >= 16'd1023) begin
                            grid_address_0 <= 10'd1022;
                            grid_address_1 <= 10'd1023;
                            grid_fraction <= 16'hffff;
                        end else begin
                            grid_address_0 <= grid_coordinate_comb[25:16];
                            grid_address_1 <= grid_coordinate_comb[25:16] + 1'b1;
                            grid_fraction <= grid_coordinate_comb[15:0];
                        end
                        state <= RECIPROCAL_WAIT;
                    end
                end

                RECIPROCAL_WAIT: state <= RECIPROCAL_CALCULATE;

                RECIPROCAL_CALCULATE: begin
                    transformed_q30 <= transformed_comb;
                    if ((transformed_comb < Z_MIN_Q30)
                        || (transformed_comb > Z_MAX_Q30))
                        clipped_pending <= 1'b1;
                    state <= SOFTPLUS_MAP;
                end

                SOFTPLUS_MAP: begin
                    if (softplus_coordinate_comb[31:16] >= 16'd8191) begin
                        softplus_address_0 <= 13'd8190;
                        softplus_address_1 <= 13'd8191;
                        softplus_fraction <= 16'hffff;
                    end else begin
                        softplus_address_0 <= softplus_coordinate_comb[28:16];
                        softplus_address_1 <= softplus_coordinate_comb[28:16] + 1'b1;
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
                    if (power_coordinate_comb[31:16] >= 16'd4095) begin
                        power_address_0 <= 12'd4094;
                        power_address_1 <= 12'd4095;
                        power_fraction <= 16'hffff;
                    end else begin
                        power_address_0 <= power_coordinate_comb[27:16];
                        power_address_1 <= power_coordinate_comb[27:16] + 1'b1;
                        power_fraction <= power_coordinate_comb[15:0];
                    end
                    state <= POWER_WAIT;
                end

                POWER_WAIT: state <= POWER_CALCULATE;

                POWER_CALCULATE: begin
                    if (v_pk_latched <= 0)
                        i_p <= '0;
                    else if (interpolated[31])
                        i_p <= '0;
                    else
                        i_p <= interpolated;
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
