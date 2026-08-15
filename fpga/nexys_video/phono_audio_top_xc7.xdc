# Nexys Video Rev. A pins. Provenance: Digilent master XDC and board manual.
set_property LOC R4 [get_ports clk_100mhz]
set_property IOSTANDARD LVCMOS33 [get_ports clk_100mhz]
create_clock -period 10.000 [get_ports clk_100mhz]

set_property LOC G4 [get_ports cpu_resetn]
set_property IOSTANDARD LVCMOS15 [get_ports cpu_resetn]
set_property LOC E22 [get_ports force_mute_switch]
set_property IOSTANDARD LVCMOS12 [get_ports force_mute_switch]

set_property LOC U6 [get_ports codec_mclk]
set_property IOSTANDARD LVCMOS33 [get_ports codec_mclk]
set_property LOC T5 [get_ports codec_bclk]
set_property IOSTANDARD LVCMOS33 [get_ports codec_bclk]
# BCLK is a fabric-divider output routed through a BUFG and also clocks the
# digital audio domain.  nextpnr cannot derive this divide-by-16 relation from
# arbitrary logic, so constrain the shared internal/output clock explicitly.
create_clock -period 325.520833 [get_nets audio_and_control.i2s_bclk]
set_property LOC U5 [get_ports codec_lrclk]
set_property IOSTANDARD LVCMOS33 [get_ports codec_lrclk]
set_property LOC T4 [get_ports codec_adc_serial_data]
set_property IOSTANDARD LVCMOS33 [get_ports codec_adc_serial_data]
set_property LOC W6 [get_ports codec_dac_serial_data]
set_property IOSTANDARD LVCMOS33 [get_ports codec_dac_serial_data]
set_property LOC W5 [get_ports codec_i2c_scl]
set_property IOSTANDARD LVCMOS33 [get_ports codec_i2c_scl]
set_property LOC V5 [get_ports codec_i2c_sda]
set_property IOSTANDARD LVCMOS33 [get_ports codec_i2c_sda]

# Pmod JA: CS_N, SCLK, MOSI, MISO.
set_property LOC AB22 [get_ports spi_cs_n]
set_property IOSTANDARD LVCMOS33 [get_ports spi_cs_n]
set_property LOC AB21 [get_ports spi_sclk]
set_property IOSTANDARD LVCMOS33 [get_ports spi_sclk]
set_property LOC AB20 [get_ports spi_mosi]
set_property IOSTANDARD LVCMOS33 [get_ports spi_mosi]
set_property LOC AB18 [get_ports spi_miso]
set_property IOSTANDARD LVCMOS33 [get_ports spi_miso]

set_property LOC T14 [get_ports led_clocks_locked]
set_property IOSTANDARD LVCMOS25 [get_ports led_clocks_locked]
set_property LOC T15 [get_ports led_codec_configured]
set_property IOSTANDARD LVCMOS25 [get_ports led_codec_configured]
set_property LOC T16 [get_ports led_codec_error]
set_property IOSTANDARD LVCMOS25 [get_ports led_codec_error]
set_property LOC U16 [get_ports led_output_muted]
set_property IOSTANDARD LVCMOS25 [get_ports led_output_muted]
