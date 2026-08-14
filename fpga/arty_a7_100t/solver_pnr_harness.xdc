# Timing-only harness pins from Digilent's Arty-A7-100 Rev. D/E master XDC.
# The board oscillator is 100 MHz.  The open P&R command independently asks
# for the design's required 98.304 MHz timing; this harness is not a bitstream
# top and does not establish the eventual audio-clock generation circuit.
set_property LOC E3 [get_ports fabric_clk]
set_property IOSTANDARD LVCMOS33 [get_ports fabric_clk]

set_property LOC D9 [get_ports reset]
set_property IOSTANDARD LVCMOS33 [get_ports reset]

set_property LOC H5 [get_ports activity]
set_property IOSTANDARD LVCMOS33 [get_ports activity]
