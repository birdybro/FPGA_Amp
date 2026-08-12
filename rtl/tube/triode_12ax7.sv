`timescale 1ns/1ps
`default_nettype none

// Koren 12AX7 static-current approximation.
//
// Inputs:  v_gk signed Q8.24 volts, v_pk signed Q12.20 volts.
// Outputs: i_p and i_g signed Q0.31 amperes.
//
// A request is accepted when ce is high in IDLE. valid pulses eight clocks
// later. The implementation is deliberately single-issue so one inferred
// ROM read port can be time-multiplexed inside the 125-cycle sample budget.
module triode_12ax7 #(
    parameter PLATE_LUT_FILE = "model/generated/12ax7_plate_128x256_q31.mem",
    parameter GRID_LUT_FILE  = "model/generated/12ax7_grid_128_q31.mem"
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

    localparam int GRID_POINTS  = 128;
    localparam int PLATE_POINTS = 256;
    localparam int PLATE_WORDS  = GRID_POINTS * PLATE_POINTS;
    localparam logic signed [31:0] VG_MIN_Q24 = -32'sd83886080;  // -5 V
    localparam logic signed [31:0] VG_MAX_Q24 =  32'sd16777216;  // +1 V
    localparam logic signed [31:0] VP_MIN_Q20 =  32'sd0;
    localparam logic signed [31:0] VP_MAX_Q20 =  32'sd419430400; // 400 V
    localparam logic signed [31:0] VG_SCALE_Q24 = 32'sd1387179;
    localparam logic signed [31:0] VP_SCALE_Q24 = 32'sd668467;

    logic signed [31:0] plate_lut [0:PLATE_WORDS-1];
    logic signed [31:0] grid_lut  [0:GRID_POINTS-1];

    initial begin
        $readmemh(PLATE_LUT_FILE, plate_lut);
        $readmemh(GRID_LUT_FILE, grid_lut);
    end

    typedef enum logic [3:0] {
        IDLE,
        MAP_COORDINATES,
        FETCH_00,
        CAPTURE_00,
        CAPTURE_10,
        CAPTURE_01,
        CAPTURE_11,
        INTERPOLATE_X,
        INTERPOLATE_Y
    } state_t;

    state_t state;
    logic [31:0] grid_coordinate;
    logic [31:0] plate_coordinate;
    logic [6:0]  grid_index;
    logic [7:0]  plate_index;
    logic [15:0] grid_fraction;
    logic [15:0] plate_fraction;
    logic clipped_pending;
    logic signed [31:0] value_00;
    logic signed [31:0] value_10;
    logic signed [31:0] value_01;
    logic signed [31:0] value_11;
    logic signed [31:0] grid_value_0;
    logic signed [31:0] grid_value_1;
    logic signed [31:0] interp_low;
    logic signed [31:0] interp_high;
    logic signed [31:0] grid_interp;
    logic [14:0] plate_address;
    logic [6:0] grid_address;
    logic signed [31:0] plate_read_data;
    logic signed [31:0] grid_read_data;

    function automatic logic [31:0] map_grid_coordinate(
        input logic signed [31:0] value_q24
    );
        logic signed [63:0] offset;
        logic signed [63:0] product;
        begin
            if (value_q24 <= VG_MIN_Q24) begin
                map_grid_coordinate = 32'd0;
            end else if (value_q24 >= VG_MAX_Q24) begin
                map_grid_coordinate = 32'd8323072; // 127 << 16
            end else begin
                offset = $signed({{32{value_q24[31]}}, value_q24})
                       - $signed({{32{VG_MIN_Q24[31]}}, VG_MIN_Q24});
                product = offset * $signed(VG_SCALE_Q24);
                product = product + 64'sd8388608;
                map_grid_coordinate = product[55:24];
            end
        end
    endfunction

    function automatic logic [6:0] grid_base_index(input logic [15:0] coordinate_integer);
        begin
            if (coordinate_integer >= 16'd127) begin
                grid_base_index = 7'd126;
            end else begin
                grid_base_index = coordinate_integer[6:0];
            end
        end
    endfunction

    function automatic logic [7:0] plate_base_index(input logic [15:0] coordinate_integer);
        begin
            if (coordinate_integer >= 16'd255) begin
                plate_base_index = 8'd254;
            end else begin
                plate_base_index = coordinate_integer[7:0];
            end
        end
    endfunction

    function automatic logic [31:0] map_plate_coordinate(
        input logic signed [31:0] value_q20
    );
        logic signed [63:0] product;
        begin
            if (value_q20 <= VP_MIN_Q20) begin
                map_plate_coordinate = 32'd0;
            end else if (value_q20 >= VP_MAX_Q20) begin
                map_plate_coordinate = 32'd16711680; // 255 << 16
            end else begin
                product = $signed(value_q20) * $signed(VP_SCALE_Q24);
                product = product + 64'sd8388608;
                map_plate_coordinate = product[55:24];
            end
        end
    endfunction

    function automatic logic signed [31:0] lerp_q31(
        input logic signed [31:0] lower,
        input logic signed [31:0] upper,
        input logic        [15:0] fraction
    );
        logic signed [32:0] delta;
        logic signed [48:0] product;
        logic signed [32:0] rounded_delta;
        logic signed [31:0] result;
        begin
            // Algebraically identical to weighted endpoints, but one full
            // multiply instead of two: lower + (upper-lower)*fraction.
            delta = $signed({upper[31], upper}) - $signed({lower[31], lower});
            product = delta * $signed({1'b0, fraction}) + 49'sd32768;
            rounded_delta = 33'($signed(product) >>> 16);
            result = 32'($signed({lower[31], lower}) + rounded_delta);
            lerp_q31 = result;
        end
    endfunction

    // One syntactic read port per table is intentional: later FPGA mapping
    // must not duplicate the 1-Mibit plate ROM merely to read four corners.
    always_ff @(posedge clk) begin
        plate_read_data <= plate_lut[plate_address];
        grid_read_data  <= grid_lut[grid_address];
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state           <= IDLE;
            i_p             <= '0;
            i_g             <= '0;
            range_clipped   <= 1'b0;
            valid           <= 1'b0;
            clipped_pending <= 1'b0;
        end else begin
            valid <= 1'b0;
            case (state)
                IDLE: begin
                    if (ce) begin
                        grid_coordinate  <= map_grid_coordinate(v_gk);
                        plate_coordinate <= map_plate_coordinate(v_pk);
                        clipped_pending  <= (v_gk < VG_MIN_Q24) ||
                                            (v_gk > VG_MAX_Q24) ||
                                            (v_pk < VP_MIN_Q20) ||
                                            (v_pk > VP_MAX_Q20);
                        state <= MAP_COORDINATES;
                    end
                end

                MAP_COORDINATES: begin
                    if (grid_coordinate[31:16] >= 16'd127) begin
                        grid_index    <= 7'd126;
                        grid_fraction <= 16'hffff;
                    end else begin
                        grid_index    <= grid_coordinate[22:16];
                        grid_fraction <= grid_coordinate[15:0];
                    end
                    if (plate_coordinate[31:16] >= 16'd255) begin
                        plate_index    <= 8'd254;
                        plate_fraction <= 16'hffff;
                    end else begin
                        plate_index    <= plate_coordinate[23:16];
                        plate_fraction <= plate_coordinate[15:0];
                    end
                    plate_address <= {
                        plate_base_index(plate_coordinate[31:16]), 7'b0
                    } + {8'b0, grid_base_index(grid_coordinate[31:16])};
                    grid_address <= grid_base_index(grid_coordinate[31:16]);
                    state <= FETCH_00;
                end

                FETCH_00: begin
                    plate_address <= {
                        plate_index, 7'b0
                    } + {8'b0, grid_index} + 15'd1;
                    grid_address <= grid_index + 7'd1;
                    state <= CAPTURE_00;
                end

                CAPTURE_00: begin
                    value_00     <= plate_read_data;
                    grid_value_0 <= grid_read_data;
                    plate_address <= {
                        plate_index, 7'b0
                    } + {8'b0, grid_index} + 15'd128;
                    state <= CAPTURE_10;
                end

                CAPTURE_10: begin
                    value_10     <= plate_read_data;
                    grid_value_1 <= grid_read_data;
                    plate_address <= {
                        plate_index, 7'b0
                    } + {8'b0, grid_index} + 15'd129;
                    state <= CAPTURE_01;
                end

                CAPTURE_01: begin
                    value_01 <= plate_read_data;
                    state <= CAPTURE_11;
                end

                CAPTURE_11: begin
                    value_11 <= plate_read_data;
                    state <= INTERPOLATE_X;
                end

                INTERPOLATE_X: begin
                    interp_low  <= lerp_q31(value_00, value_10, grid_fraction);
                    interp_high <= lerp_q31(value_01, value_11, grid_fraction);
                    grid_interp <= lerp_q31(grid_value_0, grid_value_1, grid_fraction);
                    state       <= INTERPOLATE_Y;
                end

                INTERPOLATE_Y: begin
                    i_p           <= lerp_q31(interp_low, interp_high, plate_fraction);
                    i_g           <= grid_interp;
                    range_clipped <= clipped_pending;
                    valid         <= 1'b1;
                    state         <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule

`default_nettype wire
