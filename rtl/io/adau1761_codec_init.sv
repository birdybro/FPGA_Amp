`timescale 1ns/1ps
`default_nettype none

// Fixed ADAU1761 bootstrap for the Nexys Video audio path.
//
// The FPGA supplies 12.288 MHz MCLK, 3.072 MHz BCLK, and 48 kHz LRCLK. The
// codec therefore remains a serial-port subordinate; its PLL is not used.
// Line outputs are programmed muted before signal routing and are unmuted only
// by the final two writes. Any observed NACK stops the sequence and exposes the
// failed table index. Register readback is outside this bootstrap's scope.
module adau1761_codec_init #(
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
    output logic       configured,
    output logic       error,
    output logic [4:0] sequence_index,
    output logic [4:0] failed_index
);

    localparam logic [6:0] DEVICE_ADDRESS = 7'h3b;
    localparam int unsigned WRITE_COUNT = 27;
    localparam int unsigned DELAY_COUNTER_WIDTH =
        STARTUP_DELAY_CYCLES <= 1 ? 1 : $clog2(STARTUP_DELAY_CYCLES);

    typedef enum logic [2:0] {
        STATE_STARTUP_DELAY,
        STATE_LAUNCH_WRITE,
        STATE_WAIT_WRITE,
        STATE_CONFIGURED,
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
    logic [15:0] selected_register;
    logic [7:0] selected_data;

    function automatic logic [15:0] register_for_index(input logic [4:0] index);
        case (index)
            5'd0:  register_for_index = 16'h4000; // R0 clock control
            5'd1:  register_for_index = 16'h4025; // R31 left line out mute
            5'd2:  register_for_index = 16'h4026; // R32 right line out mute
            5'd3:  register_for_index = 16'h4015; // R15 serial port control 0
            5'd4:  register_for_index = 16'h4016; // R16 serial port control 1
            5'd5:  register_for_index = 16'h4017; // R17 converter control 0
            5'd6:  register_for_index = 16'h40f8; // R64 serial sampling rate
            5'd7:  register_for_index = 16'h400a; // R4 left input mixer 0
            5'd8:  register_for_index = 16'h400b; // R5 left input mixer 1
            5'd9:  register_for_index = 16'h400c; // R6 right input mixer 0
            5'd10: register_for_index = 16'h400d; // R7 right input mixer 1
            5'd11: register_for_index = 16'h4019; // R19 ADC control
            5'd12: register_for_index = 16'h402a; // R36 DAC control 0
            5'd13: register_for_index = 16'h4029; // R35 playback power mgmt
            5'd14: register_for_index = 16'h40f2; // R58 serial input route
            5'd15: register_for_index = 16'h40f3; // R59 serial output route
            5'd16: register_for_index = 16'h401c; // R22 playback mixer 3
            5'd17: register_for_index = 16'h401d; // R23 playback mixer 4
            5'd18: register_for_index = 16'h401e; // R24 playback mixer 5
            5'd19: register_for_index = 16'h401f; // R25 playback mixer 6
            5'd20: register_for_index = 16'h4020; // R26 playback mixer 7
            5'd21: register_for_index = 16'h4021; // R27 playback mixer 8
            5'd22: register_for_index = 16'h40f4; // R60 serial pin mode
            5'd23: register_for_index = 16'h40f9; // R65 clock enable 0
            5'd24: register_for_index = 16'h40fa; // R66 clock enable 1
            5'd25: register_for_index = 16'h4025; // R31 left line unmute
            5'd26: register_for_index = 16'h4026; // R32 right line unmute
            default: register_for_index = 16'h4000;
        endcase
    endfunction

    function automatic logic [7:0] data_for_index(input logic [4:0] index);
        case (index)
            5'd0:  data_for_index = 8'h01; // direct MCLK, core enable
            5'd1:  data_for_index = 8'he4; // 0 dB, line mode, muted
            5'd2:  data_for_index = 8'he4; // 0 dB, line mode, muted
            5'd3:  data_for_index = 8'h00; // codec subordinate, stereo
            5'd4:  data_for_index = 8'h00; // 64 BCLK/frame, I2S delay
            5'd5:  data_for_index = 8'h00; // ADC/DAC at 48 kHz base
            5'd6:  data_for_index = 8'h00; // serial port at 48 kHz base
            5'd7:  data_for_index = 8'h01; // enable left input mixer
            5'd8:  data_for_index = 8'h05; // AUX 0 dB, diff input muted
            5'd9:  data_for_index = 8'h01; // enable right input mixer
            5'd10: data_for_index = 8'h05; // AUX 0 dB, diff input muted
            5'd11: data_for_index = 8'h13; // enable both ADC channels
            5'd12: data_for_index = 8'h03; // enable both DAC channels
            5'd13: data_for_index = 8'h03; // enable L/R playback paths
            5'd14: data_for_index = 8'h01; // serial L0/R0 to DACs
            5'd15: data_for_index = 8'h01; // ADCs to serial L0/R0
            5'd16: data_for_index = 8'h21; // left DAC to mixer 3, -6 dB
            5'd17: data_for_index = 8'h00; // left bypass path muted
            5'd18: data_for_index = 8'h41; // right DAC to mixer 4, -6 dB
            5'd19: data_for_index = 8'h00; // right bypass path muted
            5'd20: data_for_index = 8'h03; // board left line route
            5'd21: data_for_index = 8'h09; // board right line route
            5'd22: data_for_index = 8'h00; // standard serial pin mode
            5'd23: data_for_index = 8'h7f; // enable digital clocks
            5'd24: data_for_index = 8'h01; // CLK0 only; FPGA drives B/LRCLK
            5'd25: data_for_index = 8'he6; // 0 dB line, unmute left
            5'd26: data_for_index = 8'he6; // 0 dB line, unmute right
            default: data_for_index = 8'h00;
        endcase
    endfunction

    always_comb begin
        selected_register = register_for_index(sequence_index);
        selected_data = data_for_index(sequence_index);
        busy = state == STATE_STARTUP_DELAY ||
               state == STATE_LAUNCH_WRITE ||
               state == STATE_WAIT_WRITE;
        configured = state == STATE_CONFIGURED;
        error = state == STATE_FAILED;
    end

    i2c_write_master #(
        .CLOCK_DIVIDER(I2C_CLOCK_DIVIDER)
    ) writer (
        .clk,
        .rst_n,
        .start(writer_start),
        .device_address(DEVICE_ADDRESS),
        .register_address(selected_register),
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
                            state <= STATE_CONFIGURED;
                        end else begin
                            sequence_index <= sequence_index + 1'b1;
                            state <= STATE_LAUNCH_WRITE;
                        end
                    end
                end
                STATE_CONFIGURED: state <= STATE_CONFIGURED;
                default: state <= STATE_FAILED;
            endcase
        end
    end

endmodule

`default_nettype wire
