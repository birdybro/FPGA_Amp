`timescale 1ns/1ps
`default_nettype none

// Single-main I2C reader for one-byte register addresses and one-byte data.
// The transaction is:
//   START, address+W, register, repeated START, address+R, data, NACK, STOP.
// Pins are open drain and clock stretching is honored whenever SCL is released.
// Arbitration, multi-byte reads, and bus recovery are outside this primitive.
module i2c_read_register_master #(
    parameter int unsigned CLOCK_DIVIDER = 32
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       start,
    input  logic [6:0] device_address,
    input  logic [7:0] register_address,

    input  logic       scl_in,
    input  logic       sda_in,
    output logic       scl_drive_low,
    output logic       sda_drive_low,

    output logic       busy,
    output logic       done,
    output logic       nack,
    output logic [7:0] read_data
);

    localparam int unsigned DIVIDER_WIDTH =
        CLOCK_DIVIDER <= 1 ? 1 : $clog2(CLOCK_DIVIDER);

    typedef enum logic [4:0] {
        STATE_IDLE,
        STATE_START_RELEASE,
        STATE_START_ASSERT,
        STATE_START_LOW,
        STATE_SEND_LOW,
        STATE_SEND_RISE,
        STATE_SEND_HIGH,
        STATE_SEND_FALL,
        STATE_ACK_LOW,
        STATE_ACK_RISE,
        STATE_ACK_HIGH,
        STATE_ACK_FALL,
        STATE_RESTART_LOW,
        STATE_RESTART_RISE,
        STATE_RESTART_ASSERT,
        STATE_RESTART_HOLD_LOW,
        STATE_READ_LOW,
        STATE_READ_RISE,
        STATE_READ_HIGH,
        STATE_READ_FALL,
        STATE_NACK_LOW,
        STATE_NACK_RISE,
        STATE_NACK_HIGH,
        STATE_NACK_FALL,
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
    logic [7:0] latched_register_address;
    logic [1:0] send_byte_index;
    logic [2:0] bit_index;
    logic [7:0] send_byte;
    logic send_bit;
    logic divider_tick;

    always_comb begin
        case (send_byte_index)
            2'd0: send_byte = {latched_device_address, 1'b0};
            2'd1: send_byte = latched_register_address;
            default: send_byte = {latched_device_address, 1'b1};
        endcase
        send_bit = send_byte[bit_index];
        divider_tick = divider_count == DIVIDER_WIDTH'(CLOCK_DIVIDER - 1);

        scl_drive_low = 1'b0;
        sda_drive_low = 1'b0;
        case (state)
            STATE_START_ASSERT,
            STATE_RESTART_ASSERT: sda_drive_low = 1'b1;
            STATE_START_LOW,
            STATE_RESTART_HOLD_LOW: begin
                scl_drive_low = 1'b1;
                sda_drive_low = 1'b1;
            end
            STATE_SEND_LOW,
            STATE_SEND_FALL: begin
                scl_drive_low = 1'b1;
                sda_drive_low = !send_bit;
            end
            STATE_SEND_RISE,
            STATE_SEND_HIGH: sda_drive_low = !send_bit;
            STATE_ACK_LOW,
            STATE_ACK_FALL,
            STATE_RESTART_LOW,
            STATE_READ_LOW,
            STATE_READ_FALL,
            STATE_NACK_LOW,
            STATE_NACK_FALL: scl_drive_low = 1'b1;
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
            send_byte_index <= '0;
            bit_index <= 3'd7;
            busy <= 1'b0;
            done <= 1'b0;
            nack <= 1'b0;
            read_data <= '0;
        end else begin
            done <= 1'b0;
            if (state == STATE_IDLE) begin
                divider_count <= '0;
                if (start) begin
                    latched_device_address <= device_address;
                    latched_register_address <= register_address;
                    send_byte_index <= '0;
                    bit_index <= 3'd7;
                    busy <= 1'b1;
                    nack <= 1'b0;
                    read_data <= '0;
                    state <= STATE_START_RELEASE;
                end
            end else if (divider_tick) begin
                divider_count <= '0;
                case (state)
                    STATE_START_RELEASE: state <= STATE_START_ASSERT;
                    STATE_START_ASSERT: state <= STATE_START_LOW;
                    STATE_START_LOW: state <= STATE_SEND_LOW;
                    STATE_SEND_LOW: state <= STATE_SEND_RISE;
                    STATE_SEND_RISE: begin
                        if (scl_in)
                            state <= STATE_SEND_HIGH;
                    end
                    STATE_SEND_HIGH: state <= STATE_SEND_FALL;
                    STATE_SEND_FALL: begin
                        if (bit_index == 0)
                            state <= STATE_ACK_LOW;
                        else begin
                            bit_index <= bit_index - 1'b1;
                            state <= STATE_SEND_LOW;
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
                        if (nack) begin
                            state <= STATE_STOP_LOW;
                        end else if (send_byte_index == 2'd0) begin
                            send_byte_index <= 2'd1;
                            bit_index <= 3'd7;
                            state <= STATE_SEND_LOW;
                        end else if (send_byte_index == 2'd1) begin
                            state <= STATE_RESTART_LOW;
                        end else begin
                            bit_index <= 3'd7;
                            state <= STATE_READ_LOW;
                        end
                    end
                    STATE_RESTART_LOW: state <= STATE_RESTART_RISE;
                    STATE_RESTART_RISE: begin
                        if (scl_in)
                            state <= STATE_RESTART_ASSERT;
                    end
                    STATE_RESTART_ASSERT: state <= STATE_RESTART_HOLD_LOW;
                    STATE_RESTART_HOLD_LOW: begin
                        send_byte_index <= 2'd2;
                        bit_index <= 3'd7;
                        state <= STATE_SEND_LOW;
                    end
                    STATE_READ_LOW: state <= STATE_READ_RISE;
                    STATE_READ_RISE: begin
                        if (scl_in)
                            state <= STATE_READ_HIGH;
                    end
                    STATE_READ_HIGH: begin
                        read_data <= {read_data[6:0], sda_in};
                        state <= STATE_READ_FALL;
                    end
                    STATE_READ_FALL: begin
                        if (bit_index == 0)
                            state <= STATE_NACK_LOW;
                        else begin
                            bit_index <= bit_index - 1'b1;
                            state <= STATE_READ_LOW;
                        end
                    end
                    STATE_NACK_LOW: state <= STATE_NACK_RISE;
                    STATE_NACK_RISE: begin
                        if (scl_in)
                            state <= STATE_NACK_HIGH;
                    end
                    STATE_NACK_HIGH: state <= STATE_NACK_FALL;
                    STATE_NACK_FALL: state <= STATE_STOP_LOW;
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
