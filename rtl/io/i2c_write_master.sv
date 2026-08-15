`timescale 1ns/1ps
`default_nettype none

// Single-main I2C register writer for devices with a 16-bit register address
// and one data byte. Pins are open drain: a drive_low output of zero means the
// board wrapper must release the corresponding line. Clock stretching is
// honored while SCL is released. Arbitration and reads are deliberately out
// of scope for the fixed codec-initialization path.
module i2c_write_master #(
    parameter int unsigned CLOCK_DIVIDER = 32
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        start,
    input  logic [6:0]  device_address,
    input  logic [15:0] register_address,
    input  logic [7:0]  write_data,

    input  logic        scl_in,
    input  logic        sda_in,
    output logic        scl_drive_low,
    output logic        sda_drive_low,

    output logic        busy,
    output logic        done,
    output logic        nack
);

    localparam int unsigned DIVIDER_WIDTH =
        CLOCK_DIVIDER <= 1 ? 1 : $clog2(CLOCK_DIVIDER);

    typedef enum logic [4:0] {
        STATE_IDLE,
        STATE_START_RELEASE,
        STATE_START_ASSERT,
        STATE_START_LOW,
        STATE_BIT_LOW,
        STATE_BIT_RISE,
        STATE_BIT_HIGH,
        STATE_BIT_FALL,
        STATE_ACK_LOW,
        STATE_ACK_RISE,
        STATE_ACK_HIGH,
        STATE_ACK_FALL,
        STATE_STOP_LOW,
        STATE_STOP_RISE,
        STATE_STOP_RELEASE
    } state_t;

    initial begin
        if (CLOCK_DIVIDER < 1)
            $error("CLOCK_DIVIDER must be positive");
    end

    state_t state;
    logic [DIVIDER_WIDTH-1:0] divider_count;
    logic [6:0] latched_device_address;
    logic [15:0] latched_register_address;
    logic [7:0] latched_write_data;
    logic [1:0] byte_index;
    logic [2:0] bit_index;
    logic [7:0] active_byte;
    logic active_bit;
    logic divider_tick;

    always_comb begin
        case (byte_index)
            2'd0: active_byte = {latched_device_address, 1'b0};
            2'd1: active_byte = latched_register_address[15:8];
            2'd2: active_byte = latched_register_address[7:0];
            default: active_byte = latched_write_data;
        endcase
        active_bit = active_byte[bit_index];
        divider_tick = divider_count == DIVIDER_WIDTH'(CLOCK_DIVIDER - 1);

        scl_drive_low = 1'b0;
        sda_drive_low = 1'b0;
        case (state)
            STATE_START_ASSERT: sda_drive_low = 1'b1;
            STATE_START_LOW: begin
                scl_drive_low = 1'b1;
                sda_drive_low = 1'b1;
            end
            STATE_BIT_LOW, STATE_BIT_FALL: begin
                scl_drive_low = 1'b1;
                sda_drive_low = !active_bit;
            end
            STATE_BIT_RISE, STATE_BIT_HIGH:
                sda_drive_low = !active_bit;
            STATE_ACK_LOW, STATE_ACK_FALL:
                scl_drive_low = 1'b1;
            STATE_STOP_LOW: begin
                scl_drive_low = 1'b1;
                sda_drive_low = 1'b1;
            end
            STATE_STOP_RISE: sda_drive_low = 1'b1;
            default: begin
                scl_drive_low = 1'b0;
                sda_drive_low = 1'b0;
            end
        endcase
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= STATE_IDLE;
            divider_count <= '0;
            latched_device_address <= '0;
            latched_register_address <= '0;
            latched_write_data <= '0;
            byte_index <= '0;
            bit_index <= 3'd7;
            busy <= 1'b0;
            done <= 1'b0;
            nack <= 1'b0;
        end else begin
            done <= 1'b0;
            if (state == STATE_IDLE) begin
                divider_count <= '0;
                if (start) begin
                    latched_device_address <= device_address;
                    latched_register_address <= register_address;
                    latched_write_data <= write_data;
                    byte_index <= '0;
                    bit_index <= 3'd7;
                    busy <= 1'b1;
                    nack <= 1'b0;
                    state <= STATE_START_RELEASE;
                end
            end else if (divider_tick) begin
                divider_count <= '0;
                case (state)
                    STATE_START_RELEASE: state <= STATE_START_ASSERT;
                    STATE_START_ASSERT: state <= STATE_START_LOW;
                    STATE_START_LOW: state <= STATE_BIT_LOW;
                    STATE_BIT_LOW: state <= STATE_BIT_RISE;
                    STATE_BIT_RISE: begin
                        if (scl_in)
                            state <= STATE_BIT_HIGH;
                    end
                    STATE_BIT_HIGH: state <= STATE_BIT_FALL;
                    STATE_BIT_FALL: begin
                        if (bit_index == 0) begin
                            state <= STATE_ACK_LOW;
                        end else begin
                            bit_index <= bit_index - 1'b1;
                            state <= STATE_BIT_LOW;
                        end
                    end
                    STATE_ACK_LOW: state <= STATE_ACK_RISE;
                    STATE_ACK_RISE: begin
                        if (scl_in)
                            state <= STATE_ACK_HIGH;
                    end
                    STATE_ACK_HIGH: begin
                        if (sda_in)
                            nack <= 1'b1;
                        state <= STATE_ACK_FALL;
                    end
                    STATE_ACK_FALL: begin
                        if (byte_index == 2'd3) begin
                            state <= STATE_STOP_LOW;
                        end else begin
                            byte_index <= byte_index + 1'b1;
                            bit_index <= 3'd7;
                            state <= STATE_BIT_LOW;
                        end
                    end
                    STATE_STOP_LOW: state <= STATE_STOP_RISE;
                    STATE_STOP_RISE: begin
                        if (scl_in)
                            state <= STATE_STOP_RELEASE;
                    end
                    STATE_STOP_RELEASE: begin
                        state <= STATE_IDLE;
                        busy <= 1'b0;
                        done <= 1'b1;
                    end
                    default: begin
                        state <= STATE_IDLE;
                        busy <= 1'b0;
                        nack <= 1'b1;
                    end
                endcase
            end else begin
                divider_count <= divider_count + 1'b1;
            end
        end
    end

endmodule

`default_nettype wire
