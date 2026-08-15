`timescale 1ns/1ps
`default_nettype none

// Nexys Video clock primitive: 100 MHz board oscillator to the exact
// 48 kHz audio family. Two legal 7-series MMCM operating points are cascaded:
//
//   100 MHz * 48 / 5 / 78.125 = 12.288 MHz (codec MCLK)
//   12.288 MHz * 50 / 1 / 12.5 = 49.152 MHz (model fabric)
//
// VCO1 is 960 MHz and VCO2 is 614.4 MHz. Both fractional output divides use
// the 1/8 resolution supported by CLKOUT0_DIVIDE_F. This module is explicitly
// XC7-specific; the physical circuit/model RTL remains device-neutral.
module audio_clock_synth_xc7 (
    input  logic clk_100mhz,
    input  logic reset,
    output logic codec_mclk_12m288,
    output logic fabric_clk_49m152,
    output logic locked
);

    wire codec_mclk_unbuffered;
    wire fabric_clk_unbuffered;
    wire mmcm1_feedback;
    wire mmcm2_feedback;
    wire mmcm1_locked;
    wire mmcm2_locked;

    MMCME2_BASE #(
        .BANDWIDTH("OPTIMIZED"),
        .CLKIN1_PERIOD(10.000),
        .DIVCLK_DIVIDE(5),
        .CLKFBOUT_MULT_F(48.000),
        .CLKOUT0_DIVIDE_F(78.125),
        .CLKOUT0_DUTY_CYCLE(0.500),
        .STARTUP_WAIT("FALSE")
    ) mclk_mmcm (
        .CLKIN1(clk_100mhz),
        .CLKFBIN(mmcm1_feedback),
        .CLKFBOUT(mmcm1_feedback),
        .CLKOUT0(codec_mclk_unbuffered),
        .LOCKED(mmcm1_locked),
        .PWRDWN(1'b0),
        .RST(reset),
        .CLKFBOUTB(),
        .CLKOUT0B(),
        .CLKOUT1(),
        .CLKOUT1B(),
        .CLKOUT2(),
        .CLKOUT2B(),
        .CLKOUT3(),
        .CLKOUT3B(),
        .CLKOUT4(),
        .CLKOUT5(),
        .CLKOUT6()
    );

    BUFG mclk_buffer (
        .I(codec_mclk_unbuffered),
        .O(codec_mclk_12m288)
    );

    MMCME2_BASE #(
        .BANDWIDTH("OPTIMIZED"),
        .CLKIN1_PERIOD(81.380208333),
        .DIVCLK_DIVIDE(1),
        .CLKFBOUT_MULT_F(50.000),
        .CLKOUT0_DIVIDE_F(12.500),
        .CLKOUT0_DUTY_CYCLE(0.500),
        .STARTUP_WAIT("FALSE")
    ) fabric_mmcm (
        .CLKIN1(codec_mclk_12m288),
        .CLKFBIN(mmcm2_feedback),
        .CLKFBOUT(mmcm2_feedback),
        .CLKOUT0(fabric_clk_unbuffered),
        .LOCKED(mmcm2_locked),
        .PWRDWN(1'b0),
        .RST(reset || !mmcm1_locked),
        .CLKFBOUTB(),
        .CLKOUT0B(),
        .CLKOUT1(),
        .CLKOUT1B(),
        .CLKOUT2(),
        .CLKOUT2B(),
        .CLKOUT3(),
        .CLKOUT3B(),
        .CLKOUT4(),
        .CLKOUT5(),
        .CLKOUT6()
    );

    BUFG fabric_clock_buffer (
        .I(fabric_clk_unbuffered),
        .O(fabric_clk_49m152)
    );

    always_comb locked = mmcm1_locked && mmcm2_locked;

endmodule

// Small physical harness used to prove that the open XC7 backend can pack,
// place, route, and emit the two fractional MMCM configurations. Activity is
// divided from the generated fabric clock so neither MMCM can optimize away.
module audio_clock_synth_xc7_pnr_harness (
    input  logic clk_100mhz,
    input  logic reset,
    output logic codec_mclk_12m288,
    output logic activity,
    output logic locked
);

    logic fabric_clk_49m152;
    logic [23:0] activity_counter;

    audio_clock_synth_xc7 clocks (.*);

    always_ff @(posedge fabric_clk_49m152 or posedge reset) begin
        if (reset)
            activity_counter <= '0;
        else if (!locked)
            activity_counter <= '0;
        else
            activity_counter <= activity_counter + 1'b1;
    end

    always_comb activity = activity_counter[23];

endmodule

`default_nettype wire
