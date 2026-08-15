`timescale 1ns/1ps
`default_nettype none

// Fixed write-only PCM5242 reference-path bootstrap for the Rev-A DAC board.
//
// Board straps select I2C address 0x4c. The FPGA supplies 24.576 MHz SCK,
// 3.072 MHz BCK, and 48 kHz LRCK; the DAC is a clock subordinate and its PLL is
// disabled. The sequence explicitly selects 24-bit I2S, ROM interpolation
// program 1, unity digital/analog gain, VREF output mode, no de-emphasis, and
// no zero-detect auto mute. It leaves XSMT and the normally-open line relays to
// independent fail-low board controls.
//
// configuration_written means only that every write was ACKed. It is NOT
// permission to unmute: production control must read back the critical mode
// registers and validate DAC clock/power status before raising either hardware
// unmute permission.
module pcm5242_dac_init #(
    parameter int unsigned STARTUP_DELAY_CYCLES = 491_520,
    parameter int unsigned I2C_CLOCK_DIVIDER = 32
) (
    input  logic       clk,
    input  logic       rst_n,

    input  logic       scl_in,
    input  logic       sda_in,
    output logic       scl_drive_low,
    output logic       sda_drive_low,

    output logic       busy,
    output logic       configuration_written,
    output logic       error,
    output logic [4:0] sequence_index,
    output logic [4:0] failed_index
);

    localparam logic [6:0] DEVICE_ADDRESS = 7'h4c;
    localparam int unsigned WRITE_COUNT = 20;
    localparam int unsigned DELAY_COUNTER_WIDTH =
        STARTUP_DELAY_CYCLES <= 1 ? 1 : $clog2(STARTUP_DELAY_CYCLES);

    typedef enum logic [2:0] {
        STATE_STARTUP_DELAY,
        STATE_LAUNCH_WRITE,
        STATE_WAIT_WRITE,
        STATE_WRITTEN,
        STATE_FAILED
    } state_t;

    initial begin
        if (I2C_CLOCK_DIVIDER < 1)
            $error("I2C_CLOCK_DIVIDER must be positive");
    end

    state_t state;
    logic [DELAY_COUNTER_WIDTH-1:0] delay_counter;
    logic writer_start;
    logic writer_busy;
    logic writer_done;
    logic writer_nack;
    logic [7:0] selected_register;
    logic [7:0] selected_data;

    function automatic logic [7:0] register_for_index(input logic [4:0] index);
        case (index)
            5'd0:  register_for_index = 8'h00; // Select page 0
            5'd1:  register_for_index = 8'h03; // Internal L/R soft mute
            5'd2:  register_for_index = 8'h04; // Disable PLL; use external SCK
            5'd3:  register_for_index = 8'h07; // Disable de-emphasis
            5'd4:  register_for_index = 8'h28; // 24-bit I2S
            5'd5:  register_for_index = 8'h29; // Zero additional I2S shift
            5'd6:  register_for_index = 8'h2a; // L->L, R->R data paths
            5'd7:  register_for_index = 8'h2b; // ROM interpolation program 1
            5'd8:  register_for_index = 8'h3c; // Independent channel volume
            5'd9:  register_for_index = 8'h3d; // Left digital unity
            5'd10: register_for_index = 8'h3e; // Right digital unity
            5'd11: register_for_index = 8'h41; // Disable zero-detect auto mute
            5'd12: register_for_index = 8'h00; // Select page 1
            5'd13: register_for_index = 8'h01; // VREF output amplitude
            5'd14: register_for_index = 8'h02; // L/R analog gain 0 dB
            5'd15: register_for_index = 8'h06; // Analog mute follows digital mute
            5'd16: register_for_index = 8'h07; // Disable +10% analog boost
            5'd17: register_for_index = 8'h00; // Return to page 0
            5'd18: register_for_index = 8'h02; // Normal operation request
            default: register_for_index = 8'h03; // Release register mute under XSMT
        endcase
    endfunction

    function automatic logic [7:0] data_for_index(input logic [4:0] index);
        case (index)
            5'd0:  data_for_index = 8'h00;
            5'd1:  data_for_index = 8'h11;
            5'd2:  data_for_index = 8'h00;
            5'd3:  data_for_index = 8'h00;
            5'd4:  data_for_index = 8'h02;
            5'd5:  data_for_index = 8'h00;
            5'd6:  data_for_index = 8'h11;
            5'd7:  data_for_index = 8'h01;
            5'd8:  data_for_index = 8'h00;
            5'd9:  data_for_index = 8'h30;
            5'd10: data_for_index = 8'h30;
            5'd11: data_for_index = 8'h00;
            5'd12: data_for_index = 8'h01;
            5'd13: data_for_index = 8'h00;
            5'd14: data_for_index = 8'h00;
            5'd15: data_for_index = 8'h00;
            5'd16: data_for_index = 8'h00;
            5'd17: data_for_index = 8'h00;
            5'd18: data_for_index = 8'h00;
            default: data_for_index = 8'h00;
        endcase
    endfunction

    always_comb begin
        selected_register = register_for_index(sequence_index);
        selected_data = data_for_index(sequence_index);
        busy = state == STATE_STARTUP_DELAY ||
               state == STATE_LAUNCH_WRITE ||
               state == STATE_WAIT_WRITE;
        configuration_written = state == STATE_WRITTEN;
        error = state == STATE_FAILED;
    end

    i2c_write_master #(
        .CLOCK_DIVIDER(I2C_CLOCK_DIVIDER),
        .REGISTER_ADDRESS_BYTES(1)
    ) writer (
        .clk,
        .rst_n,
        .start(writer_start),
        .device_address(DEVICE_ADDRESS),
        .register_address({8'h00, selected_register}),
        .write_data(selected_data),
        .scl_in,
        .sda_in,
        .scl_drive_low,
        .sda_drive_low,
        .busy(writer_busy),
        .done(writer_done),
        .nack(writer_nack)
    );

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= STATE_STARTUP_DELAY;
            delay_counter <= '0;
            writer_start <= 1'b0;
            sequence_index <= '0;
            failed_index <= '0;
        end else begin
            writer_start <= 1'b0;
            case (state)
                STATE_STARTUP_DELAY: begin
                    if (STARTUP_DELAY_CYCLES == 0 ||
                        delay_counter == DELAY_COUNTER_WIDTH'(STARTUP_DELAY_CYCLES - 1)) begin
                        delay_counter <= '0;
                        state <= STATE_LAUNCH_WRITE;
                    end else begin
                        delay_counter <= delay_counter + 1'b1;
                    end
                end
                STATE_LAUNCH_WRITE: begin
                    if (!writer_busy) begin
                        writer_start <= 1'b1;
                        state <= STATE_WAIT_WRITE;
                    end
                end
                STATE_WAIT_WRITE: begin
                    if (writer_done) begin
                        if (writer_nack) begin
                            failed_index <= sequence_index;
                            state <= STATE_FAILED;
                        end else if (sequence_index == 5'(WRITE_COUNT - 1)) begin
                            state <= STATE_WRITTEN;
                        end else begin
                            sequence_index <= sequence_index + 1'b1;
                            state <= STATE_LAUNCH_WRITE;
                        end
                    end
                end
                STATE_WRITTEN: state <= STATE_WRITTEN;
                default: state <= STATE_FAILED;
            endcase
        end
    end

endmodule

`default_nettype wire
