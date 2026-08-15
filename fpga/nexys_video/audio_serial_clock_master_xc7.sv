`timescale 1ns/1ps
`default_nettype none

// XC7 board leaf for a 49.152 MHz fabric-clock master. The /16 output is the
// 3.072 MHz codec BCLK for 48 kHz, 24-bit stereo in 32-bit slots. A BUFG makes
// BCLK an explicit serial-interface clock domain. Each reset deasserts only on
// its owning clock after the cascaded audio MMCMs have locked.
module audio_serial_clock_master_xc7 (
    input  logic fabric_clk_49m152,
    input  logic async_reset,
    output logic codec_bclk_3m072,
    output logic fabric_rst_n,
    output logic i2s_rst_n
);

    logic bclk_raw;

    reset_release_sync fabric_reset_release (
        .clk(fabric_clk_49m152),
        .async_reset,
        .rst_n(fabric_rst_n)
    );

    audio_i2s_clock_divider #(
        .FABRIC_TO_BCLK_DIVIDE(16)
    ) serial_clock_divider (
        .fabric_clk(fabric_clk_49m152),
        .fabric_rst_n,
        .bclk_raw
    );

    BUFG serial_clock_buffer (
        .I(bclk_raw),
        .O(codec_bclk_3m072)
    );

    reset_release_sync i2s_reset_release (
        .clk(codec_bclk_3m072),
        .async_reset,
        .rst_n(i2s_rst_n)
    );

endmodule

`default_nettype wire
