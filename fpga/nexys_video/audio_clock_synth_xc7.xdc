# Nexys Video Rev. A clock-synthesis harness pins from Digilent's master XDC.
# R4 is the fixed 100 MHz oscillator. U6 is the ADAU1761 MCLK connection; the
# LED only proves divided generated-clock activity. This harness does not
# configure or exercise the codec.
set_property LOC R4 [get_ports clk_100mhz]
set_property IOSTANDARD LVCMOS33 [get_ports clk_100mhz]
create_clock -period 10.000 [get_ports clk_100mhz]

set_property LOC G4 [get_ports reset]
set_property IOSTANDARD LVCMOS15 [get_ports reset]

set_property LOC U6 [get_ports codec_mclk_12m288]
set_property IOSTANDARD LVCMOS33 [get_ports codec_mclk_12m288]

set_property LOC T14 [get_ports activity]
set_property IOSTANDARD LVCMOS25 [get_ports activity]

set_property LOC T15 [get_ports locked]
set_property IOSTANDARD LVCMOS25 [get_ports locked]
